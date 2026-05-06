from __future__ import annotations

import argparse
import csv
from collections import OrderedDict
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parents[1]

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from import_games import build_structured_text, clean_text, parse_list


DEFAULT_INPUT_GLOB = "data/games_recommender_candidates_minreview5_minowner10_desc3500_part_*.csv"
DEFAULT_OUTPUT_PATH = "data/games_recommender_candidates_minreview5_minowner10_desc3500_merged_normalized.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge and normalize candidate CSV parts.")
    parser.add_argument("--input-glob", type=str, default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--output-path", type=str, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def resolve_paths(input_glob: str, output_path: str) -> tuple[list[Path], Path]:
    pattern = ROOT_DIR / input_glob
    input_paths = sorted(pattern.parent.glob(pattern.name))
    if not input_paths:
        raise RuntimeError(f"No CSV files matched: {pattern}")

    output = Path(output_path)
    if not output.is_absolute():
        output = ROOT_DIR / output
    return input_paths, output


def normalize_row(row: dict[str, str], data_source: str) -> dict[str, str]:
    name = (row.get("name") or "").strip() or "Unknown title"
    genres = parse_list(row.get("genres"))
    categories = parse_list(row.get("categories"))
    tags = [tag.lower() for tag in parse_list(row.get("tags"))]
    supported_languages = [language.lower() for language in parse_list(row.get("supported_languages"))]
    about_clean = clean_text(row.get("about_clean"))
    text_for_embedding = build_structured_text(name, genres, tags, categories, about_clean)

    normalized = dict(row)
    normalized["appid"] = (row.get("appid") or "").strip()
    normalized["name"] = name
    normalized["genres"] = "|".join(genres)
    normalized["categories"] = "|".join(categories)
    normalized["tags"] = "|".join(tags)
    normalized["supported_languages"] = "|".join(supported_languages)
    normalized["about_clean"] = about_clean
    normalized["text_for_embedding"] = text_for_embedding
    normalized["data_source"] = data_source
    return normalized


def main() -> None:
    args = parse_args()
    input_paths, output_path = resolve_paths(args.input_glob, args.output_path)

    deduped_rows: OrderedDict[str, dict[str, str]] = OrderedDict()
    fieldnames: list[str] | None = None
    duplicate_appids = 0
    total_rows = 0

    for input_path in input_paths:
        with input_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if fieldnames is None:
                fieldnames = list(reader.fieldnames or [])
                if "data_source" not in fieldnames:
                    fieldnames.append("data_source")

            for row in reader:
                total_rows += 1
                appid = (row.get("appid") or "").strip()
                if not appid:
                    continue
                if appid in deduped_rows:
                    duplicate_appids += 1
                deduped_rows[appid] = normalize_row(row, input_path.name)

    if fieldnames is None:
        raise RuntimeError("No CSV headers found in input files.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temp_output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in deduped_rows.values():
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    temp_output_path.replace(output_path)

    print(
        {
            "input_files": [path.name for path in input_paths],
            "total_rows_read": total_rows,
            "unique_appids_written": len(deduped_rows),
            "duplicate_appids_overwritten": duplicate_appids,
            "output_path": str(output_path),
        }
    )


if __name__ == "__main__":
    main()
