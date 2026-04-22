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
npm run dev
```

Open `http://localhost:3000`.

## Core API

- `GET /api/puzzle` returns public puzzle metadata without the answer.
- `POST /api/guess` validates a guess and returns the result plus reveal tiles.
