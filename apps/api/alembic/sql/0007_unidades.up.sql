-- =============================================================================
--  0007 · Unidades, copropietarios, residentes y vehículos
--  Diseño: docs/UNIDADES.md
--
--  Amplía `units` (0001) en vez de crear otra tabla: recaudos y memberships ya la
--  referencian. Reutiliza de 0003: app_role(), trg_prohibir_delete(),
--  trg_inmutable(), set_updated_at() y accion_auditoria.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Tipos
-- -----------------------------------------------------------------------------
CREATE TYPE tipo_unidad              AS ENUM ('APARTAMENTO', 'CASA', 'LOCAL', 'OFICINA', 'PARQUEADERO', 'DEPOSITO', 'OTRO');
CREATE TYPE ocupacion_unidad         AS ENUM ('PROPIETARIO', 'ARRENDADA', 'DESOCUPADA', 'SIN_INFORMACION');
CREATE TYPE tipo_documento_identidad AS ENUM ('CC', 'CE', 'NIT', 'PASAPORTE', 'PPT', 'TI');
CREATE TYPE relacion_unidad          AS ENUM ('PROPIETARIO', 'ARRENDATARIO', 'RESIDENTE', 'AUTORIZADO');
CREATE TYPE tipo_vehiculo            AS ENUM ('CARRO', 'MOTO', 'BICICLETA', 'OTRO');

-- -----------------------------------------------------------------------------
-- 2. Unidades (ampliación de la tabla existente)
-- -----------------------------------------------------------------------------
ALTER TABLE units
  ADD COLUMN tipo                   tipo_unidad      NOT NULL DEFAULT 'APARTAMENTO',
  ADD COLUMN unidad_principal_id    uuid,
  ADD COLUMN area_m2                numeric(8,2)     CHECK (area_m2 IS NULL OR area_m2 > 0),
  ADD COLUMN matricula_inmobiliaria text,
  ADD COLUMN ocupacion              ocupacion_unidad NOT NULL DEFAULT 'SIN_INFORMACION',
  ADD COLUMN observaciones          text,
  ADD COLUMN activa                 boolean          NOT NULL DEFAULT true,
  ADD COLUMN created_at             timestamptz      NOT NULL DEFAULT now(),
  ADD COLUMN updated_at             timestamptz      NOT NULL DEFAULT now(),
  ADD CONSTRAINT units_numero_ck      CHECK (btrim(number) <> ''),
  ADD CONSTRAINT units_coeficiente_ck CHECK (coefficient IS NULL OR (coefficient > 0 AND coefficient <= 100)),
  ADD CONSTRAINT units_principal_ck   CHECK (unidad_principal_id IS DISTINCT FROM id),
  ADD CONSTRAINT units_principal_fk   FOREIGN KEY (tenant_id, unidad_principal_id) REFERENCES units(tenant_id, id);

CREATE UNIQUE INDEX units_matricula_idx ON units (tenant_id, matricula_inmobiliaria) WHERE matricula_inmobiliaria IS NOT NULL;
CREATE INDEX units_principal_idx ON units (tenant_id, unidad_principal_id) WHERE unidad_principal_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 3. Directorio de personas (con o sin cuenta en la plataforma)
-- -----------------------------------------------------------------------------
CREATE TABLE personas (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  tipo_documento     tipo_documento_identidad,
  numero_documento   text CHECK (numero_documento IS NULL OR numero_documento ~ '^[A-Z0-9-]{3,20}$'),
  nombre_completo    text NOT NULL CHECK (btrim(nombre_completo) <> ''),
  email              citext,
  telefono           text,
  telefono_alterno   text,
  user_id            uuid REFERENCES users(id) ON DELETE SET NULL,
  autoriza_datos_at  timestamptz,                     -- autorización Ley 1581 de 2012
  notas              text,
  activa             boolean NOT NULL DEFAULT true,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, user_id),
  UNIQUE (tenant_id, tipo_documento, numero_documento),
  -- El número sin tipo (o al revés) no identifica a nadie
  CHECK ((tipo_documento IS NULL) = (numero_documento IS NULL))
);
CREATE INDEX personas_nombre_idx ON personas (tenant_id, lower(nombre_completo));

-- -----------------------------------------------------------------------------
-- 4. Vínculos persona–unidad, con historia (se cierran con fecha_fin, no se borran)
-- -----------------------------------------------------------------------------
CREATE TABLE unidad_personas (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  unidad_id              uuid NOT NULL,
  persona_id             uuid NOT NULL,
  relacion               relacion_unidad NOT NULL,
  porcentaje_propiedad   numeric(5,2) CHECK (porcentaje_propiedad IS NULL OR (porcentaje_propiedad > 0 AND porcentaje_propiedad <= 100)),
  es_contacto_principal  boolean NOT NULL DEFAULT false,
  responsable_pago       boolean NOT NULL DEFAULT false,   -- a quién se le cobra la cuota (cartera)
  reside                 boolean NOT NULL DEFAULT false,
  fecha_inicio           date NOT NULL DEFAULT ((now() AT TIME ZONE 'America/Bogota')::date),
  fecha_fin              date,
  motivo_cierre          text,
  created_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, unidad_id)  REFERENCES units(tenant_id, id),
  FOREIGN KEY (tenant_id, persona_id) REFERENCES personas(tenant_id, id),
  CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio),
  CHECK (porcentaje_propiedad IS NULL OR relacion = 'PROPIETARIO')
);
-- Una persona no repite la misma relación vigente en la misma unidad
CREATE UNIQUE INDEX unidad_personas_vigente_idx ON unidad_personas (unidad_id, persona_id, relacion) WHERE fecha_fin IS NULL;
-- Un solo contacto principal y un solo responsable de pago vigentes por unidad
CREATE UNIQUE INDEX unidad_personas_contacto_idx ON unidad_personas (unidad_id) WHERE fecha_fin IS NULL AND es_contacto_principal;
CREATE UNIQUE INDEX unidad_personas_pago_idx ON unidad_personas (unidad_id) WHERE fecha_fin IS NULL AND responsable_pago;
CREATE INDEX unidad_personas_persona_idx ON unidad_personas (tenant_id, persona_id);

-- -----------------------------------------------------------------------------
-- 5. Vehículos
-- -----------------------------------------------------------------------------
CREATE TABLE vehiculos (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  unidad_id   uuid NOT NULL,
  persona_id  uuid,
  placa       text NOT NULL CHECK (placa ~ '^[A-Z0-9]{3,7}$'),   -- bicicletas: marcación corta
  tipo        tipo_vehiculo NOT NULL DEFAULT 'CARRO',
  marca       text,
  color       text,
  activo      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, unidad_id)  REFERENCES units(tenant_id, id),
  FOREIGN KEY (tenant_id, persona_id) REFERENCES personas(tenant_id, id)
);
CREATE UNIQUE INDEX vehiculos_placa_idx ON vehiculos (tenant_id, placa) WHERE activo;
CREATE INDEX vehiculos_unidad_idx ON vehiculos (tenant_id, unidad_id);

-- -----------------------------------------------------------------------------
-- 6. Bitácora de importaciones y auditoría
-- -----------------------------------------------------------------------------
CREATE TABLE importaciones_unidades (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  usuario_id             uuid REFERENCES users(id) ON DELETE SET NULL,
  archivo_nombre         text NOT NULL,
  sha256                 char(64) NOT NULL,
  filas_leidas           int NOT NULL DEFAULT 0,
  unidades_creadas       int NOT NULL DEFAULT 0,
  unidades_actualizadas  int NOT NULL DEFAULT 0,
  personas_creadas       int NOT NULL DEFAULT 0,
  personas_actualizadas  int NOT NULL DEFAULT 0,
  vinculos_creados       int NOT NULL DEFAULT 0,
  vehiculos_creados      int NOT NULL DEFAULT 0,
  advertencias           jsonb NOT NULL DEFAULT '[]',
  created_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX importaciones_unidades_idx ON importaciones_unidades (tenant_id, created_at DESC);

CREATE TABLE auditoria_unidades (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  entidad             text NOT NULL,          -- 'unidad', 'persona', 'vinculo', 'vehiculo'
  entidad_id          uuid NOT NULL,
  unidad_id           uuid,                   -- para armar el historial de la ficha de la unidad
  usuario_id          uuid,
  accion              accion_auditoria NOT NULL,
  valores_anteriores  jsonb,
  valores_nuevos      jsonb,
  motivo              text,
  fecha_hora          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auditoria_unidades_unidad_idx  ON auditoria_unidades (tenant_id, unidad_id, fecha_hora DESC);
CREATE INDEX auditoria_unidades_entidad_idx ON auditoria_unidades (tenant_id, entidad, entidad_id, fecha_hora DESC);

-- -----------------------------------------------------------------------------
-- 7. Reglas en la base
-- -----------------------------------------------------------------------------

-- 7.1 Anexos de un solo nivel: un anexo no tiene anexos y su principal no es anexo
CREATE FUNCTION trg_units_principal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.unidad_principal_id IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM units WHERE id = NEW.unidad_principal_id AND unidad_principal_id IS NOT NULL) THEN
      RAISE EXCEPTION 'La unidad principal es a su vez un anexo: solo se admite un nivel'
        USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM units WHERE unidad_principal_id = NEW.id) THEN
      RAISE EXCEPTION 'Esta unidad tiene anexos: no puede convertirse en anexo de otra'
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF TG_OP = 'UPDATE' THEN
    NEW.updated_at := now();
  END IF;
  RETURN NEW;
END $$;

-- 7.2 Vínculos: solo se cierran. Las demás columnas se pueden corregir mientras está vigente;
--     uno cerrado es historia y no cambia.
CREATE FUNCTION trg_unidad_personas_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.fecha_fin IS NOT NULL THEN
    RAISE EXCEPTION 'El vínculo ya está cerrado y forma parte del historial'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.unidad_id <> OLD.unidad_id OR NEW.persona_id <> OLD.persona_id OR NEW.tenant_id <> OLD.tenant_id THEN
    RAISE EXCEPTION 'No se puede cambiar la unidad o la persona de un vínculo: ciérrelo y cree otro'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.fecha_fin IS NOT NULL THEN
    -- Al cerrarse deja de ser contacto y responsable de pago (libera los índices únicos)
    NEW.es_contacto_principal := false;
    NEW.responsable_pago := false;
  END IF;
  RETURN NEW;
END $$;

-- 7.3 memberships.unit_id (unidad que ve el residente) se deriva de los vínculos vigentes
--     de la persona que tiene esa cuenta. Prioridad: reside > propietario > arrendatario.
CREATE FUNCTION sincronizar_unidad_membership(p_tenant uuid, p_user uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_unidad uuid;
BEGIN
  IF p_user IS NULL THEN
    RETURN;
  END IF;
  SELECT up.unidad_id INTO v_unidad
    FROM unidad_personas up
    JOIN personas p ON p.id = up.persona_id
   WHERE p.tenant_id = p_tenant AND p.user_id = p_user AND p.activa AND up.fecha_fin IS NULL
   ORDER BY up.reside DESC,
            CASE up.relacion WHEN 'PROPIETARIO' THEN 0 WHEN 'ARRENDATARIO' THEN 1 WHEN 'RESIDENTE' THEN 2 ELSE 3 END,
            up.fecha_inicio, up.created_at
   LIMIT 1;
  UPDATE memberships SET unit_id = v_unidad
   WHERE tenant_id = p_tenant AND user_id = p_user AND unit_id IS DISTINCT FROM v_unidad;
END $$;

CREATE FUNCTION trg_vinculo_sincronizar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM sincronizar_unidad_membership(NEW.tenant_id, (SELECT user_id FROM personas WHERE id = NEW.persona_id));
  RETURN NULL;
END $$;

-- Si cambia la cuenta enlazada o se desactiva la persona, se recalculan la cuenta vieja y la nueva
CREATE FUNCTION trg_persona_sincronizar_after() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.user_id IS NOT NULL AND OLD.user_id IS DISTINCT FROM NEW.user_id THEN
    PERFORM sincronizar_unidad_membership(OLD.tenant_id, OLD.user_id);
  END IF;
  PERFORM sincronizar_unidad_membership(NEW.tenant_id, NEW.user_id);
  RETURN NULL;
END $$;

-- 7.4 Auditoría automática
CREATE FUNCTION trg_auditar_unidades() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_entidad text := TG_ARGV[0];
  v_nuevo jsonb := to_jsonb(NEW) - 'updated_at';
  v_viejo jsonb;
  v_antes jsonb;
  v_despues jsonb;
  v_accion accion_auditoria;
BEGIN
  IF TG_OP = 'INSERT' THEN
    v_accion := 'CREACION';
    v_despues := v_nuevo;
  ELSE
    v_viejo := to_jsonb(OLD) - 'updated_at';
    SELECT jsonb_object_agg(n.key, n.value) INTO v_despues
      FROM jsonb_each(v_nuevo) n WHERE v_viejo -> n.key IS DISTINCT FROM n.value;
    IF v_despues IS NULL THEN
      RETURN NULL;
    END IF;
    SELECT jsonb_object_agg(d.key, v_viejo -> d.key) INTO v_antes FROM jsonb_each(v_despues) d;
    v_accion := CASE
      WHEN (v_despues ->> 'activa') = 'false' OR (v_despues ->> 'activo') = 'false' THEN 'ANULACION'
      WHEN v_despues ? 'fecha_fin' OR v_despues ? 'activa' OR v_despues ? 'activo' THEN 'CAMBIO_ESTADO'
      ELSE 'EDICION' END;
  END IF;

  INSERT INTO auditoria_unidades (tenant_id, entidad, entidad_id, unidad_id, usuario_id, accion,
                                  valores_anteriores, valores_nuevos, motivo)
  VALUES (NEW.tenant_id, v_entidad, NEW.id,
          CASE WHEN v_entidad = 'unidad' THEN NEW.id ELSE (v_nuevo ->> 'unidad_id')::uuid END,
          app_user_id(), v_accion, v_antes, v_despues, nullif(current_setting('app.motivo', true), ''));
  RETURN NULL;
END $$;

-- 7.5 Instalación
CREATE TRIGGER trg_units_principal BEFORE INSERT OR UPDATE ON units FOR EACH ROW EXECUTE FUNCTION trg_units_principal();
CREATE TRIGGER trg_unidad_personas_update BEFORE UPDATE ON unidad_personas
  FOR EACH ROW EXECUTE FUNCTION trg_unidad_personas_update();
CREATE TRIGGER trg_vinculo_sincronizar AFTER INSERT OR UPDATE ON unidad_personas
  FOR EACH ROW EXECUTE FUNCTION trg_vinculo_sincronizar();
CREATE TRIGGER trg_personas_updated BEFORE UPDATE ON personas FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_persona_sincronizar AFTER UPDATE OF user_id, activa ON personas
  FOR EACH ROW EXECUTE FUNCTION trg_persona_sincronizar_after();
CREATE TRIGGER trg_vehiculos_updated BEFORE UPDATE ON vehiculos FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_importaciones_inmutable BEFORE UPDATE ON importaciones_unidades
  FOR EACH ROW EXECUTE FUNCTION trg_inmutable();

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['units', 'personas', 'unidad_personas', 'vehiculos', 'importaciones_unidades', 'auditoria_unidades']
  LOOP
    EXECUTE format('CREATE TRIGGER trg_prohibir_delete BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION trg_prohibir_delete()', t);
  END LOOP;
END $$;

DO $$
DECLARE par text[];
BEGIN
  FOREACH par SLICE 1 IN ARRAY ARRAY[
    ARRAY['units', 'unidad'], ARRAY['personas', 'persona'],
    ARRAY['unidad_personas', 'vinculo'], ARRAY['vehiculos', 'vehiculo']
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER trg_auditar AFTER INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION trg_auditar_unidades(%L)',
      par[1], par[2]);
  END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- 8. Privilegios
-- -----------------------------------------------------------------------------
REVOKE DELETE ON units, personas, unidad_personas, vehiculos, importaciones_unidades, auditoria_unidades FROM app_user;
REVOKE INSERT, UPDATE ON auditoria_unidades FROM app_user;

-- -----------------------------------------------------------------------------
-- 9. Row Level Security por rol
--    El residente ve solo las unidades donde tiene un vínculo vigente (y sus anexos),
--    más la de su membresía. La función es SECURITY DEFINER para no recursar en RLS.
-- -----------------------------------------------------------------------------
CREATE FUNCTION app_unidades_propias() RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  WITH base AS (
    SELECT up.unidad_id AS id
      FROM unidad_personas up JOIN personas p ON p.id = up.persona_id
     WHERE p.tenant_id = app_tenant_id() AND p.user_id = app_user_id() AND p.activa AND up.fecha_fin IS NULL
    UNION
    SELECT unit_id FROM memberships
     WHERE tenant_id = app_tenant_id() AND user_id = app_user_id() AND unit_id IS NOT NULL
  )
  SELECT id FROM base
  UNION
  SELECT u.id FROM units u JOIN base b ON u.unidad_principal_id = b.id WHERE u.tenant_id = app_tenant_id()
$$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['personas', 'unidad_personas', 'vehiculos', 'importaciones_unidades', 'auditoria_unidades']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id())', t);
  END LOOP;
END $$;

-- Lectura (RESTRICTIVE: AND con tenant_isolation)
CREATE POLICY rbac_leer ON units AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'CONSEJO', 'MANTENIMIENTO', 'SYSTEM')
  OR id IN (SELECT app_unidades_propias()));

CREATE POLICY rbac_leer ON personas AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'SYSTEM')
  OR user_id = app_user_id()
  OR id IN (SELECT persona_id FROM unidad_personas
             WHERE fecha_fin IS NULL AND unidad_id IN (SELECT app_unidades_propias())));

CREATE POLICY rbac_leer ON unidad_personas AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'SYSTEM')
  OR (fecha_fin IS NULL AND unidad_id IN (SELECT app_unidades_propias())));

CREATE POLICY rbac_leer ON vehiculos AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM')
  OR unidad_id IN (SELECT app_unidades_propias()));

CREATE POLICY rbac_leer ON importaciones_unidades AS RESTRICTIVE FOR SELECT USING (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_leer ON auditoria_unidades AS RESTRICTIVE FOR SELECT USING (app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM'));

-- Escritura: solo administración (y tareas del sistema)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['units', 'personas', 'unidad_personas', 'vehiculos', 'importaciones_unidades']
  LOOP
    EXECUTE format('CREATE POLICY rbac_crear ON %I AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN (''ADMIN'', ''SYSTEM''))', t);
    EXECUTE format('CREATE POLICY rbac_editar ON %I AS RESTRICTIVE FOR UPDATE USING (app_role() IN (''ADMIN'', ''SYSTEM''))', t);
  END LOOP;
END $$;
