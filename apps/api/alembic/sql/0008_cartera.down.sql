-- Reversa de 0008.
DROP TABLE IF EXISTS demo_snapshot.auditoria_cartera, demo_snapshot.paz_y_salvos, demo_snapshot.ajustes_cartera,
  demo_snapshot.aplicaciones_pago, demo_snapshot.pagos_cartera, demo_snapshot.cargos_cartera,
  demo_snapshot.periodos_cartera, demo_snapshot.conceptos_cartera, demo_snapshot.cartera_config;
DROP VIEW IF EXISTS v_saldos_cargo;
DROP TABLE IF EXISTS auditoria_cartera, paz_y_salvos, ajustes_cartera, aplicaciones_pago, pagos_cartera,
  cargos_cartera, periodos_cartera, conceptos_cartera, cartera_config CASCADE;
DROP FUNCTION IF EXISTS seed_conceptos_cartera(uuid), trg_auditar_cartera(), trg_ajuste_valido(),
  trg_aplicacion_valida(), trg_solo_anular();
DELETE FROM secuencias WHERE tipo IN ('pago_cartera', 'paz_y_salvo');
DROP TYPE IF EXISTS tipo_ajuste, estado_pago_cartera, estado_cargo, estado_periodo, tipo_concepto_cartera, metodo_cuota;
