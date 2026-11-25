-- Reversa de 0010.
DROP TABLE IF EXISTS demo_snapshot.asamblea_votos, demo_snapshot.asamblea_puntos, demo_snapshot.asamblea_asistencias,
  demo_snapshot.asamblea_padron, demo_snapshot.asambleas;
DROP TABLE IF EXISTS asamblea_votos, asamblea_puntos, asamblea_asistencias, asamblea_padron, asambleas CASCADE;
DROP FUNCTION IF EXISTS trg_votos_insert(), trg_puntos_update(), trg_asamblea_en_curso(), trg_asambleas_update(),
  trg_asamblea_consecutivo();
DELETE FROM secuencias WHERE tipo = 'asamblea';
DROP TYPE IF EXISTS estado_punto, mayoria_punto, tipo_punto, tipo_asistente, estado_asamblea, convocatoria_asamblea,
  modalidad_asamblea, tipo_asamblea;
