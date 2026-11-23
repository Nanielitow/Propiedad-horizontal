-- Reversa de 0005. 'MANTENIMIENTO' permanece en user_role (PostgreSQL no quita valores de un ENUM).
DROP TABLE IF EXISTS demo_snapshot.notificaciones_mantenimiento, demo_snapshot.auditoria_activos,
  demo_snapshot.recomendaciones_tecnicas, demo_snapshot.mantenimientos_ejecutados, demo_snapshot.novedades,
  demo_snapshot.reprogramaciones, demo_snapshot.actividades_programadas, demo_snapshot.planes_preventivos,
  demo_snapshot.lecturas_uso, demo_snapshot.evidencias, demo_snapshot.activo_documentos, demo_snapshot.activos,
  demo_snapshot.contratistas, demo_snapshot.categorias_activos;
DROP VIEW IF EXISTS v_semaforo_actividades;
DROP TABLE IF EXISTS notificaciones_mantenimiento, auditoria_activos, recomendaciones_tecnicas,
  mantenimientos_ejecutados, novedades, reprogramaciones, actividades_programadas, planes_preventivos,
  lecturas_uso, evidencias, activo_documentos, activos, contratistas, categorias_activos CASCADE;
DROP FUNCTION IF EXISTS seed_categorias_activos(uuid), trg_auditar_activos(), trg_recomendaciones_update(),
  trg_novedades_update(), trg_novedades_insert(), trg_mantenimientos_efectos(), trg_mantenimientos_update(),
  trg_mantenimientos_insert(), trg_actividades_update(), trg_planes_aprobacion(), trg_lecturas_insert(),
  trg_activos_update();
DROP TYPE IF EXISTS estado_recomendacion, prioridad_recomendacion, estado_novedad, prioridad_novedad,
  tipo_mantenimiento, estado_actividad, base_calculo_plan, periodicidad, momento_evidencia, entidad_evidencia,
  tipo_documento_activo, criticidad_activo, estado_activo;
