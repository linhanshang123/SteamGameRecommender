import fs from "node:fs/promises";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

if (!supabaseUrl || !supabaseKey) {
  throw new Error("Missing Supabase environment variables.");
}

const supabase = createClient(supabaseUrl, supabaseKey, {
  auth: {
    persistSession: false,
    autoRefreshToken: false,
  },
});

const sourcePath = path.join(process.cwd(), "games_clean.json");

function normalizeRow(row) {
  return {
    appid: String(row.appid),
    name: row.name ?? "Unknown title",
    year: Number.isFinite(row.year) ? row.year : null,
    price: Number.isFinite(row.price) ? row.price : null,
    required_age: Number.isFinite(row.required_age) ? row.required_age : null,
    total_reviews: Number.isFinite(row.total_reviews) ? row.total_reviews : null,
    positive: Number.isFinite(row.positive) ? row.positive : null,
    negative: Number.isFinite(row.negative) ? row.negative : null,
    rating_ratio: Number.isFinite(row.rating_ratio) ? row.rating_ratio : null,
    genres: Array.isArray(row.genres) ? row.genres : [],
    categories: Array.isArray(row.categories) ? row.categories : [],
    tags: Array.isArray(row.tags) ? row.tags.map((tag) => String(tag).toLowerCase()) : [],
    supported_languages: Array.isArray(row.supported_languages) ? row.supported_languages : [],
    average_playtime_forever: Number.isFinite(row.average_playtime_forever)
      ? row.average_playtime_forever
      : null,
    metacritic_score: Number.isFinite(row.metacritic_score) ? row.metacritic_score : null,
    llm_context: row.llm_context ?? null,
    data_source: "games_clean.json",
    source_updated_at: null,
  };
}

async function main() {
  const file = await fs.readFile(sourcePath, "utf8");
  const parsed = JSON.parse(file);

  if (!Array.isArray(parsed)) {
    throw new Error("games_clean.json must contain an array.");
  }

  const batchSize = 500;
  let imported = 0;

  for (let index = 0; index < parsed.length; index += batchSize) {
    const batch = parsed.slice(index, index + batchSize).map(normalizeRow);
    const { error } = await supabase.from("games").upsert(batch, {
      onConflict: "appid",
      ignoreDuplicates: false,
    });

    if (error) {
      throw new Error(`Failed at batch starting ${index}: ${error.message}`);
    }

    imported += batch.length;
    console.log(`Imported ${imported}/${parsed.length}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
