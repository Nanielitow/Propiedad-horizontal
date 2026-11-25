-- Reversa de 0009. 'RECHAZADA' permanece en estado_reserva (PostgreSQL no quita valores de un ENUM).
DROP TABLE IF EXISTS demo_snapshot.auditoria_portal, demo_snapshot.circular_lecturas, demo_snapshot.circulares,
  demo_snapshot.pqrs_mensajes, demo_snapshot.pqrs;
DROP TRIGGER IF EXISTS trg_auditar ON reservas;
DROP TRIGGER IF EXISTS trg_reservas_residente ON reservas;
DROP POLICY IF EXISTS rbac_leer ON zonas_sociales;
CREATE POLICY rbac_leer ON zonas_sociales AS RESTRICTIVE FOR SELECT USING (app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'SYSTEM'));
DROP POLICY IF EXISTS rbac_leer ON reservas;
CREATE POLICY rbac_leer ON reservas AS RESTRICTIVE FOR SELECT USING (app_role() IN ('ADMIN', 'AUXILIAR', 'CONTABILIDAD', 'SYSTEM'));
DROP POLICY IF EXISTS rbac_crear ON reservas;
CREATE POLICY rbac_crear ON reservas AS RESTRICTIVE FOR INSERT WITH CHECK (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
DROP POLICY IF EXISTS rbac_editar ON reservas;
CREATE POLICY rbac_editar ON reservas AS RESTRICTIVE FOR UPDATE USING (app_role() IN ('ADMIN', 'AUXILIAR', 'SYSTEM'));
DROP TABLE IF EXISTS auditoria_portal, circular_lecturas, circulares, pqrs_mensajes, pqrs CASCADE;
DROP FUNCTION IF EXISTS trg_auditar_portal(), trg_circulares_update(), trg_pqrs_update(), trg_pqrs_consecutivo(),
  trg_reservas_residente(), disponibilidad_zona(uuid, date, date);
ALTER TABLE reservas DROP COLUMN IF EXISTS updated_at, DROP COLUMN IF EXISTS motivo_decision,
  DROP COLUMN IF EXISTS decidida_at, DROP COLUMN IF EXISTS decidida_por_id, DROP COLUMN IF EXISTS solicitada_en_portal,
  DROP COLUMN IF EXISTS numero_asistentes;
ALTER TABLE zonas_sociales DROP CONSTRAINT IF EXISTS zonas_anticipacion_ck, DROP CONSTRAINT IF EXISTS zonas_horario_ck,
  DROP COLUMN IF EXISTS reservable_residentes, DROP COLUMN IF EXISTS requiere_aprobacion,
  DROP COLUMN IF EXISTS requiere_paz_y_salvo, DROP COLUMN IF EXISTS max_reservas_mes_unidad,
  DROP COLUMN IF EXISTS anticipacion_max_dias, DROP COLUMN IF EXISTS anticipacion_min_dias,
  DROP COLUMN IF EXISTS hora_cierre, DROP COLUMN IF EXISTS hora_apertura, DROP COLUMN IF EXISTS reglas,
  DROP COLUMN IF EXISTS capacidad, DROP COLUMN IF EXISTS descripcion;
DELETE FROM secuencias WHERE tipo IN ('pqrs', 'circular');
DROP TYPE IF EXISTS estado_circular, categoria_circular, prioridad_pqrs, canal_pqrs, estado_pqrs, categoria_pqrs, tipo_pqrs;
