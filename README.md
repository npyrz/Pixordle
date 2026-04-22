# Pixordle

Pixordle is a Next.js image word puzzle. Players guess words that are meaningfully
present in the hidden image. Correct related guesses reveal image regions, and a
final answer guess solves the puzzle.

## Stack

- Frontend: React with Next.js App Router
- Backend: Next.js API routes
- Data model: puzzle metadata, accepted guesses, aliases, and reveal regions

## Run

```bash
npm install
export UNSPLASH_ACCESS_KEY=your_unsplash_access_key
# optional, defaults to America/Chicago
# export PIXORDLE_TIMEZONE=America/Chicago
npm run dev
```

Open `http://localhost:3000`.

Without `UNSPLASH_ACCESS_KEY`, Pixordle uses a built-in bicycle fallback image.

## Core API

- `GET /api/puzzle` returns public puzzle metadata without the answer.
- `POST /api/guess` validates a guess and returns the result plus reveal tiles.
