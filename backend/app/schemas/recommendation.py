from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IntentConstraints(BaseModel):
    price_max: int | None = None
    year_min: int | None = None
    single_player: bool | None = None
    multiplayer: bool | None = None


class ExperienceAxes(BaseModel):
    combat_pace: str | None = None
    combat_feel: list[str] = Field(default_factory=list)
    presentation_style: list[str] = Field(default_factory=list)
    loop_shape: list[str] = Field(default_factory=list)
    difficulty_tolerance: str | None = None


class SoftAvoids(BaseModel):
    strategy_heavy: bool = False
    slow_combat: bool = False
    clunky_feel: bool = False
    shooter_dominant: bool = False


class ReferenceAnchorProfile(BaseModel):
    anchor_names: list[str] = Field(default_factory=list)
    derived_tags: list[str] = Field(default_factory=list)
    combat_pace: str | None = None
    combat_feel: list[str] = Field(default_factory=list)
    presentation_style: list[str] = Field(default_factory=list)
    loop_shape: list[str] = Field(default_factory=list)
    summary: str = ""


class RecommendationBucketType(str, Enum):
    CLOSEST_MATCHES = "closest_matches"
    SIMILAR_BUT_NOVEL = "similar_but_novel"
    NICHE_PICKS = "niche_picks"


class RecommendationArchetype(BaseModel):
    summary: str = ""
    core_experience: list[str] = Field(default_factory=list)
    required_alignment: list[str] = Field(default_factory=list)
    allowed_novelty_axes: list[str] = Field(default_factory=list)
    hard_drifts_to_avoid: list[str] = Field(default_factory=list)


class ParsedUserIntent(BaseModel):
    preferred_tags: list[str] = Field(default_factory=list)
    avoid_tags: list[str] = Field(default_factory=list)
    reference_games: list[str] = Field(default_factory=list)
    include_reference_games: bool = False
    free_text_intent: str = ""
    experience_axes: ExperienceAxes = Field(default_factory=ExperienceAxes)
    implicit_soft_avoids: SoftAvoids = Field(default_factory=SoftAvoids)
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    reference_anchor_profile: ReferenceAnchorProfile | None = None
    constraints: IntentConstraints | None = None


class ScoreBreakdown(BaseModel):
    tag_match_score: float
    text_match_score: float
    reference_similarity_score: float
    combat_pace_match_score: float
    combat_feel_match_score: float
    presentation_match_score: float
    loop_shape_match_score: float
    rating_confidence_score: float
    popularity_reliability_score: float
    preference_history_score: float | None = None
    avoid_penalty: float
    strategy_heavy_penalty: float
    slow_combat_penalty: float
    clunky_feel_penalty: float
    shooter_dominant_penalty: float
    soft_avoid_penalty_score: float
    deterministic_score: float
    llm_match_score: float


class RerankDimensionScores(BaseModel):
    reference_match_score: float = 0.0
    combat_pace_score: float = 0.0
    combat_feel_score: float = 0.0
    presentation_score: float = 0.0
    loop_shape_score: float = 0.0
    soft_avoid_penalty_score: float = 0.0


class RecommendationDebugPayload(BaseModel):
    matched_preferred_tags: list[str] = Field(default_factory=list)
    matched_avoid_tags: list[str] = Field(default_factory=list)
    text_matched_terms: list[str] = Field(default_factory=list)
    resolved_reference_appids: list[str] = Field(default_factory=list)
    retrieval_routes: list[str] = Field(default_factory=list)
    experience_axes: ExperienceAxes = Field(default_factory=ExperienceAxes)
    implicit_soft_avoids: SoftAvoids = Field(default_factory=SoftAvoids)
    reference_anchor_profile: ReferenceAnchorProfile | None = None
    rerank_dimension_scores: RerankDimensionScores = Field(default_factory=RerankDimensionScores)
    rerank_applied: bool = False
    rerank_error: str | None = None


class LlmRerankItem(BaseModel):
    appid: str
    reference_match_score: float = 0.0
    combat_pace_score: float = 0.0
    combat_feel_score: float = 0.0
    presentation_score: float = 0.0
    loop_shape_score: float = 0.0
    soft_avoid_penalty_score: float = 0.0
    llm_match_score: float = 0.0
    reason: str = ""
    concern: str = ""


class LlmRerankResponse(BaseModel):
    results: list[LlmRerankItem] = Field(default_factory=list)


class BucketEvidence(BaseModel):
    bucket_fit_score: float = 0.0
    novelty_support_score: float = 0.0
    niche_conviction_score: float = 0.0


class LlmBucketJudgmentItem(BaseModel):
    appid: str
    bucket: RecommendationBucketType | None = None
    bucket_reason: str = ""
    concern: str = ""
    novelty_axis: str | None = None
    standout_hook: str | None = None
    secondary_traits: list[str] = Field(default_factory=list)
    bucket_fit_score: float = 0.0
    novelty_support_score: float = 0.0
    niche_conviction_score: float = 0.0


class LlmBucketJudgmentResponse(BaseModel):
    results: list[LlmBucketJudgmentItem] = Field(default_factory=list)


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
    bucket: RecommendationBucketType
    bucketRank: int
    bucketReason: str
    bucketEvidence: BucketEvidence = Field(default_factory=BucketEvidence)
    secondaryTraits: list[str] = Field(default_factory=list)


class RecommendationBuckets(BaseModel):
    closest_matches: list[RankedRecommendation] = Field(default_factory=list)
    similar_but_novel: list[RankedRecommendation] = Field(default_factory=list)
    niche_picks: list[RankedRecommendation] = Field(default_factory=list)


class RecommendationRequest(BaseModel):
    prompt: str


class RecommendationResponse(BaseModel):
    sessionId: str
    intent: ParsedUserIntent
    archetype: RecommendationArchetype
    buckets: RecommendationBuckets
    recommendations: list[RankedRecommendation]


class SessionPayload(BaseModel):
    id: str
    user_id: str
    prompt: str
    normalized_preferences: ParsedUserIntent
    archetype: RecommendationArchetype | None = None
    created_at: str


class RecommendationSessionResponse(BaseModel):
    session: SessionPayload
    archetype: RecommendationArchetype
    buckets: RecommendationBuckets
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
    data_source: str | None = None
    source_updated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
