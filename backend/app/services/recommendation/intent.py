from __future__ import annotations

import re

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.schemas.recommendation import IntentConstraints, ParsedUserIntent
from app.services.recommendation.all_tags import filter_known_tags


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

    matches.update(filter_known_tags([lower_prompt]))

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
        preferred_tags=[tag for tag in matches if tag not in avoid_tags],
        avoid_tags=avoid_tags,
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
    structured_model = model.with_structured_output(ParsedUserIntent)
    result = structured_model.invoke(
        [
            (
                "system",
                "You extract Steam search intent. Only include tags that are exact Steam tags. Put non-tag nuance in free_text_intent.",
            ),
            ("human", prompt),
        ]
    )

    return ParsedUserIntent(
        preferred_tags=filter_known_tags(result.preferred_tags),
        avoid_tags=filter_known_tags(result.avoid_tags),
        free_text_intent=result.free_text_intent or prompt.strip(),
        constraints=result.constraints,
    )
