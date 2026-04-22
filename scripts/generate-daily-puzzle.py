#!/usr/bin/env python3

import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from ultralytics import YOLO
except Exception as exc:  # pragma: no cover - runtime dependency check
    raise SystemExit(
        "ultralytics is required. Install with: pip install -r requirements.txt"
    ) from exc

BOARD_SIZE = 420
GRID_SIZE = 32
MAX_GUESSES = 8
DEFAULT_TIMEZONE = "America/Chicago"
DEFAULT_CONFIDENCE = 0.20
MAX_WORDS = 12

# Avoid weak answers that are too generic for a daily puzzle target.
GENERIC_ANSWER_LABELS = {
    "person",
    "chair",
    "table",
    "tv",
    "cell phone",
    "cup",
}

DEFAULT_TOPICS = [
    "street",
    "nature",
    "architecture",
    "travel",
    "sports",
    "food",
    "city",
    "ocean",
    "animals",
    "fashion",
]

ANSWER_ALIASES = {
    "bicycle": ["bike", "cycle"],
    "motorcycle": ["motorbike", "bike"],
    "car": ["automobile", "vehicle"],
    "bus": ["coach"],
    "truck": ["lorry"],
    "person": ["human", "rider", "cyclist"],
}

WORD_ALIASES = {
    "person": ["people", "human", "rider", "cyclist"],
    "car": ["vehicle", "automobile"],
    "motorcycle": ["motorbike", "bike"],
    "bicycle": ["bike", "cycle"],
    "bus": ["coach"],
    "truck": ["lorry"],
    "traffic light": ["signal"],
    "fire hydrant": ["hydrant"],
    "bench": ["seat"],
    "dog": ["puppy"],
    "cat": ["kitten"],
    "helmet": ["headgear"],
    "shoe": ["shoes", "sneaker", "footwear"],
    "wheel": ["wheels", "tire", "tyre", "rim"],
    "handlebar": ["handlebars", "bar", "grip"],
    "seat": ["saddle"],
    "pedal": ["pedals", "crank"],
}


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


def get_date_key(timezone_name: str) -> str:
    try:
        now = datetime.now(ZoneInfo(timezone_name))
    except Exception:
        now = datetime.now()
    return now.strftime("%Y-%m-%d")


def parse_date_arg() -> str | None:
    for arg in sys.argv[1:]:
        if arg.startswith("--date="):
            value = arg.split("=", 1)[1].strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                return value
    return None


def normalize_word(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", value.lower())).strip()


def slugify(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.lower()))[:48]


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def stable_topic_for_date(date_key: str, configured_topics: list[str]) -> str:
    topics = configured_topics or DEFAULT_TOPICS
    score = sum(ord(char) for char in date_key)
    return topics[score % len(topics)]


def convert_bbox_to_reveal(x1: float, y1: float, x2: float, y2: float, width: int, height: int) -> list[int]:
    safe_width = max(width, 1)
    safe_height = max(height, 1)

    x = clamp(x1 / safe_width, 0.0, 0.99)
    y = clamp(y1 / safe_height, 0.0, 0.99)
    w = clamp((x2 - x1) / safe_width, 0.02, 1.0)
    h = clamp((y2 - y1) / safe_height, 0.02, 1.0)

    rx = int(round(x * BOARD_SIZE))
    ry = int(round(y * BOARD_SIZE))
    rw = int(round(w * BOARD_SIZE))
    rh = int(round(h * BOARD_SIZE))

    rw = max(rw, int(round(BOARD_SIZE * 0.04)))
    rh = max(rh, int(round(BOARD_SIZE * 0.04)))

    if rx + rw > BOARD_SIZE:
        rw = BOARD_SIZE - rx
    if ry + rh > BOARD_SIZE:
        rh = BOARD_SIZE - ry

    return [rx, ry, max(rw, 1), max(rh, 1)]


def parse_topics_from_env() -> list[str]:
    raw = os.environ.get("UNSPLASH_TOPICS", "")
    if not raw.strip():
        return DEFAULT_TOPICS
    topics = [normalize_word(item) for item in raw.split(",")]
    return [topic for topic in topics if topic]


def fetch_unsplash_image(access_key: str, date_key: str) -> tuple[str, str]:
    topic = stable_topic_for_date(date_key, parse_topics_from_env())
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
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    raw_url = payload.get("urls", {}).get("raw")
    regular_url = payload.get("urls", {}).get("regular")
    if isinstance(raw_url, str) and raw_url:
        joiner = "&" if "?" in raw_url else "?"
        image_url = f"{raw_url}{joiner}auto=format&fit=crop&crop=entropy&w=1200&h=1200&q=80"
    elif isinstance(regular_url, str) and regular_url:
        image_url = regular_url
    else:
        raise RuntimeError("Unsplash response missing usable image URL")

    image_alt = payload.get("alt_description") or payload.get("description") or f"Daily {topic} photo"
    return image_url, str(image_alt)


def download_image(url: str, target_path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Pixordle/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        target_path.write_bytes(response.read())


def run_yolo(image_path: Path, model_name: str, confidence: float) -> tuple[list[dict], int, int]:
    model = YOLO(model_name)
    result = model.predict(source=str(image_path), conf=confidence, verbose=False)[0]

    height, width = result.orig_shape
    names = result.names

    detections: list[dict] = []
    if result.boxes is not None:
        for box in result.boxes:
            cls_id = int(box.cls.item())
            label = normalize_word(str(names.get(cls_id, cls_id)))
            conf = float(box.conf.item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            detections.append(
                {
                    "label": label,
                    "confidence": conf,
                    "bbox": [x1, y1, x2, y2],
                }
            )

    detections.sort(key=lambda item: item["confidence"], reverse=True)

    unique: dict[str, dict] = {}
    for item in detections:
        label = item["label"]
        if label and label not in unique:
            unique[label] = item

    return list(unique.values()), width, height


def choose_answer(detections: list[dict]) -> str:
    for item in detections:
        label = item["label"]
        if label not in GENERIC_ANSWER_LABELS:
            return label
    return detections[0]["label"] if detections else "object"


def add_word(words: list[dict], seen: set[str], guess: str, reveal: list[int], aliases: list[str] | None = None) -> None:
    normalized = normalize_word(guess)
    if not normalized or normalized in seen:
        return

    words.append(
        {
            "guess": normalized,
            "aliases": aliases if aliases is not None else WORD_ALIASES.get(normalized, []),
            "reveal": reveal,
        }
    )
    seen.add(normalized)


def split_bicycle_parts(bbox: list[float], width: int, height: int) -> list[dict]:
    x1, y1, x2, y2 = bbox
    bw = max(x2 - x1, 1)
    bh = max(y2 - y1, 1)

    return [
        {
            "guess": "wheel",
            "reveal": convert_bbox_to_reveal(x1 + 0.03 * bw, y1 + 0.55 * bh, x1 + 0.42 * bw, y1 + 0.97 * bh, width, height),
        },
        {
            "guess": "tire",
            "reveal": convert_bbox_to_reveal(x1 + 0.58 * bw, y1 + 0.55 * bh, x1 + 0.97 * bw, y1 + 0.97 * bh, width, height),
        },
        {
            "guess": "handlebar",
            "reveal": convert_bbox_to_reveal(x1 + 0.62 * bw, y1 + 0.08 * bh, x1 + 0.97 * bw, y1 + 0.36 * bh, width, height),
        },
        {
            "guess": "seat",
            "reveal": convert_bbox_to_reveal(x1 + 0.36 * bw, y1 + 0.06 * bh, x1 + 0.58 * bw, y1 + 0.24 * bh, width, height),
        },
        {
            "guess": "pedal",
            "reveal": convert_bbox_to_reveal(x1 + 0.42 * bw, y1 + 0.56 * bh, x1 + 0.62 * bw, y1 + 0.79 * bh, width, height),
        },
    ]


def split_person_parts(bbox: list[float], width: int, height: int) -> list[dict]:
    x1, y1, x2, y2 = bbox
    bw = max(x2 - x1, 1)
    bh = max(y2 - y1, 1)

    return [
        {
            "guess": "helmet",
            "reveal": convert_bbox_to_reveal(x1 + 0.28 * bw, y1 + 0.02 * bh, x1 + 0.72 * bw, y1 + 0.22 * bh, width, height),
        },
        {
            "guess": "shoe",
            "reveal": convert_bbox_to_reveal(x1 + 0.18 * bw, y1 + 0.78 * bh, x1 + 0.82 * bw, y1 + 0.98 * bh, width, height),
        },
    ]


def build_puzzle(
    date_key: str,
    image_url: str,
    image_alt: str,
    detections: list[dict],
    image_width: int,
    image_height: int,
) -> dict:
    answer = choose_answer(detections)
    aliases = ANSWER_ALIASES.get(answer, [])

    words: list[dict] = []
    seen: set[str] = set()

    bicycle_box: list[float] | None = None
    person_box: list[float] | None = None

    for detection in detections:
        label = detection["label"]
        bbox = detection["bbox"]

        if label == "bicycle" and bicycle_box is None:
            bicycle_box = bbox
        if label == "person" and person_box is None:
            person_box = bbox

        if label == answer:
            continue

        reveal = convert_bbox_to_reveal(bbox[0], bbox[1], bbox[2], bbox[3], image_width, image_height)
        add_word(words, seen, label, reveal)

        if len(words) >= MAX_WORDS:
            break

    if bicycle_box and len(words) < MAX_WORDS:
        for item in split_bicycle_parts(bicycle_box, image_width, image_height):
            add_word(words, seen, item["guess"], item["reveal"])
            if len(words) >= MAX_WORDS:
                break

    if person_box and len(words) < MAX_WORDS:
        for item in split_person_parts(person_box, image_width, image_height):
            add_word(words, seen, item["guess"], item["reveal"])
            if len(words) >= MAX_WORDS:
                break

    if not words:
        center_reveal = convert_bbox_to_reveal(
            image_width * 0.25,
            image_height * 0.25,
            image_width * 0.75,
            image_height * 0.75,
            image_width,
            image_height,
        )
        add_word(words, seen, "object", center_reveal, ["item", "thing"])

    title = f"Daily {answer.title()} Puzzle"

    return {
        "id": f"{slugify(answer)}-{date_key}",
        "dateKey": date_key,
        "title": title,
        "answer": answer,
        "aliases": aliases,
        "maxGuesses": MAX_GUESSES,
        "boardSize": BOARD_SIZE,
        "gridSize": GRID_SIZE,
        "imageUrl": image_url,
        "imageAlt": image_alt,
        "words": words,
    }


def main() -> None:
    load_env_file(Path(".env"))

    unsplash_access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not unsplash_access_key:
        raise RuntimeError("UNSPLASH_ACCESS_KEY is required")

    timezone_name = os.environ.get("PIXORDLE_TIMEZONE", DEFAULT_TIMEZONE)
    date_key = parse_date_arg() or get_date_key(timezone_name)

    model_name = os.environ.get("YOLO_MODEL", "yolov8m.pt")
    confidence = float(os.environ.get("YOLO_CONFIDENCE", str(DEFAULT_CONFIDENCE)))

    image_url, image_alt = fetch_unsplash_image(unsplash_access_key, date_key)

    with tempfile.TemporaryDirectory(prefix="pixordle-") as temp_dir:
        image_path = Path(temp_dir) / "daily-image.jpg"
        download_image(image_url, image_path)
        detections, image_width, image_height = run_yolo(image_path, model_name, confidence)

    puzzle = build_puzzle(
        date_key=date_key,
        image_url=image_url,
        image_alt=image_alt,
        detections=detections,
        image_width=image_width,
        image_height=image_height,
    )

    target_dir = Path("data") / "puzzles"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{date_key}.json"
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
