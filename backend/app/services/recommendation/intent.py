from __future__ import annotations

import re

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.schemas.recommendation import IntentConstraints, ParsedUserIntent
from app.services.recommendation.all_tags import extract_known_tags_from_text, filter_known_tags


REFERENCE_PREFIX_PATTERN = re.compile(
    r"(?:games?\s+like|similar\s+to|like)\s+([^\n,.!?]+)",
    re.I,
)
EXPLICIT_INCLUDE_PATTERN = re.compile(
    r"(?:include|recommend|return|show)\s+.+?(?:itself|same game|too)|(?:include|recommend|return|show)\s+the\s+same\s+game",
    re.I,
)
GENERIC_REFERENCE_TITLES = {"game", "games", "something", "title", "titles"}


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped


def sanitize_reference_games(values: list[str]) -> list[str]:
    sanitized: list[str] = []
    for value in values:
        cleaned = value.strip(" .,:;!?\"'")
        if not cleaned or cleaned.casefold() in GENERIC_REFERENCE_TITLES:
            continue
        sanitized.append(cleaned)
    return dedupe_preserve_order(sanitized)


def extract_reference_games(prompt: str) -> list[str]:
    matches: list[str] = []

    for raw_match in REFERENCE_PREFIX_PATTERN.findall(prompt):
        cleaned = raw_match.strip(" .,:;!?\"'")
        for stop_marker in (" but ", " with ", " that ", " which ", " except "):
            marker_index = cleaned.lower().find(stop_marker)
            if marker_index != -1:
                cleaned = cleaned[:marker_index]
                break

        split_titles = re.split(r",|/|\bor\b|\band\b", cleaned, flags=re.I)
        for title in split_titles:
            candidate = title.strip(" .,:;!?\"'")
            if len(candidate) >= 2:
                matches.append(candidate)

    return sanitize_reference_games(matches)


def detect_include_reference_games(prompt: str, reference_games: list[str]) -> bool:
    if not reference_games:
        return False

    if EXPLICIT_INCLUDE_PATTERN.search(prompt):
        return True

    lowered = prompt.lower()
    return any(
        phrase in lowered
        for phrase in (
            "recommend the same game",
            "include the same game",
            "recommend it too",
            "include it too",
        )
    )


def extract_numbers(prompt: str) -> dict[str, int | None]:
    price_match = re.search(r"\$?(\d{1,3})(?:\s*(?:dollars|usd|bucks|under|max))", prompt, re.I)
    year_match = re.search(r"(?:after|since|newer than)\s+(20\d{2}|19\d{2})", prompt, re.I)
    return {
        "price_max": int(price_match.group(1)) if price_match else None,
        "year_min": int(year_match.group(1)) if year_match else None,
    }


def heuristic_intent(prompt: str) -> ParsedUserIntent:
    lower_prompt = prompt.lower()
    matches: set[str] = set()
    reference_games = extract_reference_games(prompt)

    matches.update(filter_known_tags([lower_prompt]))
    matches.update(extract_known_tags_from_text(prompt))

    phrases: list[str] = []
    for segment in re.split(r"[,.!?]", lower_prompt):
        segment = segment.strip()
        if not segment:
            continue
        phrases.append(segment)
        words = segment.split()
        for index, word in enumerate(words):
            two = " ".join(words[index : index + 2]).strip()
            three = " ".join(words[index : index + 3]).strip()
            if two:
                phrases.append(two)
            if three:
                phrases.append(three)

    for candidate in phrases:
        filtered = filter_known_tags([candidate])
        if filtered:
            matches.add(filtered[0])

    avoid_parts = re.split(r"but not|avoid|no |don't want|not ", lower_prompt, flags=re.I)
    avoid_tags = (
        filter_known_tags(avoid_parts[1].split()) if len(avoid_parts) > 1 and avoid_parts[1] else []
    )

    constraints = IntentConstraints(
        **extract_numbers(prompt),
        single_player=True if re.search(r"single[\s-]?player", prompt, re.I) else None,
        multiplayer=True if re.search(r"multiplayer|co-op|coop|friends", prompt, re.I) else None,
    )

    return ParsedUserIntent(
        preferred_tags=dedupe_preserve_order([tag for tag in matches if tag not in avoid_tags]),
        avoid_tags=avoid_tags,
        reference_games=reference_games,
        include_reference_games=detect_include_reference_games(prompt, reference_games),
        free_text_intent=prompt.strip(),
        constraints=constraints,
    )


def parse_user_intent(prompt: str) -> ParsedUserIntent:
    settings = get_settings()
    if not settings.openai_api_key:
        return heuristic_intent(prompt)

    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        model="gpt-5.4-mini",
        temperature=0,
    )
    try:
        structured_model = model.with_structured_output(ParsedUserIntent)
        result = structured_model.invoke(
            [
                (
                    "system",
                    "You extract Steam search intent. Only include tags that are exact Steam tags. Put non-tag nuance in free_text_intent. "
                    "If the user references example games like 'like Hades' or 'similar to Gnosia', add those exact titles to reference_games. "
                    "Set include_reference_games=true only when the user explicitly asks to include the same reference game itself.",
                ),
                ("human", prompt),
            ]
        )
    except Exception:
        return heuristic_intent(prompt)

    extracted_reference_games = sanitize_reference_games(
        [*(result.reference_games or []), *extract_reference_games(prompt)]
    )
    normalized_preferred_tags = dedupe_preserve_order(
        [
            *filter_known_tags(result.preferred_tags),
            *extract_known_tags_from_text(prompt),
            *extract_known_tags_from_text(result.free_text_intent or prompt),
        ]
    )
    normalized_avoid_tags = dedupe_preserve_order(
        [
            *filter_known_tags(result.avoid_tags),
            *extract_known_tags_from_text(" ".join(result.avoid_tags or [])),
        ]
    )

    return ParsedUserIntent(
        preferred_tags=[tag for tag in normalized_preferred_tags if tag not in normalized_avoid_tags],
        avoid_tags=normalized_avoid_tags,
        reference_games=extracted_reference_games,
        include_reference_games=result.include_reference_games
        or detect_include_reference_games(prompt, extracted_reference_games),
        free_text_intent=result.free_text_intent or prompt.strip(),
        constraints=result.constraints,
    )
