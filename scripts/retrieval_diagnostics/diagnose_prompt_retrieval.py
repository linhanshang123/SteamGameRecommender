from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.supabase import get_supabase_client
from app.schemas.recommendation import GameRow
from app.services.recommendation.embedding import create_query_embedding
from app.services.recommendation.intent import parse_user_intent
from app.services.recommendation.retrieve import (
    VECTOR_RETRIEVAL_LIMIT,
    _text_search_clause,
    fetch_candidate_games,
    resolve_reference_games,
)
from app.services.recommendation.scoring import score_game
from app.services.recommendation.tokenize import tokenize
from app.core.config import get_settings


DEFAULT_PROBE_VALUES = [1, 4, 8, 16, 32, 64]


@dataclass
class RouteDiagnostics:
    local_tag_matches: list[str]
    local_genre_matches: list[str]
    local_text_matches: list[str]
    preferred_tags_raw_hit: bool
    preferred_tags_raw_rank: int | None
    genres_raw_hit: bool
    genres_raw_rank: int | None
    free_text_raw_hit: bool
    free_text_raw_rank: int | None
    semantic_raw_hit: bool
    semantic_raw_rank: int | None
    final_candidate_hit: bool
    final_candidate_routes: list[str]
    final_candidate_pretrim_score: float | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose why a target game is or is not being retrieved.")
    parser.add_argument("--prompt", required=True, help="Natural-language recommendation prompt to analyze.")
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--target-appid", help="Target Steam appid to analyze.")
    target_group.add_argument("--target-name", help="Target game name to analyze.")
    parser.add_argument("--ann-limit", type=int, default=VECTOR_RETRIEVAL_LIMIT)
    parser.add_argument("--exact-sample", type=int, default=20)
    parser.add_argument("--probe-sample", type=int, default=500)
    parser.add_argument(
        "--probe-values",
        type=str,
        default="1,4,8,16,32,64",
        help="Comma-separated IVFFlat probe counts for the diagnostic sweep.",
    )
    return parser.parse_args()


def parse_probe_values(raw: str) -> list[int]:
    values: list[int] = []
    for part in raw.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        values.append(max(int(stripped), 1))
    return values or DEFAULT_PROBE_VALUES


def print_section(title: str) -> None:
    print()
    print(f"=== {title} ===")


def format_rank(value: int | None, limit: int | None = None) -> str:
    if value is not None:
        return str(value)
    if limit is not None:
        return f"not in top {limit}"
    return "not found"


def resolve_target_game(supabase, target_appid: str | None, target_name: str | None) -> GameRow:
    if target_appid:
        response = supabase.table("games").select("*").eq("appid", target_appid).limit(1).execute()
        rows = response.data or []
        if not rows:
            raise RuntimeError(f"Target appid not found: {target_appid}")
        return GameRow.model_validate(rows[0])

    assert target_name
    exact_response = (
        supabase.table("games")
        .select("*")
        .eq("name", target_name)
        .order("total_reviews", desc=True)
        .limit(5)
        .execute()
    )
    rows = exact_response.data or []
    if not rows:
        case_insensitive_response = (
            supabase.table("games")
            .select("*")
            .ilike("name", target_name)
            .order("total_reviews", desc=True)
            .limit(5)
            .execute()
        )
        rows = case_insensitive_response.data or []
    if not rows:
        fuzzy_response = (
            supabase.table("games")
            .select("*")
            .ilike("name", f"%{target_name.replace('%', '').replace('_', '')}%")
            .order("total_reviews", desc=True)
            .limit(5)
            .execute()
        )
        rows = fuzzy_response.data or []
    if not rows:
        raise RuntimeError(f"Target game not found by name: {target_name}")
    return GameRow.model_validate(rows[0])


def find_rank(rows: list[dict], target_appid: str) -> int | None:
    return next((index + 1 for index, row in enumerate(rows) if str(row.get("appid")) == target_appid), None)


def fetch_name_map(supabase, appids: Iterable[str]) -> dict[str, str]:
    cleaned = [appid for appid in appids if appid]
    if not cleaned:
        return {}
    response = (
        supabase.table("games")
        .select("appid,name")
        .in_("appid", cleaned)
        .execute()
    )
    return {
        str(row["appid"]): str(row.get("name") or row["appid"])
        for row in (response.data or [])
        if row.get("appid")
    }


def run_production_ann(supabase, query_embedding: list[float], ann_limit: int) -> list[dict]:
    response = supabase.rpc(
        "match_games_by_embedding",
        {
            "query_embedding": query_embedding,
            "match_count": ann_limit,
        },
    ).execute()
    return response.data or []


def run_diagnostic_rank(
    supabase,
    query_embedding: list[float],
    target_appid: str,
    sample_count: int,
    search_mode: str,
    probe_count: int | None = None,
) -> list[dict]:
    params = {
        "query_embedding": query_embedding,
        "target_appid": target_appid,
        "sample_count": sample_count,
        "search_mode": search_mode,
    }
    if probe_count is not None:
        params["probe_count"] = probe_count
    response = supabase.rpc("diagnose_game_embedding_rank", params).execute()
    return response.data or []


def raw_route_hits(supabase, target_appid: str, preferred_tags: list[str], query_text: str) -> tuple[dict[str, int | None], list[str], list[str], list[str]]:
    target_tags_hit_rank: int | None = None
    target_genres_hit_rank: int | None = None
    local_genre_matches: list[str] = []
    query_tokens = tokenize(query_text)[:8]

    if preferred_tags:
        genre_terms = sorted({*preferred_tags, *(tag.title() for tag in preferred_tags)})
        tag_rows = (
            supabase.table("games")
            .select("appid")
            .overlaps("tags", preferred_tags)
            .limit(160)
            .execute()
            .data
            or []
        )
        genre_rows = (
            supabase.table("games")
            .select("appid")
            .overlaps("genres", genre_terms)
            .limit(120)
            .execute()
            .data
            or []
        )
        target_tags_hit_rank = find_rank(tag_rows, target_appid)
        target_genres_hit_rank = find_rank(genre_rows, target_appid)

    target_text_hit_rank: int | None = None
    if query_tokens:
        text_clause = _text_search_clause(query_tokens)
        if text_clause:
            text_rows = (
                supabase.table("games")
                .select("appid")
                .or_(text_clause)
                .limit(140)
                .execute()
                .data
                or []
            )
            target_text_hit_rank = find_rank(text_rows, target_appid)

    return (
        {
            "preferred_tags_raw_rank": target_tags_hit_rank,
            "genres_raw_rank": target_genres_hit_rank,
            "free_text_raw_rank": target_text_hit_rank,
        },
        query_tokens,
        preferred_tags,
        sorted({*preferred_tags, *(tag.title() for tag in preferred_tags)}),
    )


def build_route_diagnostics(supabase, target_game: GameRow, prompt: str, production_ann_rows: list[dict], ann_limit: int) -> RouteDiagnostics:
    intent = parse_user_intent(prompt)
    resolved_reference_games = resolve_reference_games(intent)
    candidate_pool = fetch_candidate_games(intent, resolved_reference_games)
    raw_ranks, query_tokens, _, genre_terms = raw_route_hits(
        supabase,
        target_game.appid,
        intent.preferred_tags,
        intent.free_text_intent,
    )

    target_tags = {tag.lower() for tag in (target_game.tags or [])}
    target_genres = {genre.lower() for genre in (target_game.genres or [])}
    preferred_tags = {tag.lower() for tag in intent.preferred_tags}
    lower_genre_terms = {term.lower() for term in genre_terms}
    game_tokens = set(tokenize(f"{target_game.name} {target_game.embedding_text or target_game.llm_context or ''}"))

    final_routes = candidate_pool.retrieval_routes.get(target_game.appid, [])
    final_candidate_score: float | None = None
    if target_game.appid in candidate_pool.retrieval_routes:
        score, _, _ = score_game(
            target_game,
            intent,
            [],
            candidate_pool.resolved_reference_games,
            final_routes,
        )
        final_candidate_score = score

    return RouteDiagnostics(
        local_tag_matches=sorted(preferred_tags & target_tags),
        local_genre_matches=sorted(lower_genre_terms & target_genres),
        local_text_matches=sorted(set(query_tokens) & game_tokens),
        preferred_tags_raw_hit=raw_ranks["preferred_tags_raw_rank"] is not None,
        preferred_tags_raw_rank=raw_ranks["preferred_tags_raw_rank"],
        genres_raw_hit=raw_ranks["genres_raw_rank"] is not None,
        genres_raw_rank=raw_ranks["genres_raw_rank"],
        free_text_raw_hit=raw_ranks["free_text_raw_rank"] is not None,
        free_text_raw_rank=raw_ranks["free_text_raw_rank"],
        semantic_raw_hit=find_rank(production_ann_rows, target_game.appid) is not None,
        semantic_raw_rank=find_rank(production_ann_rows, target_game.appid),
        final_candidate_hit=target_game.appid in candidate_pool.retrieval_routes,
        final_candidate_routes=final_routes,
        final_candidate_pretrim_score=final_candidate_score,
    )


def classify_miss(
    exact_target_rank: int | None,
    production_ann_rank: int | None,
    probe_ranks: dict[int, int | None],
    route_diagnostics: RouteDiagnostics,
    ann_limit: int,
    probe_sample: int,
) -> str:
    if exact_target_rank is not None and exact_target_rank <= ann_limit and production_ann_rank is None:
        return "vector-relevant but ANN-missed"

    if exact_target_rank is not None and exact_target_rank <= probe_sample and production_ann_rank is None:
        if any(rank is not None for rank in probe_ranks.values()):
            return "vector-relevant but ANN-missed"
        return "mixed / ambiguous"

    if not route_diagnostics.final_candidate_hit and (
        route_diagnostics.local_tag_matches
        or route_diagnostics.local_genre_matches
        or route_diagnostics.local_text_matches
    ):
        return "candidate-route missed before ranking"

    if exact_target_rank is None or exact_target_rank > probe_sample:
        return "embedding/query mismatch"

    if route_diagnostics.final_candidate_hit:
        return "target reached candidate pool"

    return "mixed / ambiguous"


def summarize_rows(rows: list[dict], limit: int = 5) -> list[dict]:
    return [
        {
            "rank": row.get("rank", index + 1),
            "appid": str(row.get("appid")),
            "name": row.get("name"),
            "similarity": round(float(row.get("similarity") or 0.0), 4),
        }
        for index, row in enumerate(rows[:limit])
    ]


def main() -> None:
    args = parse_args()
    probe_values = parse_probe_values(args.probe_values)
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required.")
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")

    supabase = get_supabase_client()
    target_game = resolve_target_game(supabase, args.target_appid, args.target_name)
    query_embedding = create_query_embedding(args.prompt, settings)
    intent = parse_user_intent(args.prompt)

    production_ann_rows = run_production_ann(supabase, query_embedding, args.ann_limit)
    production_name_map = fetch_name_map(supabase, [str(row.get("appid")) for row in production_ann_rows])
    for row in production_ann_rows:
        row["appid"] = str(row["appid"])
        row["name"] = production_name_map.get(row["appid"])
    production_ann_rank = find_rank(production_ann_rows, target_game.appid)
    production_ann_similarity = next(
        (float(row.get("similarity") or 0.0) for row in production_ann_rows if row.get("appid") == target_game.appid),
        None,
    )

    exact_rows = run_diagnostic_rank(
        supabase,
        query_embedding,
        target_game.appid,
        args.exact_sample,
        "exact",
    )
    exact_target_row = next((row for row in exact_rows if row.get("is_target")), None)
    exact_target_rank = int(exact_target_row["rank"]) if exact_target_row else None
    exact_target_similarity = float(exact_target_row["similarity"]) if exact_target_row else None

    probe_results: dict[int, dict[str, int | None | float | list[dict]]] = {}
    for probe_count in probe_values:
        ann_rows = run_diagnostic_rank(
            supabase,
            query_embedding,
            target_game.appid,
            args.probe_sample,
            "ann",
            probe_count=probe_count,
        )
        target_row = next((row for row in ann_rows if row.get("is_target")), None)
        probe_results[probe_count] = {
            "rank": int(target_row["rank"]) if target_row else None,
            "similarity": float(target_row["similarity"]) if target_row else None,
            "sample": summarize_rows(ann_rows),
        }

    route_diagnostics = build_route_diagnostics(
        supabase,
        target_game,
        args.prompt,
        production_ann_rows,
        args.ann_limit,
    )
    conclusion = classify_miss(
        exact_target_rank,
        production_ann_rank,
        {probe: result["rank"] for probe, result in probe_results.items()},
        route_diagnostics,
        args.ann_limit,
        args.probe_sample,
    )

    print_section("Prompt")
    print(args.prompt)

    print_section("Intent")
    print(json.dumps(intent.model_dump(), ensure_ascii=True, indent=2))

    print_section("Target")
    print(
        json.dumps(
            {
                "appid": target_game.appid,
                "name": target_game.name,
                "total_reviews": target_game.total_reviews,
                "rating_ratio": target_game.rating_ratio,
                "genres": target_game.genres,
                "categories": target_game.categories,
                "tags": target_game.tags,
                "has_embedding_text": bool((target_game.embedding_text or "").strip()),
                "has_embedding_vector": exact_target_row is not None,
            },
            ensure_ascii=True,
            indent=2,
        )
    )

    print_section("Production ANN")
    print(
        json.dumps(
            {
                "ann_limit": args.ann_limit,
                "target_rank": format_rank(production_ann_rank, args.ann_limit),
                "target_similarity": round(production_ann_similarity, 4) if production_ann_similarity is not None else None,
                "top_sample": summarize_rows(production_ann_rows),
            },
            ensure_ascii=True,
            indent=2,
        )
    )

    print_section("Exact Rank")
    print(
        json.dumps(
            {
                "target_rank": exact_target_rank,
                "target_similarity": round(exact_target_similarity, 4) if exact_target_similarity is not None else None,
                "top_sample": summarize_rows(exact_rows),
            },
            ensure_ascii=True,
            indent=2,
        )
    )

    print_section("Probe Sweep")
    probe_payload = {
        str(probe_count): {
            "target_rank": format_rank(result["rank"], args.probe_sample),
            "target_similarity": round(result["similarity"], 4) if result["similarity"] is not None else None,
            "top_sample": result["sample"],
        }
        for probe_count, result in probe_results.items()
    }
    print(json.dumps(probe_payload, ensure_ascii=True, indent=2))

    print_section("Route Diagnostics")
    print(
        json.dumps(
            {
                "local_tag_matches": route_diagnostics.local_tag_matches,
                "local_genre_matches": route_diagnostics.local_genre_matches,
                "local_text_matches": route_diagnostics.local_text_matches,
                "preferred_tags_raw_rank": format_rank(route_diagnostics.preferred_tags_raw_rank, 160),
                "genres_raw_rank": format_rank(route_diagnostics.genres_raw_rank, 120),
                "free_text_raw_rank": format_rank(route_diagnostics.free_text_raw_rank, 140),
                "semantic_raw_rank": format_rank(route_diagnostics.semantic_raw_rank, args.ann_limit),
                "final_candidate_hit": route_diagnostics.final_candidate_hit,
                "final_candidate_routes": route_diagnostics.final_candidate_routes,
                "final_candidate_pretrim_score": round(route_diagnostics.final_candidate_pretrim_score, 4)
                if route_diagnostics.final_candidate_pretrim_score is not None
                else None,
            },
            ensure_ascii=True,
            indent=2,
        )
    )

    print_section("Conclusion")
    print(conclusion)


if __name__ == "__main__":
    main()
