from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.supabase import get_supabase_client
from app.schemas.recommendation import GameRow, ParsedUserIntent
from app.services.recommendation.tokenize import tokenize


TARGET_MIN_CANDIDATES = 100
TARGET_MAX_CANDIDATES = 300


@dataclass
class CandidatePool:
    candidates: list[GameRow]
    retrieval_routes: dict[str, list[str]] = field(default_factory=dict)
    resolved_reference_games: list[GameRow] = field(default_factory=list)


def parse_games(payload: list[dict]) -> list[GameRow]:
    return [GameRow.model_validate(item) for item in payload]


def _upsert_candidates(
    merged: dict[str, GameRow],
    route_map: dict[str, set[str]],
    games: list[GameRow],
    route_name: str,
) -> None:
    for game in games:
        merged.setdefault(game.appid, game)
        route_map.setdefault(game.appid, set()).add(route_name)


def _pretrim_score(game: GameRow, routes: set[str]) -> float:
    route_weight = sum(
        {
            "preferred_tags": 1.6,
            "genres": 1.0,
            "free_text": 1.1,
            "reference_expansion": 1.4,
            "fallback_popular": 0.3,
        }.get(route, 0.0)
        for route in routes
    )
    review_signal = math.log10((game.total_reviews or 0) + 1)
    rating_signal = game.rating_ratio or 0
    return route_weight + 0.25 * review_signal + 0.1 * rating_signal


def _apply_constraints(games: list[GameRow], intent: ParsedUserIntent) -> list[GameRow]:
    candidates = games
    constraints = intent.constraints
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


def _text_search_clause(tokens: list[str]) -> str:
    escaped = [token.replace("%", "").replace("_", "") for token in tokens if token]
    parts = [
        part
        for token in escaped
        for part in (f"name.ilike.%{token}%", f"llm_context.ilike.%{token}%")
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


def fetch_candidate_games(intent: ParsedUserIntent, resolved_reference_games: list[GameRow]) -> CandidatePool:
    supabase = get_supabase_client()
    merged: dict[str, GameRow] = {}
    route_map: dict[str, set[str]] = {}

    if intent.preferred_tags:
        genre_terms = sorted({*intent.preferred_tags, *(tag.title() for tag in intent.preferred_tags)})
        tags_response = (
            supabase.table("games")
            .select("*")
            .overlaps("tags", intent.preferred_tags)
            .limit(160)
            .execute()
        )
        _upsert_candidates(
            merged,
            route_map,
            parse_games(tags_response.data or []),
            "preferred_tags",
        )

        genres_response = (
            supabase.table("games")
            .select("*")
            .overlaps("genres", genre_terms)
            .limit(120)
            .execute()
        )
        _upsert_candidates(
            merged,
            route_map,
            parse_games(genres_response.data or []),
            "genres",
        )

    query_tokens = tokenize(intent.free_text_intent)[:8]
    if query_tokens:
        text_clause = _text_search_clause(query_tokens)
        if text_clause:
            text_response = (
                supabase.table("games")
                .select("*")
                .or_(text_clause)
                .limit(140)
                .execute()
            )
            _upsert_candidates(
                merged,
                route_map,
                parse_games(text_response.data or []),
                "free_text",
            )

    if resolved_reference_games:
        reference_tags = sorted(
            {
                value
                for game in resolved_reference_games
                for value in [*(game.tags or []), *(game.genres or [])]
            }
        )
        reference_genres = sorted(
            {
                value
                for game in resolved_reference_games
                for value in (game.genres or [])
            }
        )
        reference_context_tokens = sorted(
            {
                token
                for game in resolved_reference_games
                for token in tokenize(game.llm_context or "")
            }
        )[:8]

        if reference_tags:
            reference_tag_response = (
                supabase.table("games")
                .select("*")
                .overlaps("tags", reference_tags)
                .limit(160)
                .execute()
            )
            _upsert_candidates(
                merged,
                route_map,
                parse_games(reference_tag_response.data or []),
                "reference_expansion",
            )

        if reference_genres:
            reference_genre_response = (
                supabase.table("games")
                .select("*")
                .overlaps("genres", reference_genres)
                .limit(120)
                .execute()
            )
            _upsert_candidates(
                merged,
                route_map,
                parse_games(reference_genre_response.data or []),
                "reference_expansion",
            )

        if reference_context_tokens:
            reference_text_clause = _text_search_clause(reference_context_tokens)
            if reference_text_clause:
                reference_text_response = (
                    supabase.table("games")
                    .select("*")
                    .or_(reference_text_clause)
                    .limit(120)
                    .execute()
                )
                _upsert_candidates(
                    merged,
                    route_map,
                    parse_games(reference_text_response.data or []),
                    "reference_expansion",
                )

    excluded_appids = {game.appid for game in resolved_reference_games}
    candidates = [
        game
        for appid, game in merged.items()
        if intent.include_reference_games or appid not in excluded_appids
    ]
    candidates = _apply_constraints(candidates, intent)

    if len(candidates) < TARGET_MIN_CANDIDATES:
        fallback_response = (
            supabase.table("games")
            .select("*")
            .order("total_reviews", desc=True)
            .limit(180)
            .execute()
        )
        fallback_games = [
            game
            for game in parse_games(fallback_response.data or [])
            if intent.include_reference_games or game.appid not in excluded_appids
        ]
        fallback_games = _apply_constraints(fallback_games, intent)
        _upsert_candidates(merged, route_map, fallback_games, "fallback_popular")
        candidates = [
            game
            for appid, game in merged.items()
            if intent.include_reference_games or appid not in excluded_appids
        ]
        candidates = _apply_constraints(candidates, intent)

    if len(candidates) > TARGET_MAX_CANDIDATES:
        candidates.sort(
            key=lambda game: _pretrim_score(game, route_map.get(game.appid, set())),
            reverse=True,
        )
        candidates = candidates[:TARGET_MAX_CANDIDATES]

    route_payload = {
        game.appid: sorted(route_map.get(game.appid, set()))
        for game in candidates
    }

    # TODO: Add embedding-based hybrid retrieval here once pgvector is introduced.
    return CandidatePool(
        candidates=candidates,
        retrieval_routes=route_payload,
        resolved_reference_games=resolved_reference_games,
    )
