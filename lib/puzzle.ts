export type PuzzleWord = {
  guess: string;
  aliases: string[];
  reveal: [number, number, number, number];
};

export type Puzzle = {
  id: string;
  title: string;
  answer: string;
  aliases: string[];
  maxGuesses: number;
  boardSize: number;
  gridSize: number;
  words: PuzzleWord[];
};

export const puzzle: Puzzle = {
  id: "bicycle-001",
  title: "Hidden bicycle",
  answer: "bicycle",
  aliases: ["bike", "cycle"],
  maxGuesses: 6,
  boardSize: 420,
  gridSize: 10,
  words: [
    {
      guess: "wheel",
      aliases: ["wheels", "tire", "tyre", "rim"],
      reveal: [40, 228, 322, 150],
    },
    {
      guess: "handlebar",
      aliases: ["handlebars", "bar", "grip", "steering"],
      reveal: [282, 104, 104, 74],
    },
    {
      guess: "pedal",
      aliases: ["pedals", "crank"],
      reveal: [196, 294, 66, 62],
    },
    {
      guess: "seat",
      aliases: ["saddle"],
      reveal: [152, 146, 74, 56],
    },
    {
      guess: "frame",
      aliases: ["triangle", "body"],
      reveal: [112, 176, 196, 142],
    },
  ],
};

export function normalizeGuess(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ");
}

export function matchesTerm(guess: string, term: string, aliases: string[] = []) {
  return [term, ...aliases].some((candidate) => guess === normalizeGuess(candidate));
}

export function getTileIndexesForReveal(
  reveal: PuzzleWord["reveal"],
  boardSize = puzzle.boardSize,
  gridSize = puzzle.gridSize,
) {
  const [x, y, width, height] = reveal;
  const tileSize = boardSize / gridSize;
  const firstCol = Math.max(0, Math.floor(x / tileSize));
  const lastCol = Math.min(gridSize - 1, Math.floor((x + width) / tileSize));
  const firstRow = Math.max(0, Math.floor(y / tileSize));
  const lastRow = Math.min(gridSize - 1, Math.floor((y + height) / tileSize));
  const indexes: number[] = [];

  for (let row = firstRow; row <= lastRow; row += 1) {
    for (let col = firstCol; col <= lastCol; col += 1) {
      indexes.push(row * gridSize + col);
    }
  }

  return indexes;
}
