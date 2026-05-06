create or replace function public.diagnose_game_embedding_rank(
  query_embedding vector(3072),
  target_appid text default null,
  sample_count integer default 20,
  probe_count integer default null,
  search_mode text default 'exact'
)
returns table (
  rank integer,
  appid text,
  name text,
  similarity double precision,
  distance double precision,
  is_target boolean
)
language plpgsql
volatile
set statement_timeout = '600000'
as $$
declare
  normalized_sample_count integer := greatest(coalesce(sample_count, 20), 0);
  normalized_probe_count integer := greatest(coalesce(probe_count, 1), 1);
  normalized_mode text := lower(coalesce(search_mode, 'exact'));
begin
  if normalized_mode not in ('exact', 'ann') then
    raise exception 'search_mode must be exact or ann';
  end if;

  if normalized_mode = 'exact' then
    perform set_config('enable_indexscan', 'off', true);
    perform set_config('enable_bitmapscan', 'off', true);
    perform set_config('enable_indexonlyscan', 'off', true);

    return query
      with target_row as (
        select
          games.appid,
          games.name,
          (games.embedding_vector <=> query_embedding) as distance
        from public.games
        where games.embedding_vector is not null
          and games.appid = target_appid
        limit 1
      ),
      exact_top_sample as (
        select
          row_number() over (order by ordered.distance, ordered.appid)::integer as rank,
          ordered.appid,
          ordered.name,
          1 - ordered.distance as similarity,
          ordered.distance,
          ordered.appid = target_appid as is_target
        from (
          select
            games.appid,
            games.name,
            (games.embedding_vector <=> query_embedding) as distance
          from public.games
          where games.embedding_vector is not null
          order by
            (games.embedding_vector <=> query_embedding),
            games.appid
          limit normalized_sample_count
        ) as ordered
      ),
      target_rank as (
        select
          (count(*) + 1)::integer as rank
        from public.games
        join target_row on true
        where games.embedding_vector is not null
          and (
            (games.embedding_vector <=> query_embedding) < target_row.distance
            or (
              (games.embedding_vector <=> query_embedding) = target_row.distance
              and games.appid < target_row.appid
            )
          )
      ),
      target_payload as (
        select
          target_rank.rank,
          target_row.appid,
          target_row.name,
          1 - target_row.distance as similarity,
          target_row.distance,
          true as is_target
        from target_row
        join target_rank on true
      )
      select
        exact_top_sample.rank,
        exact_top_sample.appid,
        exact_top_sample.name,
        exact_top_sample.similarity,
        exact_top_sample.distance,
        exact_top_sample.is_target
      from exact_top_sample

      union all

      select
        target_payload.rank,
        target_payload.appid,
        target_payload.name,
        target_payload.similarity,
        target_payload.distance,
        target_payload.is_target
      from target_payload
      where not exists (
        select 1
        from exact_top_sample
        where exact_top_sample.appid = target_payload.appid
      )

      order by rank;

    return;
  end if;

  perform set_config('ivfflat.probes', normalized_probe_count::text, true);

  return query
    with ann_matches as (
      select
        games.appid,
        games.name,
        1 - ((games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072))) as similarity,
        ((games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072))) as distance,
        games.appid = target_appid as is_target
      from public.games
      where games.embedding_vector is not null
      order by
        (games.embedding_vector::halfvec(3072)) <=> (query_embedding::halfvec(3072)),
        games.appid
      limit normalized_sample_count
    ),
    ranked as (
      select
        row_number() over (order by ann_matches.distance, ann_matches.appid)::integer as rank,
        ann_matches.appid,
        ann_matches.name,
        ann_matches.similarity,
        ann_matches.distance,
        ann_matches.is_target
      from ann_matches
    )
    select
      ranked.rank,
      ranked.appid,
      ranked.name,
      ranked.similarity,
      ranked.distance,
      ranked.is_target
    from ranked
    order by ranked.rank;
end;
$$;
