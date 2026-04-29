from __future__ import annotations

from app.core.supabase import get_supabase_client
from app.schemas.recommendation import (
    GameRow,
    HistoryEntry,
    ParsedUserIntent,
    RankedRecommendation,
    RecommendationResponse,
    RecommendationSessionResponse,
    SessionPayload,
)
from app.services.recommendation.intent import parse_user_intent
from app.services.recommendation.reason import build_reason
from app.services.recommendation.retrieve import fetch_candidate_games
from app.services.recommendation.scoring import score_game


def _rows_to_sessions(rows: list[dict]) -> list[SessionPayload]:
    return [SessionPayload.model_validate(row) for row in rows]


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
    candidates = fetch_candidate_games(intent)

    scored_candidates = []
    for game in candidates:
        final_score, breakdown = score_game(game, intent, history)
        scored_candidates.append((game, final_score, breakdown))

    scored_candidates.sort(key=lambda entry: entry[1], reverse=True)
    top_candidates = scored_candidates[:5]

    recommendations: list[RankedRecommendation] = []
    for index, (game, final_score, breakdown) in enumerate(top_candidates, start=1):
        recommendations.append(
            RankedRecommendation(
                appid=game.appid,
                name=game.name,
                price=game.price,
                year=game.year,
                tags=game.tags or [],
                genres=game.genres or [],
                ratingRatio=game.rating_ratio or 0,
                finalScore=final_score,
                scoreBreakdown=breakdown,
                reason=build_reason(game, intent, breakdown),
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
                "score": recommendation.finalScore,
                "score_breakdown": recommendation.scoreBreakdown.model_dump(),
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
                scoreBreakdown=result["score_breakdown"],
                reason=result["reason"],
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
