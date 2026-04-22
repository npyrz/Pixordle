import { NextResponse } from "next/server";
import { puzzle } from "@/lib/puzzle";

export function GET() {
  return NextResponse.json({
    id: puzzle.id,
    title: puzzle.title,
    maxGuesses: puzzle.maxGuesses,
    boardSize: puzzle.boardSize,
    gridSize: puzzle.gridSize,
    revealWords: puzzle.words.map((word) => word.guess),
  });
}
