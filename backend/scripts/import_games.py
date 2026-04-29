from __future__ import annotations

import json
from pathlib import Path
import sys

from supabase import create_client

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT_DIR / "data" / "games_clean.json"
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings


def normalize_row(row: dict) -> dict:
    return {
        "appid": str(row.get("appid")),
        "name": row.get("name") or "Unknown title",
        "year": row.get("year") if isinstance(row.get("year"), int) else None,
        "price": row.get("price") if isinstance(row.get("price"), (int, float)) else None,
        "required_age": row.get("required_age") if isinstance(row.get("required_age"), int) else None,
        "total_reviews": row.get("total_reviews") if isinstance(row.get("total_reviews"), int) else None,
        "positive": row.get("positive") if isinstance(row.get("positive"), int) else None,
        "negative": row.get("negative") if isinstance(row.get("negative"), int) else None,
        "rating_ratio": row.get("rating_ratio") if isinstance(row.get("rating_ratio"), (int, float)) else None,
        "genres": row.get("genres") if isinstance(row.get("genres"), list) else [],
        "categories": row.get("categories") if isinstance(row.get("categories"), list) else [],
        "tags": [str(tag).lower() for tag in row.get("tags", [])] if isinstance(row.get("tags"), list) else [],
        "supported_languages": row.get("supported_languages") if isinstance(row.get("supported_languages"), list) else [],
        "average_playtime_forever": row.get("average_playtime_forever")
        if isinstance(row.get("average_playtime_forever"), int)
        else None,
        "metacritic_score": row.get("metacritic_score") if isinstance(row.get("metacritic_score"), int) else None,
        "llm_context": row.get("llm_context"),
        "data_source": "games_clean.json",
        "source_updated_at": None,
    }


def main() -> None:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required.")

    supabase = create_client(settings.supabase_url, settings.supabase_key)
    parsed = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise RuntimeError("games_clean.json must contain an array.")

    batch_size = 500
    imported = 0

    for index in range(0, len(parsed), batch_size):
        batch = [normalize_row(row) for row in parsed[index : index + batch_size]]
        supabase.table("games").upsert(
            batch,
            on_conflict="appid",
            ignore_duplicates=False,
        ).execute()
        imported += len(batch)
        print(f"Imported {imported}/{len(parsed)}")


if __name__ == "__main__":
    main()
