from __future__ import annotations

import re

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.schemas.recommendation import ExperienceAxes, IntentConstraints, ParsedUserIntent, SoftAvoids
from app.services.recommendation.all_tags import extract_known_tags_from_text, filter_known_tags
from app.services.recommendation.experience import infer_prompt_axes, infer_soft_avoids


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
    experience_axes = infer_prompt_axes(prompt, list(matches), reference_games)
    implicit_soft_avoids = infer_soft_avoids(prompt, experience_axes, list(matches), reference_games)

    return ParsedUserIntent(
        preferred_tags=dedupe_preserve_order([tag for tag in matches if tag not in avoid_tags]),
        avoid_tags=avoid_tags,
        reference_games=reference_games,
        include_reference_games=detect_include_reference_games(prompt, reference_games),
        free_text_intent=prompt.strip(),
        experience_axes=experience_axes,
        implicit_soft_avoids=implicit_soft_avoids,
        must_have=dedupe_preserve_order([*matches]),
        nice_to_have=dedupe_preserve_order([*experience_axes.presentation_style, *experience_axes.combat_feel]),
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
                    "Set include_reference_games=true only when the user explicitly asks to include the same reference game itself. "
                    "Infer experience_axes and implicit_soft_avoids from the user's desired play feel. "
                    "Soft avoids are defaults, not hard bans.",
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
    prompt_axes = infer_prompt_axes(prompt, normalized_preferred_tags, extracted_reference_games)
    merged_axes = ExperienceAxes(
        combat_pace=result.experience_axes.combat_pace or prompt_axes.combat_pace,
        combat_feel=dedupe_preserve_order([*result.experience_axes.combat_feel, *prompt_axes.combat_feel]),
        presentation_style=dedupe_preserve_order(
            [*result.experience_axes.presentation_style, *prompt_axes.presentation_style]
        ),
        loop_shape=dedupe_preserve_order([*result.experience_axes.loop_shape, *prompt_axes.loop_shape]),
        difficulty_tolerance=result.experience_axes.difficulty_tolerance or prompt_axes.difficulty_tolerance,
    )
    inferred_soft_avoids = infer_soft_avoids(
        prompt,
        merged_axes,
        normalized_preferred_tags,
        extracted_reference_games,
    )
    merged_soft_avoids = SoftAvoids(
        strategy_heavy=result.implicit_soft_avoids.strategy_heavy or inferred_soft_avoids.strategy_heavy,
        slow_combat=result.implicit_soft_avoids.slow_combat or inferred_soft_avoids.slow_combat,
        clunky_feel=result.implicit_soft_avoids.clunky_feel or inferred_soft_avoids.clunky_feel,
        shooter_dominant=result.implicit_soft_avoids.shooter_dominant or inferred_soft_avoids.shooter_dominant,
    )

    return ParsedUserIntent(
        preferred_tags=[tag for tag in normalized_preferred_tags if tag not in normalized_avoid_tags],
        avoid_tags=normalized_avoid_tags,
        reference_games=extracted_reference_games,
        include_reference_games=result.include_reference_games
        or detect_include_reference_games(prompt, extracted_reference_games),
        free_text_intent=result.free_text_intent or prompt.strip(),
        experience_axes=merged_axes,
        implicit_soft_avoids=merged_soft_avoids,
        must_have=dedupe_preserve_order([*result.must_have, *normalized_preferred_tags]),
        nice_to_have=dedupe_preserve_order(
            [*result.nice_to_have, *merged_axes.presentation_style, *merged_axes.combat_feel]
        ),
        reference_anchor_profile=result.reference_anchor_profile,
        constraints=result.constraints,
    )
