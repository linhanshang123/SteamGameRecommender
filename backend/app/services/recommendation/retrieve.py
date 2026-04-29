from __future__ import annotations

from app.core.supabase import get_supabase_client
from app.schemas.recommendation import GameRow, ParsedUserIntent


def unique_games(games: list[GameRow]) -> list[GameRow]:
    return list({game.appid: game for game in games}.values())


def parse_games(payload: list[dict]) -> list[GameRow]:
    return [GameRow.model_validate(item) for item in payload]


def fetch_candidate_games(intent: ParsedUserIntent) -> list[GameRow]:
    supabase = get_supabase_client()
    query_results: list[list[GameRow]] = []

    if intent.preferred_tags:
        tags_response = (
            supabase.table("games")
            .select("*")
            .overlaps("tags", intent.preferred_tags)
            .limit(80)
            .execute()
        )
        query_results.append(parse_games(tags_response.data or []))

        genres_response = (
            supabase.table("games")
            .select("*")
            .overlaps("genres", intent.preferred_tags)
            .limit(60)
            .execute()
        )
        query_results.append(parse_games(genres_response.data or []))

    keywords = [
        token
        for token in "".join(char if char.isalnum() or char in {" ", "-"} else " " for char in intent.free_text_intent.lower()).split()
        if len(token) > 3
    ][:3]

    if keywords:
        escaped = [keyword.replace("%", "").replace("_", "") for keyword in keywords]
        or_clause = ",".join(
            filter(
                None,
                [part for keyword in escaped for part in (f"name.ilike.%{keyword}%", f"llm_context.ilike.%{keyword}%")],
            )
        )
        text_response = (
            supabase.table("games").select("*").or_(or_clause).limit(60).execute()
        )
        query_results.append(parse_games(text_response.data or []))

    if not query_results:
        fallback_response = (
            supabase.table("games")
            .select("*")
            .order("total_reviews", desc=True)
            .limit(120)
            .execute()
        )
        query_results.append(parse_games(fallback_response.data or []))

    candidates = unique_games([game for batch in query_results for game in batch])

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

    if len(candidates) < 30:
        filler_response = (
            supabase.table("games")
            .select("*")
            .order("total_reviews", desc=True)
            .limit(80)
            .execute()
        )
        candidates = unique_games(candidates + parse_games(filler_response.data or []))

    return candidates[:180]
