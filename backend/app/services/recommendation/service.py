from __future__ import annotations

from app.core.supabase import get_supabase_client
from app.schemas.recommendation import (
    BucketEvidence,
    GameRow,
    HistoryEntry,
    RankedRecommendation,
    RecommendationArchetype,
    RecommendationBucketType,
    RecommendationBuckets,
    RecommendationDebugPayload,
    RecommendationResponse,
    RecommendationSessionResponse,
    ScoreBreakdown,
    SessionPayload,
)
from app.services.recommendation.experience import build_recommendation_archetype, enrich_intent
from app.services.recommendation.intent import parse_user_intent
from app.services.recommendation.judgment import judge_bucketed_candidates
from app.services.recommendation.retrieve import fetch_candidate_games, resolve_reference_games
from app.services.recommendation.scoring import score_game


BUCKET_LIMITS = {
    RecommendationBucketType.CLOSEST_MATCHES: 2,
    RecommendationBucketType.SIMILAR_BUT_NOVEL: 2,
    RecommendationBucketType.NICHE_PICKS: 1,
}

BUCKET_ORDER = [
    RecommendationBucketType.CLOSEST_MATCHES,
    RecommendationBucketType.SIMILAR_BUT_NOVEL,
    RecommendationBucketType.NICHE_PICKS,
]


def _rows_to_sessions(rows: list[dict]) -> list[SessionPayload]:
    return [SessionPayload.model_validate(row) for row in rows]


def _normalize_score_breakdown(raw: dict | None, score: float) -> ScoreBreakdown:
    payload = raw or {}
    return ScoreBreakdown.model_validate(
        {
            "tag_match_score": payload.get("tag_match_score", 0.0),
            "text_match_score": payload.get("text_match_score", 0.0),
            "reference_similarity_score": payload.get("reference_similarity_score", 0.0),
            "combat_pace_match_score": payload.get("combat_pace_match_score", 0.0),
            "combat_feel_match_score": payload.get("combat_feel_match_score", 0.0),
            "presentation_match_score": payload.get("presentation_match_score", 0.0),
            "loop_shape_match_score": payload.get("loop_shape_match_score", 0.0),
            "rating_confidence_score": payload.get("rating_confidence_score", 0.0),
            "popularity_reliability_score": payload.get("popularity_reliability_score", 0.0),
            "preference_history_score": payload.get("preference_history_score"),
            "avoid_penalty": payload.get("avoid_penalty", 0.0),
            "strategy_heavy_penalty": payload.get("strategy_heavy_penalty", 0.0),
            "slow_combat_penalty": payload.get("slow_combat_penalty", 0.0),
            "clunky_feel_penalty": payload.get("clunky_feel_penalty", 0.0),
            "shooter_dominant_penalty": payload.get("shooter_dominant_penalty", 0.0),
            "soft_avoid_penalty_score": payload.get("soft_avoid_penalty_score", 0.0),
            "deterministic_score": payload.get("deterministic_score", score),
            "llm_match_score": payload.get("llm_match_score", 0.0),
        }
    )


def _normalize_debug_payload(raw: dict | None) -> RecommendationDebugPayload:
    return RecommendationDebugPayload.model_validate(
        {
            "matched_preferred_tags": (raw or {}).get("matched_preferred_tags", []),
            "matched_avoid_tags": (raw or {}).get("matched_avoid_tags", []),
            "text_matched_terms": (raw or {}).get("text_matched_terms", []),
            "resolved_reference_appids": (raw or {}).get("resolved_reference_appids", []),
            "retrieval_routes": (raw or {}).get("retrieval_routes", []),
            "experience_axes": (raw or {}).get("experience_axes", {}),
            "implicit_soft_avoids": (raw or {}).get("implicit_soft_avoids", {}),
            "reference_anchor_profile": (raw or {}).get("reference_anchor_profile"),
            "rerank_dimension_scores": (raw or {}).get("rerank_dimension_scores", {}),
            "rerank_applied": (raw or {}).get("rerank_applied", False),
            "rerank_error": (raw or {}).get("rerank_error"),
        }
    )


def _normalize_bucket_evidence(raw: dict | None) -> BucketEvidence:
    payload = raw or {}
    return BucketEvidence.model_validate(
        {
            "bucket_fit_score": payload.get("bucket_fit_score", 0.0),
            "novelty_support_score": payload.get("novelty_support_score", 0.0),
            "niche_conviction_score": payload.get("niche_conviction_score", 0.0),
        }
    )


def _group_recommendations(recommendations: list[RankedRecommendation]) -> RecommendationBuckets:
    return RecommendationBuckets(
        closest_matches=[
            recommendation
            for recommendation in recommendations
            if recommendation.bucket == RecommendationBucketType.CLOSEST_MATCHES
        ],
        similar_but_novel=[
            recommendation
            for recommendation in recommendations
            if recommendation.bucket == RecommendationBucketType.SIMILAR_BUT_NOVEL
        ],
        niche_picks=[
            recommendation
            for recommendation in recommendations
            if recommendation.bucket == RecommendationBucketType.NICHE_PICKS
        ],
    )


def fetch_user_history(user_id: str) -> list[SessionPayload]:
    supabase = get_supabase_client()
    response = (
        supabase.table("recommendation_sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(12)
        .execute()
    )
    return _rows_to_sessions(response.data or [])


def create_recommendation_session(prompt: str, user_id: str) -> RecommendationResponse:
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise ValueError("Prompt is required.")
    if len(normalized_prompt) > 800:
        raise ValueError("Prompt must be shorter than 800 characters.")

    intent = parse_user_intent(normalized_prompt)
    history = fetch_user_history(user_id)
    resolved_reference_games = resolve_reference_games(intent)
    intent = enrich_intent(intent, resolved_reference_games)
    archetype = build_recommendation_archetype(intent)
    candidate_pool = fetch_candidate_games(intent, resolved_reference_games)

    scored_candidates: list[tuple[GameRow, ScoreBreakdown, RecommendationDebugPayload]] = []
    for game in candidate_pool.candidates:
        deterministic_score, breakdown, debug_payload = score_game(
            game,
            intent,
            history,
            candidate_pool.resolved_reference_games,
            candidate_pool.retrieval_routes.get(game.appid, []),
        )
        breakdown.deterministic_score = deterministic_score
        scored_candidates.append((game, breakdown, debug_payload))

    scored_candidates.sort(key=lambda entry: entry[1].deterministic_score, reverse=True)
    judgment_window = scored_candidates[:24]
    judgment_map, judgment_error = judge_bucketed_candidates(
        judgment_window,
        intent,
        archetype,
    )

    bucket_candidates: dict[RecommendationBucketType, list[tuple[GameRow, ScoreBreakdown, RecommendationDebugPayload]]] = {
        bucket: [] for bucket in BUCKET_ORDER
    }
    candidate_lookup = {game.appid: (game, breakdown, debug_payload) for game, breakdown, debug_payload in judgment_window}

    for appid, decision in judgment_map.items():
        candidate = candidate_lookup.get(appid)
        if not candidate:
            continue
        game, breakdown, debug_payload = candidate
        breakdown.llm_match_score = decision.llm_match_score
        debug_payload.rerank_applied = judgment_error is None
        debug_payload.rerank_error = judgment_error
        bucket_candidates[decision.bucket].append((game, breakdown, debug_payload))

    ranked_recommendations: list[RankedRecommendation] = []
    global_rank = 1
    for bucket in BUCKET_ORDER:
        ordered = sorted(
            bucket_candidates[bucket],
            key=lambda entry: (
                judgment_map[entry[0].appid].final_score,
                entry[1].deterministic_score,
            ),
            reverse=True,
        )[: BUCKET_LIMITS[bucket]]
        for bucket_rank, (game, breakdown, debug_payload) in enumerate(ordered, start=1):
            decision = judgment_map[game.appid]
            ranked_recommendations.append(
                RankedRecommendation(
                    appid=game.appid,
                    name=game.name,
                    price=game.price,
                    year=game.year,
                    tags=game.tags or [],
                    genres=game.genres or [],
                    ratingRatio=game.rating_ratio or 0,
                    finalScore=decision.final_score,
                    scoreBreakdown=breakdown,
                    reason=decision.bucket_reason,
                    concern=decision.concern,
                    debugPayload=debug_payload,
                    deterministicScore=breakdown.deterministic_score,
                    llmMatchScore=breakdown.llm_match_score,
                    rank=global_rank,
                    bucket=bucket,
                    bucketRank=bucket_rank,
                    bucketReason=decision.bucket_reason,
                    bucketEvidence=decision.bucket_evidence,
                    secondaryTraits=decision.secondary_traits,
                )
            )
            global_rank += 1

    buckets = _group_recommendations(ranked_recommendations)

    supabase = get_supabase_client()
    session_response = (
        supabase.table("recommendation_sessions")
        .insert(
            {
                "user_id": user_id,
                "prompt": normalized_prompt,
                "normalized_preferences": intent.model_dump(),
                "archetype": archetype.model_dump(),
            }
        )
        .execute()
    )
    session_rows = session_response.data or []
    if not session_rows:
        raise RuntimeError("Failed to create recommendation session.")

    session = SessionPayload.model_validate(session_rows[0])

    if ranked_recommendations:
        supabase.table("recommendation_results").insert(
            [
                {
                    "session_id": session.id,
                    "game_appid": recommendation.appid,
                    "rank": recommendation.rank,
                    "bucket": recommendation.bucket.value,
                    "bucket_rank": recommendation.bucketRank,
                    "bucket_reason": recommendation.bucketReason,
                    "bucket_evidence": recommendation.bucketEvidence.model_dump(),
                    "secondary_traits": recommendation.secondaryTraits,
                    "reason": recommendation.reason,
                    "concern": recommendation.concern,
                    "score": recommendation.finalScore,
                    "deterministic_score": recommendation.deterministicScore,
                    "llm_match_score": recommendation.llmMatchScore,
                    "score_breakdown": recommendation.scoreBreakdown.model_dump(),
                    "debug_payload": recommendation.debugPayload.model_dump(),
                }
                for recommendation in ranked_recommendations
            ]
        ).execute()

    return RecommendationResponse(
        sessionId=session.id,
        intent=intent,
        archetype=archetype,
        buckets=buckets,
        recommendations=ranked_recommendations,
    )


def get_recommendation_session(session_id: str, user_id: str) -> RecommendationSessionResponse:
    supabase = get_supabase_client()
    session_response = (
        supabase.table("recommendation_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    session_rows = session_response.data or []
    if not session_rows:
        raise LookupError("Recommendation session not found.")

    session = SessionPayload.model_validate(session_rows[0])

    result_response = (
        supabase.table("recommendation_results")
        .select("*")
        .eq("session_id", session_id)
        .order("rank")
        .execute()
    )
    result_rows = result_response.data or []

    app_ids = [row["game_appid"] for row in result_rows]
    games_map: dict[str, GameRow] = {}
    if app_ids:
        games_response = (
            supabase.table("games")
            .select("*")
            .in_("appid", app_ids)
            .execute()
        )
        games_map = {
            row["appid"]: GameRow.model_validate(row)
            for row in (games_response.data or [])
        }

    recommendations: list[RankedRecommendation] = []
    for result in result_rows:
        game = games_map.get(result["game_appid"])
        if not game:
            continue
        score_breakdown = _normalize_score_breakdown(result.get("score_breakdown"), result["score"])
        debug_payload = _normalize_debug_payload(result.get("debug_payload"))
        bucket_value = result.get("bucket") or RecommendationBucketType.CLOSEST_MATCHES.value
        recommendations.append(
            RankedRecommendation(
                appid=game.appid,
                name=game.name,
                price=game.price,
                year=game.year,
                tags=game.tags or [],
                genres=game.genres or [],
                ratingRatio=game.rating_ratio or 0,
                finalScore=result["score"],
                scoreBreakdown=score_breakdown,
                reason=result.get("reason") or result.get("bucket_reason") or "",
                concern=result.get("concern") or "",
                debugPayload=debug_payload,
                deterministicScore=result.get("deterministic_score") or score_breakdown.deterministic_score,
                llmMatchScore=result.get("llm_match_score") or score_breakdown.llm_match_score,
                rank=result["rank"],
                bucket=RecommendationBucketType(bucket_value),
                bucketRank=result.get("bucket_rank") or result["rank"],
                bucketReason=result.get("bucket_reason") or result.get("reason") or "",
                bucketEvidence=_normalize_bucket_evidence(result.get("bucket_evidence")),
                secondaryTraits=result.get("secondary_traits") or [],
            )
        )

    archetype = session.archetype or build_recommendation_archetype(session.normalized_preferences)
    buckets = _group_recommendations(recommendations)
    return RecommendationSessionResponse(
        session=session,
        archetype=archetype,
        buckets=buckets,
        recommendations=recommendations,
    )


def get_recommendation_history(user_id: str) -> list[HistoryEntry]:
    supabase = get_supabase_client()
    session_response = (
        supabase.table("recommendation_sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    sessions = _rows_to_sessions(session_response.data or [])
    session_ids = [session.id for session in sessions]
    result_rows: list[dict] = []

    if session_ids:
        results_response = (
            supabase.table("recommendation_results")
            .select("*")
            .in_("session_id", session_ids)
            .order("rank")
            .execute()
        )
        result_rows = results_response.data or []

    app_ids = list({row["game_appid"] for row in result_rows})
    game_map: dict[str, str] = {}
    if app_ids:
        games_response = (
            supabase.table("games")
            .select("appid,name")
            .in_("appid", app_ids)
            .execute()
        )
        game_map = {row["appid"]: row["name"] for row in (games_response.data or [])}

    grouped_results: dict[str, list[str]] = {}
    for result in result_rows:
        existing = grouped_results.setdefault(result["session_id"], [])
        if len(existing) < 3:
            existing.append(game_map.get(result["game_appid"], result["game_appid"]))

    return [
        HistoryEntry(
            **session.model_dump(),
            previewTitles=grouped_results.get(session.id, []),
        )
        for session in sessions
    ]
