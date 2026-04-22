# Pixordle

Pixordle is a Next.js image word puzzle. Players guess words that are meaningfully
present in the daily image. Correct related guesses reveal image regions, and a
final answer guess solves the puzzle.

## Production Daily Flow

For each date (`YYYY-MM-DD`):

1. Select a daily Unsplash topic (deterministic by date).
2. Fetch a new image from the API.
3. Run YOLO on that exact image.
4. Build answer + reveal words from detected objects and bounding boxes.
5. Validate quality (non-bland answer, minimum reveal words, confidence thresholds).
6. If quality fails, fetch a different image and retry.
7. Write `data/puzzles/YYYY-MM-DD.json` only when puzzle quality passes.

## Stack

- Frontend: React with Next.js App Router
- Backend: Next.js API routes
- Daily generation: Unsplash + YOLO object detection
- Data model: daily puzzle JSON files + accepted guesses + reveal regions

## Environment

Use `.env` (see `.env.example`):

- `UNSPLASH_ACCESS_KEY` (required)
- `PIXORDLE_TIMEZONE` (timezone for date boundaries)
- `AUTO_GENERATE_DAILY` (`true`/`false`, API-level fallback generation)
- `YOLO_MODEL`, `YOLO_CONFIDENCE`, `YOLO_MIN_WORD_CONFIDENCE`
- `PUZZLE_MIN_REVEAL_WORDS`, `PUZZLE_MAX_REVEAL_WORDS`, `PUZZLE_MAX_IMAGE_ATTEMPTS`
- `PUZZLE_BLAND_LABELS` (comma-separated labels to reject as answer)
- `PUZZLE_BOARD_SIZE`, `PUZZLE_GRID_SIZE`, `PUZZLE_MAX_GUESSES`
- `UNSPLASH_TOPICS` (comma-separated topic pool)

## Install

```bash
npm install
python3 -m pip install -r requirements.txt
```

## Run App

```bash
npm run dev
```

Open `http://localhost:3000`.

## Generate Daily Puzzle Manually

```bash
npm run generate:daily
```

Optional date override:

```bash
npm run generate:daily -- --date=2026-04-22
```

## Generate at 00:00 (Production)

Use one of these:

1. External scheduler (recommended): cron/systemd/GitHub Actions -> `npm run generate:daily` at `00:00`.
2. Built-in daemon process:

```bash
npm run generate:daemon
```

This waits until local midnight in `PIXORDLE_TIMEZONE`, then generates each day.

## Core API

- `GET /api/puzzle` loads today's puzzle JSON.
- `POST /api/guess` validates guesses against today's answer/words.

If `AUTO_GENERATE_DAILY=true` and today's file is missing, the API attempts generation on first request.
