import { readFile } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { Puzzle } from "@/lib/puzzle";

const DEFAULT_TIMEZONE = "America/Chicago";
const DEFAULT_PUZZLE_PATH = path.join(process.cwd(), "data", "puzzles", "default.json");
const PUZZLE_DIR = path.join(process.cwd(), "data", "puzzles");
const GENERATION_FAILURE_RETRY_MS = 10 * 60 * 1000;
const generationByDate = new Map<string, Promise<boolean>>();
const generationFailureAtByDate = new Map<string, number>();
const EMERGENCY_PUZZLE: Puzzle = {
  id: "emergency-puzzle",
  dateKey: "emergency",
  title: "Emergency Puzzle",
  answer: "bicycle",
  aliases: ["bike", "cycle"],
  maxGuesses: 8,
  boardSize: 420,
  gridSize: 32,
  imageUrl:
    "https://images.unsplash.com/photo-1485965120184-e220f721d03e?auto=format&fit=crop&w=1200&h=1200&q=80",
  imageAlt: "a bicycle parked outdoors",
  words: [
    { guess: "wheel", aliases: ["wheels", "tire", "tyre", "rim"], reveal: [115, 245, 100, 105] },
    { guess: "handlebar", aliases: ["handlebars", "bar", "grip"], reveal: [225, 170, 85, 55] },
    { guess: "seat", aliases: ["saddle"], reveal: [175, 165, 60, 40] },
    { guess: "pedal", aliases: ["pedals", "crank"], reveal: [198, 260, 62, 58] },
    { guess: "frame", aliases: ["body", "triangle"], reveal: [150, 190, 145, 98] },
  ],
};

function getDateKey(timeZone: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function getNextDateKey(dateKey: string) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const tomorrow = new Date(Date.UTC(year, month - 1, day + 1, 0, 0, 0));

  return tomorrow.toISOString().slice(0, 10);
}

function getTimeZoneOffsetMs(date: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const utc = Date.UTC(
    Number(values.year),
    Number(values.month) - 1,
    Number(values.day),
    Number(values.hour),
    Number(values.minute),
    Number(values.second),
  );

  return utc - date.getTime();
}

function getUtcDateForTimeZoneMidnight(dateKey: string, timeZone: string) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const approximateUtc = new Date(
    Date.UTC(year, month - 1, day, 0, 0, 0),
  );
  const offset = getTimeZoneOffsetMs(approximateUtc, timeZone);

  return new Date(approximateUtc.getTime() - offset);
}

function getNextResetAt(dateKey: string, timeZone: string) {
  return getUtcDateForTimeZoneMidnight(getNextDateKey(dateKey), timeZone).toISOString();
}

export function getPuzzleTiming() {
  const timeZone = process.env.PIXORDLE_TIMEZONE ?? DEFAULT_TIMEZONE;
  const dateKey = getDateKey(timeZone);

  return {
    dateKey,
    resetAt: getNextResetAt(dateKey, timeZone),
    timeZone,
  };
}

function isRevealTuple(value: unknown): value is [number, number, number, number] {
  return (
    Array.isArray(value) &&
    value.length === 4 &&
    value.every((item) => typeof item === "number" && Number.isFinite(item))
  );
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parsePuzzle(value: unknown): Puzzle | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const candidate = value as Record<string, unknown>;

  const id = typeof candidate.id === "string" ? candidate.id : null;
  const title = typeof candidate.title === "string" ? candidate.title : null;
  const answer = typeof candidate.answer === "string" ? candidate.answer : null;
  const maxGuesses = asNumber(candidate.maxGuesses);
  const boardSize = asNumber(candidate.boardSize);
  const gridSize = asNumber(candidate.gridSize);
  const imageUrl = typeof candidate.imageUrl === "string" ? candidate.imageUrl : null;
  const imageAlt = typeof candidate.imageAlt === "string" ? candidate.imageAlt : null;
  const imageSize =
    candidate.imageSize && typeof candidate.imageSize === "object"
      ? (candidate.imageSize as Record<string, unknown>)
      : null;
  const aliasesRaw = candidate.aliases;
  const wordsRaw = candidate.words;

  if (
    !id ||
    !title ||
    !answer ||
    maxGuesses === null ||
    boardSize === null ||
    gridSize === null ||
    !imageUrl ||
    !imageAlt ||
    !isStringArray(aliasesRaw) ||
    !Array.isArray(wordsRaw)
  ) {
    return null;
  }

  const words = wordsRaw
    .map((word) => {
      if (!word || typeof word !== "object") {
        return null;
      }

      const candidateWord = word as Record<string, unknown>;
      if (
        typeof candidateWord.guess !== "string" ||
        !Array.isArray(candidateWord.aliases) ||
        !isRevealTuple(candidateWord.reveal)
      ) {
        return null;
      }

      return {
        guess: candidateWord.guess,
        aliases: isStringArray(candidateWord.aliases) ? candidateWord.aliases : [],
        reveal: candidateWord.reveal,
        confidence: asNumber(candidateWord.confidence) ?? undefined,
      };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null);

  if (words.length === 0) {
    return null;
  }

  return {
    id,
    dateKey: typeof candidate.dateKey === "string" ? candidate.dateKey : undefined,
    title,
    answer,
    aliases: aliasesRaw,
    maxGuesses,
    boardSize,
    gridSize,
    imageUrl,
    imageAlt,
    imageSize:
      imageSize && asNumber(imageSize.width) !== null && asNumber(imageSize.height) !== null
        ? { width: asNumber(imageSize.width) ?? 0, height: asNumber(imageSize.height) ?? 0 }
        : undefined,
    words,
    detections: parseDetections(candidate.detections),
  };
}

function parseDetections(value: unknown): Puzzle["detections"] {
  if (!Array.isArray(value)) {
    return undefined;
  }

  const detections = value
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }

      const candidate = item as Record<string, unknown>;
      if (
        typeof candidate.label !== "string" ||
        asNumber(candidate.confidence) === null ||
        !isRevealTuple(candidate.bbox)
      ) {
        return null;
      }

      return {
        label: candidate.label,
        confidence: asNumber(candidate.confidence) ?? 0,
        bbox: candidate.bbox,
        aliases: isStringArray(candidate.aliases) ? candidate.aliases : [],
      };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null);

  return detections.length > 0 ? detections : undefined;
}

async function readPuzzleFile(filePath: string) {
  const raw = await readFile(filePath, "utf8");
  const parsed = JSON.parse(raw) as unknown;
  const puzzle = parsePuzzle(parsed);

  if (!puzzle) {
    throw new Error(`Invalid puzzle JSON schema: ${filePath}`);
  }

  return puzzle;
}

async function generateDailyPuzzleIfEnabled(dateKey: string) {
  if (process.env.AUTO_GENERATE_DAILY !== "true") {
    return false;
  }

  const lastFailureAt = generationFailureAtByDate.get(dateKey);
  if (lastFailureAt && Date.now() - lastFailureAt < GENERATION_FAILURE_RETRY_MS) {
    return false;
  }

  const existing = generationByDate.get(dateKey);
  if (existing) {
    return existing;
  }

  const generation = new Promise<boolean>((resolve) => {
    const scriptPath = path.join(process.cwd(), "scripts", "generate-daily-puzzle.py");
    const processHandle = spawn("python3", [scriptPath, `--date=${dateKey}`], {
      cwd: process.cwd(),
      stdio: "pipe",
      env: process.env,
    });

    processHandle.on("close", (code) => {
      if (code === 0) {
        generationFailureAtByDate.delete(dateKey);
        resolve(true);
      } else {
        generationFailureAtByDate.set(dateKey, Date.now());
        resolve(false);
      }
    });

    processHandle.on("error", () => {
      generationFailureAtByDate.set(dateKey, Date.now());
      resolve(false);
    });
  }).finally(() => {
    generationByDate.delete(dateKey);
  });

  generationByDate.set(dateKey, generation);
  return generation;
}

export async function getCurrentPuzzle() {
  const { dateKey } = getPuzzleTiming();

  const dailyPath = path.join(PUZZLE_DIR, `${dateKey}.json`);

  try {
    return await readPuzzleFile(dailyPath);
  } catch {
    await generateDailyPuzzleIfEnabled(dateKey);

    try {
      return await readPuzzleFile(dailyPath);
    } catch {
      // Fall through to default puzzle.
    }

    try {
      return await readPuzzleFile(DEFAULT_PUZZLE_PATH);
    } catch {
      return EMERGENCY_PUZZLE;
    }
  }
}
