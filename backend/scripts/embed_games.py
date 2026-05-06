from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys
import time
from typing import Iterator

from supabase import create_client

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.services.recommendation.embedding import create_embedding_client, create_embeddings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and store game embeddings.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--fetch-limit", type=int, default=500)
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to embed in this run.")
    parser.add_argument("--force", action="store_true", help="Regenerate embeddings even when metadata matches.")
    parser.add_argument("--dry-run", action="store_true", help="Show pending rows without calling OpenAI or updating Supabase.")
    return parser.parse_args()


def chunks(rows: list[dict], size: int) -> Iterator[list[dict]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def upsert_embeddings(supabase, payload: list[dict]) -> None:
    for attempt in range(3):
        try:
            supabase.table("games").upsert(
                payload,
                on_conflict="appid",
                ignore_duplicates=False,
            ).execute()
            return
        except Exception:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            if len(payload) <= 1:
                raise
            midpoint = len(payload) // 2
            upsert_embeddings(supabase, payload[:midpoint])
            upsert_embeddings(supabase, payload[midpoint:])
            return


def fetch_pending_rows(supabase, model: str, dimensions: int, fetch_limit: int, force: bool) -> list[dict]:
    query = (
        supabase.table("games")
        .select(
            "appid,name,genres,categories,tags,supported_languages,"
            "embedding_text,embedding_model,embedding_dimensions"
        )
        .not_.is_("embedding_text", "null")
        .limit(fetch_limit)
    )

    if not force:
        query = query.or_(
            ",".join(
                [
                    "embedding_vector.is.null",
                    "embedding_model.is.null",
                    f"embedding_model.neq.{model}",
                    "embedding_dimensions.is.null",
                    f"embedding_dimensions.neq.{dimensions}",
                ]
            )
        )

    response = query.execute()
    rows = response.data or []
    return [row for row in rows if (row.get("embedding_text") or "").strip()]


def main() -> None:
    args = parse_args()
    if args.batch_size <= 0 or args.fetch_limit <= 0:
        raise ValueError("--batch-size and --fetch-limit must be positive.")

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required.")

    supabase = create_client(settings.supabase_url, settings.supabase_key)
    client = create_embedding_client(settings) if not args.dry_run else None
    imported = 0

    while args.limit is None or imported < args.limit:
        remaining = args.limit - imported if args.limit is not None else args.fetch_limit
        fetch_limit = min(args.fetch_limit, remaining)
        pending_rows = fetch_pending_rows(
            supabase,
            settings.openai_embedding_model,
            settings.openai_embedding_dimensions,
            fetch_limit,
            args.force,
        )
        if not pending_rows:
            print("No pending game embeddings.")
            break

        if args.dry_run:
            print(f"Would embed {len(pending_rows)} rows.")
            for row in pending_rows[:10]:
                print(f"{row['appid']} - {row.get('name')}")
            break

        for batch in chunks(pending_rows, args.batch_size):
            texts = [row["embedding_text"] for row in batch]
            embeddings = create_embeddings(texts, settings, client=client)
            if any(len(embedding) != settings.openai_embedding_dimensions for embedding in embeddings):
                raise RuntimeError("OpenAI returned an embedding with an unexpected dimension.")

            updated_at = datetime.now(UTC).isoformat()
            payload = [
                {
                    "appid": row["appid"],
                    "name": row.get("name") or "Unknown title",
                    "genres": row.get("genres") or [],
                    "categories": row.get("categories") or [],
                    "tags": row.get("tags") or [],
                    "supported_languages": row.get("supported_languages") or [],
                    "embedding_vector": embedding,
                    "embedding_model": settings.openai_embedding_model,
                    "embedding_dimensions": settings.openai_embedding_dimensions,
                    "embedding_updated_at": updated_at,
                }
                for row, embedding in zip(batch, embeddings, strict=True)
            ]
            upsert_embeddings(supabase, payload)
            imported += len(batch)
            print(f"Embedded {imported} rows.")

            if args.limit is not None and imported >= args.limit:
                break


if __name__ == "__main__":
    main()
