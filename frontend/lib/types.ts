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
  free_text_intent: string;
  constraints?: {
    price_max?: number;
    year_min?: number;
    single_player?: boolean;
    multiplayer?: boolean;
  };
};

export type ScoreBreakdown = {
  tag_match_score: number;
  text_match_score: number;
  rating_confidence_score: number;
  popularity_reliability_score: number;
  preference_history_score?: number;
  avoid_penalty: number;
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
  rank: number;
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
  created_at: string;
};

export type HistoryEntry = RecommendationSessionRow & {
  previewTitles: string[];
};

export type RecommendationResponse = {
  sessionId: string;
  intent: ParsedUserIntent;
  recommendations: RankedRecommendation[];
};

export type RecommendationSessionResponse = {
  session: RecommendationSessionRow;
  recommendations: RankedRecommendation[];
};

export type RecommendationResultRow = {
  id: string;
  session_id: string;
  game_appid: string;
  rank: number;
  reason: string;
  score: number;
  score_breakdown: ScoreBreakdown;
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
