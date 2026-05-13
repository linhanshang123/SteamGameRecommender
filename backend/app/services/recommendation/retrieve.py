from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from app.schemas.recommendation import GameRow, ParsedUserIntent
from app.services.recommendation.embedding import create_query_embedding
from app.services.recommendation.faiss_index import get_faiss_semantic_index


VECTOR_RETRIEVAL_LIMIT = 300


@dataclass
class CandidatePool:
    candidates: list[GameRow]
    retrieval_routes: dict[str, list[str]] = field(default_factory=dict)
    retrieval_scores: dict[str, float] = field(default_factory=dict)
    resolved_reference_games: list[GameRow] = field(default_factory=list)


def parse_games(payload: list[dict]) -> list[GameRow]:
    return [GameRow.model_validate(item) for item in payload]


def game_text_blob(game: GameRow) -> str:
    return game.embedding_text or game.llm_context or ""


def _apply_constraints(games: list[GameRow], intent: ParsedUserIntent) -> list[GameRow]:
    candidates = games
    constraints = intent.constraints
    if constraints and constraints.min_total_reviews is not None:
        candidates = [
            game
            for game in candidates
            if (game.total_reviews or 0) >= constraints.min_total_reviews
        ]

    if constraints and constraints.price_max is not None:
        candidates = [
            game for game in candidates if game.price is None or game.price <= constraints.price_max
        ]

    if constraints and constraints.year_min is not None:
        candidates = [
            game for game in candidates if game.year is None or game.year >= constraints.year_min
        ]

    if constraints and constraints.single_player:
        candidates = [
            game
            for game in candidates
            if any("single-player" in category.lower() for category in (game.categories or []))
        ]

    if constraints and constraints.multiplayer:
        candidates = [
            game
            for game in candidates
            if any(
                marker in category.lower()
                for category in (game.categories or [])
                for marker in ("multi-player", "co-op")
            )
        ]

    return candidates


def _apply_route_filters(query, intent: ParsedUserIntent):
    constraints = intent.constraints
    if constraints and constraints.min_total_reviews is not None:
        query = query.gte("total_reviews", constraints.min_total_reviews)
    return query


def _text_search_clause(tokens: list[str]) -> str:
    escaped = [token.replace("%", "").replace("_", "") for token in tokens if token]
    parts = [
        part
        for token in escaped
        for part in (
            f"name.ilike.%{token}%",
            f"llm_context.ilike.%{token}%",
            f"embedding_text.ilike.%{token}%",
        )
    ]
    return ",".join(parts)


def resolve_reference_games(intent: ParsedUserIntent) -> list[GameRow]:
    if not intent.reference_games:
        return []

    supabase = get_supabase_client()
    resolved: list[GameRow] = []
    used_appids: set[str] = set()

    for reference_name in intent.reference_games:
        exact_response = (
            supabase.table("games")
            .select("*")
            .eq("name", reference_name)
            .limit(1)
            .execute()
        )
        rows = exact_response.data or []
        if not rows:
            fuzzy_response = (
                supabase.table("games")
                .select("*")
                .ilike("name", reference_name)
                .limit(1)
                .execute()
            )
            rows = fuzzy_response.data or []

        if not rows:
            fuzzy_contains_response = (
                supabase.table("games")
                .select("*")
                .ilike("name", f"%{reference_name.replace('%', '').replace('_', '')}%")
                .limit(1)
                .execute()
            )
            rows = fuzzy_contains_response.data or []

        if not rows:
            continue

        game = GameRow.model_validate(rows[0])
        if game.appid in used_appids:
            continue
        used_appids.add(game.appid)
        resolved.append(game)

    return resolved


def fetch_embedding_candidates(
    supabase,
    intent: ParsedUserIntent,
    ownership_filtered_user_id: str | None = None,
) -> tuple[list[GameRow], dict[str, float]]:
    query_text = intent.free_text_intent.strip()
    if not query_text:
        return [], {}

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for semantic retrieval.")

    query_embedding = create_query_embedding(query_text, settings)
    matches = get_faiss_semantic_index().search(query_embedding, VECTOR_RETRIEVAL_LIMIT)
    appids = [hit.appid for hit in matches if hit.appid]
    if not appids:
        return [], {}

    similarity_scores = {
        hit.appid: float(hit.similarity)
        for hit in matches
        if hit.appid
    }

    games_query = (
        supabase.table("games")
        .select("*")
        .in_("appid", appids)
    )
    games_response = _apply_route_filters(games_query, intent).execute()
    games_by_appid = {
        game.appid: game
        for game in parse_games(games_response.data or [])
    }
    ordered_games = [games_by_appid[appid] for appid in appids if appid in games_by_appid]
    return ordered_games, similarity_scores


def fetch_candidate_games(
    intent: ParsedUserIntent,
    resolved_reference_games: list[GameRow],
    blocked_appids: set[str] | None = None,
    ownership_filtered_user_id: str | None = None,
) -> CandidatePool:
    blocked = blocked_appids or set()
    supabase = get_supabase_client()
    embedding_games, embedding_scores = fetch_embedding_candidates(
        supabase,
        intent,
        ownership_filtered_user_id=ownership_filtered_user_id,
    )

    excluded_appids = {game.appid for game in resolved_reference_games}
    candidates = []
    route_payload: dict[str, list[str]] = {}
    retrieval_scores: dict[str, float] = {}

    for game in embedding_games:
        if game.appid in blocked:
            continue
        if not intent.include_reference_games and game.appid in excluded_appids:
            continue
        candidates.append(game)
        route_payload[game.appid] = ["semantic_embedding"]
        similarity = embedding_scores.get(game.appid, 0.0)
        if similarity > 0:
            retrieval_scores[game.appid] = similarity

    candidates = _apply_constraints(candidates, intent)
    route_payload = {
        game.appid: route_payload.get(game.appid, ["semantic_embedding"])
        for game in candidates
    }
    retrieval_scores = {
        game.appid: retrieval_scores.get(game.appid, 0.0)
        for game in candidates
        if retrieval_scores.get(game.appid, 0.0) > 0
    }

    return CandidatePool(
        candidates=candidates,
        retrieval_routes=route_payload,
        retrieval_scores=retrieval_scores,
        resolved_reference_games=resolved_reference_games,
    )
