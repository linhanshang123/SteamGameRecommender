create index if not exists games_embedding_vector_hnsw_idx
  on public.games
  using hnsw ((embedding_vector::halfvec(3072)) halfvec_cosine_ops)
  with (m = 8, ef_construction = 32)
  where embedding_vector is not null;
