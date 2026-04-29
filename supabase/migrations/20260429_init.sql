create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table if not exists public.games (
  appid text primary key,
  name text not null,
  year integer,
  price numeric(10,2),
  required_age integer,
  total_reviews integer,
  positive integer,
  negative integer,
  rating_ratio double precision,
  genres text[] not null default '{}',
  categories text[] not null default '{}',
  tags text[] not null default '{}',
  supported_languages text[] not null default '{}',
  average_playtime_forever integer,
  metacritic_score integer,
  llm_context text,
  data_source text default 'games_clean.json',
  source_updated_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.recommendation_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  prompt text not null,
  normalized_preferences jsonb not null,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.recommendation_results (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.recommendation_sessions(id) on delete cascade,
  game_appid text not null references public.games(appid) on delete cascade,
  rank integer not null,
  reason text not null,
  score double precision not null,
  score_breakdown jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  unique(session_id, rank),
  unique(session_id, game_appid)
);

create index if not exists games_name_idx on public.games (name);
create index if not exists games_total_reviews_idx on public.games (total_reviews desc);
create index if not exists recommendation_sessions_user_id_idx on public.recommendation_sessions (user_id);
create index if not exists recommendation_results_session_id_idx on public.recommendation_results (session_id);
create index if not exists games_tags_gin_idx on public.games using gin (tags);
create index if not exists games_genres_gin_idx on public.games using gin (genres);
create index if not exists games_categories_gin_idx on public.games using gin (categories);
create index if not exists games_name_trgm_idx on public.games using gin (name gin_trgm_ops);
create index if not exists games_llm_context_trgm_idx on public.games using gin (llm_context gin_trgm_ops);

drop trigger if exists games_set_updated_at on public.games;
create trigger games_set_updated_at
before update on public.games
for each row
execute function public.set_updated_at();
