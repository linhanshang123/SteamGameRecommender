drop index if exists public.games_embedding_vector_hnsw_idx;

create index if not exists games_embedding_vector_ivfflat_idx
  on public.games
  using ivfflat ((embedding_vector::halfvec(3072)) halfvec_cosine_ops)
  with (lists = 64)
  where embedding_vector is not null;
