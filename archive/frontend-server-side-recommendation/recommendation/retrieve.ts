import { createSupabaseServerClient } from "@/lib/supabase";
import type { GameRow, ParsedUserIntent } from "@/lib/types";

function uniqueGames(games: GameRow[]) {
  return [...new Map(games.map((game) => [game.appid, game])).values()];
}

export async function fetchCandidateGames(intent: ParsedUserIntent) {
  const supabase = createSupabaseServerClient();
  const queries: PromiseLike<GameRow[]>[] = [];

  if (intent.preferred_tags.length) {
    queries.push(
      supabase
        .from("games")
        .select("*")
        .overlaps("tags", intent.preferred_tags)
        .limit(80)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          return (data ?? []) as GameRow[];
        }),
    );
    queries.push(
      supabase
        .from("games")
        .select("*")
        .overlaps("genres", intent.preferred_tags)
        .limit(60)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          return (data ?? []) as GameRow[];
        }),
    );
  }

  const keywords = intent.free_text_intent
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((token) => token.length > 3)
    .slice(0, 3);

  if (keywords.length) {
    const escaped = keywords.map((keyword) => keyword.replace(/[%_]/g, ""));
    const orClause = escaped
      .flatMap((keyword) => [`name.ilike.%${keyword}%`, `llm_context.ilike.%${keyword}%`])
      .join(",");

    queries.push(
      supabase
        .from("games")
        .select("*")
        .or(orClause)
        .limit(60)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          return (data ?? []) as GameRow[];
        }),
    );
  }

  if (!queries.length) {
    queries.push(
      supabase
        .from("games")
        .select("*")
        .order("total_reviews", { ascending: false })
        .limit(120)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          return (data ?? []) as GameRow[];
        }),
    );
  }

  const queryResults = await Promise.all(queries);
  let candidates = uniqueGames(queryResults.flat());

  if (intent.constraints?.price_max !== undefined) {
    candidates = candidates.filter(
      (game) => game.price === null || game.price <= intent.constraints!.price_max!,
    );
  }

  if (intent.constraints?.year_min !== undefined) {
    candidates = candidates.filter(
      (game) => game.year === null || game.year >= intent.constraints!.year_min!,
    );
  }

  if (intent.constraints?.single_player) {
    candidates = candidates.filter((game) =>
      (game.categories ?? []).some((category) => /single-player/i.test(category)),
    );
  }

  if (intent.constraints?.multiplayer) {
    candidates = candidates.filter((game) =>
      (game.categories ?? []).some((category) => /multi-player|co-op/i.test(category)),
    );
  }

  if (candidates.length < 30) {
    const { data, error } = await supabase
      .from("games")
      .select("*")
      .order("total_reviews", { ascending: false })
      .limit(80);

    if (error) {
      throw new Error(error.message);
    }

    const filler = (data ?? []) as GameRow[];
    candidates = uniqueGames([...candidates, ...filler]);
  }

  return candidates.slice(0, 180);
}
