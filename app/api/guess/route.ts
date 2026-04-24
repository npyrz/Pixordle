import { NextRequest, NextResponse } from "next/server";
import {
  getTileIndexesForReveal,
  hasEquivalentPreviousGuess,
  matchesTerm,
  normalizeGuess,
} from "@/lib/puzzle";
import { getCurrentPuzzle } from "@/lib/puzzle-store";

type GuessRequest = {
  puzzleId?: string;
  guess?: string;
  previousGuesses?: string[];
  guessesUsed?: number;
};

export async function POST(request: NextRequest) {
  const puzzle = await getCurrentPuzzle();
  const body = (await request.json()) as GuessRequest;
  const normalizedGuess = normalizeGuess(body.guess ?? "");
  const previousGuesses = body.previousGuesses ?? [];
  const guessesUsed = body.guessesUsed ?? previousGuesses.length;
  const displayGuess = body.guess?.trim() ?? "";

  if (body.puzzleId !== puzzle.id) {
    return NextResponse.json(
      {
        kind: "invalid",
        message: "Puzzle not found.",
        normalizedGuess,
        displayGuess,
      },
      { status: 404 },
    );
  }

  if (!normalizedGuess) {
    return NextResponse.json({
      kind: "invalid",
      message: "Enter a word to guess.",
      normalizedGuess,
      displayGuess,
    });
  }

  if (hasEquivalentPreviousGuess(normalizedGuess, previousGuesses, puzzle)) {
    return NextResponse.json({
      kind: "duplicate",
      message: "You already tried that word or a close helper word.",
      normalizedGuess,
      displayGuess,
    });
  }

  if (matchesTerm(normalizedGuess, puzzle.answer, puzzle.aliases)) {
    return NextResponse.json({
      kind: "answer",
      message: `Solved. The answer is ${puzzle.answer}.`,
      normalizedGuess,
      displayGuess,
      solved: true,
    });
  }

  const matchedWord = puzzle.words.find((word) =>
    matchesTerm(normalizedGuess, word.guess, word.aliases),
  );

  if (matchedWord) {
    return NextResponse.json({
      kind: "related",
      message: `${matchedWord.guess} is in the image. A region opened.`,
      normalizedGuess: matchedWord.guess,
      displayGuess,
      reveal: getTileIndexesForReveal(matchedWord.reveal, puzzle.boardSize, puzzle.gridSize),
    });
  }

  const exhausted = guessesUsed + 1 >= puzzle.maxGuesses;

  return NextResponse.json({
    kind: "miss",
    message: exhausted
      ? `Out of guesses. The answer was ${puzzle.answer}.`
      : "No match. Try another visible clue.",
    normalizedGuess,
    displayGuess,
    exhausted,
  });
}
