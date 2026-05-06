create extension if not exists vector;

alter table if exists public.games
  add column if not exists embedding_vector vector(3072),
  add column if not exists embedding_model text,
  add column if not exists embedding_dimensions integer,
  add column if not exists embedding_updated_at timestamptz;

create index if not exists games_embedding_vector_hnsw_idx
  on public.games
  using hnsw ((embedding_vector::halfvec(3072)) halfvec_cosine_ops)
  where embedding_vector is not null;

create or replace function public.match_games_by_embedding(
  query_embedding vector(3072),
  match_count integer default 80
)
returns table (
  appid text,
  similarity double precision
)
language sql
stable
as $$
  select
    games.appid,
    1 - ((games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072))) as similarity
  from public.games
  where games.embedding_vector is not null
  order by (games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072))
  limit greatest(match_count, 0);
$$;
