from __future__ import annotations

import math

from app.schemas.recommendation import (
    GameRow,
    ParsedUserIntent,
    RecommendationDebugPayload,
    ScoreBreakdown,
    SessionPayload,
)
from app.services.recommendation.experience import GameExperienceProfile, infer_game_experience_profile
from app.services.recommendation.tokenize import tokenize


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


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


def list_alignment_score(target_values: list[str], candidate_values: list[str]) -> float:
    if not target_values:
        return 0.0
    return recall_score(matched_terms(target_values, candidate_values), target_values)


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


def reference_similarity_score(game: GameRow, intent: ParsedUserIntent) -> float:
    anchor_profile = intent.reference_anchor_profile
    if not anchor_profile:
        return 0.0

    candidate_profile = infer_game_experience_profile(game)
    derived_tag_score = recall_score(
        matched_terms(anchor_profile.derived_tags, normalized_tag_pool(game)),
        anchor_profile.derived_tags,
    )
    combat_feel_score = list_alignment_score(anchor_profile.combat_feel, candidate_profile.combat_feel)
    loop_shape_score = list_alignment_score(anchor_profile.loop_shape, candidate_profile.loop_shape)
    presentation_score = list_alignment_score(
        anchor_profile.presentation_style,
        candidate_profile.presentation_style,
    )
    pace_score = 1.0 if anchor_profile.combat_pace and candidate_profile.combat_pace == anchor_profile.combat_pace else 0.0
    if not anchor_profile.combat_pace:
        pace_score = 0.0

    return clamp(
        0.35 * derived_tag_score
        + 0.20 * combat_feel_score
        + 0.20 * loop_shape_score
        + 0.15 * presentation_score
        + 0.10 * pace_score
    )


def combat_pace_match_score(profile: GameExperienceProfile, intent: ParsedUserIntent) -> float:
    target_pace = intent.experience_axes.combat_pace or (intent.reference_anchor_profile.combat_pace if intent.reference_anchor_profile else None)
    if not target_pace:
        return 0.0
    return 1.0 if profile.combat_pace == target_pace else 0.0


def combat_feel_match_score(profile: GameExperienceProfile, intent: ParsedUserIntent) -> float:
    target_values = dedupe_lowered(
        [
            *intent.experience_axes.combat_feel,
            *((intent.reference_anchor_profile.combat_feel) if intent.reference_anchor_profile else []),
        ]
    )
    return list_alignment_score(target_values, profile.combat_feel)


def presentation_match_score(profile: GameExperienceProfile, intent: ParsedUserIntent) -> float:
    target_values = dedupe_lowered(
        [
            *intent.experience_axes.presentation_style,
            *((intent.reference_anchor_profile.presentation_style) if intent.reference_anchor_profile else []),
        ]
    )
    return list_alignment_score(target_values, profile.presentation_style)


def loop_shape_match_score(profile: GameExperienceProfile, intent: ParsedUserIntent) -> float:
    target_values = dedupe_lowered(
        [
            *intent.experience_axes.loop_shape,
            *((intent.reference_anchor_profile.loop_shape) if intent.reference_anchor_profile else []),
        ]
    )
    return list_alignment_score(target_values, profile.loop_shape)


def _penalty(enabled: bool, active: bool, strength: float = 1.0) -> float:
    return clamp(strength if enabled and active else 0.0)


def score_game(
    game: GameRow,
    intent: ParsedUserIntent,
    history: list[SessionPayload],
    resolved_reference_games: list[GameRow],
    retrieval_routes: list[str] | None = None,
) -> tuple[float, ScoreBreakdown, RecommendationDebugPayload]:
    game_tag_pool = normalized_tag_pool(game)
    query_tokens = tokenize(intent.free_text_intent)
    game_text_tokens = tokenize(f"{game.name} {game.llm_context or ''}")
    profile = infer_game_experience_profile(game)

    matched_preferred_tags = matched_terms(intent.preferred_tags, game_tag_pool)
    matched_avoid_tags = matched_terms(intent.avoid_tags, game_tag_pool)
    text_matched_terms = matched_terms(query_tokens, game_text_tokens)

    tag_match = recall_score(matched_preferred_tags, intent.preferred_tags)
    text_match = recall_score(text_matched_terms, query_tokens)
    reference_match = reference_similarity_score(game, intent)
    history_match = preference_history_score(game, history) if history else None
    explicit_avoid_penalty = recall_score(matched_avoid_tags, intent.avoid_tags)

    pace_match = combat_pace_match_score(profile, intent)
    feel_match = combat_feel_match_score(profile, intent)
    presentation_match = presentation_match_score(profile, intent)
    loop_match = loop_shape_match_score(profile, intent)

    strategy_penalty = _penalty(intent.implicit_soft_avoids.strategy_heavy, profile.strategy_heavy, 0.9)
    slow_penalty = _penalty(intent.implicit_soft_avoids.slow_combat, profile.slow_combat, 0.9)
    clunky_penalty = _penalty(intent.implicit_soft_avoids.clunky_feel, profile.clunky_feel, 0.8)
    shooter_penalty = _penalty(intent.implicit_soft_avoids.shooter_dominant, profile.shooter_dominant, 1.0)
    soft_avoid_penalty = clamp(
        (strategy_penalty + slow_penalty + clunky_penalty + shooter_penalty) / 4
    )

    breakdown = ScoreBreakdown(
        tag_match_score=tag_match,
        text_match_score=text_match,
        reference_similarity_score=reference_match,
        combat_pace_match_score=pace_match,
        combat_feel_match_score=feel_match,
        presentation_match_score=presentation_match,
        loop_shape_match_score=loop_match,
        rating_confidence_score=rating_confidence_score(game),
        popularity_reliability_score=popularity_reliability_score(game),
        preference_history_score=history_match,
        avoid_penalty=explicit_avoid_penalty,
        strategy_heavy_penalty=strategy_penalty,
        slow_combat_penalty=slow_penalty,
        clunky_feel_penalty=clunky_penalty,
        shooter_dominant_penalty=shooter_penalty,
        soft_avoid_penalty_score=soft_avoid_penalty,
        deterministic_score=0.0,
        llm_match_score=0.0,
    )

    deterministic_score = (
        0.18 * breakdown.reference_similarity_score
        + 0.16 * breakdown.combat_pace_match_score
        + 0.16 * breakdown.combat_feel_match_score
        + 0.12 * breakdown.presentation_match_score
        + 0.12 * breakdown.loop_shape_match_score
        + 0.10 * breakdown.tag_match_score
        + 0.07 * breakdown.text_match_score
        + 0.05 * breakdown.rating_confidence_score
        + 0.04 * breakdown.popularity_reliability_score
        + 0.05 * (breakdown.preference_history_score or 0)
        - 0.08 * breakdown.avoid_penalty
        - 0.10 * breakdown.soft_avoid_penalty_score
        if history
        else 0.20 * breakdown.reference_similarity_score
        + 0.18 * breakdown.combat_pace_match_score
        + 0.18 * breakdown.combat_feel_match_score
        + 0.12 * breakdown.presentation_match_score
        + 0.12 * breakdown.loop_shape_match_score
        + 0.10 * breakdown.tag_match_score
        + 0.06 * breakdown.text_match_score
        + 0.05 * breakdown.rating_confidence_score
        + 0.05 * breakdown.popularity_reliability_score
        - 0.08 * breakdown.avoid_penalty
        - 0.10 * breakdown.soft_avoid_penalty_score
    )
    breakdown.deterministic_score = clamp(deterministic_score)

    debug_payload = RecommendationDebugPayload(
        matched_preferred_tags=matched_preferred_tags,
        matched_avoid_tags=matched_avoid_tags,
        text_matched_terms=text_matched_terms,
        resolved_reference_appids=[reference_game.appid for reference_game in resolved_reference_games],
        retrieval_routes=retrieval_routes or [],
        experience_axes=intent.experience_axes,
        implicit_soft_avoids=intent.implicit_soft_avoids,
        reference_anchor_profile=intent.reference_anchor_profile,
    )

    return breakdown.deterministic_score, breakdown, debug_payload
