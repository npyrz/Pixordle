"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type PublicPuzzle = {
  id: string;
  title: string;
  maxGuesses: number;
  boardSize: number;
  gridSize: number;
  revealWords: string[];
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

const defaultMessage = "Find related words to reveal the image, then name the main answer.";

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

  useEffect(() => {
    async function loadPuzzle() {
      const response = await fetch("/api/puzzle", { cache: "no-store" });
      const data = (await response.json()) as PublicPuzzle;
      setPuzzle(data);
      setLoading(false);
    }

    loadPuzzle().catch(() => {
      setMessage("Puzzle failed to load. Refresh and try again.");
      setTone("warning");
      setLoading(false);
    });
  }, []);

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
          <div>
            <p className="eyebrow">Image word puzzle</p>
            <h1>Pixordle</h1>
          </div>
          <div className="stats" aria-live="polite">
            <div>
              <span>{history.length}</span>
              <small>/{puzzle?.maxGuesses ?? 0} guesses</small>
            </div>
            <div>
              <span>{progress}%</span>
              <small>revealed</small>
            </div>
          </div>
        </header>

        <section className="workspace">
          <div className="imageStage" aria-label={puzzle?.title ?? "Loading puzzle"}>
            <BicycleImage />
            <div className="maskLayer" aria-hidden="true">
              {Array.from({ length: (puzzle?.gridSize ?? 10) ** 2 }, (_, index) => (
                <span
                  className={revealedTiles.has(index) ? "tile revealed" : "tile"}
                  key={index}
                />
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
                {history.map((entry) => (
                  <li className={entry.kind} key={`${entry.normalized}-${entry.text}`}>
                    {entry.text}
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

function BicycleImage() {
  return (
    <svg className="puzzleImage" viewBox="0 0 420 420" role="img" aria-labelledby="bikeTitle">
      <title id="bikeTitle">A bicycle illustration</title>
      <defs>
        <linearGradient id="frameGradient" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#eef7f2" />
          <stop offset="100%" stopColor="#dfeaf8" />
        </linearGradient>
        <radialGradient id="wheelShade" cx="50%" cy="50%" r="55%">
          <stop offset="0%" stopColor="#f9fbfd" />
          <stop offset="100%" stopColor="#ccd6e3" />
        </radialGradient>
      </defs>
      <rect width="420" height="420" rx="18" fill="url(#frameGradient)" />
      <path d="M46 332 C112 278, 314 282, 374 332" fill="none" stroke="#b5c7ba" strokeWidth="10" strokeLinecap="round" opacity="0.55" />
      <circle cx="128" cy="304" r="72" fill="url(#wheelShade)" stroke="#253144" strokeWidth="12" />
      <circle cx="300" cy="304" r="72" fill="url(#wheelShade)" stroke="#253144" strokeWidth="12" />
      <circle cx="128" cy="304" r="10" fill="#253144" />
      <circle cx="300" cy="304" r="10" fill="#253144" />
      <g stroke="#6b7788" strokeWidth="3" opacity="0.72">
        <path d="M128 232 L128 376 M56 304 L200 304 M77 253 L179 355 M77 355 L179 253" />
        <path d="M300 232 L300 376 M228 304 L372 304 M249 253 L351 355 M249 355 L351 253" />
      </g>
      <path d="M128 304 L190 205 L252 304 Z" fill="none" stroke="#e2513f" strokeWidth="14" strokeLinejoin="round" />
      <path d="M190 205 L284 205 L252 304 M284 205 L300 304" fill="none" stroke="#e2513f" strokeWidth="14" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M174 184 H217" stroke="#253144" strokeWidth="14" strokeLinecap="round" />
      <path d="M284 205 L304 145" stroke="#253144" strokeWidth="12" strokeLinecap="round" />
      <path d="M304 145 C328 126, 354 130, 367 146" fill="none" stroke="#253144" strokeWidth="12" strokeLinecap="round" />
      <path d="M191 204 L181 174" stroke="#253144" strokeWidth="10" strokeLinecap="round" />
      <path d="M162 171 H208" stroke="#253144" strokeWidth="11" strokeLinecap="round" />
      <path d="M219 314 L237 340" stroke="#253144" strokeWidth="8" strokeLinecap="round" />
      <path d="M212 315 H246" stroke="#f6b23d" strokeWidth="10" strokeLinecap="round" />
    </svg>
  );
}
