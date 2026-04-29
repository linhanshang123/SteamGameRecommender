from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
ALL_TAGS_PATH = ROOT_DIR / "data" / "all_tags.json"


@lru_cache(maxsize=1)
def load_all_tags() -> set[str]:
    with ALL_TAGS_PATH.open("r", encoding="utf-8") as file:
        tags = json.load(file)

    return {
        str(tag).strip().lower()
        for tag in tags
        if isinstance(tag, str) and str(tag).strip()
    }


def normalize_candidate_tag(tag: str) -> str:
    return tag.strip().lower()


def filter_known_tags(tags: list[str]) -> list[str]:
    known_tags = load_all_tags()
    result: list[str] = []
    for tag in tags:
        normalized = normalize_candidate_tag(tag)
        if normalized in known_tags and normalized not in result:
            result.append(normalized)
    return result
