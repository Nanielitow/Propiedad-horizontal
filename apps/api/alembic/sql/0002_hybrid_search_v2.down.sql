-- Reversa de 0002: restaura hybrid_search v1 (definición de la migración 0001)
DROP FUNCTION hybrid_search(uuid, boolean, vector, text, int, document_category[], int, text);

CREATE FUNCTION hybrid_search(
  p_tenant_id        uuid,
  p_is_admin         boolean,
  p_query_embedding  vector(1536),
  p_query_text       text,
  p_match_count      int DEFAULT 8,
  p_categories       document_category[] DEFAULT NULL,
  p_rrf_k            int DEFAULT 60
)
RETURNS TABLE (
  chunk_id       uuid,
  document_id    uuid,
  document_name  text,
  page_number    int,
  page_end       int,
  category       document_category,
  content        text,
  semantic_rank  bigint,
  lexical_rank   bigint,
  score          double precision
)
LANGUAGE sql STABLE AS $$
  WITH semantic AS (
    SELECT id, row_number() OVER (ORDER BY dist) AS rnk
    FROM (
      SELECT c.id, c.embedding <=> p_query_embedding AS dist
      FROM document_chunks c
      WHERE c.tenant_id = p_tenant_id
        AND (p_is_admin OR c.access_level = 'PUBLIC')
        AND (p_categories IS NULL OR c.category = ANY (p_categories))
      ORDER BY c.embedding <=> p_query_embedding      -- usa el índice HNSW
      LIMIT p_match_count * 4
    ) s
  ),
  lexical AS (
    SELECT c.id,
           row_number() OVER (ORDER BY ts_rank_cd(c.content_tsv, q) DESC) AS rnk
    FROM document_chunks c,
         websearch_to_tsquery('es_unaccent', p_query_text) q
    WHERE c.tenant_id = p_tenant_id
      AND (p_is_admin OR c.access_level = 'PUBLIC')
      AND (p_categories IS NULL OR c.category = ANY (p_categories))
      AND c.content_tsv @@ q                          -- usa el índice GIN
    ORDER BY ts_rank_cd(c.content_tsv, q) DESC
    LIMIT p_match_count * 4
  ),
  fused AS (
    SELECT coalesce(s.id, l.id) AS id,
           s.rnk AS semantic_rank,
           l.rnk AS lexical_rank,
           coalesce(1.0 / (p_rrf_k + s.rnk), 0) + coalesce(1.0 / (p_rrf_k + l.rnk), 0) AS score
    FROM semantic s
    FULL OUTER JOIN lexical l ON l.id = s.id
  )
  SELECT c.id, c.document_id, d.title, c.page_number, c.page_end, c.category, c.content,
         f.semantic_rank, f.lexical_rank, f.score
  FROM fused f
  JOIN document_chunks c ON c.id = f.id
  JOIN documents d       ON d.id = c.document_id AND d.deleted_at IS NULL
  ORDER BY f.score DESC
  LIMIT p_match_count;
$$;
