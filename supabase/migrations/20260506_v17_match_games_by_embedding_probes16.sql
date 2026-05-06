create or replace function public.match_games_by_embedding(
  query_embedding vector(3072),
  match_count integer default 80
)
returns table (
  appid text,
  similarity double precision
)
language plpgsql
stable
as $$
begin
  perform set_config('ivfflat.probes', '16', true);

  return query
  select
    games.appid,
    1 - ((games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072))) as similarity
  from public.games
  where games.embedding_vector is not null
  order by (games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072))
  limit greatest(match_count, 0);
end;
$$;
