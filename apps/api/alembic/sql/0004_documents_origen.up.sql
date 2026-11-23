-- 0004 · Origen de los documentos (subida directa o importación desde Google Drive)
ALTER TABLE documents
  ADD COLUMN source     text NOT NULL DEFAULT 'UPLOAD' CHECK (source IN ('UPLOAD', 'GOOGLE_DRIVE')),
  ADD COLUMN source_ref text,   -- id del archivo en Drive
  ADD COLUMN source_url text;   -- enlace para abrir el original en Drive

-- "Este archivo de Drive ya se importó": búsqueda por id externo
CREATE INDEX documents_source_ref_idx ON documents (tenant_id, source, source_ref) WHERE source_ref IS NOT NULL;
