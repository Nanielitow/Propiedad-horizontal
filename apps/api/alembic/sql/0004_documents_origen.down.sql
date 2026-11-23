DROP INDEX IF EXISTS documents_source_ref_idx;
ALTER TABLE documents DROP COLUMN IF EXISTS source_url, DROP COLUMN IF EXISTS source_ref, DROP COLUMN IF EXISTS source;
