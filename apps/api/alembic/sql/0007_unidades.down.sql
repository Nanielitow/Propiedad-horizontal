-- Reversa de 0007. Las columnas nuevas de `units` se eliminan (torre, número y coeficiente se conservan).
DROP TABLE IF EXISTS demo_snapshot.auditoria_unidades, demo_snapshot.importaciones_unidades,
  demo_snapshot.vehiculos, demo_snapshot.unidad_personas, demo_snapshot.personas;
DROP POLICY IF EXISTS rbac_leer ON units;
DROP POLICY IF EXISTS rbac_crear ON units;
DROP POLICY IF EXISTS rbac_editar ON units;
DROP TRIGGER IF EXISTS trg_units_principal ON units;
DROP TRIGGER IF EXISTS trg_prohibir_delete ON units;
DROP TRIGGER IF EXISTS trg_auditar ON units;
DROP TABLE IF EXISTS auditoria_unidades, importaciones_unidades, vehiculos, unidad_personas, personas CASCADE;
DROP FUNCTION IF EXISTS app_unidades_propias(), trg_auditar_unidades(), trg_persona_sincronizar_after(),
  trg_vinculo_sincronizar(), sincronizar_unidad_membership(uuid, uuid), trg_unidad_personas_update(),
  trg_units_principal();
GRANT DELETE ON units TO app_user;
ALTER TABLE units
  DROP CONSTRAINT IF EXISTS units_principal_fk,
  DROP CONSTRAINT IF EXISTS units_principal_ck,
  DROP CONSTRAINT IF EXISTS units_coeficiente_ck,
  DROP CONSTRAINT IF EXISTS units_numero_ck,
  DROP COLUMN IF EXISTS updated_at,
  DROP COLUMN IF EXISTS created_at,
  DROP COLUMN IF EXISTS activa,
  DROP COLUMN IF EXISTS observaciones,
  DROP COLUMN IF EXISTS ocupacion,
  DROP COLUMN IF EXISTS matricula_inmobiliaria,
  DROP COLUMN IF EXISTS area_m2,
  DROP COLUMN IF EXISTS unidad_principal_id,
  DROP COLUMN IF EXISTS tipo;
DROP TYPE IF EXISTS tipo_vehiculo, relacion_unidad, tipo_documento_identidad, ocupacion_unidad, tipo_unidad;
