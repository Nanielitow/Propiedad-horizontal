-- =============================================================================
--  0003 · Módulo de Recaudos y Control de Ingresos (ingresos extraordinarios)
--  Diseño: docs/RECAUDOS.md
--
--  Principio: la base de datos es la última línea de defensa. Las reglas
--  críticas (no borrar, transiciones de estado, auditoría, consecutivos sin
--  huecos, justificación de diferencias) se imponen aquí, no solo en la API.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Roles nuevos
--    (ADD VALUE no se puede usar en la misma transacción: las políticas de abajo
--     comparan app_role() como TEXTO, nunca como user_role)
-- -----------------------------------------------------------------------------
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'AUXILIAR';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'CONTABILIDAD';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'CONSEJO';

CREATE FUNCTION app_role() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT coalesce(current_setting('app.role', true), '') $$;

-- -----------------------------------------------------------------------------
-- 2. Tipos
-- -----------------------------------------------------------------------------
CREATE TYPE tipo_cobro          AS ENUM ('FIJO', 'POR_HORA', 'VARIABLE');
CREATE TYPE medio_pago          AS ENUM ('EFECTIVO', 'TRANSFERENCIA', 'CONSIGNACION');
CREATE TYPE estado_recaudo      AS ENUM (
  'RECAUDADO_EN_CAJA', 'ENTREGADO_ADMINISTRACION', 'PENDIENTE_VERIFICACION',
  'CONSIGNADO', 'VERIFICADO', 'ANULADO'
);
CREATE TYPE estado_reserva      AS ENUM ('SOLICITADA', 'CONFIRMADA', 'CANCELADA', 'REALIZADA');
CREATE TYPE estado_entrega      AS ENUM ('PENDIENTE_CONFIRMACION', 'CONFIRMADA', 'RECHAZADA');
CREATE TYPE estado_consignacion AS ENUM ('REGISTRADA', 'APROBADA', 'VERIFICADA', 'RECHAZADA');
CREATE TYPE accion_auditoria    AS ENUM ('CREACION', 'EDICION', 'CAMBIO_ESTADO', 'ANULACION');
CREATE TYPE tipo_alerta         AS ENUM (
  'DIFERENCIA_CIERRE', 'DESCUADRE_CONSIGNACION', 'DESCUADRE_ENTREGA',
  'TRANSFERENCIA_SIN_VERIFICAR', 'ANULACION_POSTERIOR'
);
CREATE TYPE severidad_alerta    AS ENUM ('INFO', 'ADVERTENCIA', 'CRITICA');
CREATE TYPE estado_alerta       AS ENUM ('ABIERTA', 'ATENDIDA');

-- -----------------------------------------------------------------------------
-- 3. Consecutivos sin huecos por copropiedad
--    UPDATE ... RETURNING dentro de la transacción del INSERT: si la transacción
--    falla, el contador también se revierte (un SERIAL dejaría huecos).
--    Solo se accede vía la función (SECURITY DEFINER): nadie puede alterar el contador.
-- -----------------------------------------------------------------------------
CREATE TABLE secuencias (
  tenant_id  uuid   NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  tipo       text   NOT NULL,                 -- 'recaudo', 'cierre', 'entrega', 'consignacion'
  ultimo     bigint NOT NULL,
  PRIMARY KEY (tenant_id, tipo)
);

CREATE FUNCTION next_consecutivo(p_tenant uuid, p_tipo text) RETURNS bigint
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
  INSERT INTO secuencias (tenant_id, tipo, ultimo) VALUES (p_tenant, p_tipo, 1)
  ON CONFLICT (tenant_id, tipo) DO UPDATE SET ultimo = secuencias.ultimo + 1
  RETURNING ultimo
$$;

CREATE FUNCTION trg_asignar_consecutivo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.consecutivo := next_consecutivo(NEW.tenant_id, TG_ARGV[0]);
  RETURN NEW;
END $$;

-- Bloquea DELETE incluso para roles con privilegios (el app_user ni siquiera lo tiene)
CREATE FUNCTION trg_prohibir_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'No se permite eliminar registros de %: use el flujo de anulación', TG_TABLE_NAME
    USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE FUNCTION trg_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Los registros de % son inmutables', TG_TABLE_NAME
    USING ERRCODE = 'insufficient_privilege';
END $$;

-- -----------------------------------------------------------------------------
-- 4. Catálogos
-- -----------------------------------------------------------------------------
CREATE TABLE conceptos_recaudo (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  codigo             text NOT NULL CHECK (codigo ~ '^[A-Z][A-Z0-9_]{1,39}$'),
  nombre             text NOT NULL,
  descripcion        text,
  tarifa_base        numeric(14,2) CHECK (tarifa_base IS NULL OR tarifa_base >= 0),
  tipo_cobro         tipo_cobro NOT NULL,
  fraccion_minutos   int CHECK (fraccion_minutos IS NULL OR fraccion_minutos BETWEEN 1 AND 1440),
  requiere_reserva   boolean NOT NULL DEFAULT false,
  requiere_vehiculo  boolean NOT NULL DEFAULT false,
  activo             boolean NOT NULL DEFAULT true,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, codigo),
  UNIQUE (tenant_id, id),
  -- Un cobro por hora necesita tarifa y fracción; uno fijo, tarifa
  CHECK (tipo_cobro <> 'POR_HORA' OR (tarifa_base IS NOT NULL AND fraccion_minutos IS NOT NULL)),
  CHECK (tipo_cobro <> 'FIJO' OR tarifa_base IS NOT NULL)
);

CREATE TABLE zonas_sociales (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  nombre           text NOT NULL,
  tarifa_alquiler  numeric(14,2) CHECK (tarifa_alquiler IS NULL OR tarifa_alquiler >= 0),
  tarifa_aseo      numeric(14,2) CHECK (tarifa_aseo IS NULL OR tarifa_aseo >= 0),
  activo           boolean NOT NULL DEFAULT true,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, nombre),
  UNIQUE (tenant_id, id)
);

CREATE TABLE reservas (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  zona_id       uuid NOT NULL,
  unidad_id     uuid,
  solicitante   text NOT NULL,
  fecha_evento  date NOT NULL,
  hora_inicio   time,
  hora_fin      time,
  estado        estado_reserva NOT NULL DEFAULT 'SOLICITADA',
  observaciones text,
  creado_por_id uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, zona_id)   REFERENCES zonas_sociales(tenant_id, id),
  FOREIGN KEY (tenant_id, unidad_id) REFERENCES units(tenant_id, id),
  CHECK (hora_fin IS NULL OR hora_inicio IS NULL OR hora_fin > hora_inicio)
);
CREATE INDEX reservas_fecha_idx ON reservas (tenant_id, fecha_evento);

-- -----------------------------------------------------------------------------
-- 5. Control de efectivo (se crean antes que recaudos porque estos las referencian)
-- -----------------------------------------------------------------------------
CREATE TABLE cierres_caja (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                 uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo               bigint NOT NULL,
  usuario_id                uuid NOT NULL REFERENCES users(id),
  inicio_turno              timestamptz NOT NULL,
  fin_turno                 timestamptz NOT NULL DEFAULT now(),
  saldo_inicial             numeric(14,2) NOT NULL DEFAULT 0 CHECK (saldo_inicial >= 0),
  saldo_esperado_sistema    numeric(14,2) NOT NULL CHECK (saldo_esperado_sistema >= 0),
  valor_fisico_contado      numeric(14,2) NOT NULL CHECK (valor_fisico_contado >= 0),
  diferencia                numeric(14,2) GENERATED ALWAYS AS (valor_fisico_contado - saldo_esperado_sistema) STORED,
  tipo_diferencia           text GENERATED ALWAYS AS (
                              CASE WHEN valor_fisico_contado > saldo_esperado_sistema THEN 'SOBRANTE'
                                   WHEN valor_fisico_contado < saldo_esperado_sistema THEN 'FALTANTE'
                                   ELSE 'CUADRADO' END) STORED,
  observacion_justificacion text,
  created_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, consecutivo),
  UNIQUE (tenant_id, id),
  CHECK (fin_turno >= inicio_turno),
  -- Con sobrante o faltante, la justificación es obligatoria
  CHECK (valor_fisico_contado = saldo_esperado_sistema
         OR length(btrim(coalesce(observacion_justificacion, ''))) >= 10)
);
CREATE INDEX cierres_usuario_idx ON cierres_caja (tenant_id, usuario_id, fin_turno DESC);

CREATE TABLE entregas_internas (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo       bigint NOT NULL,
  entregado_por_id  uuid NOT NULL REFERENCES users(id),
  recibido_por_id   uuid NOT NULL REFERENCES users(id),
  fecha_entrega     timestamptz NOT NULL DEFAULT now(),
  valor_total       numeric(14,2) NOT NULL CHECK (valor_total > 0),
  estado            estado_entrega NOT NULL DEFAULT 'PENDIENTE_CONFIRMACION',
  valor_contado     numeric(14,2) CHECK (valor_contado IS NULL OR valor_contado >= 0),  -- lo que contó quien recibe
  confirmada_at     timestamptz,
  observaciones     text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, consecutivo),
  UNIQUE (tenant_id, id),
  CHECK (entregado_por_id <> recibido_por_id)
);

-- -----------------------------------------------------------------------------
-- 6. Recaudos
-- -----------------------------------------------------------------------------
CREATE TABLE recaudos (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo            bigint NOT NULL,
  fecha_recaudo          timestamptz NOT NULL DEFAULT now(),
  concepto_id            uuid NOT NULL,
  valor_recibido         numeric(14,2) NOT NULL CHECK (valor_recibido > 0),
  nombre_pagador         text NOT NULL CHECK (length(btrim(nombre_pagador)) >= 2),
  identificacion_pagador text,
  unidad_id              uuid,
  medio_pago             medio_pago NOT NULL,
  estado                 estado_recaudo NOT NULL,
  numero_comprobante     text,
  soporte_key            text,
  observaciones          text,
  reserva_id             uuid,
  usuario_receptor_id    uuid NOT NULL REFERENCES users(id),
  cierre_id              uuid,
  entrega_id             uuid,
  anulado_por_id         uuid REFERENCES users(id),
  anulado_at             timestamptz,
  motivo_anulacion       text,
  verificado_por_id      uuid REFERENCES users(id),
  verificado_at          timestamptz,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, consecutivo),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, concepto_id) REFERENCES conceptos_recaudo(tenant_id, id),
  FOREIGN KEY (tenant_id, unidad_id)   REFERENCES units(tenant_id, id),
  FOREIGN KEY (tenant_id, reserva_id)  REFERENCES reservas(tenant_id, id),
  FOREIGN KEY (tenant_id, cierre_id)   REFERENCES cierres_caja(tenant_id, id),
  FOREIGN KEY (tenant_id, entrega_id)  REFERENCES entregas_internas(tenant_id, id),
  -- Una anulación siempre deja quién, cuándo y por qué
  CHECK (estado <> 'ANULADO' OR (anulado_por_id IS NOT NULL AND anulado_at IS NOT NULL
                                 AND length(btrim(coalesce(motivo_anulacion, ''))) >= 10)),
  -- Solo el efectivo pasa por caja y por entregas internas
  CHECK (medio_pago = 'EFECTIVO' OR (cierre_id IS NULL AND entrega_id IS NULL)),
  CHECK (medio_pago = 'EFECTIVO' OR estado NOT IN ('RECAUDADO_EN_CAJA', 'ENTREGADO_ADMINISTRACION', 'CONSIGNADO')),
  CHECK (medio_pago <> 'EFECTIVO' OR estado <> 'PENDIENTE_VERIFICACION')
);
CREATE INDEX recaudos_fecha_idx    ON recaudos (tenant_id, fecha_recaudo DESC);
CREATE INDEX recaudos_estado_idx   ON recaudos (tenant_id, estado);
CREATE INDEX recaudos_concepto_idx ON recaudos (tenant_id, concepto_id, fecha_recaudo DESC);
CREATE INDEX recaudos_unidad_idx   ON recaudos (tenant_id, unidad_id) WHERE unidad_id IS NOT NULL;
-- Efectivo de un usuario aún sin cerrar (consulta del cierre de caja)
CREATE INDEX recaudos_caja_abierta_idx ON recaudos (tenant_id, usuario_receptor_id)
  WHERE medio_pago = 'EFECTIVO' AND cierre_id IS NULL;

-- Desglose: un alquiler = una transacción con dos líneas (alquiler + aseo)
CREATE TABLE recaudo_items (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  recaudo_id   uuid NOT NULL,
  concepto_id  uuid NOT NULL,
  descripcion  text,
  valor        numeric(14,2) NOT NULL CHECK (valor > 0),
  FOREIGN KEY (tenant_id, recaudo_id)  REFERENCES recaudos(tenant_id, id),
  FOREIGN KEY (tenant_id, concepto_id) REFERENCES conceptos_recaudo(tenant_id, id)
);
CREATE INDEX recaudo_items_recaudo_idx  ON recaudo_items (recaudo_id);
CREATE INDEX recaudo_items_concepto_idx ON recaudo_items (tenant_id, concepto_id);

CREATE TABLE recaudo_parqueadero (
  recaudo_id       uuid PRIMARY KEY,
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  placa_vehiculo   text NOT NULL CHECK (placa_vehiculo ~ '^[A-Z0-9]{5,7}$'),
  hora_ingreso     timestamptz NOT NULL,
  hora_salida      timestamptz NOT NULL,
  minutos_totales  int GENERATED ALWAYS AS (
                     ceil(extract(epoch FROM (hora_salida - hora_ingreso)) / 60)::int) STORED,
  tarifa_sugerida  numeric(14,2) NOT NULL CHECK (tarifa_sugerida >= 0),
  FOREIGN KEY (tenant_id, recaudo_id) REFERENCES recaudos(tenant_id, id),
  CHECK (hora_salida > hora_ingreso)
);
CREATE INDEX parqueadero_placa_idx ON recaudo_parqueadero (tenant_id, placa_vehiculo);

-- -----------------------------------------------------------------------------
-- 7. Conciliación bancaria
-- -----------------------------------------------------------------------------
CREATE TABLE consignaciones (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo           bigint NOT NULL,
  fecha_consignacion    date NOT NULL,
  banco_destino         text NOT NULL,
  referencia_bancaria   text NOT NULL,
  valor_consignado      numeric(14,2) NOT NULL CHECK (valor_consignado > 0),
  soporte_bancario_key  text,
  usuario_consigna_id   uuid NOT NULL REFERENCES users(id),
  estado                estado_consignacion NOT NULL DEFAULT 'REGISTRADA',
  aprobada_por_id       uuid REFERENCES users(id),
  aprobada_at           timestamptz,
  verificada_por_id     uuid REFERENCES users(id),
  verificada_at         timestamptz,
  observaciones         text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, consecutivo),
  UNIQUE (tenant_id, id),
  -- El mismo depósito no puede registrarse dos veces
  UNIQUE (tenant_id, banco_destino, referencia_bancaria)
);

-- N recaudos : M consignaciones, con valor aplicado (permite consignar por partes)
CREATE TABLE consignacion_recaudos (
  consignacion_id  uuid NOT NULL,
  recaudo_id       uuid NOT NULL,
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  valor_aplicado   numeric(14,2) NOT NULL CHECK (valor_aplicado > 0),
  PRIMARY KEY (consignacion_id, recaudo_id),
  FOREIGN KEY (tenant_id, consignacion_id) REFERENCES consignaciones(tenant_id, id),
  FOREIGN KEY (tenant_id, recaudo_id)      REFERENCES recaudos(tenant_id, id)
);
CREATE INDEX consignacion_recaudos_recaudo_idx ON consignacion_recaudos (recaudo_id);

-- -----------------------------------------------------------------------------
-- 8. Auditoría, alertas y cortes
-- -----------------------------------------------------------------------------
CREATE TABLE auditoria_recaudos (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  entidad             text NOT NULL,
  entidad_id          uuid NOT NULL,
  recaudo_id          uuid,
  usuario_id          uuid REFERENCES users(id) ON DELETE SET NULL,
  accion              accion_auditoria NOT NULL,
  valores_anteriores  jsonb,
  valores_nuevos      jsonb,
  motivo              text,
  ip                  inet,
  fecha_hora          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auditoria_recaudo_idx ON auditoria_recaudos (recaudo_id, fecha_hora) WHERE recaudo_id IS NOT NULL;
CREATE INDEX auditoria_tenant_idx  ON auditoria_recaudos (tenant_id, fecha_hora DESC);

CREATE TABLE alertas_recaudo (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  tipo             tipo_alerta NOT NULL,
  severidad        severidad_alerta NOT NULL DEFAULT 'ADVERTENCIA',
  entidad          text NOT NULL,
  entidad_id       uuid NOT NULL,
  mensaje          text NOT NULL,
  monto            numeric(14,2),
  estado           estado_alerta NOT NULL DEFAULT 'ABIERTA',
  atendida_por_id  uuid REFERENCES users(id),
  atendida_at      timestamptz,
  resolucion       text,
  notificada_at    timestamptz,                    -- correo enviado (evita duplicados al reintentar)
  created_at       timestamptz NOT NULL DEFAULT now(),
  CHECK (estado <> 'ATENDIDA' OR (atendida_por_id IS NOT NULL AND atendida_at IS NOT NULL
                                  AND length(btrim(coalesce(resolucion, ''))) >= 5))
);
CREATE INDEX alertas_abiertas_idx ON alertas_recaudo (tenant_id, created_at DESC) WHERE estado = 'ABIERTA';

CREATE TABLE cortes_mensuales (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  periodo      date NOT NULL CHECK (extract(day FROM periodo) = 1),
  resumen      jsonb NOT NULL,
  pdf_key      text,
  xlsx_key     text,
  generado_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, periodo)
);

-- -----------------------------------------------------------------------------
-- 9. Reglas de negocio en triggers
-- -----------------------------------------------------------------------------

-- 9.1 Al registrar: consecutivo + estado inicial según el medio de pago
CREATE FUNCTION trg_recaudos_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.consecutivo := next_consecutivo(NEW.tenant_id, 'recaudo');
  NEW.estado := CASE WHEN NEW.medio_pago = 'EFECTIVO' THEN 'RECAUDADO_EN_CAJA'
                     ELSE 'PENDIENTE_VERIFICACION' END::estado_recaudo;
  IF NEW.cierre_id IS NOT NULL OR NEW.entrega_id IS NOT NULL OR NEW.anulado_at IS NOT NULL
     OR NEW.verificado_at IS NOT NULL THEN
    RAISE EXCEPTION 'Un recaudo nuevo no puede nacer cerrado, entregado, verificado ni anulado'
      USING ERRCODE = 'check_violation';
  END IF;
  NEW.created_at := now();
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- 9.2 Al modificar: máquina de estados, campos inmutables y permisos por rol
CREATE FUNCTION trg_recaudos_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_rol text := app_role();
  v_transicion text := OLD.estado || '>' || NEW.estado;
  v_descriptivos_cambian boolean;
BEGIN
  IF OLD.estado = 'ANULADO' THEN
    RAISE EXCEPTION 'Un recaudo anulado no admite cambios' USING ERRCODE = 'check_violation';
  END IF;

  -- El dinero no se edita: si hubo un error, se anula y se registra de nuevo
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.consecutivo IS DISTINCT FROM OLD.consecutivo
     OR NEW.concepto_id IS DISTINCT FROM OLD.concepto_id OR NEW.valor_recibido IS DISTINCT FROM OLD.valor_recibido
     OR NEW.medio_pago IS DISTINCT FROM OLD.medio_pago OR NEW.fecha_recaudo IS DISTINCT FROM OLD.fecha_recaudo
     OR NEW.usuario_receptor_id IS DISTINCT FROM OLD.usuario_receptor_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'Concepto, valor, medio de pago, fecha y receptor no se pueden modificar: anule y registre de nuevo'
      USING ERRCODE = 'check_violation';
  END IF;

  -- Un cierre de caja, una vez asignado, es definitivo
  IF OLD.cierre_id IS NOT NULL AND NEW.cierre_id IS DISTINCT FROM OLD.cierre_id THEN
    RAISE EXCEPTION 'El recaudo ya pertenece a un cierre de caja' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.entrega_id IS DISTINCT FROM OLD.entrega_id AND OLD.estado <> 'RECAUDADO_EN_CAJA' THEN
    RAISE EXCEPTION 'Solo el efectivo en caja puede asociarse a una entrega' USING ERRCODE = 'check_violation';
  END IF;

  IF NEW.estado <> OLD.estado THEN
    IF v_transicion NOT IN (
      'RECAUDADO_EN_CAJA>ENTREGADO_ADMINISTRACION', 'RECAUDADO_EN_CAJA>CONSIGNADO', 'RECAUDADO_EN_CAJA>ANULADO',
      'ENTREGADO_ADMINISTRACION>CONSIGNADO', 'ENTREGADO_ADMINISTRACION>ANULADO',
      'PENDIENTE_VERIFICACION>VERIFICADO', 'PENDIENTE_VERIFICACION>ANULADO',
      'CONSIGNADO>VERIFICADO', 'CONSIGNADO>ANULADO',
      'VERIFICADO>ANULADO'
    ) THEN
      RAISE EXCEPTION 'Transición de estado no permitida: % -> %', OLD.estado, NEW.estado
        USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.estado = 'ANULADO' AND v_rol NOT IN ('ADMIN', 'SYSTEM') THEN
      RAISE EXCEPTION 'Solo la administración puede anular recaudos' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.estado <> 'ANULADO' AND v_rol NOT IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM') THEN
      RAISE EXCEPTION 'El rol % no puede cambiar el estado de un recaudo', v_rol
        USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.estado = 'VERIFICADO' AND (NEW.verificado_por_id IS NULL OR NEW.verificado_at IS NULL) THEN
      RAISE EXCEPTION 'La verificación debe registrar quién y cuándo' USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  v_descriptivos_cambian :=
       NEW.nombre_pagador IS DISTINCT FROM OLD.nombre_pagador
    OR NEW.identificacion_pagador IS DISTINCT FROM OLD.identificacion_pagador
    OR NEW.unidad_id IS DISTINCT FROM OLD.unidad_id
    OR NEW.numero_comprobante IS DISTINCT FROM OLD.numero_comprobante
    OR NEW.soporte_key IS DISTINCT FROM OLD.soporte_key
    OR NEW.observaciones IS DISTINCT FROM OLD.observaciones
    OR NEW.reserva_id IS DISTINCT FROM OLD.reserva_id;

  IF v_descriptivos_cambian THEN
    IF OLD.estado = 'VERIFICADO' THEN
      RAISE EXCEPTION 'Un recaudo verificado no se puede editar' USING ERRCODE = 'check_violation';
    END IF;
    IF v_rol NOT IN ('ADMIN', 'AUXILIAR', 'SYSTEM') THEN
      RAISE EXCEPTION 'El rol % no puede editar recaudos', v_rol USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_rol = 'AUXILIAR' AND OLD.cierre_id IS NOT NULL THEN
      RAISE EXCEPTION 'El recaudo ya está en un cierre de caja: solo la administración puede editarlo'
        USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;

  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- 9.3 La suma del desglose debe ser igual al valor recibido (se verifica al COMMIT)
CREATE FUNCTION trg_recaudo_cuadre() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_id uuid;
  v_valor numeric;
  v_suma numeric;
BEGIN
  -- IF y no CASE: PL/pgSQL resolvería NEW.recaudo_id también para la tabla recaudos (que no lo tiene)
  IF TG_TABLE_NAME = 'recaudos' THEN
    v_id := NEW.id;
  ELSE
    v_id := NEW.recaudo_id;
  END IF;
  SELECT r.valor_recibido, coalesce(sum(i.valor), 0) INTO v_valor, v_suma
    FROM recaudos r LEFT JOIN recaudo_items i ON i.recaudo_id = r.id
   WHERE r.id = v_id GROUP BY r.valor_recibido;
  IF v_valor IS NOT NULL AND v_valor <> v_suma THEN
    RAISE EXCEPTION 'El desglose del recaudo (%) no coincide con el valor recibido (%)', v_suma, v_valor
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;

-- 9.4 Lo aplicado a un recaudo en consignaciones vigentes no puede superar su valor
CREATE FUNCTION trg_consignacion_aplicado() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  r recaudos%ROWTYPE;
  v_aplicado numeric;
BEGIN
  SELECT * INTO r FROM recaudos WHERE id = NEW.recaudo_id;
  IF r.medio_pago <> 'EFECTIVO' OR r.estado NOT IN ('RECAUDADO_EN_CAJA', 'ENTREGADO_ADMINISTRACION') THEN
    RAISE EXCEPTION 'Solo se consigna efectivo pendiente (recaudo %, estado %)', r.consecutivo, r.estado
      USING ERRCODE = 'check_violation';
  END IF;
  SELECT coalesce(sum(cr.valor_aplicado), 0) INTO v_aplicado
    FROM consignacion_recaudos cr JOIN consignaciones c ON c.id = cr.consignacion_id
   WHERE cr.recaudo_id = NEW.recaudo_id AND c.estado <> 'RECHAZADA';
  IF v_aplicado > r.valor_recibido THEN
    RAISE EXCEPTION 'Lo consignado del recaudo % (%) supera su valor (%)', r.consecutivo, v_aplicado, r.valor_recibido
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;

-- 9.5 Auditoría automática. SECURITY DEFINER: el app_user no tiene INSERT sobre
--     auditoria_recaudos, así que la ÚNICA forma de escribirla es este trigger.
--     Guarda solo los campos que cambiaron. El motivo llega con SET LOCAL app.motivo.
CREATE FUNCTION trg_auditar() RETURNS trigger
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
      RETURN NULL;  -- nada relevante cambió
    END IF;
    SELECT jsonb_object_agg(d.key, v_viejo -> d.key) INTO v_antes FROM jsonb_each(v_despues) d;
    v_accion := CASE
      WHEN v_despues ->> 'estado' IN ('ANULADO', 'RECHAZADA') THEN 'ANULACION'
      WHEN v_despues ? 'estado' THEN 'CAMBIO_ESTADO'
      ELSE 'EDICION' END;
  END IF;

  INSERT INTO auditoria_recaudos (tenant_id, entidad, entidad_id, recaudo_id, usuario_id, accion,
                                  valores_anteriores, valores_nuevos, motivo, ip)
  VALUES (NEW.tenant_id, v_entidad, NEW.id, CASE WHEN v_entidad = 'recaudo' THEN NEW.id END,
          app_user_id(), v_accion, v_antes, v_despues,
          nullif(current_setting('app.motivo', true), ''),
          nullif(current_setting('app.ip', true), '')::inet);
  RETURN NULL;
END $$;

-- 9.6 Instalación de triggers
CREATE TRIGGER trg_recaudos_insert BEFORE INSERT ON recaudos FOR EACH ROW EXECUTE FUNCTION trg_recaudos_insert();
CREATE TRIGGER trg_recaudos_update BEFORE UPDATE ON recaudos FOR EACH ROW EXECUTE FUNCTION trg_recaudos_update();

CREATE CONSTRAINT TRIGGER trg_recaudos_cuadre AFTER INSERT ON recaudos
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION trg_recaudo_cuadre();
CREATE CONSTRAINT TRIGGER trg_items_cuadre AFTER INSERT ON recaudo_items
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION trg_recaudo_cuadre();

CREATE TRIGGER trg_consignacion_aplicado AFTER INSERT ON consignacion_recaudos
  FOR EACH ROW EXECUTE FUNCTION trg_consignacion_aplicado();

CREATE TRIGGER trg_cierres_consecutivo       BEFORE INSERT ON cierres_caja
  FOR EACH ROW EXECUTE FUNCTION trg_asignar_consecutivo('cierre');
CREATE TRIGGER trg_entregas_consecutivo      BEFORE INSERT ON entregas_internas
  FOR EACH ROW EXECUTE FUNCTION trg_asignar_consecutivo('entrega');
CREATE TRIGGER trg_consignaciones_consecutivo BEFORE INSERT ON consignaciones
  FOR EACH ROW EXECUTE FUNCTION trg_asignar_consecutivo('consignacion');

CREATE TRIGGER trg_conceptos_updated      BEFORE UPDATE ON conceptos_recaudo FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_entregas_updated       BEFORE UPDATE ON entregas_internas FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_consignaciones_updated BEFORE UPDATE ON consignaciones    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Detalles inmutables: el desglose, el parqueadero, los cierres y lo aplicado a consignaciones
CREATE TRIGGER trg_items_inmutable        BEFORE UPDATE ON recaudo_items         FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_parqueadero_inmutable  BEFORE UPDATE ON recaudo_parqueadero   FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_cierres_inmutable      BEFORE UPDATE ON cierres_caja          FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_aplicado_inmutable     BEFORE UPDATE ON consignacion_recaudos FOR EACH ROW EXECUTE FUNCTION trg_inmutable();

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'recaudos', 'recaudo_items', 'recaudo_parqueadero', 'cierres_caja', 'entregas_internas',
    'consignaciones', 'consignacion_recaudos', 'auditoria_recaudos', 'cortes_mensuales'
  ] LOOP
    EXECUTE format('CREATE TRIGGER trg_prohibir_delete BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION trg_prohibir_delete()', t);
  END LOOP;
END $$;

DO $$
DECLARE par text[];
BEGIN
  FOREACH par SLICE 1 IN ARRAY ARRAY[
    ARRAY['recaudos', 'recaudo'], ARRAY['cierres_caja', 'cierre_caja'],
    ARRAY['entregas_internas', 'entrega_interna'], ARRAY['consignaciones', 'consignacion'],
    ARRAY['conceptos_recaudo', 'concepto']
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER trg_auditar AFTER INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION trg_auditar(%L)',
      par[1], par[2]);
  END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- 10. Privilegios: el app_user no puede borrar, ni escribir la auditoría o el contador
-- -----------------------------------------------------------------------------
REVOKE DELETE ON recaudos, recaudo_items, recaudo_parqueadero, cierres_caja, entregas_internas,
                 consignaciones, consignacion_recaudos, auditoria_recaudos, cortes_mensuales,
                 alertas_recaudo
  FROM app_user;
REVOKE INSERT, UPDATE ON auditoria_recaudos FROM app_user;
REVOKE ALL ON secuencias FROM app_user;

-- -----------------------------------------------------------------------------
-- 11. Row Level Security por copropiedad y por rol
-- -----------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'secuencias', 'conceptos_recaudo', 'zonas_sociales', 'reservas', 'cierres_caja', 'entregas_internas',
    'recaudos', 'recaudo_items', 'recaudo_parqueadero', 'consignaciones', 'consignacion_recaudos',
    'auditoria_recaudos', 'alertas_recaudo', 'cortes_mensuales'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id())', t);
  END LOOP;
END $$;

-- Catálogos: los lee el personal operativo; solo la administración los modifica
CREATE POLICY rbac_leer ON conceptos_recaudo AS RESTRICTIVE FOR SELECT
  USING (app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'SYSTEM'));
CREATE POLICY rbac_crear ON conceptos_recaudo AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON conceptos_recaudo AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_borrar ON conceptos_recaudo AS RESTRICTIVE FOR DELETE USING (app_role() IN ('ADMIN', 'SYSTEM'));

CREATE POLICY rbac_leer ON zonas_sociales AS RESTRICTIVE FOR SELECT
  USING (app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'SYSTEM'));
CREATE POLICY rbac_crear ON zonas_sociales AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON zonas_sociales AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_borrar ON zonas_sociales AS RESTRICTIVE FOR DELETE USING (app_role() IN ('ADMIN', 'SYSTEM'));

CREATE POLICY rbac_leer ON reservas AS RESTRICTIVE FOR SELECT
  USING (app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'SYSTEM'));
CREATE POLICY rbac_crear ON reservas AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
CREATE POLICY rbac_editar ON reservas AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
CREATE POLICY rbac_borrar ON reservas AS RESTRICTIVE FOR DELETE USING (app_role() IN ('ADMIN', 'SYSTEM'));

-- Recaudos: el auxiliar solo ve y registra lo que él mismo recibió.
-- Contabilidad lee todo y cambia estados (verificación); el consejo no ve el detalle.
CREATE POLICY rbac_leer ON recaudos AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM')
  OR (app_role() = 'AUXILIAR' AND usuario_receptor_id = app_user_id()));
CREATE POLICY rbac_crear ON recaudos AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'SYSTEM')
  OR (app_role() = 'AUXILIAR' AND usuario_receptor_id = app_user_id()));
CREATE POLICY rbac_editar ON recaudos AS RESTRICTIVE FOR UPDATE USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM')
  OR (app_role() = 'AUXILIAR' AND usuario_receptor_id = app_user_id()));

-- Detalles: heredan la visibilidad del recaudo (la subconsulta aplica su RLS)
CREATE POLICY rbac_leer ON recaudo_items AS RESTRICTIVE FOR SELECT
  USING (EXISTS (SELECT 1 FROM recaudos r WHERE r.id = recaudo_id));
CREATE POLICY rbac_crear ON recaudo_items AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM') AND EXISTS (SELECT 1 FROM recaudos r WHERE r.id = recaudo_id));
CREATE POLICY rbac_leer ON recaudo_parqueadero AS RESTRICTIVE FOR SELECT
  USING (EXISTS (SELECT 1 FROM recaudos r WHERE r.id = recaudo_id));
CREATE POLICY rbac_crear ON recaudo_parqueadero AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM') AND EXISTS (SELECT 1 FROM recaudos r WHERE r.id = recaudo_id));

CREATE POLICY rbac_leer ON cierres_caja AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM')
  OR (app_role() = 'AUXILIAR' AND usuario_id = app_user_id()));
CREATE POLICY rbac_crear ON cierres_caja AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'SYSTEM')
  OR (app_role() = 'AUXILIAR' AND usuario_id = app_user_id()));

CREATE POLICY rbac_leer ON entregas_internas AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM')
  OR (app_role() = 'AUXILIAR' AND entregado_por_id = app_user_id()));
CREATE POLICY rbac_crear ON entregas_internas AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'SYSTEM')
  OR (app_role() = 'AUXILIAR' AND entregado_por_id = app_user_id()));
CREATE POLICY rbac_editar ON entregas_internas AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));

CREATE POLICY rbac_leer ON consignaciones AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM')
  OR (app_role() = 'AUXILIAR' AND usuario_consigna_id = app_user_id()));
CREATE POLICY rbac_crear ON consignaciones AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'SYSTEM')
  OR (app_role() = 'AUXILIAR' AND usuario_consigna_id = app_user_id()));
CREATE POLICY rbac_editar ON consignaciones AS RESTRICTIVE FOR UPDATE
  USING (app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM'));

CREATE POLICY rbac_leer ON consignacion_recaudos AS RESTRICTIVE FOR SELECT
  USING (EXISTS (SELECT 1 FROM consignaciones c WHERE c.id = consignacion_id));
CREATE POLICY rbac_crear ON consignacion_recaudos AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM') AND EXISTS (SELECT 1 FROM consignaciones c WHERE c.id = consignacion_id));

CREATE POLICY rbac_leer ON auditoria_recaudos AS RESTRICTIVE FOR SELECT
  USING (app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM'));

-- Alertas: las genera cualquier rol operativo (p. ej. un cierre con faltante); las atiende la administración
CREATE POLICY rbac_leer ON alertas_recaudo AS RESTRICTIVE FOR SELECT
  USING (app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM'));
CREATE POLICY rbac_crear ON alertas_recaudo AS RESTRICTIVE FOR INSERT
  WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'SYSTEM'));
CREATE POLICY rbac_editar ON alertas_recaudo AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));

CREATE POLICY rbac_leer ON cortes_mensuales AS RESTRICTIVE FOR SELECT
  USING (app_role() IN ('ADMIN', 'CONTABILIDAD', 'CONSEJO', 'SYSTEM'));
CREATE POLICY rbac_crear ON cortes_mensuales AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON cortes_mensuales AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));

-- -----------------------------------------------------------------------------
-- 11b. Resumen para el dashboard
--      El Consejo ve totales pero NO el detalle de los recaudos (RLS se lo niega):
--      esta función SECURITY DEFINER entrega solo agregados, comprueba el rol y
--      filtra EXPLÍCITAMENTE por copropiedad (como dueño, no la limita RLS).
-- -----------------------------------------------------------------------------
CREATE FUNCTION resumen_recaudos(p_anio int, p_mes int) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_tenant   uuid := app_tenant_id();
  v_ini      date := make_date(p_anio, p_mes, 1);
  v_fin      date := (make_date(p_anio, p_mes, 1) + interval '1 month')::date;
  v_ini_anio date := make_date(p_anio, 1, 1);
  v_r        jsonb;
BEGIN
  IF v_tenant IS NULL OR app_role() NOT IN ('ADMIN', 'CONTABILIDAD', 'CONSEJO', 'SYSTEM') THEN
    RAISE EXCEPTION 'Su rol no permite consultar el resumen de recaudos' USING ERRCODE = 'insufficient_privilege';
  END IF;

  WITH activos AS (
    SELECT r.id, r.valor_recibido, r.medio_pago, r.estado,
           (r.fecha_recaudo AT TIME ZONE 'America/Bogota')::date AS dia
      FROM recaudos r
     WHERE r.tenant_id = v_tenant AND r.estado <> 'ANULADO'
  ),
  mes AS (SELECT * FROM activos WHERE dia >= v_ini AND dia < v_fin),
  aplicado AS (
    SELECT cr.recaudo_id, sum(cr.valor_aplicado) AS valor
      FROM consignacion_recaudos cr JOIN consignaciones c ON c.id = cr.consignacion_id
     WHERE cr.tenant_id = v_tenant AND c.estado <> 'RECHAZADA'
     GROUP BY cr.recaudo_id
  ),
  pendiente AS (  -- efectivo que aún no está aplicado a ninguna consignación vigente
    SELECT a.estado, a.valor_recibido - coalesce(ap.valor, 0) AS saldo
      FROM activos a LEFT JOIN aplicado ap ON ap.recaudo_id = a.id
     WHERE a.medio_pago = 'EFECTIVO' AND a.estado IN ('RECAUDADO_EN_CAJA', 'ENTREGADO_ADMINISTRACION')
  )
  SELECT jsonb_build_object(
    'periodo', to_char(v_ini, 'YYYY-MM'),
    'total_mes', (SELECT coalesce(sum(valor_recibido), 0) FROM mes),
    'cantidad_mes', (SELECT count(*) FROM mes),
    'total_anio', (SELECT coalesce(sum(valor_recibido), 0) FROM activos WHERE dia >= v_ini_anio AND dia < v_fin),
    'por_concepto', (SELECT coalesce(jsonb_agg(jsonb_build_object('codigo', x.codigo, 'concepto', x.nombre, 'total', x.total)
                                            ORDER BY x.total DESC), '[]')
                       FROM (SELECT c.codigo, c.nombre, sum(i.valor) AS total
                               FROM mes m JOIN recaudo_items i ON i.recaudo_id = m.id
                               JOIN conceptos_recaudo c ON c.id = i.concepto_id
                              GROUP BY c.codigo, c.nombre) x),
    'por_medio', (SELECT coalesce(jsonb_object_agg(x.medio_pago, x.total), '{}')
                    FROM (SELECT medio_pago, sum(valor_recibido) AS total FROM mes GROUP BY medio_pago) x),
    'por_estado', (SELECT coalesce(jsonb_object_agg(x.estado, x.total), '{}')
                     FROM (SELECT estado, sum(valor_recibido) AS total FROM mes GROUP BY estado) x),
    'serie_diaria', (SELECT coalesce(jsonb_agg(jsonb_build_object('dia', x.dia, 'total', x.total) ORDER BY x.dia), '[]')
                       FROM (SELECT dia, sum(valor_recibido) AS total FROM mes GROUP BY dia) x),
    'efectivo_en_caja', (SELECT coalesce(sum(saldo), 0) FROM pendiente WHERE estado = 'RECAUDADO_EN_CAJA'),
    'efectivo_en_administracion', (SELECT coalesce(sum(saldo), 0) FROM pendiente WHERE estado = 'ENTREGADO_ADMINISTRACION'),
    'transferencias_pendientes', (SELECT jsonb_build_object('cantidad', count(*), 'total', coalesce(sum(valor_recibido), 0))
                                    FROM activos WHERE estado = 'PENDIENTE_VERIFICACION'),
    'alertas_abiertas', (SELECT count(*) FROM alertas_recaudo WHERE tenant_id = v_tenant AND estado = 'ABIERTA')
  ) INTO v_r;
  RETURN v_r;
END $$;

-- -----------------------------------------------------------------------------
-- 12. Conceptos iniciales (idempotente). Tarifas de ejemplo: la administración las ajusta.
-- -----------------------------------------------------------------------------
CREATE FUNCTION seed_conceptos_recaudo(p_tenant uuid) RETURNS void LANGUAGE sql AS $$
  INSERT INTO conceptos_recaudo
    (tenant_id, codigo, nombre, descripcion, tarifa_base, tipo_cobro, fraccion_minutos, requiere_reserva, requiere_vehiculo)
  VALUES
    (p_tenant, 'PARQUEADERO', 'Parqueadero de visitantes', 'Cobro por tiempo de permanencia del vehículo',
     2000, 'POR_HORA', 60, false, true),
    (p_tenant, 'ASEO', 'Aseo de áreas sociales', 'Aseo posterior al uso de una zona social',
     50000, 'FIJO', NULL, false, false),
    (p_tenant, 'ALQUILER_ZONA', 'Alquiler de zonas sociales', 'Salón social, BBQ y demás zonas reservables',
     150000, 'FIJO', NULL, true, false),
    (p_tenant, 'OTROS', 'Otros recaudos', 'Ingresos extraordinarios no clasificados',
     NULL, 'VARIABLE', NULL, false, false)
  ON CONFLICT (tenant_id, codigo) DO NOTHING
$$;

DO $$
DECLARE t uuid;
BEGIN
  FOR t IN SELECT id FROM tenants LOOP
    PERFORM set_config('app.tenant_id', t::text, true);
    PERFORM set_config('app.role', 'SYSTEM', true);
    PERFORM seed_conceptos_recaudo(t);
  END LOOP;
END $$;
