from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
ALL_TAGS_PATH = ROOT_DIR / "data" / "all_tags.json"

TAG_ALIAS_MAP: dict[str, list[str]] = {
    "fast paced": ["fast-paced"],
    "fastpaced": ["fast-paced"],
    "fast pace": ["fast-paced"],
    "action rogue like": ["action roguelike"],
    "action rogue-lite": ["action roguelike"],
    "action roguelite": ["action roguelike"],
    "action rogue lite": ["action roguelike"],
    "rogue like": ["action roguelike"],
    "rogue-lite": ["action roguelike"],
    "roguelite": ["action roguelike"],
    "rougelike": ["action roguelike"],
    "roguelike": ["action roguelike"],
    "rogue lite": ["action roguelike"],
    "paced action": ["fast-paced"],
}


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
    normalized = tag.strip().lower().replace("_", " ").replace("/", " ")
    normalized = normalized.replace("-", " - ")
    normalized = " ".join(normalized.split())
    return normalized.replace(" - ", "-")


def filter_known_tags(tags: list[str]) -> list[str]:
    known_tags = load_all_tags()
    result: list[str] = []
    for tag in tags:
        normalized = normalize_candidate_tag(tag)
        candidates = [normalized, *(TAG_ALIAS_MAP.get(normalized, []))]
        for candidate in candidates:
            if candidate in known_tags and candidate not in result:
                result.append(candidate)
    return result


def extract_known_tags_from_text(text: str) -> list[str]:
    normalized_text = normalize_candidate_tag(text)
    phrase_candidates = {normalized_text}
    words = normalized_text.split()

    for size in (1, 2, 3, 4):
        for index in range(len(words) - size + 1):
            phrase_candidates.add(" ".join(words[index : index + size]))

    return filter_known_tags(list(phrase_candidates))
