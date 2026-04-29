export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export type ParsedUserIntent = {
  preferred_tags: string[];
  avoid_tags: string[];
  reference_games: string[];
  include_reference_games: boolean;
  free_text_intent: string;
  experience_axes: {
    combat_pace?: string | null;
    combat_feel: string[];
    presentation_style: string[];
    loop_shape: string[];
    difficulty_tolerance?: string | null;
  };
  implicit_soft_avoids: {
    strategy_heavy: boolean;
    slow_combat: boolean;
    clunky_feel: boolean;
    shooter_dominant: boolean;
  };
  must_have: string[];
  nice_to_have: string[];
  reference_anchor_profile?: {
    anchor_names: string[];
    derived_tags: string[];
    combat_pace?: string | null;
    combat_feel: string[];
    presentation_style: string[];
    loop_shape: string[];
    summary: string;
  } | null;
  constraints?: {
    price_max?: number;
    year_min?: number;
    single_player?: boolean;
    multiplayer?: boolean;
  };
};

export type RecommendationBucketType =
  | "closest_matches"
  | "similar_but_novel"
  | "niche_picks";

export type RecommendationArchetype = {
  summary: string;
  core_experience: string[];
  required_alignment: string[];
  allowed_novelty_axes: string[];
  hard_drifts_to_avoid: string[];
};

export type ScoreBreakdown = {
  tag_match_score: number;
  text_match_score: number;
  reference_similarity_score: number;
  combat_pace_match_score: number;
  combat_feel_match_score: number;
  presentation_match_score: number;
  loop_shape_match_score: number;
  rating_confidence_score: number;
  popularity_reliability_score: number;
  preference_history_score?: number;
  avoid_penalty: number;
  strategy_heavy_penalty: number;
  slow_combat_penalty: number;
  clunky_feel_penalty: number;
  shooter_dominant_penalty: number;
  soft_avoid_penalty_score: number;
  deterministic_score: number;
  llm_match_score: number;
};

export type RecommendationDebugPayload = {
  matched_preferred_tags: string[];
  matched_avoid_tags: string[];
  text_matched_terms: string[];
  resolved_reference_appids: string[];
  retrieval_routes: string[];
  experience_axes: ParsedUserIntent["experience_axes"];
  implicit_soft_avoids: ParsedUserIntent["implicit_soft_avoids"];
  reference_anchor_profile: ParsedUserIntent["reference_anchor_profile"];
  rerank_dimension_scores: {
    reference_match_score: number;
    combat_pace_score: number;
    combat_feel_score: number;
    presentation_score: number;
    loop_shape_score: number;
    soft_avoid_penalty_score: number;
  };
  rerank_applied: boolean;
  rerank_error: string | null;
};

export type BucketEvidence = {
  bucket_fit_score: number;
  novelty_support_score: number;
  niche_conviction_score: number;
};

export type RankedRecommendation = {
  appid: string;
  name: string;
  price: number | null;
  year: number | null;
  tags: string[];
  genres: string[];
  ratingRatio: number;
  finalScore: number;
  scoreBreakdown: ScoreBreakdown;
  reason: string;
  concern: string;
  debugPayload: RecommendationDebugPayload;
  deterministicScore: number;
  llmMatchScore: number;
  rank: number;
  bucket?: RecommendationBucketType;
  bucketRank?: number;
  bucketReason?: string;
  bucketEvidence?: BucketEvidence;
  secondaryTraits?: string[];
};

export type RecommendationBuckets = {
  closest_matches: RankedRecommendation[];
  similar_but_novel: RankedRecommendation[];
  niche_picks: RankedRecommendation[];
};

export type GameRow = {
  appid: string;
  name: string;
  year: number | null;
  price: number | null;
  required_age: number | null;
  total_reviews: number | null;
  positive: number | null;
  negative: number | null;
  rating_ratio: number | null;
  genres: string[] | null;
  categories: string[] | null;
  tags: string[] | null;
  supported_languages: string[] | null;
  average_playtime_forever: number | null;
  metacritic_score: number | null;
  llm_context: string | null;
  data_source: string | null;
  source_updated_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RecommendationSessionRow = {
  id: string;
  user_id: string;
  prompt: string;
  normalized_preferences: ParsedUserIntent;
  archetype?: RecommendationArchetype | null;
  created_at: string;
};

export type HistoryEntry = RecommendationSessionRow & {
  previewTitles: string[];
};

export type RecommendationResponse = {
  sessionId: string;
  intent: ParsedUserIntent;
  archetype?: RecommendationArchetype;
  buckets?: RecommendationBuckets;
  recommendations: RankedRecommendation[];
};

export type RecommendationSessionResponse = {
  session: RecommendationSessionRow;
  archetype?: RecommendationArchetype;
  buckets?: RecommendationBuckets;
  recommendations: RankedRecommendation[];
};

export type RecommendationResultRow = {
  id: string;
  session_id: string;
  game_appid: string;
  rank: number;
  reason: string;
  concern: string | null;
  score: number;
  deterministic_score: number | null;
  llm_match_score: number | null;
  bucket: RecommendationBucketType | null;
  bucket_rank: number | null;
  bucket_reason: string | null;
  bucket_evidence: BucketEvidence | null;
  secondary_traits: string[] | null;
  score_breakdown: ScoreBreakdown;
  debug_payload: RecommendationDebugPayload | null;
  created_at: string;
};

export type Database = {
  public: {
    Tables: {
      games: {
        Row: GameRow;
        Insert: Omit<GameRow, "created_at" | "updated_at"> & {
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<GameRow>;
        Relationships: [];
      };
      recommendation_sessions: {
        Row: RecommendationSessionRow;
        Insert: Omit<RecommendationSessionRow, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<RecommendationSessionRow>;
        Relationships: [];
      };
      recommendation_results: {
        Row: RecommendationResultRow;
        Insert: Omit<RecommendationResultRow, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<RecommendationResultRow>;
        Relationships: [
          {
            foreignKeyName: "recommendation_results_game_appid_fkey";
            columns: ["game_appid"];
            referencedRelation: "games";
            referencedColumns: ["appid"];
          },
          {
            foreignKeyName: "recommendation_results_session_id_fkey";
            columns: ["session_id"];
            referencedRelation: "recommendation_sessions";
            referencedColumns: ["id"];
          },
        ];
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
};
