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
MAX_IMAGE_ATTEMPTS = 10
MIN_REVEAL_WORDS = 5

GENERIC_ANSWER_LABELS = {
    "person",
    "chair",
    "table",
    "tv",
    "cell phone",
    "cup",
    "object",
}

BLAND_ANSWER_LABELS = {
    "building",
    "sky",
    "moon",
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
    "building": ["tower", "apartment"],
    "moon": ["lunar"],
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
    "building": ["tower", "apartment", "highrise"],
    "moon": ["lunar"],
    "sky": ["blue sky"],
    "window": ["windows"],
    "balcony": ["balconies"],
}

LABEL_ALT_SYNONYMS = {
    "building": {"building", "tower", "apartment", "highrise", "block"},
    "frisbee": {"frisbee", "disc"},
    "sports ball": {"ball", "football", "basketball", "soccer", "tennis"},
    "bicycle": {"bike", "bicycle", "cycle"},
    "person": {"person", "man", "woman", "boy", "girl", "people", "rider", "cyclist"},
    "car": {"car", "vehicle", "sedan", "auto"},
    "moon": {"moon", "lunar"},
    "sky": {"sky"},
    "window": {"window", "windows"},
}

ALT_REGION_HINTS = {
    "moon": [330, 30, 54, 54],
    "sky": [0, 0, 420, 180],
    "building": [70, 150, 290, 260],
    "window": [140, 220, 160, 150],
    "balcony": [120, 250, 190, 120],
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


def tokenize_text(value: str) -> set[str]:
    if not value:
        return set()
    words = re.findall(r"[a-z0-9]+", value.lower())
    return {word for word in words if len(word) > 1}


def label_matches_alt(label: str, alt_tokens: set[str]) -> bool:
    if not alt_tokens:
        return False

    label_tokens = set(label.split())
    if label_tokens & alt_tokens:
        return True

    synonyms = LABEL_ALT_SYNONYMS.get(label, set())
    return bool(synonyms & alt_tokens)


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


def choose_answer(detections: list[dict], alt_tokens: set[str]) -> str:
    for item in detections:
        label = item["label"]
        if label in GENERIC_ANSWER_LABELS:
            continue
        if label_matches_alt(label, alt_tokens):
            return label

    for item in detections:
        label = item["label"]
        if label not in GENERIC_ANSWER_LABELS:
            return label

    # Last resort prefers a concrete noun from caption tokens over generic "object".
    if "building" in alt_tokens:
        return "building"
    if "moon" in alt_tokens:
        return "moon"
    if "car" in alt_tokens:
        return "car"
    if "bike" in alt_tokens or "bicycle" in alt_tokens:
        return "bicycle"
    return detections[0]["label"] if detections else "building"


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


def add_alt_hint_words(words: list[dict], seen: set[str], alt_tokens: set[str]) -> None:
    for token in alt_tokens:
        if token in ALT_REGION_HINTS and token not in seen:
            add_word(words, seen, token, ALT_REGION_HINTS[token])


def build_puzzle(
    date_key: str,
    image_url: str,
    image_alt: str,
    detections: list[dict],
    image_width: int,
    image_height: int,
) -> dict:
    alt_tokens = tokenize_text(image_alt)
    answer = choose_answer(detections, alt_tokens)
    aliases = ANSWER_ALIASES.get(answer, [])

    words: list[dict] = []
    seen: set[str] = set()

    bicycle_box: list[float] | None = None
    person_box: list[float] | None = None

    prioritized = sorted(
        detections,
        key=lambda item: (
            label_matches_alt(item["label"], alt_tokens),
            item["confidence"],
        ),
        reverse=True,
    )

    for detection in prioritized:
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

    if len(words) < 4:
        add_alt_hint_words(words, seen, alt_tokens)

    if len(words) < 3:
        # Use caption-driven words instead of generic object fallback.
        add_alt_hint_words(words, seen, alt_tokens)

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
        "words": words[:MAX_WORDS],
    }


def score_puzzle_quality(puzzle: dict, detections: list[dict], alt_tokens: set[str]) -> int:
    score = 0
    if puzzle.get("answer") != "object":
        score += 2
    if puzzle.get("answer") in BLAND_ANSWER_LABELS:
        score -= 4
    if label_matches_alt(str(puzzle.get("answer", "")), alt_tokens):
        score += 5
    score += min(len(puzzle.get("words", [])), 8)
    score += min(len(detections), 6)
    return score


def is_valid_puzzle(puzzle: dict, detections: list[dict], alt_tokens: set[str]) -> bool:
    answer = str(puzzle.get("answer", ""))
    words = puzzle.get("words", [])
    if not answer or not isinstance(words, list):
        return False
    if answer == "object":
        return False
    if answer in BLAND_ANSWER_LABELS:
        return False
    if len(words) < MIN_REVEAL_WORDS:
        return False
    if not detections:
        return False
    if answer == "frisbee" and "moon" in alt_tokens:
        return False
    if answer in {"sports ball", "frisbee"} and not label_matches_alt(answer, alt_tokens):
        return False
    if alt_tokens and not label_matches_alt(answer, alt_tokens):
        return False
    return True


def main() -> None:
    load_env_file(Path(".env"))

    unsplash_access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not unsplash_access_key:
        raise RuntimeError("UNSPLASH_ACCESS_KEY is required")

    timezone_name = os.environ.get("PIXORDLE_TIMEZONE", DEFAULT_TIMEZONE)
    date_key = parse_date_arg() or get_date_key(timezone_name)

    model_name = os.environ.get("YOLO_MODEL", "yolov8m.pt")
    confidence = float(os.environ.get("YOLO_CONFIDENCE", str(DEFAULT_CONFIDENCE)))

    best_candidate: dict | None = None
    valid_candidate: dict | None = None
    best_score = -1
    seen_urls: set[str] = set()

    for _ in range(MAX_IMAGE_ATTEMPTS):
        image_url, image_alt = fetch_unsplash_image(unsplash_access_key, date_key)
        if image_url in seen_urls:
            continue
        seen_urls.add(image_url)

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

        alt_tokens = tokenize_text(image_alt)
        quality = score_puzzle_quality(puzzle, detections, alt_tokens)
        if quality > best_score:
            best_score = quality
            best_candidate = puzzle

        if is_valid_puzzle(puzzle, detections, alt_tokens):
            best_candidate = puzzle
            valid_candidate = puzzle
            break

    if not best_candidate or not valid_candidate:
        raise RuntimeError(
            "Failed to generate a high-quality puzzle after multiple image attempts. Try again."
        )

    target_dir = Path("data") / "puzzles"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{date_key}.json"
    target_path.write_text(f"{json.dumps(best_candidate, indent=2)}\n", encoding="utf-8")

    print(f"Generated puzzle: {target_path}")
    print(f"Answer: {best_candidate['answer']}")
    print("Reveal words:", ", ".join(word["guess"] for word in best_candidate["words"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - script entry point
        print(str(exc), file=sys.stderr)
        sys.exit(1)
