alter table if exists public.recommendation_sessions
  add column if not exists archetype jsonb;

alter table if exists public.recommendation_results
  add column if not exists bucket text,
  add column if not exists bucket_rank integer,
  add column if not exists bucket_reason text,
  add column if not exists bucket_evidence jsonb,
  add column if not exists secondary_traits text[] not null default '{}';
