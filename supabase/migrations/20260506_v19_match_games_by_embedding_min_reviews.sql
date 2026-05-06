drop function if exists public.match_games_by_embedding(vector, integer);

create or replace function public.match_games_by_embedding(
  query_embedding vector(3072),
  match_count integer default 80,
  minimum_total_reviews integer default null
)
returns table (
  appid text,
  similarity double precision
)
language plpgsql
stable
set statement_timeout = '20000'
as $$
declare
  normalized_minimum_total_reviews integer := greatest(coalesce(minimum_total_reviews, 0), 0);
begin
  perform set_config('ivfflat.probes', '16', true);

  return query
  select
    games.appid,
    1 - ((games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072))) as similarity
  from public.games
  where games.embedding_vector is not null
    and coalesce(games.total_reviews, 0) >= normalized_minimum_total_reviews
  order by (games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072))
  limit greatest(match_count, 0);
end;
$$;
