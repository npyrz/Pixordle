# Pixordle

Pixordle is a Next.js image word puzzle. Players guess words that are meaningfully
present in the daily image. Correct related guesses reveal image regions, and a
final answer guess solves the puzzle.

## How Daily Generation Works

At local midnight (configured timezone), a new date key starts.

For each date (`YYYY-MM-DD`):

1. A new image is selected from Unsplash.
2. The generator runs YOLO object detection on that exact game image.
3. It chooses a main answer and many reveal words from detected objects.
4. It maps object boxes to precise reveal coordinates.
5. It writes `data/puzzles/YYYY-MM-DD.json`.

The app then serves that file for the day.

## Stack

- Frontend: React with Next.js App Router
- Backend: Next.js API routes
- Daily generation: Unsplash + YOLO object detection
- Data model: daily puzzle JSON files + accepted guesses + reveal regions

## Environment

Use `.env` (see `.env.example`):

- `UNSPLASH_ACCESS_KEY` (required)
- `PIXORDLE_TIMEZONE` (optional, default `America/Chicago`)
- `YOLO_MODEL` (optional, default `yolov8m.pt`)
- `YOLO_CONFIDENCE` (optional, default `0.20`)
- `UNSPLASH_TOPICS` (optional, comma-separated topic pool)
- `AUTO_GENERATE_DAILY` (optional, set `true` to auto-generate if today's file is missing)

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

## Midnight Behavior

For true scheduled generation exactly at `00:00`, run this script with a cron job or scheduler:

```bash
npm run generate:daily
```

If you set `AUTO_GENERATE_DAILY=true`, the API will also attempt generation on the first request after midnight when today's file is missing.

## Core API

- `GET /api/puzzle` loads today's puzzle file and returns public metadata.
- `POST /api/guess` validates guesses against today's puzzle answer and reveal words.
