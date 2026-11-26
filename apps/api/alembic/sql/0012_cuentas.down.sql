-- Reversa de 0012. Los usuarios invitados que nunca activaron su cuenta se borran (no tienen clave).
DROP FUNCTION IF EXISTS plataforma_resumen();
DROP TABLE IF EXISTS account_tokens;
ALTER TABLE tenants DROP COLUMN IF EXISTS is_demo;
DELETE FROM users WHERE password_hash IS NULL;
ALTER TABLE users
  DROP COLUMN IF EXISTS terms_version,
  DROP COLUMN IF EXISTS terms_accepted_at,
  DROP COLUMN IF EXISTS sessions_valid_after,
  DROP COLUMN IF EXISTS is_platform_admin;
ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;
