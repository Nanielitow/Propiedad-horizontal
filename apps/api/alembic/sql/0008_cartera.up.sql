-- =============================================================================
--  0008 · Cartera de cuotas de administración
--  Diseño: docs/CARTERA.md
--
--  Cada mes se emite un periodo con un cargo por unidad (cuota ordinaria) y los
--  intereses de mora sobre el capital vencido. Los pagos se imputan por la ley
--  (primero intereses, luego lo más antiguo) mediante `aplicaciones_pago`; el
--  saldo de cada cargo es valor − aplicaciones − ajustes, nunca un campo editable.
--
--  Reutiliza: app_role(), app_unidades_propias(), next_consecutivo(),
--  trg_asignar_consecutivo(), trg_prohibir_delete(), trg_inmutable(),
--  set_updated_at(), accion_auditoria y medio_pago.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Tipos
-- -----------------------------------------------------------------------------
CREATE TYPE metodo_cuota        AS ENUM ('COEFICIENTE', 'TARIFA_POR_TIPO');
CREATE TYPE tipo_concepto_cartera AS ENUM ('ORDINARIA', 'EXTRAORDINARIA', 'INTERES', 'MULTA', 'OTRO');
CREATE TYPE estado_periodo      AS ENUM ('EMITIDO', 'ANULADO');
CREATE TYPE estado_cargo        AS ENUM ('VIGENTE', 'ANULADO');
CREATE TYPE estado_pago_cartera AS ENUM ('APLICADO', 'ANULADO');
CREATE TYPE tipo_ajuste         AS ENUM ('DESCUENTO_PRONTO_PAGO', 'CONDONACION', 'CORRECCION');

-- -----------------------------------------------------------------------------
-- 2. Configuración por copropiedad
-- -----------------------------------------------------------------------------
CREATE TABLE cartera_config (
  tenant_id             uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  metodo                metodo_cuota NOT NULL DEFAULT 'COEFICIENTE',
  presupuesto_mensual   numeric(14,2) CHECK (presupuesto_mensual IS NULL OR presupuesto_mensual > 0),
  tarifas_por_tipo      jsonb NOT NULL DEFAULT '{}',   -- {"APARTAMENTO": 250000, "LOCAL": 180000}
  redondeo              int NOT NULL DEFAULT 100 CHECK (redondeo IN (1, 10, 50, 100, 500, 1000)),
  dia_vencimiento       int NOT NULL DEFAULT 10 CHECK (dia_vencimiento BETWEEN 1 AND 28),
  descuento_pct         numeric(5,2) NOT NULL DEFAULT 0 CHECK (descuento_pct BETWEEN 0 AND 50),
  dia_limite_descuento  int CHECK (dia_limite_descuento IS NULL OR dia_limite_descuento BETWEEN 1 AND 28),
  cobrar_intereses      boolean NOT NULL DEFAULT true,
  tasa_mora_mensual     numeric(6,4) NOT NULL DEFAULT 1.5 CHECK (tasa_mora_mensual BETWEEN 0 AND 5),
  nota_cuenta_cobro     text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CHECK (metodo <> 'COEFICIENTE' OR presupuesto_mensual IS NOT NULL),
  CHECK (descuento_pct = 0 OR dia_limite_descuento IS NOT NULL)
);

-- -----------------------------------------------------------------------------
-- 3. Conceptos (tabla maestra extensible)
-- -----------------------------------------------------------------------------
CREATE TABLE conceptos_cartera (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  codigo           text NOT NULL CHECK (codigo ~ '^[A-Z][A-Z0-9_]{1,39}$'),
  nombre           text NOT NULL,
  tipo             tipo_concepto_cartera NOT NULL,
  genera_interes   boolean NOT NULL DEFAULT true,   -- los intereses NO generan interés (anatocismo)
  activo           boolean NOT NULL DEFAULT true,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, codigo),
  UNIQUE (tenant_id, id),
  CHECK (tipo <> 'INTERES' OR NOT genera_interes)
);

-- -----------------------------------------------------------------------------
-- 4. Periodos de facturación
-- -----------------------------------------------------------------------------
CREATE TABLE periodos_cartera (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  anio                    int NOT NULL CHECK (anio BETWEEN 2000 AND 2100),
  mes                     int NOT NULL CHECK (mes BETWEEN 1 AND 12),
  estado                  estado_periodo NOT NULL DEFAULT 'EMITIDO',
  fecha_emision           date NOT NULL,
  fecha_vencimiento       date NOT NULL,
  fecha_limite_descuento  date,
  metodo                  metodo_cuota NOT NULL,          -- fotografía de la configuración usada
  presupuesto_mensual     numeric(14,2),
  descuento_pct           numeric(5,2) NOT NULL DEFAULT 0,
  tasa_mora_mensual       numeric(6,4),
  unidades_facturadas     int NOT NULL DEFAULT 0,
  total_cuotas            numeric(14,2) NOT NULL DEFAULT 0,
  total_intereses         numeric(14,2) NOT NULL DEFAULT 0,
  advertencias            jsonb NOT NULL DEFAULT '[]',
  emitido_por_id          uuid REFERENCES users(id) ON DELETE SET NULL,
  anulado_por_id          uuid REFERENCES users(id) ON DELETE SET NULL,
  anulado_at              timestamptz,
  motivo_anulacion        text,
  created_at              timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  CHECK (fecha_vencimiento >= fecha_emision),
  CHECK (fecha_limite_descuento IS NULL OR fecha_limite_descuento <= fecha_vencimiento),
  CHECK ((estado = 'ANULADO') = (anulado_at IS NOT NULL)),
  CHECK (estado <> 'ANULADO' OR length(btrim(motivo_anulacion)) >= 10)
);
CREATE UNIQUE INDEX periodos_cartera_mes_idx ON periodos_cartera (tenant_id, anio, mes) WHERE estado = 'EMITIDO';

-- -----------------------------------------------------------------------------
-- 5. Cargos (lo que se le cobra a cada unidad)
-- -----------------------------------------------------------------------------
CREATE TABLE cargos_cartera (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  unidad_id               uuid NOT NULL,
  periodo_id              uuid,                            -- NULL: cargo manual (extraordinaria, multa)
  concepto_id             uuid NOT NULL,
  descripcion             text NOT NULL CHECK (btrim(descripcion) <> ''),
  valor                   numeric(14,2) NOT NULL CHECK (valor > 0),
  fecha_causacion         date NOT NULL,
  fecha_vencimiento       date NOT NULL,
  genera_interes          boolean NOT NULL,                -- fotografía del concepto
  descuento_pct           numeric(5,2),                    -- pronto pago (solo cuota ordinaria)
  fecha_limite_descuento  date,
  responsable_persona_id  uuid,                            -- responsable de pago al causarse
  responsable_nombre      text,
  estado                  estado_cargo NOT NULL DEFAULT 'VIGENTE',
  anulado_por_id          uuid REFERENCES users(id) ON DELETE SET NULL,
  anulado_at              timestamptz,
  motivo_anulacion        text,
  creado_por_id           uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at              timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, unidad_id)              REFERENCES units(tenant_id, id),
  FOREIGN KEY (tenant_id, periodo_id)             REFERENCES periodos_cartera(tenant_id, id),
  FOREIGN KEY (tenant_id, concepto_id)            REFERENCES conceptos_cartera(tenant_id, id),
  FOREIGN KEY (tenant_id, responsable_persona_id) REFERENCES personas(tenant_id, id),
  CHECK (fecha_vencimiento >= fecha_causacion),
  CHECK ((descuento_pct IS NULL) = (fecha_limite_descuento IS NULL)),
  CHECK ((estado = 'ANULADO') = (anulado_at IS NOT NULL)),
  CHECK (estado <> 'ANULADO' OR length(btrim(motivo_anulacion)) >= 10)
);
CREATE INDEX cargos_cartera_unidad_idx  ON cargos_cartera (tenant_id, unidad_id, fecha_vencimiento);
CREATE INDEX cargos_cartera_periodo_idx ON cargos_cartera (tenant_id, periodo_id) WHERE periodo_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 6. Pagos, su imputación y ajustes
-- -----------------------------------------------------------------------------
CREATE TABLE pagos_cartera (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo       bigint NOT NULL,                  -- número de recibo, sin huecos (trigger)
  unidad_id         uuid NOT NULL,
  fecha_pago        date NOT NULL,
  valor             numeric(14,2) NOT NULL CHECK (valor > 0),
  medio_pago        medio_pago NOT NULL,
  referencia        text,                             -- número de transacción o consignación
  pagador_nombre    text,
  soporte_key       text,
  observaciones     text,
  estado            estado_pago_cartera NOT NULL DEFAULT 'APLICADO',
  registrado_por_id uuid NOT NULL REFERENCES users(id),
  anulado_por_id    uuid REFERENCES users(id) ON DELETE SET NULL,
  anulado_at        timestamptz,
  motivo_anulacion  text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, consecutivo),
  FOREIGN KEY (tenant_id, unidad_id) REFERENCES units(tenant_id, id),
  CHECK (medio_pago = 'EFECTIVO' OR referencia IS NOT NULL OR soporte_key IS NOT NULL),
  CHECK ((estado = 'ANULADO') = (anulado_at IS NOT NULL)),
  CHECK (estado <> 'ANULADO' OR length(btrim(motivo_anulacion)) >= 10)
);
CREATE INDEX pagos_cartera_unidad_idx ON pagos_cartera (tenant_id, unidad_id, fecha_pago);
-- Una misma referencia bancaria no se registra dos veces (doble digitación)
CREATE UNIQUE INDEX pagos_cartera_referencia_idx ON pagos_cartera (tenant_id, medio_pago, referencia)
  WHERE referencia IS NOT NULL AND estado = 'APLICADO';

CREATE TABLE aplicaciones_pago (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  pago_id     uuid NOT NULL,
  cargo_id    uuid NOT NULL,
  valor       numeric(14,2) NOT NULL CHECK (valor > 0),
  created_at  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, pago_id)  REFERENCES pagos_cartera(tenant_id, id),
  FOREIGN KEY (tenant_id, cargo_id) REFERENCES cargos_cartera(tenant_id, id)
);
CREATE INDEX aplicaciones_pago_cargo_idx ON aplicaciones_pago (cargo_id);
CREATE INDEX aplicaciones_pago_pago_idx  ON aplicaciones_pago (pago_id);

CREATE TABLE ajustes_cartera (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  cargo_id          uuid NOT NULL,
  tipo              tipo_ajuste NOT NULL,
  valor             numeric(14,2) NOT NULL CHECK (valor > 0),
  motivo            text NOT NULL CHECK (length(btrim(motivo)) >= 5),
  pago_id           uuid,                             -- el descuento nace de un pago y cae con él
  registrado_por_id uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, cargo_id) REFERENCES cargos_cartera(tenant_id, id),
  FOREIGN KEY (tenant_id, pago_id)  REFERENCES pagos_cartera(tenant_id, id),
  CHECK (tipo <> 'DESCUENTO_PRONTO_PAGO' OR pago_id IS NOT NULL)
);
CREATE INDEX ajustes_cartera_cargo_idx ON ajustes_cartera (cargo_id);

-- -----------------------------------------------------------------------------
-- 7. Paz y salvo
-- -----------------------------------------------------------------------------
CREATE TABLE paz_y_salvos (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  consecutivo          bigint NOT NULL,
  unidad_id            uuid NOT NULL,
  fecha_emision        date NOT NULL,
  valido_hasta         date NOT NULL,
  titular_nombre       text,
  codigo_verificacion  text NOT NULL UNIQUE,
  emitido_por_id       uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, consecutivo),
  FOREIGN KEY (tenant_id, unidad_id) REFERENCES units(tenant_id, id),
  CHECK (valido_hasta >= fecha_emision)
);

-- -----------------------------------------------------------------------------
-- 8. Auditoría
-- -----------------------------------------------------------------------------
CREATE TABLE auditoria_cartera (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  entidad             text NOT NULL,          -- 'config', 'periodo', 'cargo', 'pago', 'ajuste', 'paz_y_salvo'
  entidad_id          uuid NOT NULL,
  unidad_id           uuid,
  usuario_id          uuid,
  accion              accion_auditoria NOT NULL,
  valores_anteriores  jsonb,
  valores_nuevos      jsonb,
  motivo              text,
  fecha_hora          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auditoria_cartera_unidad_idx ON auditoria_cartera (tenant_id, unidad_id, fecha_hora DESC);

-- -----------------------------------------------------------------------------
-- 9. Saldos: siempre calculados (vista con la RLS de quien consulta)
-- -----------------------------------------------------------------------------
CREATE VIEW v_saldos_cargo WITH (security_invoker = true) AS
SELECT c.id, c.tenant_id, c.unidad_id, c.periodo_id, c.concepto_id, c.valor, c.fecha_causacion,
       c.fecha_vencimiento, c.genera_interes, c.estado,
       coalesce(ap.total, 0) AS aplicado,
       coalesce(aj.total, 0) AS ajustado,
       CASE WHEN c.estado = 'ANULADO' THEN 0 ELSE c.valor - coalesce(ap.total, 0) - coalesce(aj.total, 0) END AS saldo
  FROM cargos_cartera c
  LEFT JOIN LATERAL (
    SELECT sum(a.valor) AS total FROM aplicaciones_pago a
      JOIN pagos_cartera p ON p.id = a.pago_id AND p.estado = 'APLICADO'
     WHERE a.cargo_id = c.id) ap ON true
  LEFT JOIN LATERAL (
    SELECT sum(j.valor) AS total FROM ajustes_cartera j
      LEFT JOIN pagos_cartera p ON p.id = j.pago_id
     WHERE j.cargo_id = c.id AND (j.pago_id IS NULL OR p.estado = 'APLICADO')) aj ON true;

-- -----------------------------------------------------------------------------
-- 10. Reglas en la base
-- -----------------------------------------------------------------------------

-- 10.1 Lo emitido no se edita: solo se anula (con motivo)
CREATE FUNCTION trg_solo_anular() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_viejo jsonb := to_jsonb(OLD); v_nuevo jsonb := to_jsonb(NEW); k text;
BEGIN
  IF OLD.estado::text = 'ANULADO' THEN
    RAISE EXCEPTION 'El registro ya está anulado' USING ERRCODE = 'insufficient_privilege';
  END IF;
  FOR k IN SELECT jsonb_object_keys(v_nuevo) LOOP
    IF k NOT IN ('estado', 'anulado_por_id', 'anulado_at', 'motivo_anulacion')
       AND v_viejo -> k IS DISTINCT FROM v_nuevo -> k THEN
      RAISE EXCEPTION 'Los registros de % no se editan: anúlelos con un motivo', TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

-- 10.2 Una aplicación no puede dejar un cargo con saldo negativo ni exceder el pago
CREATE FUNCTION trg_aplicacion_valida() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_saldo numeric; v_disponible numeric; v_unidad_pago uuid; v_unidad_cargo uuid; v_estado text;
BEGIN
  -- Dos pagos simultáneos sobre el mismo cargo se serializan (candado de la transacción)
  PERFORM pg_advisory_xact_lock(hashtext('cargo:' || NEW.cargo_id::text));
  PERFORM pg_advisory_xact_lock(hashtext('pago:' || NEW.pago_id::text));
  SELECT unidad_id, estado::text INTO v_unidad_pago, v_estado FROM pagos_cartera WHERE id = NEW.pago_id;
  SELECT unidad_id INTO v_unidad_cargo FROM cargos_cartera WHERE id = NEW.cargo_id;
  IF v_estado <> 'APLICADO' THEN
    RAISE EXCEPTION 'No se puede aplicar un pago anulado' USING ERRCODE = 'check_violation';
  END IF;
  IF v_unidad_pago <> v_unidad_cargo THEN
    RAISE EXCEPTION 'El pago y el cargo son de unidades distintas' USING ERRCODE = 'check_violation';
  END IF;
  SELECT saldo INTO v_saldo FROM v_saldos_cargo WHERE id = NEW.cargo_id;
  IF NEW.valor > v_saldo THEN
    RAISE EXCEPTION 'La aplicación (%) supera el saldo del cargo (%)', NEW.valor, v_saldo USING ERRCODE = 'check_violation';
  END IF;
  SELECT p.valor - coalesce(sum(a.valor), 0) INTO v_disponible
    FROM pagos_cartera p LEFT JOIN aplicaciones_pago a ON a.pago_id = p.id
   WHERE p.id = NEW.pago_id GROUP BY p.valor;
  IF NEW.valor > v_disponible THEN
    RAISE EXCEPTION 'La aplicación (%) supera lo disponible del pago (%)', NEW.valor, v_disponible USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION trg_ajuste_valido() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_saldo numeric;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('cargo:' || NEW.cargo_id::text));
  SELECT saldo INTO v_saldo FROM v_saldos_cargo WHERE id = NEW.cargo_id;
  IF NEW.valor > v_saldo THEN
    RAISE EXCEPTION 'El ajuste (%) supera el saldo del cargo (%)', NEW.valor, v_saldo USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

-- 10.3 Auditoría automática
CREATE FUNCTION trg_auditar_cartera() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_entidad text := TG_ARGV[0];
  v_nuevo jsonb := to_jsonb(NEW) - 'updated_at';
  v_viejo jsonb;
  v_antes jsonb;
  v_despues jsonb;
  v_accion accion_auditoria;
  v_id uuid;
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
    v_accion := CASE WHEN (v_despues ->> 'estado') = 'ANULADO' THEN 'ANULACION' ELSE 'EDICION' END;
  END IF;
  v_id := CASE WHEN v_entidad = 'config' THEN (v_nuevo ->> 'tenant_id')::uuid ELSE (v_nuevo ->> 'id')::uuid END;
  INSERT INTO auditoria_cartera (tenant_id, entidad, entidad_id, unidad_id, usuario_id, accion,
                                 valores_anteriores, valores_nuevos, motivo)
  VALUES (NEW.tenant_id, v_entidad, v_id, (v_nuevo ->> 'unidad_id')::uuid, app_user_id(), v_accion,
          v_antes, v_despues, nullif(current_setting('app.motivo', true), ''));
  RETURN NULL;
END $$;

-- 10.4 Instalación
CREATE TRIGGER trg_config_updated BEFORE UPDATE ON cartera_config FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_pagos_consecutivo BEFORE INSERT ON pagos_cartera
  FOR EACH ROW EXECUTE FUNCTION trg_asignar_consecutivo('pago_cartera');
CREATE TRIGGER trg_paz_y_salvo_consecutivo BEFORE INSERT ON paz_y_salvos
  FOR EACH ROW EXECUTE FUNCTION trg_asignar_consecutivo('paz_y_salvo');
CREATE TRIGGER trg_periodos_solo_anular BEFORE UPDATE ON periodos_cartera FOR EACH ROW EXECUTE FUNCTION trg_solo_anular();
CREATE TRIGGER trg_cargos_solo_anular BEFORE UPDATE ON cargos_cartera FOR EACH ROW EXECUTE FUNCTION trg_solo_anular();
CREATE TRIGGER trg_pagos_solo_anular BEFORE UPDATE ON pagos_cartera FOR EACH ROW EXECUTE FUNCTION trg_solo_anular();
CREATE TRIGGER trg_aplicaciones_inmutable BEFORE UPDATE ON aplicaciones_pago FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_ajustes_inmutable BEFORE UPDATE ON ajustes_cartera FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_paz_y_salvos_inmutable BEFORE UPDATE ON paz_y_salvos FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER trg_aplicacion_valida BEFORE INSERT ON aplicaciones_pago FOR EACH ROW EXECUTE FUNCTION trg_aplicacion_valida();
CREATE TRIGGER trg_ajuste_valido BEFORE INSERT ON ajustes_cartera FOR EACH ROW EXECUTE FUNCTION trg_ajuste_valido();

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['cartera_config', 'conceptos_cartera', 'periodos_cartera', 'cargos_cartera', 'pagos_cartera',
                           'aplicaciones_pago', 'ajustes_cartera', 'paz_y_salvos', 'auditoria_cartera']
  LOOP
    EXECUTE format('CREATE TRIGGER trg_prohibir_delete BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION trg_prohibir_delete()', t);
  END LOOP;
END $$;

DO $$
DECLARE par text[];
BEGIN
  FOREACH par SLICE 1 IN ARRAY ARRAY[
    ARRAY['cartera_config', 'config'], ARRAY['periodos_cartera', 'periodo'], ARRAY['cargos_cartera', 'cargo'],
    ARRAY['pagos_cartera', 'pago'], ARRAY['ajustes_cartera', 'ajuste'], ARRAY['paz_y_salvos', 'paz_y_salvo']
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER trg_auditar AFTER INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION trg_auditar_cartera(%L)',
      par[1], par[2]);
  END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- 11. Privilegios
-- -----------------------------------------------------------------------------
REVOKE DELETE ON cartera_config, conceptos_cartera, periodos_cartera, cargos_cartera, pagos_cartera,
                 aplicaciones_pago, ajustes_cartera, paz_y_salvos, auditoria_cartera FROM app_user;
REVOKE INSERT, UPDATE ON auditoria_cartera FROM app_user;

-- -----------------------------------------------------------------------------
-- 12. Row Level Security
--     Personal que consulta: ADMIN, CONTABILIDAD, AUXILIAR (informa saldos en recepción),
--     CONSEJO (vigilancia de la cartera). El residente: solo sus unidades.
-- -----------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['cartera_config', 'conceptos_cartera', 'periodos_cartera', 'cargos_cartera', 'pagos_cartera',
                           'aplicaciones_pago', 'ajustes_cartera', 'paz_y_salvos', 'auditoria_cartera']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id())', t);
  END LOOP;
END $$;

-- Lectura del personal (y del residente donde aplica)
CREATE POLICY rbac_leer ON cartera_config AS RESTRICTIVE FOR SELECT USING (true);  -- fechas y descuento: públicas en la copropiedad
CREATE POLICY rbac_leer ON conceptos_cartera AS RESTRICTIVE FOR SELECT USING (true);
CREATE POLICY rbac_leer ON periodos_cartera AS RESTRICTIVE FOR SELECT USING (true);
CREATE POLICY rbac_leer ON cargos_cartera AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'AUXILIAR', 'CONSEJO', 'SYSTEM') OR unidad_id IN (SELECT app_unidades_propias()));
CREATE POLICY rbac_leer ON pagos_cartera AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'AUXILIAR', 'CONSEJO', 'SYSTEM') OR unidad_id IN (SELECT app_unidades_propias()));
CREATE POLICY rbac_leer ON aplicaciones_pago AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'AUXILIAR', 'CONSEJO', 'SYSTEM')
  OR cargo_id IN (SELECT id FROM cargos_cartera WHERE unidad_id IN (SELECT app_unidades_propias())));
CREATE POLICY rbac_leer ON ajustes_cartera AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'AUXILIAR', 'CONSEJO', 'SYSTEM')
  OR cargo_id IN (SELECT id FROM cargos_cartera WHERE unidad_id IN (SELECT app_unidades_propias())));
CREATE POLICY rbac_leer ON paz_y_salvos AS RESTRICTIVE FOR SELECT USING (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'AUXILIAR', 'CONSEJO', 'SYSTEM') OR unidad_id IN (SELECT app_unidades_propias()));
CREATE POLICY rbac_leer ON auditoria_cartera AS RESTRICTIVE FOR SELECT USING (app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM'));

-- Escritura
CREATE POLICY rbac_crear ON cartera_config AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON cartera_config AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_crear ON conceptos_cartera AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON conceptos_cartera AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_crear ON periodos_cartera AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON periodos_cartera AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_crear ON cargos_cartera AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_editar ON cargos_cartera AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));
-- Pagos: administración y contabilidad (concilia con el extracto). La aplicación de saldos a
-- favor al emitir un periodo la hace el administrador con la misma regla.
CREATE POLICY rbac_crear ON pagos_cartera AS RESTRICTIVE FOR INSERT
  WITH CHECK (app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM') AND registrado_por_id = coalesce(app_user_id(), registrado_por_id));
CREATE POLICY rbac_editar ON pagos_cartera AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'SYSTEM'));
CREATE POLICY rbac_crear ON aplicaciones_pago AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'CONTABILIDAD', 'SYSTEM'));
CREATE POLICY rbac_crear ON ajustes_cartera AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'SYSTEM') OR (app_role() = 'CONTABILIDAD' AND tipo = 'DESCUENTO_PRONTO_PAGO'));
-- Paz y salvo: el personal y el propio residente (si está al día; lo verifica el servicio)
CREATE POLICY rbac_crear ON paz_y_salvos AS RESTRICTIVE FOR INSERT WITH CHECK (
  app_role() IN ('ADMIN', 'CONTABILIDAD', 'AUXILIAR', 'SYSTEM') OR unidad_id IN (SELECT app_unidades_propias()));

-- -----------------------------------------------------------------------------
-- 13. Conceptos iniciales (idempotente)
-- -----------------------------------------------------------------------------
CREATE FUNCTION seed_conceptos_cartera(p_tenant uuid) RETURNS void LANGUAGE sql AS $$
  INSERT INTO conceptos_cartera (tenant_id, codigo, nombre, tipo, genera_interes) VALUES
    (p_tenant, 'ADMINISTRACION', 'Cuota de administración', 'ORDINARIA', true),
    (p_tenant, 'EXTRAORDINARIA', 'Cuota extraordinaria', 'EXTRAORDINARIA', true),
    (p_tenant, 'INTERESES_MORA', 'Intereses de mora', 'INTERES', false),
    (p_tenant, 'MULTA', 'Multa por incumplimiento del reglamento', 'MULTA', false),
    (p_tenant, 'OTRO', 'Otros cobros', 'OTRO', false)
  ON CONFLICT (tenant_id, codigo) DO NOTHING
$$;
SELECT seed_conceptos_cartera(id) FROM tenants;
