# Pixordle

Pixordle is a Next.js image word puzzle. Players guess words that are meaningfully
present in the daily image. Correct related guesses reveal image regions, and a
final answer guess solves the puzzle.

## Stack

- Frontend: React with Next.js App Router
- Backend: Next.js API routes
- Daily generation: Unsplash + YOLO object detection
- Data model: daily puzzle JSON files + accepted guesses + reveal regions

## Environment

Use `.env` (see `.env.example`):

- `UNSPLASH_ACCESS_KEY` (required to fetch the daily image)
- `PIXORDLE_TIMEZONE` (optional, default `America/Chicago`)
- `YOLO_MODEL` (optional, default `yolov8n.pt`)
- `YOLO_CONFIDENCE` (optional, default `0.25`)

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

If no file exists for today, the app falls back to `data/puzzles/default.json`.

## Generate Daily Puzzle (YOLO)

```bash
npm run generate:daily
```

Optional date override:

```bash
npm run generate:daily -- --date=2026-04-22
```

Generation flow:

1. Fetches a new Unsplash image for the day.
2. Runs YOLO on the image to detect visible objects.
3. Chooses puzzle answer + related words from detected labels.
4. Converts detection boxes into puzzle reveal coordinates.
5. Writes `data/puzzles/YYYY-MM-DD.json`.

## Core API

- `GET /api/puzzle` loads today's puzzle file and returns public metadata.
- `POST /api/guess` validates guesses against today's puzzle answer and reveal words.
