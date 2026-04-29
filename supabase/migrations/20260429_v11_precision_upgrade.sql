alter table if exists public.recommendation_results
  add column if not exists deterministic_score double precision,
  add column if not exists llm_match_score double precision,
  add column if not exists concern text,
  add column if not exists debug_payload jsonb;
