import { z } from "zod";
import { ChatOpenAI } from "@langchain/openai";
import { env } from "@/lib/env";
import { filterKnownTags } from "@/lib/recommendation/all-tags";
import type { ParsedUserIntent } from "@/lib/types";

const parsedIntentSchema = z.object({
  preferred_tags: z.array(z.string()).default([]),
  avoid_tags: z.array(z.string()).default([]),
  free_text_intent: z.string().default(""),
  constraints: z
    .object({
      price_max: z.number().optional(),
      year_min: z.number().optional(),
      single_player: z.boolean().optional(),
      multiplayer: z.boolean().optional(),
    })
    .partial()
    .optional(),
});

function extractNumbers(prompt: string) {
  const priceMatch = prompt.match(/\$?(\d{1,3})(?:\s*(?:dollars|usd|bucks|under|max))/i);
  const yearMatch = prompt.match(/(?:after|since|newer than)\s+(20\d{2}|19\d{2})/i);

  return {
    price_max: priceMatch ? Number(priceMatch[1]) : undefined,
    year_min: yearMatch ? Number(yearMatch[1]) : undefined,
  };
}

function heuristicIntent(prompt: string): ParsedUserIntent {
  const lowerPrompt = prompt.toLowerCase();
  const matches = new Set<string>();

  for (const tag of filterKnownTags([lowerPrompt])) {
    matches.add(tag);
  }

  // Phrase-level scan for known Steam tags.
  const phrases = lowerPrompt.split(/[,.!?]/).flatMap((segment) => [
    segment.trim(),
    ...segment.trim().split(/\s+/).reduce<string[]>((acc, word, index, parts) => {
      const two = `${word} ${parts[index + 1] ?? ""}`.trim();
      const three = `${word} ${parts[index + 1] ?? ""} ${parts[index + 2] ?? ""}`.trim();
      if (two) acc.push(two);
      if (three) acc.push(three);
      return acc;
    }, []),
  ]);

  for (const candidate of phrases) {
    const filtered = filterKnownTags([candidate]);
    if (filtered[0]) {
      matches.add(filtered[0]);
    }
  }

  const avoidParts = lowerPrompt.split(/but not|avoid|no |don't want|not /i);
  const avoidTags =
    avoidParts.length > 1 ? filterKnownTags(avoidParts.slice(1).join(" ").split(/\s+/)) : [];

  return {
    preferred_tags: [...matches].filter((tag) => !avoidTags.includes(tag)),
    avoid_tags: avoidTags,
    free_text_intent: prompt.trim(),
    constraints: {
      ...extractNumbers(prompt),
      single_player: /single[\s-]?player/i.test(prompt) ? true : undefined,
      multiplayer: /multiplayer|co-op|coop|friends/i.test(prompt) ? true : undefined,
    },
  };
}

export async function parseUserIntent(prompt: string) {
  if (!env.openAiApiKey) {
    return heuristicIntent(prompt);
  }

  const model = new ChatOpenAI({
    apiKey: env.openAiApiKey,
    model: "gpt-4.1-mini",
    temperature: 0,
  });

  const structuredModel = model.withStructuredOutput(parsedIntentSchema);
  const result = await structuredModel.invoke([
    {
      role: "system",
      content:
        "You extract Steam search intent. Only include tags that are exact Steam tags. Put non-tag nuance in free_text_intent.",
    },
    {
      role: "user",
      content: prompt,
    },
  ]);

  return {
    preferred_tags: filterKnownTags(result.preferred_tags ?? []),
    avoid_tags: filterKnownTags(result.avoid_tags ?? []),
    free_text_intent: result.free_text_intent || prompt.trim(),
    constraints: result.constraints,
  } satisfies ParsedUserIntent;
}
