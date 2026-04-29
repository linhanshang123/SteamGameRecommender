import { createSupabaseServerClient } from "@/lib/supabase";
import type {
  ParsedUserIntent,
  RankedRecommendation,
  RecommendationSessionRow,
} from "@/lib/types";
import { parseUserIntent } from "@/lib/recommendation/intent";
import { buildReason } from "@/lib/recommendation/reason";
import { fetchCandidateGames } from "@/lib/recommendation/retrieve";
import { scoreGame } from "@/lib/recommendation/scoring";

async function fetchUserHistory(userId: string) {
  const supabase = createSupabaseServerClient();
  const { data, error } = await supabase
    .from("recommendation_sessions")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(12);

  if (error) {
    throw new Error(error.message);
  }

  return (data ?? []) as RecommendationSessionRow[];
}

export async function createRecommendationSession(args: {
  prompt: string;
  userId: string;
}) {
  const intent = await parseUserIntent(args.prompt);
  const [history, candidates] = await Promise.all([
    fetchUserHistory(args.userId),
    fetchCandidateGames(intent),
  ]);

  const rankedCandidates = candidates
    .map((game) => {
      const scored = scoreGame(game, intent, history);
      return {
        game,
        ...scored,
      };
    })
    .sort((a, b) => b.finalScore - a.finalScore)
    .slice(0, 5);

  const recommendations: RankedRecommendation[] = await Promise.all(
    rankedCandidates.map(async ({ game, finalScore, breakdown }, index) => ({
      appid: game.appid,
      name: game.name,
      price: game.price,
      year: game.year,
      tags: game.tags ?? [],
      genres: game.genres ?? [],
      ratingRatio: game.rating_ratio ?? 0,
      finalScore,
      scoreBreakdown: breakdown,
      reason: await buildReason(game, intent, breakdown),
      rank: index + 1,
    })),
  );

  const supabase = createSupabaseServerClient();
  const { data: session, error: sessionError } = await supabase
    .from("recommendation_sessions")
    .insert({
      user_id: args.userId,
      prompt: args.prompt,
      normalized_preferences: intent,
    })
    .select("*")
    .single();

  if (sessionError || !session) {
    throw new Error(sessionError?.message ?? "Failed to create recommendation session.");
  }

  const { error: resultsError } = await supabase.from("recommendation_results").insert(
    recommendations.map((recommendation) => ({
      session_id: session.id,
      game_appid: recommendation.appid,
      rank: recommendation.rank,
      reason: recommendation.reason,
      score: recommendation.finalScore,
      score_breakdown: recommendation.scoreBreakdown,
    })),
  );

  if (resultsError) {
    throw new Error(resultsError.message);
  }

  return {
    sessionId: session.id,
    intent,
    recommendations,
  };
}

export async function getRecommendationSession(sessionId: string, userId: string) {
  const supabase = createSupabaseServerClient();
  const { data: session, error: sessionError } = await supabase
    .from("recommendation_sessions")
    .select("*")
    .eq("id", sessionId)
    .eq("user_id", userId)
    .single();

  if (sessionError || !session) {
    throw new Error(sessionError?.message ?? "Recommendation session not found.");
  }

  const { data: results, error: resultsError } = await supabase
    .from("recommendation_results")
    .select("*")
    .eq("session_id", sessionId)
    .order("rank", { ascending: true });

  if (resultsError) {
    throw new Error(resultsError.message);
  }

  const appIds = (results ?? []).map((result) => result.game_appid);
  const { data: games, error: gamesError } = await supabase
    .from("games")
    .select("*")
    .in("appid", appIds);

  if (gamesError) {
    throw new Error(gamesError.message);
  }

  const gameMap = new Map((games ?? []).map((game) => [game.appid, game]));

  return {
    session,
    recommendations: (results ?? []).map((result) => {
      const game = gameMap.get(result.game_appid);
      if (!game) {
        throw new Error(`Game not found for appid ${result.game_appid}`);
      }

      return {
        appid: game.appid,
        name: game.name,
        price: game.price,
        year: game.year,
        tags: game.tags ?? [],
        genres: game.genres ?? [],
        ratingRatio: game.rating_ratio ?? 0,
        finalScore: result.score,
        scoreBreakdown: result.score_breakdown,
        reason: result.reason,
        rank: result.rank,
      };
    }),
  };
}

export async function getRecommendationHistory(userId: string) {
  const supabase = createSupabaseServerClient();
  const { data: sessions, error } = await supabase
    .from("recommendation_sessions")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(20);

  if (error) {
    throw new Error(error.message);
  }

  const sessionIds = (sessions ?? []).map((session) => session.id);
  const { data: results, error: resultsError } = await supabase
    .from("recommendation_results")
    .select("*")
    .in("session_id", sessionIds)
    .order("rank", { ascending: true });

  if (resultsError) {
    throw new Error(resultsError.message);
  }

  const appIds = [...new Set((results ?? []).map((result) => result.game_appid))];
  const { data: games, error: gamesError } = await supabase
    .from("games")
    .select("appid,name")
    .in("appid", appIds);

  if (gamesError) {
    throw new Error(gamesError.message);
  }

  const gameMap = new Map((games ?? []).map((game) => [game.appid, game.name]));
  const groupedResults = new Map<string, string[]>();

  for (const result of results ?? []) {
    const existing = groupedResults.get(result.session_id) ?? [];
    if (existing.length < 3) {
      existing.push(gameMap.get(result.game_appid) ?? result.game_appid);
    }
    groupedResults.set(result.session_id, existing);
  }

  return (sessions ?? []).map((session) => ({
    ...session,
    previewTitles: groupedResults.get(session.id) ?? [],
  }));
}
