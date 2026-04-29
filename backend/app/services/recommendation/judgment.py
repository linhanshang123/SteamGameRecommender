from __future__ import annotations

from dataclasses import dataclass

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.schemas.recommendation import (
    BucketEvidence,
    GameRow,
    LlmBucketJudgmentItem,
    LlmBucketJudgmentResponse,
    ParsedUserIntent,
    RecommendationArchetype,
    RecommendationBucketType,
    RecommendationDebugPayload,
    ScoreBreakdown,
)
from app.services.recommendation.experience import GameExperienceProfile, infer_game_experience_profile


@dataclass
class BucketDecision:
    bucket: RecommendationBucketType
    bucket_reason: str
    concern: str
    bucket_evidence: BucketEvidence
    secondary_traits: list[str]
    llm_match_score: float
    final_score: float


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _list_overlap(left: list[str], right: list[str]) -> list[str]:
    right_lower = {value.lower() for value in right}
    return [value for value in left if value.lower() in right_lower]


def _core_fit_score(breakdown: ScoreBreakdown) -> float:
    return clamp(
        0.34 * breakdown.reference_similarity_score
        + 0.18 * breakdown.combat_pace_match_score
        + 0.20 * breakdown.combat_feel_match_score
        + 0.14 * breakdown.loop_shape_match_score
        + 0.10 * breakdown.presentation_match_score
        + 0.04 * breakdown.tag_match_score
        - 0.16 * breakdown.soft_avoid_penalty_score
    )


def _presentation_novelty(profile: GameExperienceProfile, archetype: RecommendationArchetype) -> list[str]:
    reference = {value.lower() for value in archetype.core_experience}
    return [
        f"presentation:{value}"
        for value in profile.presentation_style
        if value.lower() not in reference
    ][:2]


def _loop_novelty(profile: GameExperienceProfile, archetype: RecommendationArchetype) -> list[str]:
    reference = {value.lower() for value in archetype.core_experience}
    return [f"structure:{value}" for value in profile.loop_shape if value.lower() not in reference][:2]


def _combat_novelty(profile: GameExperienceProfile, archetype: RecommendationArchetype) -> list[str]:
    reference = {value.lower() for value in archetype.core_experience}
    return [f"combat:{value}" for value in profile.combat_feel if value.lower() not in reference][:2]


def _novelty_axes(profile: GameExperienceProfile, archetype: RecommendationArchetype) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *_presentation_novelty(profile, archetype),
                *_loop_novelty(profile, archetype),
                *_combat_novelty(profile, archetype),
            ]
        )
    )


def _structural_drift(
    profile: GameExperienceProfile,
    breakdown: ScoreBreakdown,
    archetype: RecommendationArchetype,
) -> bool:
    if breakdown.soft_avoid_penalty_score >= 0.72:
        return True
    if profile.strategy_heavy and "strategy-heavy drift" in archetype.hard_drifts_to_avoid:
        return True
    if profile.shooter_dominant and "shooter-dominant drift" in archetype.hard_drifts_to_avoid:
        return True
    if profile.slow_combat and "slow or deliberate combat drag" in archetype.hard_drifts_to_avoid:
        return True
    if "top-down" in {value.lower() for value in archetype.core_experience} and "platforming" in {
        value.lower() for value in profile.loop_shape
    }:
        return True
    return False


def _closest_eligible(
    profile: GameExperienceProfile,
    breakdown: ScoreBreakdown,
    archetype: RecommendationArchetype,
) -> bool:
    return (
        not _structural_drift(profile, breakdown, archetype)
        and _core_fit_score(breakdown) >= 0.48
        and breakdown.reference_similarity_score >= 0.28
        and breakdown.soft_avoid_penalty_score <= 0.45
    )


def _novel_eligible(
    profile: GameExperienceProfile,
    breakdown: ScoreBreakdown,
    archetype: RecommendationArchetype,
) -> tuple[bool, list[str]]:
    novelty_axes = _novelty_axes(profile, archetype)
    eligible = (
        not _structural_drift(profile, breakdown, archetype)
        and _core_fit_score(breakdown) >= 0.40
        and bool(novelty_axes)
    )
    return eligible, novelty_axes


def _niche_eligible(
    game: GameRow,
    profile: GameExperienceProfile,
    breakdown: ScoreBreakdown,
    archetype: RecommendationArchetype,
) -> tuple[bool, str | None]:
    if _structural_drift(profile, breakdown, archetype) or _core_fit_score(breakdown) < 0.32:
        return False, None

    standout_dimensions = [
        ("combat feel", breakdown.combat_feel_match_score),
        ("loop shape", breakdown.loop_shape_match_score),
        ("presentation", breakdown.presentation_match_score),
        ("reference pull", breakdown.reference_similarity_score),
    ]
    standout_dimensions.sort(key=lambda entry: entry[1], reverse=True)
    dimension, strength = standout_dimensions[0]

    low_visibility = (game.total_reviews or 0) < 1500
    if strength >= 0.58 and low_visibility:
        return True, f"its {dimension} hits unusually well despite being less obvious or less mainstream"
    if strength >= 0.70:
        return True, f"its {dimension} is strong enough to justify a higher-variance recommendation"
    return False, None


def _default_bucket_reason(
    bucket: RecommendationBucketType,
    game: GameRow,
    breakdown: ScoreBreakdown,
    debug_payload: RecommendationDebugPayload,
    novelty_axes: list[str],
    niche_hook: str | None,
) -> str:
    if bucket == RecommendationBucketType.CLOSEST_MATCHES:
        if breakdown.reference_similarity_score >= 0.35:
            return f"{game.name} stays closest to the reference game's core rhythm and combat direction."
        if breakdown.combat_feel_match_score >= 0.5:
            return f"{game.name} keeps the requested combat feel without introducing major structural drift."
        return f"{game.name} is the cleanest same-direction match among the current candidates."

    if bucket == RecommendationBucketType.SIMILAR_BUT_NOVEL:
        if novelty_axes:
            return f"{game.name} keeps the core feel intact while adding fresh energy through {novelty_axes[0].split(':', 1)[1]}."
        return f"{game.name} preserves the target experience but approaches it from a fresher angle."

    if niche_hook:
        return f"{game.name} is a worthwhile gamble because {niche_hook}."
    return f"{game.name} is not the obvious answer, but it has a distinctive hit worth betting on."


def _default_concern(
    breakdown: ScoreBreakdown,
    debug_payload: RecommendationDebugPayload,
) -> str:
    if breakdown.shooter_dominant_penalty >= 0.8:
        return "It leans more shooter-forward than the core target."
    if breakdown.strategy_heavy_penalty >= 0.8:
        return "It carries more strategy drag than the requested action-first feel."
    if breakdown.slow_combat_penalty >= 0.8:
        return "Its combat pace may feel heavier than the prompt suggests."
    if debug_payload.matched_avoid_tags:
        return f"It still brushes against avoided elements such as {', '.join(debug_payload.matched_avoid_tags[:2])}."
    return ""


def _bucket_evidence(
    bucket: RecommendationBucketType,
    breakdown: ScoreBreakdown,
    novelty_axes: list[str],
    niche_hook: str | None,
) -> BucketEvidence:
    bucket_fit = _core_fit_score(breakdown)
    novelty_support = clamp(
        0.45 * len(novelty_axes[:2])
        + 0.25 * breakdown.presentation_match_score
        + 0.20 * breakdown.loop_shape_match_score
        + 0.10 * breakdown.combat_feel_match_score
    )
    niche_conviction = clamp(
        0.45 * (breakdown.presentation_match_score or breakdown.combat_feel_match_score)
        + 0.25 * breakdown.reference_similarity_score
        + 0.20 * breakdown.rating_confidence_score
        + (0.10 if niche_hook else 0.0)
    )

    if bucket == RecommendationBucketType.CLOSEST_MATCHES:
        novelty_support = 0.0
        niche_conviction = 0.0
    elif bucket == RecommendationBucketType.SIMILAR_BUT_NOVEL:
        niche_conviction = 0.0
    else:
        novelty_support = clamp(novelty_support * 0.6)

    return BucketEvidence(
        bucket_fit_score=bucket_fit,
        novelty_support_score=novelty_support,
        niche_conviction_score=niche_conviction,
    )


def _bucket_sort_score(bucket: RecommendationBucketType, breakdown: ScoreBreakdown, evidence: BucketEvidence) -> float:
    if bucket == RecommendationBucketType.CLOSEST_MATCHES:
        return clamp(
            0.62 * evidence.bucket_fit_score
            + 0.28 * breakdown.deterministic_score
            + 0.10 * breakdown.rating_confidence_score
        )
    if bucket == RecommendationBucketType.SIMILAR_BUT_NOVEL:
        return clamp(
            0.45 * evidence.bucket_fit_score
            + 0.32 * evidence.novelty_support_score
            + 0.15 * breakdown.deterministic_score
            + 0.08 * breakdown.rating_confidence_score
        )
    return clamp(
        0.38 * evidence.bucket_fit_score
        + 0.34 * evidence.niche_conviction_score
        + 0.16 * breakdown.rating_confidence_score
        + 0.12 * breakdown.deterministic_score
    )


def _heuristic_bucket(
    game: GameRow,
    profile: GameExperienceProfile,
    breakdown: ScoreBreakdown,
    archetype: RecommendationArchetype,
) -> tuple[RecommendationBucketType | None, list[str], str | None]:
    if _closest_eligible(profile, breakdown, archetype):
        return RecommendationBucketType.CLOSEST_MATCHES, [], None

    novel_eligible, novelty_axes = _novel_eligible(profile, breakdown, archetype)
    if novel_eligible:
        return RecommendationBucketType.SIMILAR_BUT_NOVEL, novelty_axes, None

    niche_eligible, niche_hook = _niche_eligible(game, profile, breakdown, archetype)
    if niche_eligible:
        return RecommendationBucketType.NICHE_PICKS, novelty_axes, niche_hook

    return None, novelty_axes, niche_hook


def _build_candidate_payload(
    candidates: list[tuple[GameRow, ScoreBreakdown, RecommendationDebugPayload]],
    archetype: RecommendationArchetype,
) -> list[dict]:
    payload: list[dict] = []
    for game, breakdown, debug_payload in candidates:
        profile = infer_game_experience_profile(game)
        rule_bucket, novelty_axes, niche_hook = _heuristic_bucket(game, profile, breakdown, archetype)
        payload.append(
            {
                "appid": game.appid,
                "name": game.name,
                "tags": game.tags or [],
                "genres": game.genres or [],
                "llm_context": (game.llm_context or "")[:500],
                "deterministic_score": breakdown.deterministic_score,
                "reference_similarity_score": breakdown.reference_similarity_score,
                "combat_pace_match_score": breakdown.combat_pace_match_score,
                "combat_feel_match_score": breakdown.combat_feel_match_score,
                "presentation_match_score": breakdown.presentation_match_score,
                "loop_shape_match_score": breakdown.loop_shape_match_score,
                "soft_avoid_penalty_score": breakdown.soft_avoid_penalty_score,
                "matched_preferred_tags": debug_payload.matched_preferred_tags,
                "matched_avoid_tags": debug_payload.matched_avoid_tags,
                "profile": {
                    "combat_pace": profile.combat_pace,
                    "combat_feel": profile.combat_feel,
                    "presentation_style": profile.presentation_style,
                    "loop_shape": profile.loop_shape,
                    "strategy_heavy": profile.strategy_heavy,
                    "slow_combat": profile.slow_combat,
                    "clunky_feel": profile.clunky_feel,
                    "shooter_dominant": profile.shooter_dominant,
                },
                "rule_bucket": rule_bucket.value if rule_bucket else None,
                "novelty_axes": novelty_axes,
                "niche_hook": niche_hook,
            }
        )
    return payload


def _llm_bucket_judgments(
    candidates: list[tuple[GameRow, ScoreBreakdown, RecommendationDebugPayload]],
    intent: ParsedUserIntent,
    archetype: RecommendationArchetype,
) -> tuple[dict[str, LlmBucketJudgmentItem], str | None]:
    settings = get_settings()
    if not settings.openai_api_key or not candidates:
        return {}, "OPENAI_API_KEY not configured or candidate list is empty."

    try:
        model = ChatOpenAI(
            api_key=settings.openai_api_key,
            model="gpt-5.4-mini",
            temperature=0,
        )
        structured_model = model.with_structured_output(LlmBucketJudgmentResponse)
        response = structured_model.invoke(
            [
                (
                    "system",
                    "You classify Steam recommendation candidates into recommendation angles rather than a single ranking. "
                    "Use only these buckets: closest_matches, similar_but_novel, niche_picks, or null to exclude. "
                    "closest_matches means the candidate's main selling point is close same-direction alignment with low structural drift. "
                    "similar_but_novel means it preserves the core target experience but introduces one meaningful fresh angle. "
                    "niche_picks means it is not the obvious answer but has one high-upside reason that makes it worth the gamble. "
                    "Do not force every candidate into a bucket. Exclude candidates that drift too far. "
                    "Return concise reasons and concerns. secondary_traits should be short labels only."
                ),
                (
                    "human",
                    str(
                        {
                            "prompt": intent.free_text_intent,
                            "reference_games": intent.reference_games,
                            "archetype": archetype.model_dump(),
                            "candidates": _build_candidate_payload(candidates, archetype),
                        }
                    ),
                ),
            ]
        )
    except Exception as exc:
        return {}, str(exc)

    judgments: dict[str, LlmBucketJudgmentItem] = {}
    allowed_appids = {game.appid for game, _, _ in candidates}
    for item in response.results:
        if item.appid not in allowed_appids:
            continue
        judgments[item.appid] = item
    if not judgments:
        return {}, "Bucket judgment returned no usable classifications."
    return judgments, None


def judge_bucketed_candidates(
    candidates: list[tuple[GameRow, ScoreBreakdown, RecommendationDebugPayload]],
    intent: ParsedUserIntent,
    archetype: RecommendationArchetype,
) -> tuple[dict[str, BucketDecision], str | None]:
    llm_judgments, judgment_error = _llm_bucket_judgments(candidates, intent, archetype)
    decisions: dict[str, BucketDecision] = {}

    for game, breakdown, debug_payload in candidates:
        profile = infer_game_experience_profile(game)
        heuristic_bucket, novelty_axes, niche_hook = _heuristic_bucket(game, profile, breakdown, archetype)
        llm_item = llm_judgments.get(game.appid)

        bucket = heuristic_bucket
        if llm_item and llm_item.bucket:
            if llm_item.bucket == RecommendationBucketType.CLOSEST_MATCHES and _closest_eligible(profile, breakdown, archetype):
                bucket = llm_item.bucket
            elif llm_item.bucket == RecommendationBucketType.SIMILAR_BUT_NOVEL:
                novel_eligible, computed_novelty_axes = _novel_eligible(profile, breakdown, archetype)
                novelty_axes = computed_novelty_axes
                if novel_eligible:
                    bucket = llm_item.bucket
            elif llm_item.bucket == RecommendationBucketType.NICHE_PICKS:
                niche_eligible, computed_niche_hook = _niche_eligible(game, profile, breakdown, archetype)
                niche_hook = computed_niche_hook
                if niche_eligible:
                    bucket = llm_item.bucket
            elif llm_item.bucket is None:
                bucket = None

        if bucket is None:
            continue

        if llm_item and llm_item.novelty_axis:
            novelty_axes = list(dict.fromkeys([llm_item.novelty_axis, *novelty_axes]))
        if llm_item and llm_item.standout_hook:
            niche_hook = llm_item.standout_hook

        bucket_reason = (
            llm_item.bucket_reason.strip()
            if llm_item and llm_item.bucket_reason.strip()
            else _default_bucket_reason(bucket, game, breakdown, debug_payload, novelty_axes, niche_hook)
        )
        concern = (
            llm_item.concern.strip()
            if llm_item and llm_item.concern.strip()
            else _default_concern(breakdown, debug_payload)
        )
        secondary_traits = (
            llm_item.secondary_traits[:3]
            if llm_item and llm_item.secondary_traits
            else [axis.split(":", 1)[1] for axis in novelty_axes[:2]]
        )
        evidence = _bucket_evidence(bucket, breakdown, novelty_axes, niche_hook)
        if llm_item:
            evidence.bucket_fit_score = clamp(max(evidence.bucket_fit_score, llm_item.bucket_fit_score))
            evidence.novelty_support_score = clamp(
                max(evidence.novelty_support_score, llm_item.novelty_support_score)
            )
            evidence.niche_conviction_score = clamp(
                max(evidence.niche_conviction_score, llm_item.niche_conviction_score)
            )

        final_score = _bucket_sort_score(bucket, breakdown, evidence)
        llm_match_score = clamp(
            max(
                evidence.bucket_fit_score,
                evidence.novelty_support_score,
                evidence.niche_conviction_score,
            )
        )
        decisions[game.appid] = BucketDecision(
            bucket=bucket,
            bucket_reason=bucket_reason,
            concern=concern,
            bucket_evidence=evidence,
            secondary_traits=secondary_traits,
            llm_match_score=llm_match_score,
            final_score=final_score,
        )

    return decisions, judgment_error
