import { NextResponse } from "next/server";
import { getCurrentPuzzle, getPuzzleTiming } from "@/lib/puzzle-store";

export async function GET() {
  const puzzle = await getCurrentPuzzle();
  const timing = getPuzzleTiming();

  return NextResponse.json({
    id: puzzle.id,
    dateKey:
      puzzle.dateKey && !["default", "emergency"].includes(puzzle.dateKey)
        ? puzzle.dateKey
        : timing.dateKey,
    resetAt: timing.resetAt,
    timeZone: timing.timeZone,
    title: puzzle.title,
    maxGuesses: puzzle.maxGuesses,
    boardSize: puzzle.boardSize,
    gridSize: puzzle.gridSize,
    revealWords: puzzle.words.map((word) => word.guess),
    imageUrl: puzzle.imageUrl,
    imageAlt: puzzle.imageAlt,
  });
}
