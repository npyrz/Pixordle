"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

type PublicPuzzle = {
  id: string;
  dateKey: string;
  resetAt: string;
  timeZone: string;
  title: string;
  maxGuesses: number;
  boardSize: number;
  gridSize: number;
  revealWords: string[];
  imageUrl: string;
  imageAlt: string;
};

type GuessResult = {
  normalizedGuess: string;
  displayGuess: string;
  kind: "answer" | "related" | "miss" | "duplicate" | "invalid";
  message: string;
  reveal?: number[];
  solved?: boolean;
  exhausted?: boolean;
};

type GuessEntry = {
  text: string;
  normalized: string;
  kind: "answer" | "related" | "miss";
};

const defaultMessage = "Guess objects or close helper words to reveal their locations, then name the image.";

function getMsUntilReset(resetAt?: string) {
  if (!resetAt) {
    return null;
  }

  const resetTime = new Date(resetAt).getTime();
  if (!Number.isFinite(resetTime)) {
    return null;
  }

  return Math.max(resetTime - Date.now(), 1000);
}

export default function Home() {
  const [puzzle, setPuzzle] = useState<PublicPuzzle | null>(null);
  const [guess, setGuess] = useState("");
  const [message, setMessage] = useState(defaultMessage);
  const [tone, setTone] = useState<"neutral" | "success" | "warning">("neutral");
  const [history, setHistory] = useState<GuessEntry[]>([]);
  const [revealedTiles, setRevealedTiles] = useState<Set<number>>(new Set());
  const [solved, setSolved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const isOver = solved || (puzzle ? history.length >= puzzle.maxGuesses : false);
  const progress = useMemo(() => {
    if (!puzzle) {
      return 0;
    }

    return Math.round((revealedTiles.size / (puzzle.gridSize * puzzle.gridSize)) * 100);
  }, [puzzle, revealedTiles]);

  const loadPuzzle = useCallback(async (reset = false) => {
    const response = await fetch("/api/puzzle", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Puzzle request failed");
    }

    const data = (await response.json()) as PublicPuzzle;
    setPuzzle(data);

    if (reset) {
      setGuess("");
      setMessage(defaultMessage);
      setTone("neutral");
      setHistory([]);
      setRevealedTiles(new Set());
      setSolved(false);
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    loadPuzzle().catch(() => {
      setMessage("Puzzle failed to load. Refresh and try again.");
      setTone("warning");
      setLoading(false);
    });
  }, [loadPuzzle]);

  useEffect(() => {
    const delay = getMsUntilReset(puzzle?.resetAt);
    if (!delay) {
      return;
    }

    const timeout = window.setTimeout(() => {
      loadPuzzle(true).catch(() => {
        setMessage("A new daily image was expected, but refresh failed.");
        setTone("warning");
      });
    }, delay);

    return () => window.clearTimeout(timeout);
  }, [loadPuzzle, puzzle?.resetAt]);

  async function submitGuess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!puzzle || submitting || isOver) {
      return;
    }

    setSubmitting(true);
    const previousGuesses = history.map((entry) => entry.normalized);
    const response = await fetch("/api/guess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        puzzleId: puzzle.id,
        guess,
        previousGuesses,
        guessesUsed: history.length,
      }),
    });
    const result = (await response.json()) as GuessResult;
    setSubmitting(false);

    if (result.kind === "invalid" || result.kind === "duplicate") {
      setMessage(result.message);
      setTone("warning");
      return;
    }

    setHistory((current) => [
      ...current,
      {
        text: result.displayGuess,
        normalized: result.normalizedGuess,
        kind: result.kind === "answer" ? "answer" : result.kind === "related" ? "related" : "miss",
      },
    ]);

    if (result.reveal) {
      setRevealedTiles((current) => {
        const next = new Set(current);
        result.reveal?.forEach((tile) => next.add(tile));
        return next;
      });
    }

    if (result.solved) {
      setSolved(true);
      setRevealedTiles(new Set(Array.from({ length: puzzle.gridSize * puzzle.gridSize }, (_, index) => index)));
    }

    setMessage(result.message);
    setTone(result.kind === "miss" || result.exhausted ? "warning" : "success");
    setGuess("");
  }

  function resetGame() {
    setGuess("");
    setMessage(defaultMessage);
    setTone("neutral");
    setHistory([]);
    setRevealedTiles(new Set());
    setSolved(false);
  }

  return (
    <main className="app">
      <section className="game">
        <header className="topbar">
          <div className="brandBlock">
            <p className="eyebrow">
              Daily image puzzle{puzzle?.dateKey ? ` / ${puzzle.dateKey}` : ""}
            </p>
            <h1 className="logoWord">Pixordle</h1>
          </div>
          <div className="stats" aria-live="polite">
            <div className="statCard">
              <span className="statValue">{history.length}</span>
              <small>/{puzzle?.maxGuesses ?? 0} guesses</small>
            </div>
            <div className="statCard">
              <span className="statValue">{progress}%</span>
              <small>revealed</small>
            </div>
          </div>
        </header>

        <section className="workspace">
          <div
            className="imageStage"
            aria-label={puzzle?.title ?? "Loading puzzle"}
            style={{ "--grid-size": puzzle?.gridSize ?? 10 } as CSSProperties}
          >
            {puzzle?.imageUrl ? (
              <img alt={puzzle.imageAlt || puzzle.title} className="puzzleImage" src={puzzle.imageUrl} />
            ) : (
              <div className="puzzleImage" />
            )}
            <div className="maskLayer" aria-hidden="true">
              {Array.from({ length: (puzzle?.gridSize ?? 10) ** 2 }, (_, index) => (
                <span className={revealedTiles.has(index) ? "tile revealed" : "tile"} key={index} />
              ))}
            </div>
            {loading && <div className="loading">Loading puzzle</div>}
          </div>

          <aside className="sidePanel">
            <form className="guessForm" onSubmit={submitGuess}>
              <label htmlFor="guess">Your guess</label>
              <div className="guessRow">
                <input
                  id="guess"
                  value={guess}
                  onChange={(event) => setGuess(event.target.value)}
                  disabled={!puzzle || isOver || submitting}
                  maxLength={32}
                  autoComplete="off"
                />
                <button disabled={!puzzle || isOver || submitting || !guess.trim()} type="submit">
                  Guess
                </button>
              </div>
            </form>

            <p className={`message ${tone}`} aria-live="polite">
              {message}
            </p>

            <div className="answerBank">
              <h2>Known reveal words</h2>
              <div className="wordGrid">
                {puzzle?.revealWords.map((word) => {
                  const found = history.some((entry) => entry.normalized === word);
                  return (
                    <span className={found ? "word found" : "word"} key={word}>
                      {found ? word : "????"}
                    </span>
                  );
                })}
              </div>
            </div>

            <div className="history">
              <div className="panelHeader">
                <h2>Guesses</h2>
                <button className="secondary" onClick={resetGame} type="button">
                  Reset
                </button>
              </div>
              <ol>
                {history.map((entry, index) => (
                  <li className={entry.kind} key={`${entry.normalized}-${entry.text}`}>
                    <span className="guessIndex">{index + 1}.</span>
                    <span className="guessPill">{entry.text}</span>
                  </li>
                ))}
              </ol>
            </div>
          </aside>
        </section>
      </section>
    </main>
  );
}
