import { NextResponse } from "next/server";
import { getCurrentPuzzle } from "@/lib/puzzle-store";

export async function GET() {
  const puzzle = await getCurrentPuzzle();

  return NextResponse.json({
    id: puzzle.id,
    title: puzzle.title,
    maxGuesses: puzzle.maxGuesses,
    boardSize: puzzle.boardSize,
    gridSize: puzzle.gridSize,
    revealWords: puzzle.words.map((word) => word.guess),
    imageUrl: puzzle.imageUrl,
    imageAlt: puzzle.imageAlt,
  });
}
