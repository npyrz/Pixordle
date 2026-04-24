#!/usr/bin/env python3

import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

try:
    from ultralytics import YOLO
except Exception as exc:  # pragma: no cover - runtime dependency check
    raise SystemExit(
        "ultralytics is required. Install with: pip install -r requirements.txt"
    ) from exc

DEFAULT_TOPICS = [
    "pets",
    "park",
    "street",
    "city",
    "beach",
    "kitchen",
    "dining",
    "food",
    "market",
    "sports",
    "playground",
    "home",
    "office",
    "garden",
    "farm",
    "transportation",
]

DEFAULT_BLAND_LABELS = {
    "building",
    "sky",
    "moon",
    "person",
    "chair",
    "table",
    "tv",
    "cell phone",
    "cup",
    "object",
}

LABEL_ALIASES = {
    "bicycle": ["bike", "cycle"],
    "motorcycle": ["motorbike", "bike"],
    "car": ["automobile", "vehicle"],
    "bus": ["coach"],
    "truck": ["lorry"],
    "person": ["people", "human"],
    "dog": ["puppy"],
    "cat": ["kitten"],
    "bird": ["animal"],
    "horse": ["pony", "animal"],
    "sheep": ["lamb", "animal"],
    "cow": ["cattle", "animal"],
    "elephant": ["animal"],
    "bear": ["animal"],
    "zebra": ["animal"],
    "giraffe": ["animal"],
    "backpack": ["bag", "rucksack"],
    "handbag": ["bag", "purse"],
    "suitcase": ["luggage", "case"],
    "sports ball": ["ball"],
    "baseball bat": ["bat"],
    "baseball glove": ["glove"],
    "skateboard": ["board"],
    "surfboard": ["surf board", "board"],
    "tennis racket": ["racket", "racquet"],
    "wine glass": ["glass"],
    "cup": ["mug"],
    "fork": ["utensil"],
    "knife": ["utensil"],
    "spoon": ["utensil"],
    "bowl": ["dish"],
    "banana": ["fruit"],
    "apple": ["fruit"],
    "orange": ["fruit"],
    "broccoli": ["vegetable", "veg"],
    "carrot": ["vegetable", "veg"],
    "hot dog": ["hotdog"],
    "pizza": ["food"],
    "donut": ["doughnut", "food"],
    "cake": ["dessert", "food"],
    "couch": ["sofa", "settee"],
    "potted plant": ["plant", "houseplant"],
    "dining table": ["table"],
    "tv": ["television", "screen"],
    "laptop": ["computer"],
    "mouse": ["computer mouse"],
    "remote": ["remote control"],
    "cell phone": ["phone", "mobile phone", "smartphone"],
    "book": ["novel"],
    "clock": ["watch", "timepiece"],
    "vase": ["pot"],
    "teddy bear": ["stuffed bear", "plush bear"],
    "hair drier": ["hair dryer", "dryer"],
}


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: list[float]  # [x1, y1, x2, y2]


@dataclass
class Config:
    timezone: str
    board_size: int
    grid_size: int
    max_guesses: int
    yolo_model: str
    yolo_confidence: float
    yolo_min_word_confidence: float
    min_reveal_words: int
    max_reveal_words: int
    max_image_attempts: int
    bland_labels: set[str]
    topics: list[str]


def load_env_file(file_path: Path) -> None:
    if not file_path.exists():
        return

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def normalize_word(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", value.lower())).strip()


def slugify(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.lower()))[:48]


def parse_list_env(name: str, fallback: list[str]) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    values = [normalize_word(item) for item in raw.split(",")]
    parsed = [value for value in values if value]
    return parsed if parsed else fallback


def parse_set_env(name: str, fallback: set[str]) -> set[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    values = {normalize_word(item) for item in raw.split(",") if normalize_word(item)}
    return values if values else fallback


def parse_config() -> Config:
    return Config(
        timezone=os.environ.get("PIXORDLE_TIMEZONE", "America/Chicago"),
        board_size=int(os.environ.get("PUZZLE_BOARD_SIZE", "420")),
        grid_size=int(os.environ.get("PUZZLE_GRID_SIZE", "32")),
        max_guesses=int(os.environ.get("PUZZLE_MAX_GUESSES", "8")),
        yolo_model=os.environ.get("YOLO_MODEL", "yolov8m.pt"),
        yolo_confidence=float(os.environ.get("YOLO_CONFIDENCE", "0.2")),
        yolo_min_word_confidence=float(os.environ.get("YOLO_MIN_WORD_CONFIDENCE", "0.25")),
        min_reveal_words=int(os.environ.get("PUZZLE_MIN_REVEAL_WORDS", "5")),
        max_reveal_words=int(os.environ.get("PUZZLE_MAX_REVEAL_WORDS", "12")),
        max_image_attempts=int(os.environ.get("PUZZLE_MAX_IMAGE_ATTEMPTS", "10")),
        bland_labels=parse_set_env("PUZZLE_BLAND_LABELS", DEFAULT_BLAND_LABELS),
        topics=parse_list_env("UNSPLASH_TOPICS", DEFAULT_TOPICS),
    )


def get_date_key(timezone_name: str) -> str:
    try:
        now = datetime.now(ZoneInfo(timezone_name))
    except Exception:
        now = datetime.now()
    return now.strftime("%Y-%m-%d")


def parse_args() -> tuple[Optional[str], bool]:
    date_key = None
    force = False

    for arg in sys.argv[1:]:
        if arg.startswith("--date="):
            value = arg.split("=", 1)[1].strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                date_key = value
        elif arg == "--force":
            force = True

    return date_key, force


def stable_topic_for_date(date_key: str, topics: list[str]) -> str:
    score = sum(ord(char) for char in date_key)
    return topics[score % len(topics)]


def read_json_from_request(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = ""
        try:
            body = error.read().decode("utf-8")
        except Exception:
            body = ""
        detail = body or error.reason
        raise RuntimeError(f"Unsplash request failed ({error.code}): {detail}") from error


def fetch_unsplash_image(access_key: str, topic: str) -> tuple[str, str]:
    query = urllib.parse.urlencode(
        {
            "query": topic,
            "orientation": "squarish",
            "content_filter": "high",
        }
    )
    url = f"https://api.unsplash.com/photos/random?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Client-ID {access_key}",
            "Accept-Version": "v1",
            "User-Agent": "Pixordle/1.0",
        },
    )

    payload = read_json_from_request(request)

    raw_url = payload.get("urls", {}).get("raw")
    regular_url = payload.get("urls", {}).get("regular")
    # Prefer regular for reliability; raw can be denied in some setups.
    if isinstance(regular_url, str) and regular_url:
        image_url = regular_url
    elif isinstance(raw_url, str) and raw_url:
        joiner = "&" if "?" in raw_url else "?"
        image_url = f"{raw_url}{joiner}auto=format&fit=crop&crop=entropy&w=1200&h=1200&q=80"
    else:
        raise RuntimeError("Unsplash response missing usable image URL")

    image_alt = payload.get("alt_description") or payload.get("description") or f"Daily {topic} photo"
    return image_url, str(image_alt)


def download_image(url: str, target_path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Pixordle/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            target_path.write_bytes(response.read())
    except urllib.error.HTTPError as error:
        body = ""
        try:
            body = error.read().decode("utf-8")
        except Exception:
            body = ""
        detail = body or error.reason
        raise RuntimeError(f"Image download failed ({error.code}): {detail}") from error


def run_yolo(image_path: Path, config: Config) -> tuple[list[Detection], int, int]:
    model = YOLO(config.yolo_model)
    result = model.predict(source=str(image_path), conf=config.yolo_confidence, verbose=False)[0]

    height, width = result.orig_shape
    names = result.names

    detections: list[Detection] = []
    if result.boxes is not None:
        for box in result.boxes:
            cls_id = int(box.cls.item())
            label = normalize_word(str(names.get(cls_id, cls_id)))
            confidence = float(box.conf.item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            if label:
                detections.append(Detection(label=label, confidence=confidence, bbox=[x1, y1, x2, y2]))

    # Keep highest-confidence detection per label.
    detections.sort(key=lambda item: item.confidence, reverse=True)
    deduped: dict[str, Detection] = {}
    for item in detections:
        if item.label not in deduped:
            deduped[item.label] = item

    return list(deduped.values()), width, height


def choose_answer(detections: list[Detection], config: Config) -> Optional[str]:
    sorted_items = sorted(detections, key=lambda item: item.confidence, reverse=True)
    for item in sorted_items:
        if item.label in config.bland_labels:
            continue
        if item.confidence < config.yolo_min_word_confidence:
            continue
        return item.label
    return None


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def convert_bbox_to_reveal(bbox: list[float], width: int, height: int, board_size: int) -> list[int]:
    x1, y1, x2, y2 = bbox
    safe_width = max(width, 1)
    safe_height = max(height, 1)

    x = clamp(x1 / safe_width, 0.0, 0.99)
    y = clamp(y1 / safe_height, 0.0, 0.99)
    w = clamp((x2 - x1) / safe_width, 0.02, 1.0)
    h = clamp((y2 - y1) / safe_height, 0.02, 1.0)

    rx = int(round(x * board_size))
    ry = int(round(y * board_size))
    rw = max(int(round(w * board_size)), int(round(board_size * 0.04)))
    rh = max(int(round(h * board_size)), int(round(board_size * 0.04)))

    if rx + rw > board_size:
        rw = board_size - rx
    if ry + rh > board_size:
        rh = board_size - ry

    return [rx, ry, max(rw, 1), max(rh, 1)]


def pluralize(label: str) -> Optional[str]:
    if label.endswith("s"):
        return None
    if label.endswith("y") and len(label) > 1 and label[-2] not in "aeiou":
        return f"{label[:-1]}ies"
    if label.endswith(("s", "x", "ch", "sh")):
        return f"{label}es"
    return f"{label}s"


def singularize(label: str) -> Optional[str]:
    if label.endswith("ies") and len(label) > 3:
        return f"{label[:-3]}y"
    if label.endswith("es") and label[:-2].endswith(("s", "x", "ch", "sh")):
        return label[:-2]
    if label.endswith("s") and len(label) > 1:
        return label[:-1]
    return None


def aliases_for_label(label: str) -> list[str]:
    normalized_label = normalize_word(label)
    aliases: list[str] = []

    for alias in LABEL_ALIASES.get(normalized_label, []):
        aliases.append(alias)

    plural = pluralize(normalized_label)
    singular = singularize(normalized_label)
    if plural:
        aliases.append(plural)
    if singular:
        aliases.append(singular)

    parts = normalized_label.split()
    if len(parts) > 1 and len(parts[-1]) > 2:
        aliases.append(parts[-1])

    deduped: list[str] = []
    seen: set[str] = {normalized_label}
    for alias in aliases:
        normalized_alias = normalize_word(alias)
        if not normalized_alias or normalized_alias in seen:
            continue
        seen.add(normalized_alias)
        deduped.append(normalized_alias)

    return deduped


def serialize_detection(item: Detection) -> dict:
    return {
        "label": item.label,
        "aliases": aliases_for_label(item.label),
        "confidence": round(item.confidence, 4),
        "bbox": [round(value, 2) for value in item.bbox],
    }


def build_puzzle(
    date_key: str,
    image_url: str,
    image_alt: str,
    detections: list[Detection],
    image_width: int,
    image_height: int,
    config: Config,
) -> Optional[dict]:
    answer = choose_answer(detections, config)
    if not answer:
        return None

    words: list[dict] = []
    seen: set[str] = set()

    sorted_items = sorted(detections, key=lambda item: item.confidence, reverse=True)
    for item in sorted_items:
        if item.label == answer:
            continue
        if item.label in config.bland_labels:
            continue
        if item.confidence < config.yolo_min_word_confidence:
            continue
        if item.label in seen:
            continue

        words.append(
            {
                "guess": item.label,
                "aliases": aliases_for_label(item.label),
                "reveal": convert_bbox_to_reveal(item.bbox, image_width, image_height, config.board_size),
                "confidence": round(item.confidence, 4),
            }
        )
        seen.add(item.label)

        if len(words) >= config.max_reveal_words:
            break

    if len(words) < config.min_reveal_words:
        return None

    return {
        "id": f"{slugify(answer)}-{date_key}",
        "dateKey": date_key,
        "title": f"Daily {answer.title()} Puzzle",
        "answer": answer,
        "aliases": aliases_for_label(answer),
        "maxGuesses": config.max_guesses,
        "boardSize": config.board_size,
        "gridSize": config.grid_size,
        "imageUrl": image_url,
        "imageAlt": image_alt,
        "imageSize": {
            "width": image_width,
            "height": image_height,
        },
        "words": words,
        "detections": [serialize_detection(item) for item in sorted_items],
    }


def generate_puzzle(date_key: str, config: Config, access_key: str) -> dict:
    seen_urls: set[str] = set()
    topic = stable_topic_for_date(date_key, config.topics)

    for _ in range(config.max_image_attempts):
        image_url, image_alt = fetch_unsplash_image(access_key, topic)
        if image_url in seen_urls:
            continue
        seen_urls.add(image_url)

        with tempfile.TemporaryDirectory(prefix="pixordle-") as temp_dir:
            image_path = Path(temp_dir) / "daily-image.jpg"
            download_image(image_url, image_path)
            detections, image_width, image_height = run_yolo(image_path, config)

        puzzle = build_puzzle(
            date_key=date_key,
            image_url=image_url,
            image_alt=image_alt,
            detections=detections,
            image_width=image_width,
            image_height=image_height,
            config=config,
        )
        if puzzle:
            return puzzle

    raise RuntimeError(
        "Failed to generate a high-quality puzzle after multiple attempts. "
        "Try a different topic pool or lower strictness thresholds."
    )


def main() -> None:
    load_env_file(Path(".env"))
    config = parse_config()

    target_dir = Path("data") / "puzzles"
    target_dir.mkdir(parents=True, exist_ok=True)

    date_arg, force = parse_args()
    date_key = date_arg or get_date_key(config.timezone)
    target_path = target_dir / f"{date_key}.json"
    if target_path.exists() and not force:
        print(f"Puzzle already exists: {target_path}")
        print("Use --force to replace it.")
        return

    unsplash_access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not unsplash_access_key:
        raise RuntimeError("UNSPLASH_ACCESS_KEY is required")

    puzzle = generate_puzzle(date_key=date_key, config=config, access_key=unsplash_access_key)

    target_path.write_text(f"{json.dumps(puzzle, indent=2)}\n", encoding="utf-8")

    print(f"Generated puzzle: {target_path}")
    print(f"Answer: {puzzle['answer']}")
    print("Reveal words:", ", ".join(word["guess"] for word in puzzle["words"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - script entry point
        print(str(exc), file=sys.stderr)
        sys.exit(1)
