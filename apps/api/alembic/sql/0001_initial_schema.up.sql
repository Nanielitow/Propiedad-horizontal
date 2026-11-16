-- =============================================================================
--  PH-SaaS · Migración 0001 · Esquema inicial (PostgreSQL 16+, pgvector >= 0.8)
--  Multi-tenant (shared schema + tenant_id + Row Level Security)
--  Migraciones "SQL-first": RLS, triggers, funciones y enums no se pueden
--  expresar con autogenerate de Alembic, así que la fuente de verdad es SQL.
--  Los modelos SQLAlchemy (app/models) reflejan estas tablas.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 0. Extensiones y configuración de búsqueda en español
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;     -- embeddings + HNSW
CREATE EXTENSION IF NOT EXISTS unaccent;   -- "mantenimiento" == "mantenimiénto"
CREATE EXTENSION IF NOT EXISTS citext;     -- emails case-insensitive

-- Config FTS propia: stemming español + sin tildes. to_tsvector(regconfig, text)
-- es IMMUTABLE, por lo que puede usarse en una columna GENERATED.
CREATE TEXT SEARCH CONFIGURATION es_unaccent (COPY = spanish);
ALTER TEXT SEARCH CONFIGURATION es_unaccent
  ALTER MAPPING FOR hword, hword_part, word WITH unaccent, spanish_stem;

-- -----------------------------------------------------------------------------
-- 1. Tipos enumerados
-- -----------------------------------------------------------------------------
CREATE TYPE user_role         AS ENUM ('ADMIN', 'RESIDENTE');
CREATE TYPE access_level      AS ENUM ('ADMIN', 'PUBLIC');
CREATE TYPE document_category AS ENUM (
  'MANTENIMIENTO', 'ACTAS', 'CONTRATOS', 'FINANCIERO', 'CONVIVENCIA',
  'COMUNICADOS',   -- comunicados públicos a residentes
  'COTIZACIONES'   -- insumo del comparador de cotizaciones
);
CREATE TYPE document_status   AS ENUM ('UPLOADED', 'QUEUED', 'PROCESSING', 'READY', 'FAILED');
CREATE TYPE extraction_method AS ENUM ('NATIVE', 'OCR');
CREATE TYPE job_type          AS ENUM ('INGEST', 'EXTRACT_DEADLINES', 'SUMMARIZE_MINUTES', 'COMPARE_QUOTES');
CREATE TYPE job_status        AS ENUM ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RETRYING');
CREATE TYPE deadline_type     AS ENUM ('POLICY_EXPIRY', 'CONTRACT_END', 'MAINTENANCE', 'CERTIFICATION', 'OTHER');
CREATE TYPE deadline_status   AS ENUM ('PENDING_REVIEW', 'ACTIVE', 'DONE', 'DISMISSED');
CREATE TYPE task_status       AS ENUM ('OPEN', 'IN_PROGRESS', 'DONE');
CREATE TYPE message_role      AS ENUM ('user', 'assistant');

-- -----------------------------------------------------------------------------
-- 2. Funciones de contexto (alimentadas por la API con SET LOCAL en cada tx)
-- -----------------------------------------------------------------------------
CREATE FUNCTION app_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$;

CREATE FUNCTION app_user_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;

-- 'SYSTEM' lo usan los workers de Celery (actúan con privilegios de admin del tenant)
CREATE FUNCTION app_is_admin() RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(current_setting('app.role', true), '') IN ('ADMIN', 'SYSTEM') $$;

CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS
$$ BEGIN NEW.updated_at := now(); RETURN NEW; END $$;

-- -----------------------------------------------------------------------------
-- 3. Identidad y tenants (tablas GLOBALES, sin RLS por tenant)
-- -----------------------------------------------------------------------------
CREATE TABLE tenants (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text        NOT NULL,                 -- "Conjunto Residencial Los Pinos"
  slug        text        NOT NULL UNIQUE,          -- usado en la URL del frontend
  nit         text,
  address     text,
  city        text,
  settings    jsonb       NOT NULL DEFAULT '{}',    -- p.ej. días de aviso por defecto
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  deleted_at  timestamptz
);

CREATE TABLE users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          citext      NOT NULL UNIQUE,
  full_name      text        NOT NULL,
  password_hash  text        NOT NULL,              -- argon2id
  is_active      boolean     NOT NULL DEFAULT true,
  last_login_at  timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 4. Tablas por tenant
--    Patrón: UNIQUE (tenant_id, id) en el padre + FK compuesta (tenant_id, x_id)
--    en el hijo => es IMPOSIBLE referenciar una fila de otro edificio.
-- -----------------------------------------------------------------------------
CREATE TABLE units (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  tower       text NOT NULL DEFAULT '',
  number      text NOT NULL,                          -- "502"
  coefficient numeric(7,4),                           -- coeficiente de copropiedad (votaciones)
  UNIQUE (tenant_id, tower, number),
  UNIQUE (tenant_id, id)
);

-- Un usuario puede pertenecer a varios edificios (p.ej. una empresa administradora)
CREATE TABLE memberships (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
  role        user_role NOT NULL,
  unit_id     uuid,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, user_id),
  FOREIGN KEY (tenant_id, unit_id) REFERENCES units(tenant_id, id) ON DELETE SET NULL (unit_id)
);
CREATE INDEX memberships_user_idx ON memberships (user_id);

CREATE TABLE documents (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  uploaded_by        uuid REFERENCES users(id) ON DELETE SET NULL,
  title              text              NOT NULL,      -- = document_name en las citas
  original_filename  text              NOT NULL,
  category           document_category NOT NULL,
  access_level       access_level      NOT NULL,
  status             document_status   NOT NULL DEFAULT 'UPLOADED',
  storage_key        text              NOT NULL,      -- tenants/{tid}/documents/{id}/original.pdf
  ocr_storage_key    text,                            -- PDF con capa de texto (ocrmypdf)
  mime_type          text              NOT NULL DEFAULT 'application/pdf',
  size_bytes         bigint            NOT NULL CHECK (size_bytes > 0),
  sha256             char(64)          NOT NULL,      -- idempotencia / deduplicación
  page_count         int,
  is_scanned         boolean,
  document_date      date,                            -- fecha del documento (no de subida)
  error_message      text,
  processed_at       timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  deleted_at         timestamptz,                     -- soft delete
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX documents_dedup_idx  ON documents (tenant_id, sha256) WHERE deleted_at IS NULL;
CREATE INDEX documents_list_idx          ON documents (tenant_id, category, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX documents_status_idx        ON documents (tenant_id, status) WHERE status <> 'READY';

-- Texto completo por página: permite re-chunkear / re-embeber sin repetir OCR,
-- y alimenta los extractores (vencimientos, actas, cotizaciones).
CREATE TABLE document_pages (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL,
  document_id        uuid NOT NULL,
  page_number        int  NOT NULL CHECK (page_number >= 1),
  text               text NOT NULL,
  extraction_method  extraction_method NOT NULL,
  ocr_confidence     real,                            -- 0..100 (Tesseract)
  UNIQUE (document_id, page_number),
  FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id) ON DELETE CASCADE
);

-- Núcleo del RAG. category y access_level se DESNORMALIZAN desde documents para
-- poder filtrar en la misma consulta que el índice vectorial (sin JOIN previo).
CREATE TABLE document_chunks (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  document_id      uuid NOT NULL,
  chunk_index      int  NOT NULL,
  page_number      int  NOT NULL,                     -- página donde inicia el chunk (cita)
  page_end         int  NOT NULL,                     -- página donde termina
  category         document_category NOT NULL,
  access_level     access_level      NOT NULL,
  section_title    text,                              -- "CAPÍTULO III - De las mascotas"
  content          text NOT NULL,
  token_count      int  NOT NULL,
  content_tsv      tsvector GENERATED ALWAYS AS (to_tsvector('es_unaccent', content)) STORED,
  embedding        vector(1536) NOT NULL,             -- text-embedding-3-small (ver README)
  embedding_model  text NOT NULL,                     -- versionado para re-embeber
  metadata         jsonb NOT NULL DEFAULT '{}',
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index),
  CHECK (page_end >= page_number),
  FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id) ON DELETE CASCADE
);
-- Vectorial: HNSW + distancia coseno. Con pgvector >= 0.8 se activa
-- `SET LOCAL hnsw.iterative_scan = relaxed_order` para que los filtros
-- (tenant_id, access_level) no dejen el top-k incompleto.
CREATE INDEX chunks_embedding_hnsw ON document_chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
-- Léxico (keyword) para la parte híbrida
CREATE INDEX chunks_tsv_gin ON document_chunks USING gin (content_tsv);
-- Filtros de aislamiento / RBAC
CREATE INDEX chunks_filter_idx ON document_chunks (tenant_id, access_level, category);

-- Trazabilidad del pipeline asíncrono (reintentos, errores, métricas por etapa)
CREATE TABLE processing_jobs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  document_id     uuid,
  type            job_type   NOT NULL,
  status          job_status NOT NULL DEFAULT 'PENDING',
  celery_task_id  text,
  attempts        int  NOT NULL DEFAULT 0,
  current_step    text,                               -- 'ocr' | 'chunking' | 'embedding' ...
  payload         jsonb NOT NULL DEFAULT '{}',
  result          jsonb,
  error           text,
  started_at      timestamptz,
  finished_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX jobs_tenant_idx ON processing_jobs (tenant_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- 5. Detector de vencimientos (Structured Outputs + revisión humana)
-- -----------------------------------------------------------------------------
CREATE TABLE deadlines (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  document_id       uuid NOT NULL,
  title             text NOT NULL,                    -- "Póliza todo riesgo - Seguros X"
  type              deadline_type   NOT NULL,
  status            deadline_status NOT NULL DEFAULT 'PENDING_REVIEW',
  due_date          date NOT NULL,
  start_date        date,
  recurrence_months int CHECK (recurrence_months > 0), -- lavado de tanques: 6
  provider_name     text,
  source_page       int,                              -- trazabilidad -> visor PDF
  source_quote      text,                             -- frase literal de donde salió la fecha
  confidence        numeric(3,2) CHECK (confidence BETWEEN 0 AND 1),
  reminder_days     int[] NOT NULL DEFAULT '{30,15,7,1}',
  reviewed_by       uuid REFERENCES users(id) ON DELETE SET NULL,
  reviewed_at       timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX deadlines_calendar_idx ON deadlines (tenant_id, due_date) WHERE status IN ('PENDING_REVIEW', 'ACTIVE');

-- Idempotencia del envío de recordatorios (Celery beat diario)
CREATE TABLE deadline_notifications (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL,
  deadline_id  uuid NOT NULL,
  notify_on    date NOT NULL,
  channel      text NOT NULL DEFAULT 'email',
  sent_at      timestamptz,
  UNIQUE (deadline_id, notify_on, channel),
  FOREIGN KEY (tenant_id, deadline_id) REFERENCES deadlines(tenant_id, id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------------------
-- 6. Comparador de cotizaciones
-- -----------------------------------------------------------------------------
CREATE TABLE quote_comparisons (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  created_by      uuid REFERENCES users(id) ON DELETE SET NULL,
  title           text NOT NULL,                      -- "Impermeabilización cubierta torre 2"
  status          job_status NOT NULL DEFAULT 'PENDING',
  result          jsonb,                              -- tabla normalizada (filas = criterios)
  recommendation  text,
  model           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);

CREATE TABLE quote_comparison_documents (
  tenant_id      uuid NOT NULL,
  comparison_id  uuid NOT NULL,
  document_id    uuid NOT NULL,
  provider_name  text,
  extracted      jsonb,   -- {total, currency, items[], warranty_months, delivery_days, validity_date, ...}
  PRIMARY KEY (comparison_id, document_id),
  FOREIGN KEY (tenant_id, comparison_id) REFERENCES quote_comparisons(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, document_id)   REFERENCES documents(tenant_id, id)         ON DELETE CASCADE
);

-- -----------------------------------------------------------------------------
-- 7. Resumidor de actas de asamblea
-- -----------------------------------------------------------------------------
CREATE TABLE minutes_summaries (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL,
  document_id     uuid NOT NULL UNIQUE,
  assembly_type   text,                               -- ordinaria / extraordinaria
  assembly_date   date,
  quorum_pct      numeric(5,2),
  summary         text,
  agreements      jsonb NOT NULL DEFAULT '[]',        -- [{text, approved, source_page}]
  votes           jsonb NOT NULL DEFAULT '[]',        -- [{topic, yes_pct, no_pct, abstain_pct, source_page}]
  model           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id) ON DELETE CASCADE
);

-- Tareas normalizadas (no JSONB) porque se filtran/actualizan en el dashboard
CREATE TABLE action_items (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL,
  minutes_summary_id  uuid NOT NULL,
  description         text NOT NULL,
  assignee            text,                           -- texto libre: "Consejo de administración"
  due_date            date,
  status              task_status NOT NULL DEFAULT 'OPEN',
  source_page         int,
  created_at          timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, minutes_summary_id) REFERENCES minutes_summaries(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX action_items_open_idx ON action_items (tenant_id, status, due_date);

-- -----------------------------------------------------------------------------
-- 8. Chat / buscador (historial + citas + traza de recuperación para evaluar RAG)
-- -----------------------------------------------------------------------------
CREATE TABLE conversations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
  title       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX conversations_user_idx ON conversations (tenant_id, user_id, created_at DESC);

CREATE TABLE messages (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL,
  conversation_id    uuid NOT NULL,
  role               message_role NOT NULL,
  content            text NOT NULL,
  citations          jsonb NOT NULL DEFAULT '[]',  -- [{n, document_id, document_name, page_number, chunk_id}]
  retrieval_trace    jsonb,                        -- chunk_ids, scores, query reescrita
  model              text,
  prompt_tokens      int,
  completion_tokens  int,
  latency_ms         int,
  created_at         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX messages_conv_idx ON messages (conversation_id, created_at);

CREATE TABLE audit_logs (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
  action       text NOT NULL,                      -- 'document.view', 'document.delete', ...
  entity_type  text,
  entity_id    uuid,
  ip           inet,
  metadata     jsonb NOT NULL DEFAULT '{}',
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_tenant_idx ON audit_logs (tenant_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- 9. Triggers
-- -----------------------------------------------------------------------------
CREATE TRIGGER trg_tenants_updated   BEFORE UPDATE ON tenants   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_users_updated     BEFORE UPDATE ON users     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_documents_updated BEFORE UPDATE ON documents FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_deadlines_updated BEFORE UPDATE ON deadlines FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Si un admin reclasifica un documento (p.ej. ADMIN -> PUBLIC), los chunks
-- deben cambiar en la MISMA transacción; si no, habría fuga o pérdida de acceso.
CREATE FUNCTION propagate_document_acl() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE document_chunks
     SET access_level = NEW.access_level, category = NEW.category
   WHERE document_id = NEW.id;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_documents_acl
  AFTER UPDATE OF access_level, category ON documents
  FOR EACH ROW
  WHEN (OLD.access_level IS DISTINCT FROM NEW.access_level OR OLD.category IS DISTINCT FROM NEW.category)
  EXECUTE FUNCTION propagate_document_acl();

-- -----------------------------------------------------------------------------
-- 10. Row Level Security (defensa en profundidad)
--     La app se conecta con el rol `app_user` (NO owner). FORCE aplica RLS
--     incluso al owner. Sin `app.tenant_id` seteado, las consultas devuelven 0 filas.
-- -----------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'units', 'memberships', 'documents', 'document_pages', 'document_chunks',
    'processing_jobs', 'deadlines', 'deadline_notifications', 'quote_comparisons',
    'quote_comparison_documents', 'minutes_summaries', 'action_items',
    'conversations', 'messages', 'audit_logs'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id())', t);
  END LOOP;
END $$;

-- En el login aún no hay tenant activo: el usuario debe poder listar SUS
-- membresías para elegir edificio. (Permissive => OR con tenant_isolation)
CREATE POLICY own_memberships ON memberships FOR SELECT USING (user_id = app_user_id());

-- RBAC sobre el contenido: un RESIDENTE solo ve documentos/chunks PUBLIC.
-- Políticas RESTRICTIVE => se combinan con AND sobre tenant_isolation.
CREATE POLICY rbac_documents ON documents AS RESTRICTIVE FOR SELECT
  USING (access_level = 'PUBLIC' OR app_is_admin());
CREATE POLICY rbac_chunks ON document_chunks AS RESTRICTIVE FOR SELECT
  USING (access_level = 'PUBLIC' OR app_is_admin());

-- Escritura de documentos solo para ADMIN / workers
CREATE POLICY rbac_documents_write ON documents AS RESTRICTIVE FOR INSERT WITH CHECK (app_is_admin());
CREATE POLICY rbac_documents_upd   ON documents AS RESTRICTIVE FOR UPDATE USING (app_is_admin());
CREATE POLICY rbac_documents_del   ON documents AS RESTRICTIVE FOR DELETE USING (app_is_admin());

-- Módulos exclusivamente administrativos
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'document_pages', 'processing_jobs', 'deadlines', 'deadline_notifications',
    'quote_comparisons', 'quote_comparison_documents', 'minutes_summaries',
    'action_items'
  ] LOOP
    EXECUTE format('CREATE POLICY admin_only ON %I AS RESTRICTIVE USING (app_is_admin()) WITH CHECK (app_is_admin())', t);
  END LOOP;
END $$;

-- Auditoría append-only: cualquier usuario del tenant puede registrar eventos
-- (p.ej. un residente que abre un documento), solo el admin los lee y NADIE
-- puede modificarlos o borrarlos.
CREATE POLICY audit_read_admin ON audit_logs AS RESTRICTIVE FOR SELECT USING (app_is_admin());
CREATE POLICY audit_no_update  ON audit_logs AS RESTRICTIVE FOR UPDATE USING (false);
CREATE POLICY audit_no_delete  ON audit_logs AS RESTRICTIVE FOR DELETE USING (false);

-- Historial de chat privado por usuario (ni siquiera el admin lee chats ajenos)
CREATE POLICY own_conversations ON conversations AS RESTRICTIVE
  USING (user_id = app_user_id() OR current_setting('app.role', true) = 'SYSTEM');
CREATE POLICY own_messages ON messages AS RESTRICTIVE
  USING (EXISTS (SELECT 1 FROM conversations c WHERE c.id = conversation_id));  -- hereda RLS de conversations

-- -----------------------------------------------------------------------------
-- 11. Búsqueda híbrida (vector + keyword) con Reciprocal Rank Fusion
--     SECURITY INVOKER (default) => RLS se sigue aplicando. Los filtros
--     explícitos son redundantes a propósito (y ayudan al planner).
--     Antes de llamarla, la API ejecuta en la misma tx:
--       SET LOCAL hnsw.ef_search = 100;
--       SET LOCAL hnsw.iterative_scan = relaxed_order;
-- -----------------------------------------------------------------------------
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
