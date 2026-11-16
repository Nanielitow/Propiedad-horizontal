-- Reversa de 0001. Las extensiones (vector, unaccent, citext) se conservan.
DROP FUNCTION IF EXISTS hybrid_search(uuid, boolean, vector, text, int, document_category[], int);

DROP TABLE IF EXISTS
  audit_logs, messages, conversations, action_items, minutes_summaries,
  quote_comparison_documents, quote_comparisons, deadline_notifications, deadlines,
  processing_jobs, document_chunks, document_pages, documents, memberships, units,
  users, tenants
CASCADE;

DROP FUNCTION IF EXISTS propagate_document_acl();
DROP FUNCTION IF EXISTS set_updated_at();
DROP FUNCTION IF EXISTS app_is_admin();
DROP FUNCTION IF EXISTS app_user_id();
DROP FUNCTION IF EXISTS app_tenant_id();

DROP TYPE IF EXISTS
  message_role, task_status, deadline_status, deadline_type, job_status, job_type,
  extraction_method, document_status, document_category, access_level, user_role;

DROP TEXT SEARCH CONFIGURATION IF EXISTS es_unaccent;
