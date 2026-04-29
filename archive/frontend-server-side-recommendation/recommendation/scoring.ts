import type { GameRow, ParsedUserIntent, RecommendationSessionRow, ScoreBreakdown } from "@/lib/types";
import { overlapScore, tokenize } from "@/lib/recommendation/tokenize";

function clamp(value: number, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value));
}

function normalizedTagPool(game: GameRow) {
  return [...(game.tags ?? []), ...(game.genres ?? []), ...(game.categories ?? [])].map((item) =>
    item.toLowerCase(),
  );
}

function tagMatchScore(game: GameRow, intent: ParsedUserIntent) {
  const tags = normalizedTagPool(game);
  return overlapScore(intent.preferred_tags, tags);
}

function textMatchScore(game: GameRow, intent: ParsedUserIntent) {
  const promptTokens = tokenize(intent.free_text_intent);
  const gameTokens = tokenize(`${game.name} ${game.llm_context ?? ""}`);
  return overlapScore(promptTokens, gameTokens);
}

function ratingConfidenceScore(game: GameRow) {
  const ratio = clamp(game.rating_ratio ?? 0);
  const volume = clamp(Math.log10((game.total_reviews ?? 0) + 1) / 5);
  return clamp(0.65 * ratio + 0.35 * volume);
}

function popularityReliabilityScore(game: GameRow) {
  const reviewSignal = clamp(Math.log10((game.total_reviews ?? 0) + 1) / 5);
  const playtimeSignal = clamp(Math.log10((game.average_playtime_forever ?? 0) + 1) / 4);
  return clamp(0.75 * reviewSignal + 0.25 * playtimeSignal);
}

function preferenceHistoryScore(game: GameRow, history: RecommendationSessionRow[]) {
  if (!history.length) {
    return 0;
  }

  const historicalTags = history.flatMap((session) => [
    ...(session.normalized_preferences.preferred_tags ?? []),
  ]);

  return overlapScore(historicalTags, normalizedTagPool(game));
}

function avoidPenalty(game: GameRow, intent: ParsedUserIntent) {
  const tags = normalizedTagPool(game);
  return overlapScore(intent.avoid_tags, tags);
}

export function scoreGame(
  game: GameRow,
  intent: ParsedUserIntent,
  history: RecommendationSessionRow[],
) {
  const breakdown: ScoreBreakdown = {
    tag_match_score: tagMatchScore(game, intent),
    text_match_score: textMatchScore(game, intent),
    rating_confidence_score: ratingConfidenceScore(game),
    popularity_reliability_score: popularityReliabilityScore(game),
    avoid_penalty: avoidPenalty(game, intent),
  };

  if (history.length) {
    breakdown.preference_history_score = preferenceHistoryScore(game, history);
  }

  const finalScore = history.length
    ? 0.35 * breakdown.tag_match_score +
      0.25 * breakdown.text_match_score +
      0.15 * breakdown.rating_confidence_score +
      0.1 * breakdown.popularity_reliability_score +
      0.1 * (breakdown.preference_history_score ?? 0) -
      0.2 * breakdown.avoid_penalty
    : 0.4 * breakdown.tag_match_score +
      0.3 * breakdown.text_match_score +
      0.15 * breakdown.rating_confidence_score +
      0.15 * breakdown.popularity_reliability_score -
      0.25 * breakdown.avoid_penalty;

  return {
    finalScore: clamp(finalScore, -1, 1),
    breakdown,
  };
}
