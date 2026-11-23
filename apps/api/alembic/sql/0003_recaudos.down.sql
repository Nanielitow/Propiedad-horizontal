-- Reversa de 0003. Nota: PostgreSQL no permite quitar valores de un ENUM, así que
-- 'AUXILIAR', 'CONTABILIDAD' y 'CONSEJO' permanecen en user_role (sin efecto si nadie los usa).

-- Las copias de estas tablas en la instantánea de la demo usan los tipos de abajo: sin el módulo no sirven
DROP TABLE IF EXISTS demo_snapshot.cortes_mensuales, demo_snapshot.alertas_recaudo, demo_snapshot.auditoria_recaudos,
  demo_snapshot.consignacion_recaudos, demo_snapshot.consignaciones, demo_snapshot.recaudo_parqueadero,
  demo_snapshot.recaudo_items, demo_snapshot.recaudos, demo_snapshot.entregas_internas, demo_snapshot.cierres_caja,
  demo_snapshot.reservas, demo_snapshot.zonas_sociales, demo_snapshot.conceptos_recaudo, demo_snapshot.secuencias;
DROP TABLE IF EXISTS cortes_mensuales, alertas_recaudo, auditoria_recaudos, consignacion_recaudos,
  consignaciones, recaudo_parqueadero, recaudo_items, recaudos, entregas_internas, cierres_caja,
  reservas, zonas_sociales, conceptos_recaudo, secuencias CASCADE;

DROP FUNCTION IF EXISTS resumen_recaudos(int, int), seed_conceptos_recaudo(uuid), trg_auditar(), trg_consignacion_aplicado(),
  trg_recaudo_cuadre(), trg_recaudos_update(), trg_recaudos_insert(), trg_inmutable(),
  trg_prohibir_delete(), trg_asignar_consecutivo(), next_consecutivo(uuid, text), app_role();

DROP TYPE IF EXISTS estado_alerta, severidad_alerta, tipo_alerta, accion_auditoria, estado_consignacion,
  estado_entrega, estado_reserva, estado_recaudo, medio_pago, tipo_cobro;
