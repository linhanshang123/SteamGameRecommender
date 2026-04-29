# SteamRecommender

A catalog-grounded Steam discovery app for players who know the feeling they want, but not the exact search terms.

## Stack

- Next.js App Router
- Clerk for authentication
- Supabase for catalog + recommendation history
- Tailwind CSS v4
- LangChain OpenAI integration with a built-in heuristic fallback when `OPENAI_API_KEY` is not configured

## Environment

Create `.env.local` with:

```bash
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=
OPENAI_API_KEY=
```

`OPENAI_API_KEY` is optional for local development. If it is missing, the app still works with heuristic intent parsing and templated reasons.

## Local setup

```bash
npm install
npm run import:games
npm run dev
```

The import script loads `games_clean.json` into Supabase `public.games`.

## Database

The base schema lives in `supabase/migrations/20260429_init.sql`.

Tables:

- `games`
- `recommendation_sessions`
- `recommendation_results`

## Recommendation flow

1. User enters a natural-language prompt.
2. The system parses intent into preferred tags, avoid tags, free-text nuance, and simple constraints.
3. Supabase returns a candidate pool from the imported Steam catalog.
4. Candidates are scored with the explicit weighted formula.
5. Top results are saved to history and shown in the UI.

With history:

```text
final_score =
  0.35 * tag_match_score
+ 0.25 * text_match_score
+ 0.15 * rating_confidence_score
+ 0.10 * popularity_reliability_score
+ 0.10 * preference_history_score
- 0.20 * avoid_penalty
```

Without history:

```text
final_score =
  0.40 * tag_match_score
+ 0.30 * text_match_score
+ 0.15 * rating_confidence_score
+ 0.15 * popularity_reliability_score
- 0.25 * avoid_penalty
```

## Notes

- `all_tags.json` is treated as the controlled Steam tag vocabulary.
- The current implementation does not include in-result refinement controls yet.
- Supabase RLS is currently disabled for the v1 bootstrap schema because the app uses Clerk auth rather than Supabase auth.
