-- =============================================================================
--  0002 · hybrid_search v2
--  1. Léxico con OR: plainto/websearch_to_tsquery exigen TODOS los términos, y
--     una pregunta natural ("¿puedo tener un perro en el conjunto?") casi nunca
--     coincide completa. Se unen los lexemas con | y ts_rank_cd premia los
--     chunks que contienen más términos.
--  2. Devuelve semantic_distance (para medir relevancia) y section_title.
--  3. p_embedding_model: compara solo contra vectores del mismo modelo (al
--     migrar de proveedor conviven vectores incompatibles durante el re-embebido).
-- =============================================================================
DROP FUNCTION hybrid_search(uuid, boolean, vector, text, int, document_category[], int);

CREATE FUNCTION hybrid_search(
  p_tenant_id        uuid,
  p_is_admin         boolean,
  p_query_embedding  vector(1536),
  p_query_text       text,
  p_match_count      int DEFAULT 8,
  p_categories       document_category[] DEFAULT NULL,
  p_rrf_k            int DEFAULT 60,
  p_embedding_model  text DEFAULT NULL
)
RETURNS TABLE (
  chunk_id           uuid,
  document_id        uuid,
  document_name      text,
  page_number        int,
  page_end           int,
  category           document_category,
  section_title      text,
  content            text,
  semantic_rank      bigint,
  lexical_rank       bigint,
  semantic_distance  double precision,
  score              double precision
)
LANGUAGE sql STABLE AS $$
  WITH query AS (
    -- 'piscin' & 'lun'  ->  'piscin' | 'lun'   (cast directo: sin re-aplicar stemming)
    SELECT nullif(replace(plainto_tsquery('es_unaccent', p_query_text)::text, ' & ', ' | '), '')::tsquery AS tsq
  ),
  semantic AS (
    SELECT id, dist, row_number() OVER (ORDER BY dist) AS rnk
    FROM (
      SELECT c.id, c.embedding <=> p_query_embedding AS dist
      FROM document_chunks c
      WHERE c.tenant_id = p_tenant_id
        AND (p_is_admin OR c.access_level = 'PUBLIC')
        AND (p_categories IS NULL OR c.category = ANY (p_categories))
        AND (p_embedding_model IS NULL OR c.embedding_model = p_embedding_model)
      ORDER BY c.embedding <=> p_query_embedding
      LIMIT p_match_count * 4
    ) s
  ),
  lexical AS (
    SELECT c.id,
           row_number() OVER (ORDER BY ts_rank_cd(c.content_tsv, q.tsq) DESC) AS rnk
    FROM document_chunks c, query q
    WHERE c.tenant_id = p_tenant_id
      AND (p_is_admin OR c.access_level = 'PUBLIC')
      AND (p_categories IS NULL OR c.category = ANY (p_categories))
      AND c.content_tsv @@ q.tsq
    ORDER BY ts_rank_cd(c.content_tsv, q.tsq) DESC
    LIMIT p_match_count * 4
  ),
  fused AS (
    SELECT coalesce(s.id, l.id) AS id,
           s.rnk  AS semantic_rank,
           l.rnk  AS lexical_rank,
           s.dist AS semantic_distance,
           coalesce(1.0 / (p_rrf_k + s.rnk), 0) + coalesce(1.0 / (p_rrf_k + l.rnk), 0) AS score
    FROM semantic s
    FULL OUTER JOIN lexical l ON l.id = s.id
  )
  SELECT c.id, c.document_id, d.title, c.page_number, c.page_end, c.category, c.section_title,
         c.content, f.semantic_rank, f.lexical_rank, f.semantic_distance, f.score
  FROM fused f
  JOIN document_chunks c ON c.id = f.id
  JOIN documents d       ON d.id = c.document_id AND d.deleted_at IS NULL
  ORDER BY f.score DESC
  LIMIT p_match_count;
$$;
