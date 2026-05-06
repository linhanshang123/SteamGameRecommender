from __future__ import annotations

import json

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.schemas.recommendation import (
    GameRow,
    LlmRerankItem,
    LlmRerankResponse,
    ParsedUserIntent,
    RecommendationDebugPayload,
    ScoreBreakdown,
)


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def game_text_blob(game: GameRow) -> str:
    return game.embedding_text or game.llm_context or ""


def fallback_reason(
    game: GameRow,
    intent: ParsedUserIntent,
    score_breakdown: ScoreBreakdown,
    debug_payload: RecommendationDebugPayload,
) -> tuple[str, str]:
    matched_tags = debug_payload.matched_preferred_tags[:3]
    text_terms = debug_payload.text_matched_terms[:3]

    if matched_tags:
        reason = f"It matches your requested directions through {', '.join(matched_tags)}."
    elif text_terms:
        reason = f"It lines up with your prompt language around {', '.join(text_terms)}."
    else:
        reason = "It remains one of the closest catalog matches after broader candidate filtering."

    concern = ""
    if debug_payload.matched_avoid_tags:
        concern = f"It still brushes against avoided elements such as {', '.join(debug_payload.matched_avoid_tags[:2])}."
    elif score_breakdown.reference_similarity_score < 0.2 and intent.reference_games:
        concern = "It fits the broad request, but its similarity to the reference game is weaker than the top matches."

    return reason, concern


def rerank_candidates(
    candidates: list[tuple[GameRow, ScoreBreakdown, RecommendationDebugPayload]],
    intent: ParsedUserIntent,
    resolved_reference_games: list[GameRow],
) -> tuple[dict[str, LlmRerankItem], str | None]:
    settings = get_settings()
    if not settings.openai_api_key or not candidates:
        return {}, "OPENAI_API_KEY not configured or candidate list is empty."

    candidate_payload = [
        {
            "appid": game.appid,
            "name": game.name,
            "tags": game.tags or [],
            "genres": game.genres or [],
            "llm_context": game_text_blob(game)[:500],
            "deterministic_score": breakdown.deterministic_score,
            "matched_preferred_tags": debug_payload.matched_preferred_tags,
            "text_matched_terms": debug_payload.text_matched_terms,
            "matched_avoid_tags": debug_payload.matched_avoid_tags,
        }
        for game, breakdown, debug_payload in candidates
    ]
    reference_payload = [
        {
            "appid": game.appid,
            "name": game.name,
            "tags": game.tags or [],
            "genres": game.genres or [],
            "llm_context": game_text_blob(game)[:350],
        }
        for game in resolved_reference_games
    ]

    try:
        model = ChatOpenAI(
            api_key=settings.openai_api_key,
            model="gpt-5.4-mini",
            temperature=0,
        )
        response = model.invoke(
            [
                (
                    "system",
                    "You rerank Steam game candidates. You may score only the provided candidates and must not invent or rename any game. "
                    "Return valid JSON only with a top-level object shaped like {\"results\":[...]} and no markdown fences. "
                    "Return each appid exactly as provided in the candidate list, preserving it as the same string ID. "
                    "llm_match_score must be a number from 0.0 to 1.0. "
                    "reason should be one concise sentence about why the game matches. "
                    "concern should be one concise sentence about any mismatch or risk, or an empty string if none.",
                ),
                (
                    "human",
                    str(
                        {
                            "prompt": intent.free_text_intent,
                            "preferred_tags": intent.preferred_tags,
                            "avoid_tags": intent.avoid_tags,
                            "reference_games": intent.reference_games,
                            "resolved_reference_games": reference_payload,
                            "candidates": candidate_payload,
                        }
                    ),
                ),
            ]
        )
        raw_content = response.content if isinstance(response.content, str) else str(response.content)
        normalized_content = raw_content.strip()
        if normalized_content.startswith("```"):
            normalized_content = normalized_content.strip("`")
            normalized_content = normalized_content.removeprefix("json").strip()
        try:
            parsed_payload = json.loads(normalized_content)
        except json.JSONDecodeError as exc:
            return {}, f"Reranker returned invalid JSON: {exc}"

        try:
            response_payload = LlmRerankResponse.model_validate(parsed_payload)
        except Exception as exc:
            return {}, f"Reranker returned an invalid response payload: {exc}"
    except Exception as exc:
        return {}, f"Reranker request failed: {exc}"

    allowed_appids = {game.appid for game, _, _ in candidates}
    reranked: dict[str, LlmRerankItem] = {}
    for item in response_payload.results:
        if item.appid not in allowed_appids:
            continue
        reranked[item.appid] = LlmRerankItem(
            appid=item.appid,
            llm_match_score=clamp(item.llm_match_score),
            reason=item.reason.strip(),
            concern=item.concern.strip(),
        )

    if not reranked:
        return {}, "Reranker returned no usable candidate scores."

    return reranked, None


# TODO: Replace fallback-only reasoning with richer hybrid explanations once embedding retrieval exists.
