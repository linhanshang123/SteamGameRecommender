create or replace function public.export_game_embeddings_for_faiss(
  after_appid text default null,
  batch_count integer default 500
)
returns table (
  appid text,
  embedding_vector_text text
)
language sql
stable
set statement_timeout = '30000'
as $$
  select
    games.appid,
    games.embedding_vector::text as embedding_vector_text
  from public.games
  where games.embedding_vector is not null
    and (after_appid is null or games.appid > after_appid)
  order by games.appid
  limit greatest(coalesce(batch_count, 500), 1);
$$;
