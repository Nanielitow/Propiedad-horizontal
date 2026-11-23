-- =============================================================================
--  0005 · Activos, hojas de vida y plan de mantenimiento (CMMS)
--  Diseño: docs/MANTENIMIENTO.md
--
--  Reutiliza de 0003: app_role(), next_consecutivo(), trg_asignar_consecutivo(),
--  trg_prohibir_delete(), trg_inmutable(), set_updated_at() y accion_auditoria.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Rol del personal de mantenimiento (todero / técnico interno)
-- -----------------------------------------------------------------------------
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'MANTENIMIENTO';

-- -----------------------------------------------------------------------------
-- 2. Tipos
-- -----------------------------------------------------------------------------
CREATE TYPE estado_activo           AS ENUM ('OPERATIVO', 'OPERATIVO_CON_OBSERVACIONES', 'EN_MANTENIMIENTO',
                                             'FUERA_DE_SERVICIO', 'DADO_DE_BAJA');
CREATE TYPE criticidad_activo       AS ENUM ('ALTA', 'MEDIA', 'BAJA');
CREATE TYPE tipo_documento_activo   AS ENUM ('MANUAL', 'PLANO', 'FICHA_TECNICA', 'GARANTIA', 'CONTRATO', 'ACTA',
                                             'CERTIFICACION', 'FACTURA', 'INFORME_TECNICO', 'OTRO');
CREATE TYPE entidad_evidencia       AS ENUM ('ACTIVO', 'MANTENIMIENTO', 'NOVEDAD');
CREATE TYPE momento_evidencia       AS ENUM ('ANTES', 'DESPUES', 'EVIDENCIA', 'FOTO_ACTIVO', 'INFORME', 'FACTURA');
CREATE TYPE periodicidad            AS ENUM ('SEMANAL', 'QUINCENAL', 'MENSUAL', 'BIMESTRAL', 'TRIMESTRAL',
                                             'SEMESTRAL', 'ANUAL', 'POR_HORAS_USO');
CREATE TYPE base_calculo_plan       AS ENUM ('CALENDARIO_FIJO', 'DESDE_ULTIMA_EJECUCION');
CREATE TYPE estado_actividad        AS ENUM ('PROGRAMADA', 'EJECUTADA', 'CANCELADA');
CREATE TYPE tipo_mantenimiento      AS ENUM ('PREVENTIVO', 'CORRECTIVO', 'PREDICTIVO', 'INSPECCION_TECNICA');
CREATE TYPE prioridad_novedad       AS ENUM ('BAJA', 'MEDIA', 'ALTA', 'CRITICA');
CREATE TYPE estado_novedad          AS ENUM ('REPORTADA', 'EN_GESTION', 'PENDIENTE_COTIZACION', 'PROGRAMADA',
                                             'EN_EJECUCION', 'CERRADA', 'DESCARTADA');
CREATE TYPE prioridad_recomendacion AS ENUM ('ALTA', 'MEDIA', 'BAJA');
CREATE TYPE estado_recomendacion    AS ENUM ('PENDIENTE', 'EN_PROCESO', 'EJECUTADA', 'DESCARTADA_CON_JUSTIFICACION');

-- -----------------------------------------------------------------------------
-- 3. Catálogos
-- -----------------------------------------------------------------------------
CREATE TABLE categorias_activos (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  codigo              text NOT NULL CHECK (codigo ~ '^[A-Z][A-Z0-9_]{1,39}$'),
  nombre              text NOT NULL,
  descripcion         text,
  subtipos            text[] NOT NULL DEFAULT '{}',
  es_infraestructura  boolean NOT NULL DEFAULT false,
  activo              boolean NOT NULL DEFAULT true,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, codigo),
  UNIQUE (tenant_id, id)
);

CREATE TABLE contratistas (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                 uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  razon_social              text NOT NULL CHECK (length(btrim(razon_social)) >= 2),
  nit                       text,
  contacto_nombre           text,
  telefono                  text,
  email                     citext,
  especialidades            text[] NOT NULL DEFAULT '{}',
  vigencia_contrato_inicio  date,
  vigencia_contrato_fin     date,
  alcance_contrato          text,
  periodicidad_pactada      text,
  valor_contrato            numeric(14,2) CHECK (valor_contrato IS NULL OR valor_contrato >= 0),
  contrato_documento_id     uuid,
  activo                    boolean NOT NULL DEFAULT true,
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, nit),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, contrato_documento_id) REFERENCES documents(tenant_id, id),
  CHECK (vigencia_contrato_fin IS NULL OR vigencia_contrato_inicio IS NULL OR vigencia_contrato_fin >= vigencia_contrato_inicio)
);

-- -----------------------------------------------------------------------------
-- 4. Hoja de vida del activo
-- -----------------------------------------------------------------------------
CREATE TABLE activos (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo                 bigint NOT NULL,
  codigo_interno              text GENERATED ALWAYS AS (
                                'ACT-' || CASE WHEN consecutivo < 1000 THEN lpad(consecutivo::text, 3, '0')
                                               ELSE consecutivo::text END) STORED,
  -- Token aleatorio del QR (lo genera la aplicación): no contiene datos; se puede regenerar
  qr_token                    text NOT NULL UNIQUE CHECK (qr_token ~ '^[A-Za-z0-9_-]{24,64}$'),
  nombre                      text NOT NULL CHECK (length(btrim(nombre)) >= 2),
  categoria_id                uuid NOT NULL,
  subtipo                     text,
  ubicacion                   text NOT NULL,
  marca                       text,
  modelo                      text,
  fabricante                  text,
  numero_serie                text,
  especificaciones            jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(especificaciones) = 'object'),
  vida_util_anios             int CHECK (vida_util_anios IS NULL OR vida_util_anios BETWEEN 1 AND 200),
  fecha_instalacion           date,
  instalador_id               uuid,
  mantenedor_id               uuid,
  fecha_vencimiento_garantia  date,
  criticidad                  criticidad_activo NOT NULL DEFAULT 'MEDIA',
  estado                      estado_activo NOT NULL DEFAULT 'OPERATIVO',
  motivo_baja                 text,
  fecha_baja                  date,
  created_at                  timestamptz NOT NULL DEFAULT now(),
  updated_at                  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, consecutivo),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, categoria_id)  REFERENCES categorias_activos(tenant_id, id),
  FOREIGN KEY (tenant_id, instalador_id) REFERENCES contratistas(tenant_id, id),
  FOREIGN KEY (tenant_id, mantenedor_id) REFERENCES contratistas(tenant_id, id),
  -- Dar de baja reemplaza al borrado: siempre con motivo y fecha
  CHECK (estado <> 'DADO_DE_BAJA' OR (fecha_baja IS NOT NULL AND length(btrim(coalesce(motivo_baja, ''))) >= 10))
);
CREATE INDEX activos_categoria_idx ON activos (tenant_id, categoria_id);
CREATE INDEX activos_estado_idx    ON activos (tenant_id, estado);

-- Documentos de la plataforma (PDF con OCR e IA) vinculados al activo
CREATE TABLE activo_documentos (
  activo_id        uuid NOT NULL,
  document_id      uuid NOT NULL,
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  tipo             tipo_documento_activo NOT NULL,
  fecha_documento  date,
  vinculado_por_id uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (activo_id, document_id),
  FOREIGN KEY (tenant_id, activo_id)   REFERENCES activos(tenant_id, id),
  FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX activo_documentos_doc_idx ON activo_documentos (document_id);

-- Fotos y archivos que no son documentos con IA (antes/después, evidencias de fallas)
CREATE TABLE evidencias (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  entidad       entidad_evidencia NOT NULL,
  entidad_id    uuid NOT NULL,
  momento       momento_evidencia NOT NULL,
  storage_key   text NOT NULL CHECK (storage_key ~ '^tenants/[0-9a-f-]{36}/activos/evidencias/[0-9a-f-]{36}\.(jpg|png|webp|pdf)$'),
  content_type  text NOT NULL,
  size_bytes    bigint NOT NULL CHECK (size_bytes > 0),
  descripcion   text,
  subido_por_id uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  -- La carpeta del archivo debe ser la de la copropiedad dueña del registro
  CHECK (storage_key LIKE 'tenants/' || tenant_id::text || '/%')
);
CREATE INDEX evidencias_entidad_idx ON evidencias (entidad, entidad_id);

-- Horómetro (planes por horas de uso)
CREATE TABLE lecturas_uso (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  activo_id          uuid NOT NULL,
  fecha              timestamptz NOT NULL DEFAULT now(),
  horas_acumuladas   numeric(10,1) NOT NULL CHECK (horas_acumuladas >= 0),
  registrado_por_id  uuid REFERENCES users(id) ON DELETE SET NULL,
  FOREIGN KEY (tenant_id, activo_id) REFERENCES activos(tenant_id, id)
);
CREATE INDEX lecturas_activo_idx ON lecturas_uso (activo_id, fecha DESC);

-- -----------------------------------------------------------------------------
-- 5. Plan preventivo, actividades y reprogramaciones
-- -----------------------------------------------------------------------------
CREATE TABLE planes_preventivos (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  activo_id              uuid NOT NULL,
  nombre                 text NOT NULL CHECK (length(btrim(nombre)) >= 3),
  actividades_checklist  text[] NOT NULL DEFAULT '{}',
  periodicidad           periodicidad NOT NULL,
  intervalo_horas        int CHECK (intervalo_horas IS NULL OR intervalo_horas > 0),
  base_calculo           base_calculo_plan NOT NULL DEFAULT 'CALENDARIO_FIJO',
  fecha_inicio           date NOT NULL,
  contratista_id         uuid,
  costo_estimado         numeric(14,2) CHECK (costo_estimado IS NULL OR costo_estimado >= 0),
  aprobado_por_id        uuid REFERENCES users(id),
  aprobado_at            timestamptz,
  activo                 boolean NOT NULL DEFAULT true,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, activo_id)      REFERENCES activos(tenant_id, id),
  FOREIGN KEY (tenant_id, contratista_id) REFERENCES contratistas(tenant_id, id),
  CHECK ((periodicidad = 'POR_HORAS_USO') = (intervalo_horas IS NOT NULL)),
  CHECK ((aprobado_por_id IS NULL) = (aprobado_at IS NULL))
);
CREATE INDEX planes_activo_idx ON planes_preventivos (tenant_id, activo_id);

CREATE TABLE actividades_programadas (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  plan_id           uuid NOT NULL,
  activo_id         uuid NOT NULL,
  fecha_programada  date NOT NULL,
  fecha_original    date NOT NULL,
  estado            estado_actividad NOT NULL DEFAULT 'PROGRAMADA',
  asignado_a_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (plan_id, fecha_original),  -- el generador puede correr dos veces sin duplicar
  FOREIGN KEY (tenant_id, plan_id)   REFERENCES planes_preventivos(tenant_id, id),
  FOREIGN KEY (tenant_id, activo_id) REFERENCES activos(tenant_id, id)
);
CREATE INDEX actividades_calendario_idx ON actividades_programadas (tenant_id, fecha_programada) WHERE estado = 'PROGRAMADA';
CREATE INDEX actividades_activo_idx ON actividades_programadas (activo_id, fecha_programada);

CREATE TABLE reprogramaciones (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  actividad_id   uuid NOT NULL,
  fecha_anterior date NOT NULL,
  nueva_fecha    date NOT NULL,
  motivo         text NOT NULL CHECK (length(btrim(motivo)) >= 10),
  usuario_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, actividad_id) REFERENCES actividades_programadas(tenant_id, id),
  CHECK (nueva_fecha <> fecha_anterior)
);
CREATE INDEX reprogramaciones_actividad_idx ON reprogramaciones (actividad_id, created_at);

-- -----------------------------------------------------------------------------
-- 6. Novedades (correctivos)
-- -----------------------------------------------------------------------------
CREATE TABLE novedades (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo              bigint NOT NULL,
  codigo                   text GENERATED ALWAYS AS (
                             'NOV-' || CASE WHEN consecutivo < 10000 THEN lpad(consecutivo::text, 4, '0')
                                            ELSE consecutivo::text END) STORED,
  activo_id                uuid NOT NULL,
  fecha_reporte            timestamptz NOT NULL DEFAULT now(),
  reportado_por_id         uuid NOT NULL REFERENCES users(id),
  descripcion              text NOT NULL CHECK (length(btrim(descripcion)) >= 5),
  riesgo_identificado      text,
  prioridad                prioridad_novedad NOT NULL DEFAULT 'MEDIA',
  estado                   estado_novedad NOT NULL DEFAULT 'REPORTADA',
  contratista_asignado_id  uuid,
  asignado_a_id            uuid REFERENCES users(id) ON DELETE SET NULL,  -- técnico interno
  cotizacion_id            uuid,
  fecha_atencion           timestamptz,
  diagnostico              text,
  solucion_implementada    text,
  costo_reparacion         numeric(14,2) CHECK (costo_reparacion IS NULL OR costo_reparacion >= 0),
  cerrada_por_id           uuid REFERENCES users(id),
  cerrada_at               timestamptz,
  motivo_descarte          text,
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, consecutivo),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, activo_id)               REFERENCES activos(tenant_id, id),
  FOREIGN KEY (tenant_id, contratista_asignado_id) REFERENCES contratistas(tenant_id, id),
  FOREIGN KEY (tenant_id, cotizacion_id)           REFERENCES quote_comparisons(tenant_id, id),
  CHECK (estado NOT IN ('CERRADA', 'DESCARTADA') OR (cerrada_por_id IS NOT NULL AND cerrada_at IS NOT NULL)),
  CHECK (estado <> 'DESCARTADA' OR length(btrim(coalesce(motivo_descarte, ''))) >= 10)
);
CREATE INDEX novedades_abiertas_idx ON novedades (tenant_id, prioridad) WHERE estado NOT IN ('CERRADA', 'DESCARTADA');
CREATE INDEX novedades_activo_idx ON novedades (activo_id, fecha_reporte DESC);

-- -----------------------------------------------------------------------------
-- 7. Historial de intervenciones (inmutable)
-- -----------------------------------------------------------------------------
CREATE TABLE mantenimientos_ejecutados (
  id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo                bigint NOT NULL,
  codigo                     text GENERATED ALWAYS AS (
                               'MTO-' || CASE WHEN consecutivo < 10000 THEN lpad(consecutivo::text, 4, '0')
                                              ELSE consecutivo::text END) STORED,
  activo_id                  uuid NOT NULL,
  tipo                       tipo_mantenimiento NOT NULL,
  fecha_ejecucion            date NOT NULL,
  contratista_id             uuid,
  nombre_tecnico             text NOT NULL CHECK (length(btrim(nombre_tecnico)) >= 2),
  tiempo_ejecucion_horas     numeric(6,2) CHECK (tiempo_ejecucion_horas IS NULL OR tiempo_ejecucion_horas >= 0),
  diagnostico_inicial        text,
  actividades_realizadas     text NOT NULL CHECK (length(btrim(actividades_realizadas)) >= 5),
  repuestos_utilizados       text,
  novedades_encontradas      text,
  recomendaciones_tecnico    text,
  checklist                  jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(checklist) = 'array'),
  estado_post_intervencion   estado_activo NOT NULL CHECK (estado_post_intervencion <> 'DADO_DE_BAJA'),
  costo_mano_obra            numeric(14,2) NOT NULL DEFAULT 0 CHECK (costo_mano_obra >= 0),
  costo_repuestos            numeric(14,2) NOT NULL DEFAULT 0 CHECK (costo_repuestos >= 0),
  costo_total                numeric(14,2) GENERATED ALWAYS AS (costo_mano_obra + costo_repuestos) STORED,
  fecha_proximo_recomendado  date,
  actividad_id               uuid,
  novedad_id                 uuid,
  informe_documento_id       uuid,
  factura_documento_id       uuid,
  registrado_por_id          uuid NOT NULL REFERENCES users(id),
  anulado_por_id             uuid REFERENCES users(id),
  anulado_at                 timestamptz,
  motivo_anulacion           text,
  created_at                 timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, consecutivo),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, activo_id)            REFERENCES activos(tenant_id, id),
  FOREIGN KEY (tenant_id, contratista_id)       REFERENCES contratistas(tenant_id, id),
  FOREIGN KEY (tenant_id, actividad_id)         REFERENCES actividades_programadas(tenant_id, id),
  FOREIGN KEY (tenant_id, novedad_id)           REFERENCES novedades(tenant_id, id),
  FOREIGN KEY (tenant_id, informe_documento_id) REFERENCES documents(tenant_id, id),
  FOREIGN KEY (tenant_id, factura_documento_id) REFERENCES documents(tenant_id, id),
  CHECK (anulado_at IS NULL OR (anulado_por_id IS NOT NULL AND length(btrim(coalesce(motivo_anulacion, ''))) >= 10)),
  CHECK (fecha_proximo_recomendado IS NULL OR fecha_proximo_recomendado > fecha_ejecucion)
);
-- Una actividad preventiva se cumple con UN mantenimiento vigente
CREATE UNIQUE INDEX mantenimientos_actividad_uq ON mantenimientos_ejecutados (actividad_id)
  WHERE actividad_id IS NOT NULL AND anulado_at IS NULL;
CREATE INDEX mantenimientos_activo_idx ON mantenimientos_ejecutados (activo_id, fecha_ejecucion DESC);
CREATE INDEX mantenimientos_fecha_idx  ON mantenimientos_ejecutados (tenant_id, fecha_ejecucion);

-- -----------------------------------------------------------------------------
-- 8. Recomendaciones técnicas
-- -----------------------------------------------------------------------------
CREATE TABLE recomendaciones_tecnicas (
  id                           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  activo_id                    uuid NOT NULL,
  mantenimiento_origen_id      uuid,
  descripcion                  text NOT NULL CHECK (length(btrim(descripcion)) >= 5),
  prioridad                    prioridad_recomendacion NOT NULL DEFAULT 'MEDIA',
  responsable_id               uuid REFERENCES users(id) ON DELETE SET NULL,
  fecha_limite                 date,
  costo_estimado               numeric(14,2) CHECK (costo_estimado IS NULL OR costo_estimado >= 0),
  observaciones_administracion text,
  estado                       estado_recomendacion NOT NULL DEFAULT 'PENDIENTE',
  justificacion_descarte       text,
  mantenimiento_ejecucion_id   uuid,  -- el mantenimiento que la cumplió
  creado_por_id                uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at                   timestamptz NOT NULL DEFAULT now(),
  updated_at                   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, activo_id)                  REFERENCES activos(tenant_id, id),
  FOREIGN KEY (tenant_id, mantenimiento_origen_id)    REFERENCES mantenimientos_ejecutados(tenant_id, id),
  FOREIGN KEY (tenant_id, mantenimiento_ejecucion_id) REFERENCES mantenimientos_ejecutados(tenant_id, id),
  CHECK (estado <> 'DESCARTADA_CON_JUSTIFICACION' OR length(btrim(coalesce(justificacion_descarte, ''))) >= 10)
);
CREATE INDEX recomendaciones_pendientes_idx ON recomendaciones_tecnicas (tenant_id, prioridad)
  WHERE estado IN ('PENDIENTE', 'EN_PROCESO');

-- -----------------------------------------------------------------------------
-- 9. Auditoría y registro de avisos
-- -----------------------------------------------------------------------------
CREATE TABLE auditoria_activos (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  entidad             text NOT NULL,
  entidad_id          uuid NOT NULL,
  activo_id           uuid,
  usuario_id          uuid REFERENCES users(id) ON DELETE SET NULL,
  accion              accion_auditoria NOT NULL,
  valores_anteriores  jsonb,
  valores_nuevos      jsonb,
  motivo              text,
  fecha_hora          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auditoria_activos_activo_idx ON auditoria_activos (activo_id, fecha_hora) WHERE activo_id IS NOT NULL;
CREATE INDEX auditoria_activos_entidad_idx ON auditoria_activos (entidad, entidad_id, fecha_hora);

CREATE TABLE notificaciones_mantenimiento (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  tipo        text NOT NULL,         -- 'actividad_proxima', 'garantia', 'novedad_critica'...
  entidad_id  uuid NOT NULL,
  fecha_aviso date NOT NULL,
  enviado_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tipo, entidad_id, fecha_aviso)  -- un aviso nunca se envía dos veces
);

-- -----------------------------------------------------------------------------
-- 10. Reglas de negocio en triggers
-- -----------------------------------------------------------------------------

-- 10.1 Activos: dar de baja es definitivo; el consecutivo no cambia
CREATE FUNCTION trg_activos_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado = 'DADO_DE_BAJA' THEN
    RAISE EXCEPTION 'El activo % está dado de baja: no admite cambios', OLD.codigo_interno USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.consecutivo IS DISTINCT FROM OLD.consecutivo OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    RAISE EXCEPTION 'El código interno de un activo no se puede cambiar' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.estado = 'DADO_DE_BAJA' AND app_role() NOT IN ('ADMIN', 'SYSTEM') THEN
    RAISE EXCEPTION 'Solo la administración puede dar de baja un activo' USING ERRCODE = 'insufficient_privilege';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- 10.2 Lecturas de horómetro: nunca hacia atrás
CREATE FUNCTION trg_lecturas_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_max numeric;
BEGIN
  SELECT max(horas_acumuladas) INTO v_max FROM lecturas_uso WHERE activo_id = NEW.activo_id;
  IF v_max IS NOT NULL AND NEW.horas_acumuladas < v_max THEN
    RAISE EXCEPTION 'La lectura (% h) es menor que la anterior (% h)', NEW.horas_acumuladas, v_max
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

-- 10.3 Planes: solo la administración aprueba
CREATE FUNCTION trg_planes_aprobacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.aprobado_at IS NOT NULL AND (TG_OP = 'INSERT' OR OLD.aprobado_at IS NULL) AND app_role() NOT IN ('ADMIN', 'SYSTEM') THEN
    RAISE EXCEPTION 'Solo la administración aprueba planes de mantenimiento' USING ERRCODE = 'insufficient_privilege';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- 10.4 Actividades: la fecha solo cambia con una reprogramación registrada en la misma transacción
CREATE FUNCTION trg_actividades_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.fecha_original IS DISTINCT FROM OLD.fecha_original OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
     OR NEW.activo_id IS DISTINCT FROM OLD.activo_id THEN
    RAISE EXCEPTION 'La fecha original, el plan y el activo de una actividad no se modifican'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.fecha_programada IS DISTINCT FROM OLD.fecha_programada THEN
    IF OLD.estado <> 'PROGRAMADA' THEN
      RAISE EXCEPTION 'Solo se reprograman actividades pendientes' USING ERRCODE = 'check_violation';
    END IF;
    -- now() es la hora de inicio de la transacción: la reprogramación debe nacer en esta misma transacción
    IF NOT EXISTS (
      SELECT 1 FROM reprogramaciones r
       WHERE r.actividad_id = NEW.id AND r.fecha_anterior = OLD.fecha_programada
         AND r.nueva_fecha = NEW.fecha_programada AND r.created_at = now()
    ) THEN
      RAISE EXCEPTION 'Para cambiar la fecha registre la reprogramación con su motivo' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.estado = 'EJECUTADA' AND OLD.estado <> 'EJECUTADA' AND NOT EXISTS (
    SELECT 1 FROM mantenimientos_ejecutados m WHERE m.actividad_id = NEW.id AND m.anulado_at IS NULL
  ) THEN
    RAISE EXCEPTION 'Una actividad se marca ejecutada registrando el mantenimiento que la cumple'
      USING ERRCODE = 'check_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- 10.5 Mantenimientos: inmutables salvo la anulación; validan su actividad y su novedad
CREATE FUNCTION trg_mantenimientos_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_activo uuid; v_estado text;
BEGIN
  NEW.consecutivo := next_consecutivo(NEW.tenant_id, 'mantenimiento');
  IF NEW.anulado_at IS NOT NULL THEN
    RAISE EXCEPTION 'Un mantenimiento no puede registrarse anulado' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.actividad_id IS NOT NULL THEN
    SELECT activo_id, estado::text INTO v_activo, v_estado FROM actividades_programadas WHERE id = NEW.actividad_id;
    IF v_activo IS DISTINCT FROM NEW.activo_id THEN
      RAISE EXCEPTION 'La actividad programada pertenece a otro activo' USING ERRCODE = 'check_violation';
    END IF;
    IF v_estado <> 'PROGRAMADA' THEN
      RAISE EXCEPTION 'La actividad ya está % ', lower(v_estado) USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.novedad_id IS NOT NULL THEN
    SELECT activo_id INTO v_activo FROM novedades WHERE id = NEW.novedad_id;
    IF v_activo IS DISTINCT FROM NEW.activo_id THEN
      RAISE EXCEPTION 'La novedad pertenece a otro activo' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  NEW.created_at := now();
  RETURN NEW;
END $$;

CREATE FUNCTION trg_mantenimientos_update() RETURNS trigger LANGUAGE plpgsql AS $$
-- En BEFORE UPDATE las columnas generadas (costo_total, codigo) llegan NULL en NEW: se excluyen
DECLARE v_campos_anulacion text[] := ARRAY['anulado_por_id', 'anulado_at', 'motivo_anulacion', 'costo_total', 'codigo'];
BEGIN
  IF OLD.anulado_at IS NOT NULL THEN
    RAISE EXCEPTION 'El mantenimiento % ya está anulado', OLD.codigo USING ERRCODE = 'check_violation';
  END IF;
  IF (to_jsonb(NEW) - v_campos_anulacion) IS DISTINCT FROM (to_jsonb(OLD) - v_campos_anulacion) THEN
    RAISE EXCEPTION 'El historial de mantenimientos no se edita: anule el registro y créelo de nuevo'
      USING ERRCODE = 'check_violation';
  END IF;
  IF app_role() NOT IN ('ADMIN', 'SYSTEM') THEN
    RAISE EXCEPTION 'Solo la administración anula mantenimientos' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

-- Efectos colaterales con privilegios del dueño (el técnico no tiene UPDATE sobre
-- actividades ni activos): cumplir la actividad, actualizar el estado del activo y,
-- si se anula, devolver la actividad a pendiente. La auditoría registra igual al usuario.
CREATE FUNCTION trg_mantenimientos_efectos() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  p planes_preventivos%ROWTYPE;
  v_siguiente date;
BEGIN
  IF NEW.actividad_id IS NOT NULL THEN
    SELECT pl.* INTO p FROM actividades_programadas a JOIN planes_preventivos pl ON pl.id = a.plan_id
     WHERE a.id = NEW.actividad_id;
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.actividad_id IS NOT NULL THEN
      UPDATE actividades_programadas SET estado = 'EJECUTADA' WHERE id = NEW.actividad_id;
      -- Planes que cuentan desde la última ejecución (o por horas): la siguiente fecha nace de esta
      IF p.activo AND p.aprobado_at IS NOT NULL
         AND (p.base_calculo = 'DESDE_ULTIMA_EJECUCION' OR p.periodicidad = 'POR_HORAS_USO') THEN
        v_siguiente := coalesce(NEW.fecha_proximo_recomendado, (NEW.fecha_ejecucion + CASE p.periodicidad
          WHEN 'SEMANAL' THEN interval '7 days'      WHEN 'QUINCENAL' THEN interval '15 days'
          WHEN 'MENSUAL' THEN interval '1 month'     WHEN 'BIMESTRAL' THEN interval '2 months'
          WHEN 'TRIMESTRAL' THEN interval '3 months' WHEN 'SEMESTRAL' THEN interval '6 months'
          WHEN 'ANUAL' THEN interval '1 year'
          ELSE interval '30 days' END)::date);  -- por horas: estimación inicial, se ajusta con las lecturas
        INSERT INTO actividades_programadas (tenant_id, plan_id, activo_id, fecha_programada, fecha_original)
        VALUES (NEW.tenant_id, p.id, NEW.activo_id, v_siguiente, v_siguiente)
        ON CONFLICT (plan_id, fecha_original) DO NOTHING;
      END IF;
    END IF;
    UPDATE activos SET estado = NEW.estado_post_intervencion
     WHERE id = NEW.activo_id AND estado <> 'DADO_DE_BAJA' AND estado IS DISTINCT FROM NEW.estado_post_intervencion;
  ELSIF NEW.anulado_at IS NOT NULL AND OLD.anulado_at IS NULL AND NEW.actividad_id IS NOT NULL THEN
    UPDATE actividades_programadas SET estado = 'PROGRAMADA' WHERE id = NEW.actividad_id AND estado = 'EJECUTADA';
    -- La siguiente fecha que generó esta ejecución ya no aplica
    IF p.base_calculo = 'DESDE_ULTIMA_EJECUCION' OR p.periodicidad = 'POR_HORAS_USO' THEN
      UPDATE actividades_programadas SET estado = 'CANCELADA'
       WHERE plan_id = p.id AND estado = 'PROGRAMADA' AND id <> NEW.actividad_id;
    END IF;
  END IF;
  RETURN NULL;
END $$;

-- 10.6 Novedades: máquina de estados; cerrar y descartar es de la administración
CREATE FUNCTION trg_novedades_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.consecutivo := next_consecutivo(NEW.tenant_id, 'novedad');
  NEW.estado := 'REPORTADA';
  NEW.cerrada_por_id := NULL;
  NEW.cerrada_at := NULL;
  NEW.fecha_reporte := coalesce(NEW.fecha_reporte, now());
  RETURN NEW;
END $$;

CREATE FUNCTION trg_novedades_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_transicion text := OLD.estado || '>' || NEW.estado;
BEGIN
  IF OLD.estado IN ('CERRADA', 'DESCARTADA') THEN
    RAISE EXCEPTION 'La novedad % ya está %', OLD.codigo, lower(OLD.estado::text) USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.activo_id IS DISTINCT FROM OLD.activo_id OR NEW.consecutivo IS DISTINCT FROM OLD.consecutivo
     OR NEW.reportado_por_id IS DISTINCT FROM OLD.reportado_por_id OR NEW.fecha_reporte IS DISTINCT FROM OLD.fecha_reporte THEN
    RAISE EXCEPTION 'El activo, el reporte y su autor no se modifican' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.estado <> OLD.estado THEN
    IF v_transicion NOT IN (
      'REPORTADA>EN_GESTION', 'REPORTADA>DESCARTADA',
      'EN_GESTION>PENDIENTE_COTIZACION', 'EN_GESTION>PROGRAMADA', 'EN_GESTION>EN_EJECUCION', 'EN_GESTION>DESCARTADA',
      'PENDIENTE_COTIZACION>PROGRAMADA', 'PENDIENTE_COTIZACION>DESCARTADA',
      'PROGRAMADA>EN_EJECUCION',
      'EN_EJECUCION>CERRADA'
    ) THEN
      RAISE EXCEPTION 'Transición de estado no permitida: % -> %', OLD.estado, NEW.estado USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.estado IN ('CERRADA', 'DESCARTADA') AND app_role() NOT IN ('ADMIN', 'SYSTEM') THEN
      RAISE EXCEPTION 'Solo la administración cierra o descarta novedades' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.estado = 'CERRADA' AND length(btrim(coalesce(NEW.solucion_implementada, ''))) < 5 AND NOT EXISTS (
      SELECT 1 FROM mantenimientos_ejecutados m WHERE m.novedad_id = NEW.id AND m.anulado_at IS NULL
    ) THEN
      RAISE EXCEPTION 'Para cerrar la novedad registre la solución o el mantenimiento que la resolvió'
        USING ERRCODE = 'check_violation';
    END IF;
    -- La primera atención mide el tiempo de respuesta
    IF OLD.estado = 'REPORTADA' AND NEW.fecha_atencion IS NULL AND NEW.estado <> 'DESCARTADA' THEN
      NEW.fecha_atencion := now();
    END IF;
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- 10.7 Recomendaciones: cerradas no vuelven atrás
CREATE FUNCTION trg_recomendaciones_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado IN ('EJECUTADA', 'DESCARTADA_CON_JUSTIFICACION') THEN
    RAISE EXCEPTION 'La recomendación ya está cerrada' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.activo_id IS DISTINCT FROM OLD.activo_id OR NEW.mantenimiento_origen_id IS DISTINCT FROM OLD.mantenimiento_origen_id THEN
    RAISE EXCEPTION 'El activo y el origen de una recomendación no se modifican' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.estado = 'DESCARTADA_CON_JUSTIFICACION' AND app_role() NOT IN ('ADMIN', 'SYSTEM') THEN
    RAISE EXCEPTION 'Solo la administración descarta recomendaciones' USING ERRCODE = 'insufficient_privilege';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- 10.8 Auditoría automática (misma idea que trg_auditar de recaudos)
CREATE FUNCTION trg_auditar_activos() RETURNS trigger
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
      WHEN v_despues ? 'anulado_at' OR v_despues ->> 'estado' IN ('DADO_DE_BAJA', 'DESCARTADA', 'DESCARTADA_CON_JUSTIFICACION', 'CANCELADA')
        THEN 'ANULACION'
      WHEN v_despues ? 'estado' OR v_despues ? 'fecha_programada' THEN 'CAMBIO_ESTADO'
      ELSE 'EDICION' END;
  END IF;

  INSERT INTO auditoria_activos (tenant_id, entidad, entidad_id, activo_id, usuario_id, accion,
                                 valores_anteriores, valores_nuevos, motivo)
  VALUES (NEW.tenant_id, v_entidad, NEW.id,
          CASE WHEN v_entidad = 'activo' THEN NEW.id ELSE (v_nuevo ->> 'activo_id')::uuid END,
          app_user_id(), v_accion, v_antes, v_despues, nullif(current_setting('app.motivo', true), ''));
  RETURN NULL;
END $$;

-- 10.9 Instalación
CREATE TRIGGER trg_activos_consecutivo BEFORE INSERT ON activos
  FOR EACH ROW EXECUTE FUNCTION trg_asignar_consecutivo('activo');
CREATE TRIGGER trg_activos_update BEFORE UPDATE ON activos FOR EACH ROW EXECUTE FUNCTION trg_activos_update();
CREATE TRIGGER trg_lecturas_insert BEFORE INSERT ON lecturas_uso FOR EACH ROW EXECUTE FUNCTION trg_lecturas_insert();
CREATE TRIGGER trg_planes_aprobacion BEFORE INSERT OR UPDATE ON planes_preventivos
  FOR EACH ROW EXECUTE FUNCTION trg_planes_aprobacion();
CREATE TRIGGER trg_actividades_update BEFORE UPDATE ON actividades_programadas
  FOR EACH ROW EXECUTE FUNCTION trg_actividades_update();
CREATE TRIGGER trg_mantenimientos_insert BEFORE INSERT ON mantenimientos_ejecutados
  FOR EACH ROW EXECUTE FUNCTION trg_mantenimientos_insert();
CREATE TRIGGER trg_mantenimientos_update BEFORE UPDATE ON mantenimientos_ejecutados
  FOR EACH ROW EXECUTE FUNCTION trg_mantenimientos_update();
CREATE TRIGGER trg_mantenimientos_efectos AFTER INSERT OR UPDATE ON mantenimientos_ejecutados
  FOR EACH ROW EXECUTE FUNCTION trg_mantenimientos_efectos();
CREATE TRIGGER trg_novedades_insert BEFORE INSERT ON novedades FOR EACH ROW EXECUTE FUNCTION trg_novedades_insert();
CREATE TRIGGER trg_novedades_update BEFORE UPDATE ON novedades FOR EACH ROW EXECUTE FUNCTION trg_novedades_update();
CREATE TRIGGER trg_recomendaciones_update BEFORE UPDATE ON recomendaciones_tecnicas
  FOR EACH ROW EXECUTE FUNCTION trg_recomendaciones_update();
CREATE TRIGGER trg_contratistas_updated BEFORE UPDATE ON contratistas FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_reprogramaciones_inmutable BEFORE UPDATE ON reprogramaciones FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_evidencias_inmutable BEFORE UPDATE ON evidencias FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_lecturas_inmutable BEFORE UPDATE ON lecturas_uso FOR EACH ROW EXECUTE FUNCTION trg_inmutable();

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'activos', 'evidencias', 'lecturas_uso', 'planes_preventivos', 'actividades_programadas', 'reprogramaciones',
    'mantenimientos_ejecutados', 'novedades', 'recomendaciones_tecnicas', 'auditoria_activos'
  ] LOOP
    EXECUTE format('CREATE TRIGGER trg_prohibir_delete BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION trg_prohibir_delete()', t);
  END LOOP;
END $$;

DO $$
DECLARE par text[];
BEGIN
  FOREACH par SLICE 1 IN ARRAY ARRAY[
    ARRAY['activos', 'activo'], ARRAY['contratistas', 'contratista'], ARRAY['categorias_activos', 'categoria'],
    ARRAY['planes_preventivos', 'plan'], ARRAY['actividades_programadas', 'actividad'],
    ARRAY['mantenimientos_ejecutados', 'mantenimiento'], ARRAY['novedades', 'novedad'],
    ARRAY['recomendaciones_tecnicas', 'recomendacion']
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER trg_auditar AFTER INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION trg_auditar_activos(%L)',
      par[1], par[2]);
  END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- 11. Privilegios
-- -----------------------------------------------------------------------------
REVOKE DELETE ON activos, evidencias, lecturas_uso, planes_preventivos, actividades_programadas, reprogramaciones,
                 mantenimientos_ejecutados, novedades, recomendaciones_tecnicas, auditoria_activos,
                 categorias_activos, contratistas
  FROM app_user;
REVOKE INSERT, UPDATE ON auditoria_activos FROM app_user;

-- -----------------------------------------------------------------------------
-- 12. Row Level Security por copropiedad y por rol
--     Personal = ADMIN, AUXILIAR, MANTENIMIENTO, CONTABILIDAD (+ SYSTEM para tareas).
--     El Consejo no lee el detalle: verá agregados por una función SECURITY DEFINER (fase 5).
-- -----------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'categorias_activos', 'contratistas', 'activos', 'activo_documentos', 'evidencias', 'lecturas_uso',
    'planes_preventivos', 'actividades_programadas', 'reprogramaciones', 'mantenimientos_ejecutados', 'novedades',
    'recomendaciones_tecnicas', 'auditoria_activos', 'notificaciones_mantenimiento'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id())', t);
    IF t NOT IN ('auditoria_activos', 'notificaciones_mantenimiento') THEN
      EXECUTE format(
        'CREATE POLICY rbac_leer ON %I AS RESTRICTIVE FOR SELECT USING (app_role() IN (''ADMIN'', ''AUXILIAR'', ''MANTENIMIENTO'', ''CONTABILIDAD'', ''SYSTEM''))', t);
    END IF;
  END LOOP;
END $$;

-- Escritura por tabla (RESTRICTIVE: se combinan con AND sobre tenant_isolation)
CREATE POLICY rbac_crear ON categorias_activos AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON categorias_activos AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));

CREATE POLICY rbac_crear ON contratistas AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON contratistas AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));

CREATE POLICY rbac_crear ON activos AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON activos AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));

CREATE POLICY rbac_crear ON activo_documentos AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
CREATE POLICY rbac_borrar ON activo_documentos AS RESTRICTIVE FOR DELETE USING (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
CREATE POLICY rbac_editar ON activo_documentos AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));

CREATE POLICY rbac_crear ON evidencias AS RESTRICTIVE FOR INSERT
  WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'MANTENIMIENTO', 'SYSTEM'));
CREATE POLICY rbac_crear ON lecturas_uso AS RESTRICTIVE FOR INSERT
  WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'MANTENIMIENTO', 'SYSTEM'));

CREATE POLICY rbac_crear ON planes_preventivos AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
CREATE POLICY rbac_editar ON planes_preventivos AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));

CREATE POLICY rbac_crear ON actividades_programadas AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
CREATE POLICY rbac_editar ON actividades_programadas AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));

CREATE POLICY rbac_crear ON reprogramaciones AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));

CREATE POLICY rbac_crear ON mantenimientos_ejecutados AS RESTRICTIVE FOR INSERT
  WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'MANTENIMIENTO', 'SYSTEM') AND registrado_por_id = coalesce(app_user_id(), registrado_por_id));
CREATE POLICY rbac_editar ON mantenimientos_ejecutados AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));

-- Novedades: el técnico reporta y actualiza solo las que tiene asignadas
CREATE POLICY rbac_crear ON novedades AS RESTRICTIVE FOR INSERT
  WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'MANTENIMIENTO', 'SYSTEM'));
CREATE POLICY rbac_editar ON novedades AS RESTRICTIVE FOR UPDATE USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM')
  OR (app_role() = 'MANTENIMIENTO' AND asignado_a_id = app_user_id()));

CREATE POLICY rbac_crear ON recomendaciones_tecnicas AS RESTRICTIVE FOR INSERT
  WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'MANTENIMIENTO', 'SYSTEM'));
CREATE POLICY rbac_editar ON recomendaciones_tecnicas AS RESTRICTIVE FOR UPDATE USING (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM')
  OR (app_role() = 'MANTENIMIENTO' AND responsable_id = app_user_id()));

CREATE POLICY rbac_leer ON auditoria_activos AS RESTRICTIVE FOR SELECT USING (app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM'));
CREATE POLICY rbac_sistema ON notificaciones_mantenimiento AS RESTRICTIVE USING (app_role() IN ('ADMIN', 'SYSTEM'))
  WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));

-- -----------------------------------------------------------------------------
-- 13. Semáforo (calculado al consultar, nunca guardado). security_invoker: aplica la
--     RLS de quien consulta. Umbral configurable: tenants.settings->>'umbral_semaforo_dias'.
-- -----------------------------------------------------------------------------
CREATE VIEW v_semaforo_actividades WITH (security_invoker = true) AS
SELECT a.id, a.tenant_id, a.plan_id, a.activo_id, a.fecha_programada, a.fecha_original, a.asignado_a_id,
       (a.fecha_programada - hoy.d) AS dias_restantes,
       CASE
         WHEN a.fecha_programada < hoy.d THEN 'ROJO'
         WHEN a.fecha_programada - hoy.d <= coalesce((t.settings ->> 'umbral_semaforo_dias')::int, 15) THEN 'AMARILLO'
         ELSE 'VERDE'
       END AS semaforo
  FROM actividades_programadas a
  JOIN tenants t ON t.id = a.tenant_id
 CROSS JOIN (SELECT (now() AT TIME ZONE 'America/Bogota')::date AS d) hoy
 WHERE a.estado = 'PROGRAMADA';

-- -----------------------------------------------------------------------------
-- 14. Categorías iniciales (idempotente)
-- -----------------------------------------------------------------------------
CREATE FUNCTION seed_categorias_activos(p_tenant uuid) RETURNS void LANGUAGE sql AS $$
  INSERT INTO categorias_activos (tenant_id, codigo, nombre, descripcion, subtipos, es_infraestructura) VALUES
    (p_tenant, 'ELECTROMECANICOS', 'Equipos electromecánicos', 'Equipos con partes móviles y motores',
     ARRAY['Ascensor', 'Motobomba', 'Bomba eyectora', 'Bomba de presión', 'Planta eléctrica', 'Ventilación mecánica',
           'Caldera', 'Piscina / turco / sauna', 'Equipos de gimnasio', 'Sistema de riego'], false),
    (p_tenant, 'SEGURIDAD_TECNOLOGIA', 'Seguridad y tecnología', 'Sistemas electrónicos de seguridad y comunicación',
     ARRAY['CCTV', 'Control de acceso', 'Citofonía', 'Detección y alarma contra incendios', 'Control de puertas',
           'Comunicaciones', 'Automatización'], false),
    (p_tenant, 'REDES_INSTALACIONES', 'Redes e instalaciones', 'Redes y sistemas ocultos de servicios',
     ARRAY['Red hidráulica', 'Red sanitaria', 'Red eléctrica', 'Aguas lluvias', 'Drenaje', 'Tablero eléctrico',
           'Tanque de agua', 'Sistema de tratamiento'], true),
    (p_tenant, 'INFRAESTRUCTURA', 'Infraestructura y constructivos', 'Elementos constructivos de la edificación',
     ARRAY['Fachada', 'Cubierta / terraza', 'Impermeabilización', 'Plazoleta', 'Parqueadero', 'Muro / estructura',
           'Pisos y acabados', 'Puertas y ventanas', 'Junta de dilatación'], true)
  ON CONFLICT (tenant_id, codigo) DO NOTHING
$$;

DO $$
DECLARE t uuid;
BEGIN
  FOR t IN SELECT id FROM tenants LOOP
    PERFORM set_config('app.tenant_id', t::text, true);
    PERFORM set_config('app.role', 'SYSTEM', true);
    PERFORM seed_categorias_activos(t);
  END LOOP;
END $$;
