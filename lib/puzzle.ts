export type PuzzleWord = {
  guess: string;
  aliases: string[];
  reveal: [number, number, number, number];
};

export type Puzzle = {
  id: string;
  dateKey?: string;
  title: string;
  answer: string;
  aliases: string[];
  maxGuesses: number;
  boardSize: number;
  gridSize: number;
  imageUrl: string;
  imageAlt: string;
  words: PuzzleWord[];
};

export function normalizeGuess(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ");
}

export function matchesTerm(guess: string, term: string, aliases: string[] = []) {
  return [term, ...aliases].some((candidate) => guess === normalizeGuess(candidate));
}

export function getTileIndexesForReveal(
  reveal: PuzzleWord["reveal"],
  boardSize: number,
  gridSize: number,
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
