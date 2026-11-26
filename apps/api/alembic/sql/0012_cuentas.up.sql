-- =============================================================================
-- 0012 · Cuentas reales: invitaciones, recuperación de clave, dueño de la plataforma y demo por copropiedad
-- =============================================================================
-- Hasta aquí los usuarios solo se creaban por script. Ahora:
--   * El dueño de la plataforma (users.is_platform_admin) crea copropiedades y su primer administrador.
--   * El administrador de cada copropiedad invita a su equipo y a los residentes por correo.
--   * El invitado define su clave con un enlace de un solo uso (account_tokens) y acepta la política de
--     tratamiento de datos (Ley 1581 de 2012).
--   * La demo deja de ser global (DEMO_MODE) y pasa a ser una marca por copropiedad (tenants.is_demo): la
--     app real y los conjuntos de ejemplo conviven en la misma instalación.

-- 1. Usuarios -----------------------------------------------------------------------------------
-- Un invitado existe (para tener membresías) pero aún no tiene clave: no puede iniciar sesión.
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users
  ADD COLUMN is_platform_admin   boolean     NOT NULL DEFAULT false,
  -- Tokens emitidos antes de esta fecha dejan de valer (cambio o recuperación de clave)
  ADD COLUMN sessions_valid_after timestamptz,
  ADD COLUMN terms_accepted_at   timestamptz,
  ADD COLUMN terms_version       text;

-- 2. Demo por copropiedad -----------------------------------------------------------------------
ALTER TABLE tenants ADD COLUMN is_demo boolean NOT NULL DEFAULT false;
-- Los conjuntos de ejemplo existentes (datos ficticios con correos @*.demo)
UPDATE tenants SET is_demo = true WHERE slug IN ('los-pinos', 'torre-central');

-- 3. Enlaces de un solo uso -----------------------------------------------------------------------
-- Solo se guarda el SHA-256 del token: quien lea la base no puede usar los enlaces.
CREATE TABLE account_tokens (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind          text        NOT NULL CHECK (kind IN ('INVITACION', 'RECUPERACION')),
  token_hash    text        NOT NULL UNIQUE,
  tenant_id     uuid        REFERENCES tenants(id) ON DELETE CASCADE,  -- copropiedad que invitó (para el correo)
  created_by_id uuid        REFERENCES users(id) ON DELETE SET NULL,
  expires_at    timestamptz NOT NULL,
  used_at       timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX account_tokens_user_idx ON account_tokens (user_id, kind) WHERE used_at IS NULL;

-- 4. Resumen para el panel de la plataforma ----------------------------------------------------
-- El dueño no pertenece a cada copropiedad: RLS le ocultaría las unidades. Solo conteos, sin datos personales.
CREATE FUNCTION plataforma_resumen()
RETURNS TABLE (tenant_id uuid, unidades bigint, usuarios bigint, administradores bigint, invitaciones_pendientes bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT t.id,
         (SELECT count(*) FROM units u WHERE u.tenant_id = t.id),
         (SELECT count(*) FROM memberships m WHERE m.tenant_id = t.id),
         (SELECT count(*) FROM memberships m WHERE m.tenant_id = t.id AND m.role = 'ADMIN'),
         (SELECT count(*) FROM memberships m JOIN users x ON x.id = m.user_id
           WHERE m.tenant_id = t.id AND x.password_hash IS NULL)
    FROM tenants t
   WHERE t.deleted_at IS NULL
     AND EXISTS (SELECT 1 FROM users p WHERE p.id = app_user_id() AND p.is_platform_admin AND p.is_active)
$$;
REVOKE ALL ON FUNCTION plataforma_resumen() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plataforma_resumen() TO app_user;
