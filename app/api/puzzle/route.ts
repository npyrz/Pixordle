import { NextResponse } from "next/server";
import { getDailyUnsplashBicycleImage } from "@/lib/daily-image";
import { puzzle } from "@/lib/puzzle";

export async function GET() {
  const { imageUrl, imageAlt } = await getDailyUnsplashBicycleImage();

  return NextResponse.json({
    id: puzzle.id,
    title: puzzle.title,
    maxGuesses: puzzle.maxGuesses,
    boardSize: puzzle.boardSize,
    gridSize: puzzle.gridSize,
    revealWords: puzzle.words.map((word) => word.guess),
    imageUrl,
    imageAlt,
  });
}
