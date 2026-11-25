-- =============================================================================
--  0009 · Portal del residente: PQRS, circulares y reservas hechas por el residente
--  Diseño: docs/PORTAL.md
--
--  Reutiliza: app_role(), app_unidades_propias(), next_consecutivo(),
--  trg_prohibir_delete(), trg_inmutable(), set_updated_at(), accion_auditoria.
--  Las reservas y las zonas sociales existen desde 0003 (recaudos): aquí se amplían.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Tipos
-- -----------------------------------------------------------------------------
CREATE TYPE tipo_pqrs       AS ENUM ('PETICION', 'QUEJA', 'RECLAMO', 'SUGERENCIA', 'FELICITACION');
CREATE TYPE categoria_pqrs  AS ENUM ('ADMINISTRACION', 'CONVIVENCIA', 'MANTENIMIENTO', 'SEGURIDAD', 'ASEO',
                                     'PARQUEADEROS', 'ZONAS_COMUNES', 'CARTERA', 'OTRO');
CREATE TYPE estado_pqrs     AS ENUM ('RADICADA', 'EN_TRAMITE', 'RESPONDIDA', 'CERRADA', 'DESISTIDA');
CREATE TYPE canal_pqrs      AS ENUM ('PORTAL', 'PRESENCIAL', 'CORREO', 'TELEFONO');
CREATE TYPE prioridad_pqrs  AS ENUM ('BAJA', 'MEDIA', 'ALTA');
CREATE TYPE categoria_circular AS ENUM ('INFORMATIVA', 'CONVOCATORIA', 'SERVICIOS', 'MANTENIMIENTO', 'SEGURIDAD',
                                        'CARTERA', 'CONVIVENCIA');
CREATE TYPE estado_circular AS ENUM ('BORRADOR', 'PUBLICADA', 'ARCHIVADA');

-- Una reserva puede ser rechazada por la administración (no se usa en esta misma migración)
ALTER TYPE estado_reserva ADD VALUE IF NOT EXISTS 'RECHAZADA';

-- -----------------------------------------------------------------------------
-- 2. PQRS
-- -----------------------------------------------------------------------------
CREATE TABLE pqrs (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo              bigint NOT NULL,                -- radicado sin huecos (trigger)
  tipo                     tipo_pqrs NOT NULL,
  categoria                categoria_pqrs NOT NULL,
  asunto                   text NOT NULL CHECK (length(btrim(asunto)) >= 5),
  descripcion              text NOT NULL CHECK (length(btrim(descripcion)) >= 10),
  unidad_id                uuid,
  canal                    canal_pqrs NOT NULL DEFAULT 'PORTAL',
  estado                   estado_pqrs NOT NULL DEFAULT 'RADICADA',
  prioridad                prioridad_pqrs NOT NULL DEFAULT 'MEDIA',
  radicado_por_id          uuid NOT NULL REFERENCES users(id),     -- quien la registró en la plataforma
  solicitante_nombre       text NOT NULL,                          -- a nombre de quién (puede ser presencial)
  solicitante_contacto     text,
  asignado_a_id            uuid REFERENCES users(id) ON DELETE SET NULL,
  fecha_limite             date NOT NULL,                          -- 15 días hábiles por defecto
  respondida_at            timestamptz,
  cerrada_at               timestamptz,
  calificacion             int CHECK (calificacion IS NULL OR calificacion BETWEEN 1 AND 5),
  comentario_calificacion  text,
  adjuntos                 jsonb NOT NULL DEFAULT '[]',            -- [{"key","nombre","tipo"}]
  novedad_id               uuid,                                   -- si se convirtió en novedad de mantenimiento
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, consecutivo),
  FOREIGN KEY (tenant_id, unidad_id)  REFERENCES units(tenant_id, id),
  FOREIGN KEY (tenant_id, novedad_id) REFERENCES novedades(tenant_id, id),
  CHECK (calificacion IS NULL OR estado IN ('RESPONDIDA', 'CERRADA'))
);
CREATE INDEX pqrs_bandeja_idx ON pqrs (tenant_id, estado, fecha_limite);
CREATE INDEX pqrs_radicador_idx ON pqrs (tenant_id, radicado_por_id);

CREATE TABLE pqrs_mensajes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  pqrs_id     uuid NOT NULL,
  autor_id    uuid NOT NULL REFERENCES users(id),
  autor_rol   text NOT NULL,
  texto       text NOT NULL CHECK (length(btrim(texto)) >= 1),
  interno     boolean NOT NULL DEFAULT false,   -- nota del personal: el residente no la ve (RLS)
  es_respuesta boolean NOT NULL DEFAULT false,  -- respuesta formal de la administración
  adjuntos    jsonb NOT NULL DEFAULT '[]',
  created_at  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, pqrs_id) REFERENCES pqrs(tenant_id, id),
  CHECK (NOT (interno AND es_respuesta))
);
CREATE INDEX pqrs_mensajes_idx ON pqrs_mensajes (pqrs_id, created_at);

-- -----------------------------------------------------------------------------
-- 3. Circulares
-- -----------------------------------------------------------------------------
CREATE TABLE circulares (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo      bigint,                         -- se asigna al publicar
  titulo           text NOT NULL CHECK (length(btrim(titulo)) >= 3),
  cuerpo           text NOT NULL CHECK (length(btrim(cuerpo)) >= 10),   -- markdown
  categoria        categoria_circular NOT NULL DEFAULT 'INFORMATIVA',
  importante       boolean NOT NULL DEFAULT false,  -- pide acuse de lectura y se destaca
  torres           text[] NOT NULL DEFAULT '{}',    -- vacío = toda la copropiedad
  document_id      uuid,                            -- PDF adjunto del módulo de documentos
  estado           estado_circular NOT NULL DEFAULT 'BORRADOR',
  enviar_correo    boolean NOT NULL DEFAULT true,
  publicada_at     timestamptz,
  publicada_por_id uuid REFERENCES users(id) ON DELETE SET NULL,
  vigente_hasta    date,
  correos_enviados int NOT NULL DEFAULT 0,
  creada_por_id    uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id),
  CHECK ((estado = 'BORRADOR') = (publicada_at IS NULL)),
  CHECK ((consecutivo IS NULL) = (publicada_at IS NULL))
);
CREATE UNIQUE INDEX circulares_consecutivo_idx ON circulares (tenant_id, consecutivo) WHERE consecutivo IS NOT NULL;
CREATE INDEX circulares_publicadas_idx ON circulares (tenant_id, publicada_at DESC) WHERE estado = 'PUBLICADA';

CREATE TABLE circular_lecturas (
  circular_id  uuid NOT NULL,
  user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  leida_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (circular_id, user_id),
  FOREIGN KEY (tenant_id, circular_id) REFERENCES circulares(tenant_id, id)
);

-- -----------------------------------------------------------------------------
-- 4. Zonas sociales y reservas (ampliación de 0003)
-- -----------------------------------------------------------------------------
ALTER TABLE zonas_sociales
  ADD COLUMN descripcion              text,
  ADD COLUMN capacidad                int CHECK (capacidad IS NULL OR capacidad > 0),
  ADD COLUMN reglas                   text,
  ADD COLUMN hora_apertura            time NOT NULL DEFAULT '08:00',
  ADD COLUMN hora_cierre              time NOT NULL DEFAULT '22:00',
  ADD COLUMN anticipacion_min_dias    int NOT NULL DEFAULT 2 CHECK (anticipacion_min_dias BETWEEN 0 AND 60),
  ADD COLUMN anticipacion_max_dias    int NOT NULL DEFAULT 60 CHECK (anticipacion_max_dias BETWEEN 1 AND 365),
  ADD COLUMN max_reservas_mes_unidad  int NOT NULL DEFAULT 2 CHECK (max_reservas_mes_unidad BETWEEN 1 AND 31),
  ADD COLUMN requiere_paz_y_salvo     boolean NOT NULL DEFAULT true,
  ADD COLUMN requiere_aprobacion      boolean NOT NULL DEFAULT true,
  ADD COLUMN reservable_residentes    boolean NOT NULL DEFAULT true,
  ADD CONSTRAINT zonas_horario_ck CHECK (hora_cierre > hora_apertura),
  ADD CONSTRAINT zonas_anticipacion_ck CHECK (anticipacion_max_dias > anticipacion_min_dias);

ALTER TABLE reservas
  ADD COLUMN numero_asistentes     int CHECK (numero_asistentes IS NULL OR numero_asistentes > 0),
  ADD COLUMN solicitada_en_portal  boolean NOT NULL DEFAULT false,
  ADD COLUMN decidida_por_id       uuid REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN decidida_at           timestamptz,
  ADD COLUMN motivo_decision       text,         -- motivo del rechazo o de la cancelación
  ADD COLUMN updated_at            timestamptz NOT NULL DEFAULT now();

-- Disponibilidad sin datos personales: el residente ve que una franja está ocupada, no por quién
CREATE FUNCTION disponibilidad_zona(p_zona uuid, p_desde date, p_hasta date)
RETURNS TABLE (fecha_evento date, hora_inicio time, hora_fin time, propia boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT r.fecha_evento, r.hora_inicio, r.hora_fin, coalesce(r.unidad_id IN (SELECT app_unidades_propias()), false)
    FROM reservas r
   WHERE r.tenant_id = app_tenant_id() AND r.zona_id = p_zona
     AND r.fecha_evento BETWEEN p_desde AND p_hasta
     AND r.estado::text IN ('SOLICITADA', 'CONFIRMADA')
   ORDER BY r.fecha_evento, r.hora_inicio
$$;
GRANT EXECUTE ON FUNCTION disponibilidad_zona(uuid, date, date) TO app_user;

-- El residente solo cancela sus reservas: no cambia fecha, zona ni estado a otro valor
CREATE FUNCTION trg_reservas_residente() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    NEW.updated_at := now();
  END IF;
  IF app_role() <> 'RESIDENTE' THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.estado::text NOT IN ('SOLICITADA', 'CONFIRMADA') OR NOT NEW.solicitada_en_portal THEN
      RAISE EXCEPTION 'Reserva no válida desde el portal' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.estado::text <> 'CANCELADA' OR OLD.estado::text NOT IN ('SOLICITADA', 'CONFIRMADA')
     OR NEW.zona_id <> OLD.zona_id OR NEW.fecha_evento <> OLD.fecha_evento
     OR NEW.hora_inicio IS DISTINCT FROM OLD.hora_inicio OR NEW.hora_fin IS DISTINCT FROM OLD.hora_fin
     OR NEW.unidad_id IS DISTINCT FROM OLD.unidad_id THEN
    RAISE EXCEPTION 'Desde el portal solo puede cancelar su reserva' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_reservas_residente BEFORE INSERT OR UPDATE ON reservas
  FOR EACH ROW EXECUTE FUNCTION trg_reservas_residente();

-- -----------------------------------------------------------------------------
-- 5. Reglas de PQRS y circulares
-- -----------------------------------------------------------------------------
CREATE FUNCTION trg_pqrs_consecutivo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.consecutivo := next_consecutivo(NEW.tenant_id, 'pqrs');
  RETURN NEW;
END $$;

-- Flujo de estados. Lo que ya se dijo (asunto, descripción, quién radicó) no cambia.
CREATE FUNCTION trg_pqrs_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_de text := OLD.estado::text; v_a text := NEW.estado::text;
BEGIN
  IF NEW.asunto <> OLD.asunto OR NEW.descripcion <> OLD.descripcion OR NEW.radicado_por_id <> OLD.radicado_por_id
     OR NEW.consecutivo <> OLD.consecutivo OR NEW.tipo <> OLD.tipo OR NEW.created_at <> OLD.created_at THEN
    RAISE EXCEPTION 'Lo radicado no se modifica: agregue un mensaje' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF v_de IN ('CERRADA', 'DESISTIDA') AND v_a = v_de AND NEW.calificacion IS NOT DISTINCT FROM OLD.calificacion THEN
    RAISE EXCEPTION 'La PQRS está %', lower(v_de) USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF v_a <> v_de AND NOT (
       (v_de = 'RADICADA'   AND v_a IN ('EN_TRAMITE', 'RESPONDIDA', 'DESISTIDA'))
    OR (v_de = 'EN_TRAMITE' AND v_a IN ('RESPONDIDA', 'DESISTIDA'))
    OR (v_de = 'RESPONDIDA' AND v_a IN ('EN_TRAMITE', 'CERRADA'))
  ) THEN
    RAISE EXCEPTION 'No se puede pasar una PQRS de % a %', v_de, v_a USING ERRCODE = 'check_violation';
  END IF;
  IF v_a = 'RESPONDIDA' AND v_de <> 'RESPONDIDA' THEN
    NEW.respondida_at := now();
  END IF;
  IF v_a IN ('CERRADA', 'DESISTIDA') AND v_de <> v_a THEN
    NEW.cerrada_at := now();
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

CREATE FUNCTION trg_circulares_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado::text <> 'BORRADOR' AND (NEW.titulo <> OLD.titulo OR NEW.cuerpo <> OLD.cuerpo
     OR NEW.torres <> OLD.torres OR NEW.importante <> OLD.importante) THEN
    RAISE EXCEPTION 'Una circular publicada no se edita: publique una aclaración' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF OLD.estado::text = 'BORRADOR' AND NEW.estado::text = 'PUBLICADA' THEN
    NEW.consecutivo := next_consecutivo(NEW.tenant_id, 'circular');
    NEW.publicada_at := now();
  END IF;
  IF OLD.estado::text = 'ARCHIVADA' AND NEW.estado::text <> 'ARCHIVADA' THEN
    RAISE EXCEPTION 'La circular está archivada' USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- Auditoría (comparte el patrón de los otros módulos)
CREATE TABLE auditoria_portal (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  entidad             text NOT NULL,          -- 'pqrs', 'circular', 'reserva', 'zona'
  entidad_id          uuid NOT NULL,
  usuario_id          uuid,
  accion              accion_auditoria NOT NULL,
  valores_anteriores  jsonb,
  valores_nuevos      jsonb,
  fecha_hora          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auditoria_portal_idx ON auditoria_portal (tenant_id, entidad, entidad_id, fecha_hora DESC);

CREATE FUNCTION trg_auditar_portal() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_nuevo jsonb := to_jsonb(NEW) - 'updated_at';
  v_viejo jsonb;
  v_antes jsonb;
  v_despues jsonb;
BEGIN
  IF TG_OP = 'INSERT' THEN
    v_despues := v_nuevo;
  ELSE
    v_viejo := to_jsonb(OLD) - 'updated_at';
    SELECT jsonb_object_agg(n.key, n.value) INTO v_despues
      FROM jsonb_each(v_nuevo) n WHERE v_viejo -> n.key IS DISTINCT FROM n.value;
    IF v_despues IS NULL THEN
      RETURN NULL;
    END IF;
    SELECT jsonb_object_agg(d.key, v_viejo -> d.key) INTO v_antes FROM jsonb_each(v_despues) d;
  END IF;
  INSERT INTO auditoria_portal (tenant_id, entidad, entidad_id, usuario_id, accion, valores_anteriores, valores_nuevos)
  VALUES (NEW.tenant_id, TG_ARGV[0], NEW.id, app_user_id(),
          CASE WHEN TG_OP = 'INSERT' THEN 'CREACION'::accion_auditoria
               WHEN v_despues ? 'estado' THEN 'CAMBIO_ESTADO'::accion_auditoria
               ELSE 'EDICION'::accion_auditoria END,
          v_antes, v_despues);
  RETURN NULL;
END $$;

CREATE TRIGGER trg_pqrs_consecutivo BEFORE INSERT ON pqrs FOR EACH ROW EXECUTE FUNCTION trg_pqrs_consecutivo();
CREATE TRIGGER trg_pqrs_update BEFORE UPDATE ON pqrs FOR EACH ROW EXECUTE FUNCTION trg_pqrs_update();
CREATE TRIGGER trg_pqrs_mensajes_inmutable BEFORE UPDATE ON pqrs_mensajes FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_circulares_update BEFORE UPDATE ON circulares FOR EACH ROW EXECUTE FUNCTION trg_circulares_update();
CREATE TRIGGER trg_auditar AFTER INSERT OR UPDATE ON pqrs FOR EACH ROW EXECUTE FUNCTION trg_auditar_portal('pqrs');
CREATE TRIGGER trg_auditar AFTER INSERT OR UPDATE ON circulares FOR EACH ROW EXECUTE FUNCTION trg_auditar_portal('circular');
CREATE TRIGGER trg_auditar AFTER INSERT OR UPDATE ON reservas FOR EACH ROW EXECUTE FUNCTION trg_auditar_portal('reserva');

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pqrs', 'pqrs_mensajes', 'auditoria_portal'] LOOP
    EXECUTE format('CREATE TRIGGER trg_prohibir_delete BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION trg_prohibir_delete()', t);
  END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- 6. Privilegios y RLS
-- -----------------------------------------------------------------------------
REVOKE DELETE ON pqrs, pqrs_mensajes, circulares, auditoria_portal FROM app_user;
REVOKE INSERT, UPDATE ON auditoria_portal FROM app_user;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pqrs', 'pqrs_mensajes', 'circulares', 'circular_lecturas', 'auditoria_portal'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id())', t);
  END LOOP;
END $$;

-- PQRS: la administración y recepción gestionan todas; el consejo las lee (comité de convivencia);
-- contabilidad, las de cartera; mantenimiento, las que tiene asignadas; el residente, las suyas.
CREATE POLICY rbac_leer ON pqrs AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'CONSEJO', 'SYSTEM')
  OR (app_role() = 'CONTABILIDAD' AND categoria = 'CARTERA')
  OR (app_role() = 'MANTENIMIENTO' AND asignado_a_id = app_user_id())
  OR radicado_por_id = app_user_id());
CREATE POLICY rbac_crear ON pqrs AS RESTRICTIVE FOR INSERT WITH CHECK (
  radicado_por_id = coalesce(app_user_id(), radicado_por_id)
  AND (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM')
       OR (app_role() = 'RESIDENTE' AND canal = 'PORTAL' AND (unidad_id IS NULL OR unidad_id IN (SELECT app_unidades_propias())))));
CREATE POLICY rbac_editar ON pqrs AS RESTRICTIVE FOR UPDATE USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM')
  OR (app_role() = 'CONTABILIDAD' AND categoria = 'CARTERA')
  OR (app_role() = 'MANTENIMIENTO' AND asignado_a_id = app_user_id())
  OR radicado_por_id = app_user_id());   -- el residente: desistir, calificar, reabrir (lo valida el servicio)

CREATE POLICY rbac_leer ON pqrs_mensajes AS RESTRICTIVE FOR SELECT USING (
  pqrs_id IN (SELECT id FROM pqrs)  -- la RLS de pqrs decide a cuáles accede
  AND (NOT interno OR app_role() IN ('ADMIN', 'AUXILIAR', 'CONSEJO', 'CONTABILIDAD', 'MANTENIMIENTO', 'SYSTEM')));
CREATE POLICY rbac_crear ON pqrs_mensajes AS RESTRICTIVE FOR INSERT WITH CHECK (
  autor_id = coalesce(app_user_id(), autor_id)
  AND pqrs_id IN (SELECT id FROM pqrs)
  AND (app_role() <> 'RESIDENTE' OR (NOT interno AND NOT es_respuesta))
  AND app_role() <> 'CONSEJO');

-- Circulares: publicadas para todos; borradores solo administración
CREATE POLICY rbac_leer ON circulares AS RESTRICTIVE FOR SELECT USING (
  estado <> 'BORRADOR' OR app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
CREATE POLICY rbac_crear ON circulares AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
CREATE POLICY rbac_editar ON circulares AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));

CREATE POLICY rbac_leer ON circular_lecturas AS RESTRICTIVE FOR SELECT USING (
  user_id = app_user_id() OR app_role() IN ('ADMIN', 'AUXILIAR', 'CONSEJO', 'SYSTEM'));
CREATE POLICY rbac_crear ON circular_lecturas AS RESTRICTIVE FOR INSERT WITH CHECK (user_id = app_user_id());

CREATE POLICY rbac_leer ON auditoria_portal AS RESTRICTIVE FOR SELECT USING (app_role() IN ('ADMIN', 'SYSTEM'));

-- Zonas y reservas (0003): el residente ve las zonas reservables y sus propias reservas, y reserva/cancela
DROP POLICY rbac_leer ON zonas_sociales;
CREATE POLICY rbac_leer ON zonas_sociales AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'CONSEJO', 'SYSTEM')
  OR (app_role() = 'RESIDENTE' AND activo AND reservable_residentes));

DROP POLICY rbac_leer ON reservas;
CREATE POLICY rbac_leer ON reservas AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'CONSEJO', 'SYSTEM')
  OR unidad_id IN (SELECT app_unidades_propias()));
DROP POLICY rbac_crear ON reservas;
CREATE POLICY rbac_crear ON reservas AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM')
  OR (app_role() = 'RESIDENTE' AND creado_por_id = app_user_id() AND unidad_id IN (SELECT app_unidades_propias())));
DROP POLICY rbac_editar ON reservas;
CREATE POLICY rbac_editar ON reservas AS RESTRICTIVE FOR UPDATE USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM')
  OR (app_role() = 'RESIDENTE' AND unidad_id IN (SELECT app_unidades_propias())));
