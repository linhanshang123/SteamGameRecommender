from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.schemas.recommendation import GameRow, ParsedUserIntent, ScoreBreakdown


def fallback_reason(
    game: GameRow,
    intent: ParsedUserIntent,
    score_breakdown: ScoreBreakdown,
) -> str:
    matched_tags = [
        tag for tag in (game.tags or []) if tag.lower() in intent.preferred_tags
    ][:3]

    tag_phrase = (
        f"It lines up with {', '.join(matched_tags)}."
        if matched_tags
        else "It broadly fits the vibe described in your prompt."
    )
    review_phrase = (
        " It also has a stronger review base than most niche candidates."
        if (game.total_reviews or 0) > 500
        else " It stays in the mix because its text match is stronger than average."
    )
    guard_phrase = (
        " There is some tension with one avoided direction, so it ranked lower than a cleaner match would."
        if score_breakdown.avoid_penalty > 0.1
        else ""
    )
    return f"{tag_phrase}{review_phrase}{guard_phrase}"


def build_reason(
    game: GameRow,
    intent: ParsedUserIntent,
    score_breakdown: ScoreBreakdown,
) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        return fallback_reason(game, intent, score_breakdown)

    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        model="gpt-5.4-mini",
        temperature=0.3,
    )
    response = model.invoke(
        [
            (
                "system",
                "Write one concise recommendation reason for a Steam game. Mention fit, not chain-of-thought. Keep it under 28 words.",
            ),
            (
                "human",
                str(
                    {
                        "prompt": intent.free_text_intent,
                        "preferred_tags": intent.preferred_tags,
                        "avoid_tags": intent.avoid_tags,
                        "game": {
                            "name": game.name,
                            "tags": game.tags or [],
                            "genres": game.genres or [],
                            "description": game.llm_context or "",
                        },
                        "scoreBreakdown": score_breakdown.model_dump(),
                    }
                ),
            ),
        ]
    )
    return response.content if isinstance(response.content, str) else str(response.content)
