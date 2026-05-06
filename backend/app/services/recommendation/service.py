from __future__ import annotations

from app.core.supabase import get_supabase_client
from app.schemas.recommendation import (
    GameRow,
    HistoryEntry,
    IntentConstraints,
    ParsedUserIntent,
    RankedRecommendation,
    RecommendationDebugPayload,
    RecommendationResponse,
    RecommendationSessionResponse,
    ScoreBreakdown,
    SessionPayload,
)
from app.services.recommendation.intent import parse_user_intent
from app.services.recommendation.reason import fallback_reason, rerank_candidates
from app.services.recommendation.retrieve import fetch_candidate_games, resolve_reference_games
from app.services.recommendation.scoring import score_game
from app.services.steam import fetch_owned_appids_for_user


def _rows_to_sessions(rows: list[dict]) -> list[SessionPayload]:
    return [SessionPayload.model_validate(row) for row in rows]


def _normalize_score_breakdown(raw: dict | None, score: float) -> ScoreBreakdown:
    payload = raw or {}
    return ScoreBreakdown.model_validate(
        {
            "tag_match_score": payload.get("tag_match_score", 0.0),
            "text_match_score": payload.get("text_match_score", 0.0),
            "reference_similarity_score": payload.get("reference_similarity_score", 0.0),
            "rating_confidence_score": payload.get("rating_confidence_score", 0.0),
            "popularity_reliability_score": payload.get("popularity_reliability_score", 0.0),
            "preference_history_score": payload.get("preference_history_score"),
            "avoid_penalty": payload.get("avoid_penalty", 0.0),
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
            "rerank_applied": (raw or {}).get("rerank_applied", False),
            "rerank_error": (raw or {}).get("rerank_error"),
        }
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


def _merge_constraints(
    parsed: IntentConstraints | None,
    override: IntentConstraints | None,
) -> IntentConstraints | None:
    if parsed is None and override is None:
        return None

    merged = IntentConstraints(
        price_max=override.price_max if override and override.price_max is not None else parsed.price_max if parsed else None,
        year_min=override.year_min if override and override.year_min is not None else parsed.year_min if parsed else None,
        single_player=override.single_player if override and override.single_player is not None else parsed.single_player if parsed else None,
        multiplayer=override.multiplayer if override and override.multiplayer is not None else parsed.multiplayer if parsed else None,
        min_total_reviews=override.min_total_reviews if override and override.min_total_reviews is not None else parsed.min_total_reviews if parsed else None,
    )
    return merged if any(value is not None for value in merged.model_dump().values()) else None


def create_recommendation_session(
    prompt: str,
    user_id: str,
    request_constraints: IntentConstraints | None = None,
) -> RecommendationResponse:
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise ValueError("Prompt is required.")
    if len(normalized_prompt) > 800:
        raise ValueError("Prompt must be shorter than 800 characters.")

    intent = parse_user_intent(normalized_prompt)
    intent.constraints = _merge_constraints(intent.constraints, request_constraints)
    history = fetch_user_history(user_id)
    resolved_reference_games = resolve_reference_games(intent)
    owned_appids = fetch_owned_appids_for_user(user_id)
    candidate_pool = fetch_candidate_games(
        intent,
        resolved_reference_games,
        blocked_appids=owned_appids,
        ownership_filtered_user_id=user_id if owned_appids else None,
    )

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
    vector_candidates = sorted(
        scored_candidates,
        key=lambda entry: candidate_pool.retrieval_scores.get(entry[0].appid, 0.0),
        reverse=True,
    )[:20]
    rerank_candidates_by_appid = {
        game.appid: (game, breakdown, debug_payload)
        for game, breakdown, debug_payload in [*scored_candidates[:20], *vector_candidates]
    }
    rerank_window = sorted(
        rerank_candidates_by_appid.values(),
        key=lambda entry: (
            entry[1].deterministic_score
            + 0.15 * candidate_pool.retrieval_scores.get(entry[0].appid, 0.0)
        ),
        reverse=True,
    )[:20]
    rerank_map, rerank_error = rerank_candidates(
        rerank_window,
        intent,
        candidate_pool.resolved_reference_games,
    )

    recommendations: list[RankedRecommendation] = []
    final_candidates: list[tuple[GameRow, ScoreBreakdown, RecommendationDebugPayload, str, str, float]] = []

    for game, breakdown, debug_payload in rerank_window:
        rerank_item = rerank_map.get(game.appid)
        llm_match_score = rerank_item.llm_match_score if rerank_item else 0.0
        breakdown.llm_match_score = llm_match_score
        combined_score = 0.50 * breakdown.deterministic_score + 0.50 * llm_match_score
        debug_payload.rerank_applied = rerank_error is None
        debug_payload.rerank_error = rerank_error

        if rerank_item and rerank_item.reason:
            reason = rerank_item.reason
            concern = rerank_item.concern
        else:
            reason, concern = fallback_reason(game, intent, breakdown, debug_payload)

        final_candidates.append(
            (game, breakdown, debug_payload, reason, concern, combined_score)
        )

    final_candidates.sort(
        key=lambda entry: (entry[5], entry[1].deterministic_score),
        reverse=True,
    )

    for index, (game, breakdown, debug_payload, reason, concern, combined_score) in enumerate(
        final_candidates[:5],
        start=1,
    ):
        recommendations.append(
            RankedRecommendation(
                appid=game.appid,
                name=game.name,
                price=game.price,
                year=game.year,
                totalReviews=game.total_reviews,
                tags=game.tags or [],
                genres=game.genres or [],
                ratingRatio=game.rating_ratio or 0,
                finalScore=combined_score,
                scoreBreakdown=breakdown,
                reason=reason,
                concern=concern,
                debugPayload=debug_payload,
                deterministicScore=breakdown.deterministic_score,
                llmMatchScore=breakdown.llm_match_score,
                rank=index,
            )
        )

    supabase = get_supabase_client()
    session_response = (
        supabase.table("recommendation_sessions")
        .insert(
            {
                "user_id": user_id,
                "prompt": normalized_prompt,
                "normalized_preferences": intent.model_dump(),
            }
        )
        .execute()
    )
    session_rows = session_response.data or []
    if not session_rows:
        raise RuntimeError("Failed to create recommendation session.")

    session = SessionPayload.model_validate(session_rows[0])

    supabase.table("recommendation_results").insert(
        [
            {
                "session_id": session.id,
                "game_appid": recommendation.appid,
                "rank": recommendation.rank,
                "reason": recommendation.reason,
                "concern": recommendation.concern,
                "score": recommendation.finalScore,
                "deterministic_score": recommendation.deterministicScore,
                "llm_match_score": recommendation.llmMatchScore,
                "score_breakdown": recommendation.scoreBreakdown.model_dump(),
                "debug_payload": recommendation.debugPayload.model_dump(),
            }
            for recommendation in recommendations
        ]
    ).execute()

    return RecommendationResponse(
        sessionId=session.id,
        intent=intent,
        recommendations=recommendations,
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

    recommendations = []
    for result in result_rows:
        game = games_map.get(result["game_appid"])
        if not game:
            continue
        score_breakdown = _normalize_score_breakdown(result.get("score_breakdown"), result["score"])
        debug_payload = _normalize_debug_payload(result.get("debug_payload"))
        recommendations.append(
            RankedRecommendation(
                appid=game.appid,
                name=game.name,
                price=game.price,
                year=game.year,
                totalReviews=game.total_reviews,
                tags=game.tags or [],
                genres=game.genres or [],
                ratingRatio=game.rating_ratio or 0,
                finalScore=result["score"],
                scoreBreakdown=score_breakdown,
                reason=result["reason"],
                concern=result.get("concern") or "",
                debugPayload=debug_payload,
                deterministicScore=result.get("deterministic_score") or score_breakdown.deterministic_score,
                llmMatchScore=result.get("llm_match_score") or score_breakdown.llm_match_score,
                rank=result["rank"],
            )
        )

    return RecommendationSessionResponse(session=session, recommendations=recommendations)


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
