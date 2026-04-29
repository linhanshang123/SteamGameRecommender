const STOP_WORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "but",
  "for",
  "from",
  "game",
  "games",
  "i",
  "if",
  "in",
  "it",
  "like",
  "of",
  "or",
  "something",
  "that",
  "the",
  "to",
  "want",
  "with",
]);

export function tokenize(text: string) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .map((token) => token.trim())
    .filter((token) => token.length > 1 && !STOP_WORDS.has(token));
}

export function overlapScore(a: string[], b: string[]) {
  if (!a.length || !b.length) {
    return 0;
  }

  const aSet = new Set(a);
  const bSet = new Set(b);
  let shared = 0;

  for (const token of aSet) {
    if (bSet.has(token)) {
      shared += 1;
    }
  }

  return shared / Math.max(aSet.size, bSet.size);
}
