from __future__ import annotations

import math

from app.schemas.recommendation import (
    GameRow,
    ParsedUserIntent,
    RecommendationDebugPayload,
    ScoreBreakdown,
    SessionPayload,
)
from app.services.recommendation.tokenize import tokenize


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def game_text_blob(game: GameRow) -> str:
    return game.embedding_text or game.llm_context or ""


def dedupe_lowered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(lowered)
    return deduped


def normalized_tag_pool(game: GameRow) -> list[str]:
    return dedupe_lowered([*(game.tags or []), *(game.genres or []), *(game.categories or [])])


def matched_terms(query_values: list[str], candidate_values: list[str]) -> list[str]:
    candidate_set = {value.lower() for value in candidate_values}
    matches = [value.lower() for value in query_values if value.lower() in candidate_set]
    return dedupe_lowered(matches)


def recall_score(matches: list[str], query_values: list[str]) -> float:
    query_size = len({value.lower() for value in query_values if value})
    if query_size == 0:
        return 0.0
    return clamp(len({value.lower() for value in matches}) / query_size)


def rating_confidence_score(game: GameRow) -> float:
    ratio = clamp(game.rating_ratio or 0)
    volume = clamp(math.log10((game.total_reviews or 0) + 1) / 5)
    return clamp(0.6 * ratio + 0.4 * volume)


def popularity_reliability_score(game: GameRow) -> float:
    review_signal = clamp(math.log10((game.total_reviews or 0) + 1) / 5)
    playtime_signal = clamp(math.log10((game.average_playtime_forever or 0) + 1) / 4)
    return clamp(0.7 * review_signal + 0.3 * playtime_signal)


def preference_history_score(game: GameRow, history: list[SessionPayload]) -> float:
    if not history:
        return 0.0
    historical_tags = dedupe_lowered(
        [
            tag
            for session in history
            for tag in session.normalized_preferences.preferred_tags
        ]
    )
    return recall_score(matched_terms(historical_tags, normalized_tag_pool(game)), historical_tags)


def reference_similarity_score(game: GameRow, resolved_reference_games: list[GameRow]) -> float:
    if not resolved_reference_games:
        return 0.0

    reference_terms = dedupe_lowered(
        [
            value
            for reference_game in resolved_reference_games
            for value in [*(reference_game.tags or []), *(reference_game.genres or [])]
        ]
    )
    reference_context_terms = dedupe_lowered(
        [
            token
            for reference_game in resolved_reference_games
            for token in tokenize(game_text_blob(reference_game))
        ]
    )[:10]
    tag_recall = recall_score(
        matched_terms(reference_terms, normalized_tag_pool(game)),
        reference_terms,
    )
    text_recall = recall_score(
        matched_terms(reference_context_terms, tokenize(f"{game.name} {game_text_blob(game)}")),
        reference_context_terms,
    )
    return clamp(0.7 * tag_recall + 0.3 * text_recall)


def score_game(
    game: GameRow,
    intent: ParsedUserIntent,
    history: list[SessionPayload],
    resolved_reference_games: list[GameRow],
    retrieval_routes: list[str] | None = None,
) -> tuple[float, ScoreBreakdown, RecommendationDebugPayload]:
    game_tag_pool = normalized_tag_pool(game)
    query_tokens = tokenize(intent.free_text_intent)
    game_text_tokens = tokenize(f"{game.name} {game_text_blob(game)}")

    matched_preferred_tags = matched_terms(intent.preferred_tags, game_tag_pool)
    matched_avoid_tags = matched_terms(intent.avoid_tags, game_tag_pool)
    text_matched_terms = matched_terms(query_tokens, game_text_tokens)

    tag_match = recall_score(matched_preferred_tags, intent.preferred_tags)
    text_match = recall_score(text_matched_terms, query_tokens)
    reference_match = reference_similarity_score(game, resolved_reference_games)
    history_match = preference_history_score(game, history) if history else None
    avoid_match = recall_score(matched_avoid_tags, intent.avoid_tags)

    breakdown = ScoreBreakdown(
        tag_match_score=tag_match,
        text_match_score=text_match,
        reference_similarity_score=reference_match,
        rating_confidence_score=rating_confidence_score(game),
        popularity_reliability_score=popularity_reliability_score(game),
        preference_history_score=history_match,
        avoid_penalty=avoid_match,
        deterministic_score=0.0,
        llm_match_score=0.0,
    )

    deterministic_score = (
        0.30 * breakdown.tag_match_score
        + 0.15 * breakdown.text_match_score
        + 0.20 * breakdown.reference_similarity_score
        + 0.10 * breakdown.rating_confidence_score
        + 0.05 * breakdown.popularity_reliability_score
        + 0.10 * (breakdown.preference_history_score or 0)
        - 0.10 * breakdown.avoid_penalty
        if history
        else 0.35 * breakdown.tag_match_score
        + 0.20 * breakdown.text_match_score
        + 0.20 * breakdown.reference_similarity_score
        + 0.10 * breakdown.rating_confidence_score
        + 0.05 * breakdown.popularity_reliability_score
        - 0.10 * breakdown.avoid_penalty
    )
    breakdown.deterministic_score = clamp(deterministic_score)

    debug_payload = RecommendationDebugPayload(
        matched_preferred_tags=matched_preferred_tags,
        matched_avoid_tags=matched_avoid_tags,
        text_matched_terms=text_matched_terms,
        resolved_reference_appids=[game.appid for game in resolved_reference_games],
        retrieval_routes=retrieval_routes or [],
    )

    return breakdown.deterministic_score, breakdown, debug_payload
