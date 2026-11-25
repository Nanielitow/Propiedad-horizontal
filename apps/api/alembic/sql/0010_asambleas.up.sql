-- =============================================================================
--  0010 · Asambleas de copropietarios (Ley 675 de 2001)
--  Diseño: docs/ASAMBLEAS.md
--
--  Padrón (foto de unidades y coeficientes al abrir), asistencia con poderes,
--  quórum en vivo, orden del día con votaciones ponderadas por coeficiente y
--  resultados según la mayoría que exige cada punto. Los votos no se cambian ni
--  se borran; la asamblea cerrada queda inmutable.
--
--  Reutiliza: app_role(), app_unidades_propias(), next_consecutivo(),
--  trg_prohibir_delete(), trg_inmutable(), accion_auditoria.
-- =============================================================================

CREATE TYPE tipo_asamblea       AS ENUM ('ORDINARIA', 'EXTRAORDINARIA');
CREATE TYPE modalidad_asamblea  AS ENUM ('PRESENCIAL', 'VIRTUAL', 'MIXTA');
CREATE TYPE convocatoria_asamblea AS ENUM ('PRIMERA', 'SEGUNDA');
CREATE TYPE estado_asamblea     AS ENUM ('PROGRAMADA', 'EN_CURSO', 'CERRADA', 'CANCELADA');
CREATE TYPE tipo_asistente      AS ENUM ('PROPIETARIO', 'APODERADO');
CREATE TYPE tipo_punto          AS ENUM ('INFORMATIVO', 'VOTACION');
CREATE TYPE mayoria_punto       AS ENUM ('SIMPLE', 'CALIFICADA_70', 'ELECCION');
CREATE TYPE estado_punto        AS ENUM ('PENDIENTE', 'EN_VOTACION', 'CERRADO');

-- -----------------------------------------------------------------------------
-- 1. Asambleas
-- -----------------------------------------------------------------------------
CREATE TABLE asambleas (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo                 bigint NOT NULL,
  titulo                      text NOT NULL CHECK (length(btrim(titulo)) >= 5),
  tipo                        tipo_asamblea NOT NULL DEFAULT 'ORDINARIA',
  modalidad                   modalidad_asamblea NOT NULL DEFAULT 'PRESENCIAL',
  convocatoria                convocatoria_asamblea NOT NULL DEFAULT 'PRIMERA',
  fecha_hora                  timestamptz NOT NULL,
  lugar                       text,
  estado                      estado_asamblea NOT NULL DEFAULT 'PROGRAMADA',
  max_poderes_por_apoderado   int NOT NULL DEFAULT 2 CHECK (max_poderes_por_apoderado BETWEEN 1 AND 50),
  circular_id                 uuid,                       -- convocatoria publicada como circular
  presidente                  text,
  secretario                  text,
  coeficiente_total           numeric(9,4),               -- del padrón, al abrir
  abierta_at                  timestamptz,
  cerrada_at                  timestamptz,
  acta_document_id            uuid,                       -- acta en el módulo de documentos
  observaciones               text,
  creada_por_id               uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at                  timestamptz NOT NULL DEFAULT now(),
  updated_at                  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, consecutivo),
  FOREIGN KEY (tenant_id, circular_id)      REFERENCES circulares(tenant_id, id),
  FOREIGN KEY (tenant_id, acta_document_id) REFERENCES documents(tenant_id, id),
  CHECK ((estado IN ('EN_CURSO', 'CERRADA')) = (abierta_at IS NOT NULL) OR estado = 'CANCELADA'),
  CHECK ((estado = 'CERRADA') = (cerrada_at IS NOT NULL))
);

-- -----------------------------------------------------------------------------
-- 2. Padrón: una fila por unidad con coeficiente, fijada al abrir la asamblea
-- -----------------------------------------------------------------------------
CREATE TABLE asamblea_padron (
  asamblea_id         uuid NOT NULL,
  unidad_id           uuid NOT NULL,
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  etiqueta            text NOT NULL,
  coeficiente         numeric(7,4) NOT NULL CHECK (coeficiente > 0),
  propietarios        text,                 -- nombres, para el acta
  votante_user_ids    uuid[] NOT NULL DEFAULT '{}',   -- propietarios con cuenta (votan desde el portal)
  al_dia              boolean,              -- informativo (cartera); no quita el voto
  PRIMARY KEY (asamblea_id, unidad_id),
  FOREIGN KEY (tenant_id, asamblea_id) REFERENCES asambleas(tenant_id, id),
  FOREIGN KEY (tenant_id, unidad_id)   REFERENCES units(tenant_id, id)
);

-- -----------------------------------------------------------------------------
-- 3. Asistencia (una vigente por unidad; un retiro cierra la fila)
-- -----------------------------------------------------------------------------
CREATE TABLE asamblea_asistencias (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  asamblea_id        uuid NOT NULL,
  unidad_id          uuid NOT NULL,
  tipo               tipo_asistente NOT NULL,
  asistente_nombre   text NOT NULL CHECK (length(btrim(asistente_nombre)) >= 3),
  asistente_documento text,
  user_id            uuid REFERENCES users(id) ON DELETE SET NULL,   -- si se registró desde el portal
  virtual            boolean NOT NULL DEFAULT false,
  poder_soporte_key  text,                  -- foto o PDF del poder firmado
  registrada_por_id  uuid REFERENCES users(id) ON DELETE SET NULL,
  llegada_at         timestamptz NOT NULL DEFAULT now(),
  retiro_at          timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (asamblea_id, unidad_id) REFERENCES asamblea_padron(asamblea_id, unidad_id),
  CHECK (retiro_at IS NULL OR retiro_at >= llegada_at),
  CHECK (tipo <> 'APODERADO' OR asistente_documento IS NOT NULL)
);
CREATE UNIQUE INDEX asamblea_asistencia_vigente_idx ON asamblea_asistencias (asamblea_id, unidad_id) WHERE retiro_at IS NULL;
CREATE INDEX asamblea_asistencia_apoderado_idx ON asamblea_asistencias (asamblea_id, asistente_documento) WHERE retiro_at IS NULL AND tipo = 'APODERADO';

-- -----------------------------------------------------------------------------
-- 4. Orden del día y votos
-- -----------------------------------------------------------------------------
CREATE TABLE asamblea_puntos (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  asamblea_id              uuid NOT NULL,
  orden                    int NOT NULL CHECK (orden > 0),
  titulo                   text NOT NULL CHECK (length(btrim(titulo)) >= 3),
  descripcion              text,
  tipo                     tipo_punto NOT NULL DEFAULT 'INFORMATIVO',
  mayoria                  mayoria_punto,
  opciones                 text[] NOT NULL DEFAULT '{}',
  estado                   estado_punto NOT NULL DEFAULT 'PENDIENTE',
  abierto_at               timestamptz,
  cerrado_at               timestamptz,
  coeficiente_presente     numeric(9,4),     -- quórum al cerrar la votación
  resultado                jsonb,            -- {opcion: coeficiente} + aprobado/ganador
  aprobado                 boolean,
  conclusion               text,             -- texto para el acta
  UNIQUE (tenant_id, id),
  UNIQUE (asamblea_id, orden) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id, asamblea_id) REFERENCES asambleas(tenant_id, id),
  CHECK ((tipo = 'VOTACION') = (mayoria IS NOT NULL)),
  CHECK (tipo = 'INFORMATIVO' OR cardinality(opciones) >= 2)
);

CREATE TABLE asamblea_votos (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  asamblea_id    uuid NOT NULL,
  punto_id       uuid NOT NULL,
  unidad_id      uuid NOT NULL,
  opcion         text NOT NULL,
  coeficiente    numeric(7,4) NOT NULL,
  emitido_por_id uuid REFERENCES users(id) ON DELETE SET NULL,   -- residente (portal) o personal (en sala)
  desde_portal   boolean NOT NULL DEFAULT false,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (punto_id, unidad_id),                                   -- un voto por unidad y punto
  FOREIGN KEY (tenant_id, punto_id)    REFERENCES asamblea_puntos(tenant_id, id),
  FOREIGN KEY (asamblea_id, unidad_id) REFERENCES asamblea_padron(asamblea_id, unidad_id)
);
CREATE INDEX asamblea_votos_punto_idx ON asamblea_votos (punto_id);

-- -----------------------------------------------------------------------------
-- 5. Reglas en la base
-- -----------------------------------------------------------------------------
CREATE FUNCTION trg_asamblea_consecutivo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.consecutivo := next_consecutivo(NEW.tenant_id, 'asamblea');
  RETURN NEW;
END $$;

-- Flujo y cierre: una asamblea cerrada o cancelada no cambia (salvo enlazar el acta)
CREATE FUNCTION trg_asambleas_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_de text := OLD.estado::text; v_a text := NEW.estado::text;
BEGIN
  IF v_de IN ('CERRADA', 'CANCELADA') THEN
    IF (to_jsonb(NEW) - 'acta_document_id' - 'updated_at') IS DISTINCT FROM (to_jsonb(OLD) - 'acta_document_id' - 'updated_at') THEN
      RAISE EXCEPTION 'La asamblea está %: no se modifica', lower(v_de) USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  IF v_a <> v_de AND NOT (
       (v_de = 'PROGRAMADA' AND v_a IN ('EN_CURSO', 'CANCELADA'))
    OR (v_de = 'EN_CURSO' AND v_a = 'CERRADA')
  ) THEN
    RAISE EXCEPTION 'No se puede pasar una asamblea de % a %', v_de, v_a USING ERRCODE = 'check_violation';
  END IF;
  IF v_de = 'EN_CURSO' AND (NEW.convocatoria <> OLD.convocatoria OR NEW.coeficiente_total IS DISTINCT FROM OLD.coeficiente_total) THEN
    RAISE EXCEPTION 'Con la asamblea en curso no cambia la convocatoria ni el padrón' USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- Asistencia, puntos y votos solo con la asamblea en curso (el padrón se arma al abrir)
CREATE FUNCTION trg_asamblea_en_curso() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_estado text;
BEGIN
  SELECT estado::text INTO v_estado FROM asambleas WHERE id = NEW.asamblea_id;
  IF TG_TABLE_NAME = 'asamblea_puntos' THEN
    IF v_estado IN ('CERRADA', 'CANCELADA') THEN
      RAISE EXCEPTION 'La asamblea está %', lower(v_estado) USING ERRCODE = 'insufficient_privilege';
    END IF;
  ELSIF TG_TABLE_NAME = 'asamblea_padron' THEN
    -- Se arma al abrir, en la misma transacción y antes de pasar a EN_CURSO
    IF v_estado <> 'PROGRAMADA' THEN
      RAISE EXCEPTION 'El padrón ya está fijado' USING ERRCODE = 'insufficient_privilege';
    END IF;
  ELSIF v_estado <> 'EN_CURSO' THEN
    RAISE EXCEPTION 'La asamblea no está en curso' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

-- Un punto cerrado no cambia; un voto solo entra con el punto en votación y una asistencia vigente
CREATE FUNCTION trg_puntos_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.estado::text = 'EN_VOTACION' AND OLD.estado::text = 'PENDIENTE'
     AND (SELECT estado::text FROM asambleas WHERE id = NEW.asamblea_id) <> 'EN_CURSO' THEN
    RAISE EXCEPTION 'Solo se vota con la asamblea en curso' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.estado::text = 'CERRADO' THEN
    IF (to_jsonb(NEW) - 'conclusion') IS DISTINCT FROM (to_jsonb(OLD) - 'conclusion') THEN
      RAISE EXCEPTION 'La votación de este punto ya se cerró' USING ERRCODE = 'insufficient_privilege';
    END IF;
  ELSIF OLD.estado::text = 'EN_VOTACION' AND NEW.estado::text = 'EN_VOTACION'
     AND (NEW.opciones <> OLD.opciones OR NEW.mayoria IS DISTINCT FROM OLD.mayoria OR NEW.tipo <> OLD.tipo) THEN
    RAISE EXCEPTION 'No se cambian las opciones ni la mayoría con la votación abierta' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.estado::text <> OLD.estado::text AND NOT (
       (OLD.estado::text = 'PENDIENTE' AND NEW.estado::text IN ('EN_VOTACION', 'CERRADO'))
    OR (OLD.estado::text = 'EN_VOTACION' AND NEW.estado::text = 'CERRADO')
  ) THEN
    RAISE EXCEPTION 'Paso de estado no válido para el punto' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION trg_votos_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_estado text; v_opciones text[]; v_coef numeric;
BEGIN
  SELECT estado::text, opciones INTO v_estado, v_opciones FROM asamblea_puntos WHERE id = NEW.punto_id AND asamblea_id = NEW.asamblea_id;
  IF v_estado IS DISTINCT FROM 'EN_VOTACION' THEN
    RAISE EXCEPTION 'La votación de este punto no está abierta' USING ERRCODE = 'check_violation';
  END IF;
  IF NOT NEW.opcion = ANY (v_opciones) THEN
    RAISE EXCEPTION 'Opción no válida: %', NEW.opcion USING ERRCODE = 'check_violation';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM asamblea_asistencias WHERE asamblea_id = NEW.asamblea_id AND unidad_id = NEW.unidad_id AND retiro_at IS NULL) THEN
    RAISE EXCEPTION 'La unidad no está registrada como presente' USING ERRCODE = 'check_violation';
  END IF;
  SELECT coeficiente INTO v_coef FROM asamblea_padron WHERE asamblea_id = NEW.asamblea_id AND unidad_id = NEW.unidad_id;
  NEW.coeficiente := v_coef;   -- el peso lo fija el padrón, no quien vota
  RETURN NEW;
END $$;

CREATE TRIGGER trg_asamblea_consecutivo BEFORE INSERT ON asambleas FOR EACH ROW EXECUTE FUNCTION trg_asamblea_consecutivo();
CREATE TRIGGER trg_asambleas_update BEFORE UPDATE ON asambleas FOR EACH ROW EXECUTE FUNCTION trg_asambleas_update();
CREATE TRIGGER trg_asistencia_en_curso BEFORE INSERT OR UPDATE ON asamblea_asistencias FOR EACH ROW EXECUTE FUNCTION trg_asamblea_en_curso();
CREATE TRIGGER trg_puntos_en_curso BEFORE INSERT OR UPDATE ON asamblea_puntos FOR EACH ROW EXECUTE FUNCTION trg_asamblea_en_curso();
CREATE TRIGGER trg_puntos_update BEFORE UPDATE ON asamblea_puntos FOR EACH ROW EXECUTE FUNCTION trg_puntos_update();
CREATE TRIGGER trg_votos_insert BEFORE INSERT ON asamblea_votos FOR EACH ROW EXECUTE FUNCTION trg_votos_insert();
CREATE TRIGGER trg_votos_inmutable BEFORE UPDATE ON asamblea_votos FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_padron_inmutable BEFORE UPDATE ON asamblea_padron FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_padron_en_curso BEFORE INSERT ON asamblea_padron FOR EACH ROW EXECUTE FUNCTION trg_asamblea_en_curso();

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['asambleas', 'asamblea_padron', 'asamblea_asistencias', 'asamblea_votos'] LOOP
    EXECUTE format('CREATE TRIGGER trg_prohibir_delete BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION trg_prohibir_delete()', t);
  END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- 6. Privilegios y RLS
--    Personal: ADMIN gestiona; AUXILIAR registra asistencia y votos en sala;
--    CONSEJO y CONTABILIDAD consultan. RESIDENTE: ve las asambleas convocadas,
--    el padrón y resultados, y registra asistencia/votos de SUS unidades.
-- -----------------------------------------------------------------------------
REVOKE DELETE ON asambleas, asamblea_padron, asamblea_asistencias, asamblea_votos FROM app_user;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['asambleas', 'asamblea_padron', 'asamblea_asistencias', 'asamblea_puntos', 'asamblea_votos'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id())', t);
  END LOOP;
END $$;

-- Lectura: toda la copropiedad (la asamblea es de todos los copropietarios); asistencias y votos
-- individuales solo para el personal y para la unidad propia (el residente ve totales por la API)
CREATE POLICY rbac_leer ON asambleas AS RESTRICTIVE FOR SELECT USING (true);
CREATE POLICY rbac_leer ON asamblea_puntos AS RESTRICTIVE FOR SELECT USING (true);
CREATE POLICY rbac_leer ON asamblea_padron AS RESTRICTIVE FOR SELECT USING (true);
CREATE POLICY rbac_leer ON asamblea_asistencias AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'CONSEJO', 'CONTABILIDAD', 'SYSTEM') OR unidad_id IN (SELECT app_unidades_propias()));
CREATE POLICY rbac_leer ON asamblea_votos AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'CONSEJO', 'CONTABILIDAD', 'SYSTEM') OR unidad_id IN (SELECT app_unidades_propias()));

CREATE POLICY rbac_crear ON asambleas AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON asambleas AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_crear ON asamblea_padron AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_crear ON asamblea_puntos AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON asamblea_puntos AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_borrar ON asamblea_puntos AS RESTRICTIVE FOR DELETE USING (app_role() IN ('ADMIN', 'SYSTEM') AND estado = 'PENDIENTE');
CREATE POLICY rbac_crear ON asamblea_asistencias AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM')
  OR (app_role() = 'RESIDENTE' AND virtual AND tipo = 'PROPIETARIO' AND user_id = app_user_id() AND unidad_id IN (SELECT app_unidades_propias())));
CREATE POLICY rbac_editar ON asamblea_asistencias AS RESTRICTIVE FOR UPDATE USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM') OR (app_role() = 'RESIDENTE' AND user_id = app_user_id()));
CREATE POLICY rbac_crear ON asamblea_votos AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM')
  OR (app_role() = 'RESIDENTE' AND desde_portal AND emitido_por_id = app_user_id()
      AND EXISTS (SELECT 1 FROM asamblea_padron p
                   WHERE p.asamblea_id = asamblea_votos.asamblea_id AND p.unidad_id = asamblea_votos.unidad_id
                     AND app_user_id() = ANY (p.votante_user_ids))));
