from __future__ import annotations

import math

from app.schemas.recommendation import GameRow, ParsedUserIntent, ScoreBreakdown, SessionPayload
from app.services.recommendation.tokenize import overlap_score, tokenize


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def normalized_tag_pool(game: GameRow) -> list[str]:
    return [
        item.lower()
        for item in [*(game.tags or []), *(game.genres or []), *(game.categories or [])]
    ]


def tag_match_score(game: GameRow, intent: ParsedUserIntent) -> float:
    return overlap_score(intent.preferred_tags, normalized_tag_pool(game))


def text_match_score(game: GameRow, intent: ParsedUserIntent) -> float:
    prompt_tokens = tokenize(intent.free_text_intent)
    game_tokens = tokenize(f"{game.name} {game.llm_context or ''}")
    return overlap_score(prompt_tokens, game_tokens)


def rating_confidence_score(game: GameRow) -> float:
    ratio = clamp(game.rating_ratio or 0)
    volume = clamp(math.log10((game.total_reviews or 0) + 1) / 5)
    return clamp(0.65 * ratio + 0.35 * volume)


def popularity_reliability_score(game: GameRow) -> float:
    review_signal = clamp(math.log10((game.total_reviews or 0) + 1) / 5)
    playtime_signal = clamp(math.log10((game.average_playtime_forever or 0) + 1) / 4)
    return clamp(0.75 * review_signal + 0.25 * playtime_signal)


def preference_history_score(game: GameRow, history: list[SessionPayload]) -> float:
    if not history:
        return 0.0
    historical_tags = [
        tag
        for session in history
        for tag in session.normalized_preferences.preferred_tags
    ]
    return overlap_score(historical_tags, normalized_tag_pool(game))


def avoid_penalty(game: GameRow, intent: ParsedUserIntent) -> float:
    return overlap_score(intent.avoid_tags, normalized_tag_pool(game))


def score_game(
    game: GameRow,
    intent: ParsedUserIntent,
    history: list[SessionPayload],
) -> tuple[float, ScoreBreakdown]:
    breakdown = ScoreBreakdown(
        tag_match_score=tag_match_score(game, intent),
        text_match_score=text_match_score(game, intent),
        rating_confidence_score=rating_confidence_score(game),
        popularity_reliability_score=popularity_reliability_score(game),
        avoid_penalty=avoid_penalty(game, intent),
        preference_history_score=preference_history_score(game, history) if history else None,
    )

    final_score = (
        0.35 * breakdown.tag_match_score
        + 0.25 * breakdown.text_match_score
        + 0.15 * breakdown.rating_confidence_score
        + 0.10 * breakdown.popularity_reliability_score
        + 0.10 * (breakdown.preference_history_score or 0)
        - 0.20 * breakdown.avoid_penalty
        if history
        else 0.40 * breakdown.tag_match_score
        + 0.30 * breakdown.text_match_score
        + 0.15 * breakdown.rating_confidence_score
        + 0.15 * breakdown.popularity_reliability_score
        - 0.25 * breakdown.avoid_penalty
    )

    return clamp(final_score, -1.0, 1.0), breakdown
