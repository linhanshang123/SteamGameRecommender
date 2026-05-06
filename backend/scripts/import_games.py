from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
import re
import sys
import time
from typing import Iterable, Iterator

from supabase import create_client

ROOT_DIR = Path(__file__).resolve().parents[2]
CSV_DATA_PATH = (
    ROOT_DIR / "data" / "games_recommender_candidates_minreview5_minowner10_desc3500_merged_normalized.csv"
)
LEGACY_CSV_DATA_PATH = ROOT_DIR / "data" / "games_recommender_candidates_desc3500.csv"
JSON_DATA_PATH = ROOT_DIR / "data" / "games_clean.json"
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings

TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
STEAM_STORE_URL_RE = re.compile(r"https?://store\.steampowered\.com/\S+", re.IGNORECASE)
SOCIAL_URL_RE = re.compile(
    r"https?://(?:discord\.gg|discord\.com|x\.com|twitter\.com|facebook\.com|youtube\.com|t\.me|instagram\.com)/\S+",
    re.IGNORECASE,
)
SOCIAL_PHRASE_RE = re.compile(
    r"(?:wishlist now!?|join our discord!?|follow us on twitter!?)(?=\s|$)",
    re.IGNORECASE,
)
LONG_SYMBOL_RE = re.compile(r"([!?.\-*_=~#])\1{4,}")
MULTI_NL_RE = re.compile(r"\n{3,}")
MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
BROKEN_CHAR_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff\ufffd]")


def parse_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def parse_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def parse_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = [part.strip() for part in value.split("|")]
        return [part for part in parts if part]
    return []


def clean_text(text: str | None) -> str:
    if not text:
        return ""

    cleaned = html.unescape(text)
    cleaned = cleaned.replace("\u00a0", " ").replace("\u2800", " ")
    cleaned = BROKEN_CHAR_RE.sub("", cleaned)
    cleaned = TAG_RE.sub(" ", cleaned)
    cleaned = SOCIAL_URL_RE.sub(" ", cleaned)
    cleaned = STEAM_STORE_URL_RE.sub(" ", cleaned)
    cleaned = URL_RE.sub(" ", cleaned)
    cleaned = SOCIAL_PHRASE_RE.sub(" ", cleaned)
    cleaned = LONG_SYMBOL_RE.sub(lambda match: match.group(1) * 3, cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = MULTI_NL_RE.sub("\n\n", cleaned)
    cleaned = MULTI_SPACE_RE.sub(" ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    return cleaned.strip()


def build_structured_text(
    name: str,
    genres: list[str],
    tags: list[str],
    categories: list[str],
    description: str,
) -> str:
    parts: list[str] = [f"Title: {name}"]
    if genres:
        parts.append(f"Genres: {'|'.join(genres)}")
    if tags:
        parts.append(f"Tags: {'|'.join(tags)}")
    if categories:
        parts.append(f"Categories: {'|'.join(categories)}")
    if description:
        parts.append(f"Description: {description}")
    return "\n".join(parts)


def normalize_csv_row(row: dict[str, str], data_source: str) -> dict:
    name = (row.get("name") or "").strip() or "Unknown title"
    genres = parse_list(row.get("genres"))
    categories = parse_list(row.get("categories"))
    tags = [tag.lower() for tag in parse_list(row.get("tags"))]
    supported_languages = [language.lower() for language in parse_list(row.get("supported_languages"))]
    about_clean = clean_text(row.get("about_clean"))
    embedding_text = clean_text(row.get("text_for_embedding")) or build_structured_text(
        name,
        genres,
        tags,
        categories,
        about_clean,
    )

    rating_ratio = parse_float(row.get("positive_ratio"))
    if rating_ratio is None:
        positive = parse_int(row.get("positive")) or 0
        negative = parse_int(row.get("negative")) or 0
        total = positive + negative
        rating_ratio = positive / total if total > 0 else None

    year = parse_int(row.get("release_year"))
    if year is None:
        release_date = (row.get("release_date") or "").strip()
        year = parse_int(release_date[:4]) if len(release_date) >= 4 else None

    return {
        "appid": str(row.get("appid") or "").strip(),
        "name": name,
        "year": year,
        "price": parse_float(row.get("price")),
        "required_age": parse_int(row.get("required_age")),
        "total_reviews": parse_int(row.get("total_reviews")),
        "positive": parse_int(row.get("positive")),
        "negative": parse_int(row.get("negative")),
        "rating_ratio": rating_ratio,
        "genres": genres,
        "categories": categories,
        "tags": tags,
        "supported_languages": supported_languages,
        "average_playtime_forever": parse_int(row.get("average_playtime_forever")),
        "metacritic_score": parse_int(row.get("metacritic_score")),
        "llm_context": embedding_text,
        "embedding_text": embedding_text,
        "data_source": data_source,
        "source_updated_at": None,
    }


def normalize_json_row(row: dict, data_source: str) -> dict:
    name = row.get("name") or "Unknown title"
    genres = parse_list(row.get("genres"))
    categories = parse_list(row.get("categories"))
    tags = [str(tag).lower() for tag in row.get("tags", [])] if isinstance(row.get("tags"), list) else []
    description = clean_text(row.get("llm_context"))
    embedding_text = build_structured_text(name, genres, tags, categories, description)

    return {
        "appid": str(row.get("appid")),
        "name": name,
        "year": row.get("year") if isinstance(row.get("year"), int) else None,
        "price": row.get("price") if isinstance(row.get("price"), (int, float)) else None,
        "required_age": row.get("required_age") if isinstance(row.get("required_age"), int) else None,
        "total_reviews": row.get("total_reviews") if isinstance(row.get("total_reviews"), int) else None,
        "positive": row.get("positive") if isinstance(row.get("positive"), int) else None,
        "negative": row.get("negative") if isinstance(row.get("negative"), int) else None,
        "rating_ratio": row.get("rating_ratio") if isinstance(row.get("rating_ratio"), (int, float)) else None,
        "genres": genres,
        "categories": categories,
        "tags": tags,
        "supported_languages": parse_list(row.get("supported_languages")),
        "average_playtime_forever": row.get("average_playtime_forever")
        if isinstance(row.get("average_playtime_forever"), int)
        else None,
        "metacritic_score": row.get("metacritic_score") if isinstance(row.get("metacritic_score"), int) else None,
        "llm_context": embedding_text,
        "embedding_text": embedding_text,
        "data_source": data_source,
        "source_updated_at": None,
    }


def select_data_path() -> Path:
    if CSV_DATA_PATH.exists():
        return CSV_DATA_PATH
    if LEGACY_CSV_DATA_PATH.exists():
        return LEGACY_CSV_DATA_PATH
    if JSON_DATA_PATH.exists():
        return JSON_DATA_PATH
    raise RuntimeError("No supported data source found in the data directory.")


def iter_normalized_rows(data_path: Path) -> Iterator[dict]:
    if data_path.suffix.lower() == ".csv":
        with data_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                yield normalize_csv_row(row, data_path.name)
        return

    parsed = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise RuntimeError(f"{data_path.name} must contain an array.")
    for row in parsed:
        if not isinstance(row, dict):
            continue
        yield normalize_json_row(row, data_path.name)


def batched(rows: Iterable[dict], batch_size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for row in rows:
        batch.append(row)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import normalized game rows into Supabase.")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--skip", type=int, default=0, help="Number of normalized rows to skip before importing.")
    parser.add_argument(
        "--input-path",
        type=str,
        default=None,
        help="Optional path to a specific CSV or JSON file. Relative paths are resolved from the repo root.",
    )
    parser.add_argument(
        "--only-missing-embedding-text",
        action="store_true",
        help="Only import rows whose appid is missing in the database or whose existing row has no embedding_text.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show how many rows would be imported or skipped without writing to Supabase.",
    )
    return parser.parse_args()


def upsert_batch(supabase, batch: list[dict]) -> None:
    for attempt in range(3):
        try:
            supabase.table("games").upsert(
                batch,
                on_conflict="appid",
                ignore_duplicates=False,
            ).execute()
            return
        except Exception:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            if len(batch) <= 1:
                raise
            midpoint = len(batch) // 2
            upsert_batch(supabase, batch[:midpoint])
            upsert_batch(supabase, batch[midpoint:])
            return


def resolve_data_path(input_path: str | None) -> Path:
    if input_path:
        candidate = Path(input_path)
        if not candidate.is_absolute():
            candidate = ROOT_DIR / candidate
        if not candidate.exists():
            raise RuntimeError(f"Input file not found: {candidate}")
        return candidate
    return select_data_path()


def fetch_existing_rows(supabase, appids: list[str]) -> dict[str, dict]:
    if not appids:
        return {}
    response = (
        supabase.table("games")
        .select("appid,embedding_text")
        .in_("appid", appids)
        .execute()
    )
    return {
        row["appid"]: row
        for row in (response.data or [])
        if row.get("appid")
    }


def main() -> None:
    args = parse_args()
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive.")
    if args.skip < 0:
        raise ValueError("--skip cannot be negative.")

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required.")

    supabase = create_client(settings.supabase_url, settings.supabase_key)
    data_path = resolve_data_path(args.input_path)

    imported = 0
    skipped_existing = 0
    examined = 0

    rows = iter_normalized_rows(data_path)
    if args.skip:
        for _ in range(args.skip):
            next(rows, None)

    for batch in batched(rows, args.batch_size):
        examined += len(batch)
        rows_to_import = batch

        if args.only_missing_embedding_text:
            existing_rows = fetch_existing_rows(
                supabase,
                [row["appid"] for row in batch if row.get("appid")],
            )
            filtered_rows: list[dict] = []
            for row in batch:
                existing = existing_rows.get(row["appid"])
                if existing and (existing.get("embedding_text") or "").strip():
                    skipped_existing += 1
                    continue
                filtered_rows.append(row)
            rows_to_import = filtered_rows

        if not args.dry_run and rows_to_import:
            upsert_batch(supabase, rows_to_import)

        imported += len(rows_to_import)
        action = "Would import" if args.dry_run else "Imported"
        print(
            f"{action} {imported} rows from {data_path.name} "
            f"(examined {args.skip + examined}, skipped_existing {skipped_existing})"
        )


if __name__ == "__main__":
    main()
