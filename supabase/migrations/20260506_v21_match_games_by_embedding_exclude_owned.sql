drop function if exists public.match_games_by_embedding(vector, integer, integer);

create or replace function public.match_games_by_embedding(
  query_embedding vector(3072),
  match_count integer default 80,
  minimum_total_reviews integer default null,
  excluded_user_id text default null
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
    and (
      excluded_user_id is null
      or not exists (
        select 1
        from public.user_owned_games owned
        where owned.user_id = excluded_user_id
          and owned.appid = games.appid
      )
    )
  order by (games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072))
  limit greatest(match_count, 0);
end;
$$;
