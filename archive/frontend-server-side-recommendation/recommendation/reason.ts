import { ChatOpenAI } from "@langchain/openai";
import { env } from "@/lib/env";
import type { GameRow, ParsedUserIntent, ScoreBreakdown } from "@/lib/types";

function fallbackReason(game: GameRow, intent: ParsedUserIntent, scoreBreakdown: ScoreBreakdown) {
  const matchedTags = (game.tags ?? [])
    .filter((tag) => intent.preferred_tags.includes(tag.toLowerCase()))
    .slice(0, 3);

  const tagPhrase = matchedTags.length
    ? `It lines up with ${matchedTags.join(", ")}.`
    : "It broadly fits the vibe described in your prompt.";

  const reviewPhrase =
    (game.total_reviews ?? 0) > 500
      ? ` It also has a stronger review base than most niche candidates.`
      : ` It stays in the mix because its text match is stronger than average.`;

  const guardPhrase =
    scoreBreakdown.avoid_penalty > 0.1
      ? " There is some tension with one avoided direction, so it ranked lower than a cleaner match would."
      : "";

  return `${tagPhrase}${reviewPhrase}${guardPhrase}`;
}

export async function buildReason(
  game: GameRow,
  intent: ParsedUserIntent,
  scoreBreakdown: ScoreBreakdown,
) {
  if (!env.openAiApiKey) {
    return fallbackReason(game, intent, scoreBreakdown);
  }

  const model = new ChatOpenAI({
    apiKey: env.openAiApiKey,
    model: "gpt-4.1-mini",
    temperature: 0.3,
  });

  const response = await model.invoke([
    {
      role: "system",
      content:
        "Write one concise recommendation reason for a Steam game. Mention fit, not chain-of-thought. Keep it under 28 words.",
    },
    {
      role: "user",
      content: JSON.stringify({
        prompt: intent.free_text_intent,
        preferred_tags: intent.preferred_tags,
        avoid_tags: intent.avoid_tags,
        game: {
          name: game.name,
          tags: game.tags ?? [],
          genres: game.genres ?? [],
          description: game.llm_context ?? "",
        },
        scoreBreakdown,
      }),
    },
  ]);

  return response.text.trim();
}
