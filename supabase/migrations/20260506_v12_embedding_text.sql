alter table if exists public.games
  add column if not exists embedding_text text;

create index if not exists games_embedding_text_trgm_idx
  on public.games using gin (embedding_text gin_trgm_ops);
