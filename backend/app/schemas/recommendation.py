from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class IntentConstraints(BaseModel):
    price_max: int | None = None
    year_min: int | None = None
    single_player: bool | None = None
    multiplayer: bool | None = None


class ParsedUserIntent(BaseModel):
    preferred_tags: list[str] = Field(default_factory=list)
    avoid_tags: list[str] = Field(default_factory=list)
    reference_games: list[str] = Field(default_factory=list)
    include_reference_games: bool = False
    free_text_intent: str = ""
    constraints: IntentConstraints | None = None


class ScoreBreakdown(BaseModel):
    tag_match_score: float
    text_match_score: float
    reference_similarity_score: float
    rating_confidence_score: float
    popularity_reliability_score: float
    preference_history_score: float | None = None
    avoid_penalty: float
    deterministic_score: float
    llm_match_score: float


class RecommendationDebugPayload(BaseModel):
    matched_preferred_tags: list[str] = Field(default_factory=list)
    matched_avoid_tags: list[str] = Field(default_factory=list)
    text_matched_terms: list[str] = Field(default_factory=list)
    resolved_reference_appids: list[str] = Field(default_factory=list)
    retrieval_routes: list[str] = Field(default_factory=list)
    rerank_applied: bool = False
    rerank_error: str | None = None


class LlmRerankItem(BaseModel):
    appid: str
    llm_match_score: float = 0.0
    reason: str = ""
    concern: str = ""

    @field_validator("appid", mode="before")
    @classmethod
    def normalize_appid(cls, value: object) -> str:
        if isinstance(value, bool):
            raise ValueError("appid must be a string or integer.")
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("appid cannot be blank.")
            return normalized
        raise ValueError("appid must be a string or integer.")


class LlmRerankResponse(BaseModel):
    results: list[LlmRerankItem] = Field(default_factory=list)


class RankedRecommendation(BaseModel):
    appid: str
    name: str
    price: float | None = None
    year: int | None = None
    tags: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    ratingRatio: float = 0
    finalScore: float
    scoreBreakdown: ScoreBreakdown
    reason: str
    concern: str = ""
    debugPayload: RecommendationDebugPayload = Field(default_factory=RecommendationDebugPayload)
    deterministicScore: float
    llmMatchScore: float
    rank: int


class RecommendationRequest(BaseModel):
    prompt: str


class RecommendationResponse(BaseModel):
    sessionId: str
    intent: ParsedUserIntent
    recommendations: list[RankedRecommendation]


class SessionPayload(BaseModel):
    id: str
    user_id: str
    prompt: str
    normalized_preferences: ParsedUserIntent
    created_at: str


class RecommendationSessionResponse(BaseModel):
    session: SessionPayload
    recommendations: list[RankedRecommendation]


class HistoryEntry(SessionPayload):
    previewTitles: list[str] = Field(default_factory=list)


class GameRow(BaseModel):
    appid: str
    name: str
    year: int | None = None
    price: float | None = None
    required_age: int | None = None
    total_reviews: int | None = None
    positive: int | None = None
    negative: int | None = None
    rating_ratio: float | None = None
    genres: list[str] | None = None
    categories: list[str] | None = None
    tags: list[str] | None = None
    supported_languages: list[str] | None = None
    average_playtime_forever: int | None = None
    metacritic_score: int | None = None
    llm_context: str | None = None
    embedding_text: str | None = None
    data_source: str | None = None
    source_updated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
