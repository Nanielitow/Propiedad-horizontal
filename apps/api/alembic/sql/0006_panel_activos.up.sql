-- =============================================================================
-- 0006 · Panel del módulo de mantenimiento (docs/MANTENIMIENTO.md §5)
--
-- El Consejo ve indicadores y costos consolidados pero NO el detalle (RLS se lo
-- niega en todas las tablas del módulo). Igual que resumen_recaudos: función
-- SECURITY DEFINER que entrega solo agregados, comprueba el rol y filtra
-- EXPLÍCITAMENTE por copropiedad (como dueña de las tablas, RLS no la limita).
-- Es también la única fuente de las cifras del panel para los demás roles.
-- =============================================================================

CREATE FUNCTION resumen_mantenimiento(p_anio int, p_mes int, p_categoria uuid DEFAULT NULL, p_ubicacion text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_tenant    uuid := app_tenant_id();
  v_hoy       date := (now() AT TIME ZONE 'America/Bogota')::date;
  v_ini       date := make_date(p_anio, p_mes, 1);
  v_fin       date := (make_date(p_anio, p_mes, 1) + interval '1 month')::date;  -- exclusivo
  v_ini_anio  date := make_date(p_anio, 1, 1);
  v_fin_anio  date := make_date(p_anio + 1, 1, 1);                           -- exclusivo
  v_umbral    int;
  v_filtrado  boolean := p_categoria IS NOT NULL OR nullif(trim(p_ubicacion), '') IS NOT NULL;
  v_r         jsonb;
BEGIN
  IF v_tenant IS NULL OR app_role() NOT IN ('ADMIN', 'AUXILIAR', 'MANTENIMIENTO', 'CONTABILIDAD', 'CONSEJO', 'SYSTEM') THEN
    RAISE EXCEPTION 'Su rol no permite consultar el panel de mantenimiento' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT coalesce((settings->>'umbral_semaforo_dias')::int, 15) INTO v_umbral FROM tenants WHERE id = v_tenant;

  WITH
  -- Activos del filtro (con los dados de baja: su historial de costos cuenta)
  act AS (
    SELECT a.id, a.estado, a.categoria_id, a.mantenedor_id, a.fecha_instalacion, a.vida_util_anios
      FROM activos a
     WHERE a.tenant_id = v_tenant
       AND (p_categoria IS NULL OR a.categoria_id = p_categoria)
       AND (nullif(trim(p_ubicacion), '') IS NULL OR a.ubicacion ILIKE '%' || trim(p_ubicacion) || '%')
  ),
  vig AS (SELECT * FROM act WHERE estado <> 'DADO_DE_BAJA'),
  mto AS (
    SELECT m.*, (m.tipo = 'CORRECTIVO') AS es_correctivo
      FROM mantenimientos_ejecutados m JOIN act ON act.id = m.activo_id
     WHERE m.tenant_id = v_tenant AND m.anulado_at IS NULL
  ),
  pend AS (  -- actividades pendientes de activos vigentes con plan activo
    SELECT x.id, x.fecha_programada - v_hoy AS dias
      FROM actividades_programadas x
      JOIN vig ON vig.id = x.activo_id
      JOIN planes_preventivos p ON p.id = x.plan_id AND p.activo
     WHERE x.tenant_id = v_tenant AND x.estado = 'PROGRAMADA'
  ),
  -- Cumplimiento: actividades cuya fecha ya llegó dentro del periodo (las canceladas no cuentan)
  venc AS (
    SELECT x.id, x.fecha_programada, x.estado,
           EXISTS (SELECT 1 FROM mto WHERE mto.actividad_id = x.id AND mto.fecha_ejecucion <= x.fecha_programada) AS a_tiempo
      FROM actividades_programadas x JOIN act ON act.id = x.activo_id
     WHERE x.tenant_id = v_tenant AND x.estado <> 'CANCELADA'
       AND x.fecha_programada >= v_ini_anio AND x.fecha_programada < least(v_fin_anio, v_hoy + 1)
  ),
  nov AS (
    SELECT n.* FROM novedades n JOIN act ON act.id = n.activo_id WHERE n.tenant_id = v_tenant
  ),
  rec AS (
    SELECT r.* FROM recomendaciones_tecnicas r JOIN vig ON vig.id = r.activo_id
     WHERE r.tenant_id = v_tenant AND r.estado IN ('PENDIENTE', 'EN_PROCESO')
  ),
  -- Contratos anuales vigentes: su valor ya cubre los planes que ejecuta ese contratista
  contratos AS (
    SELECT c.id, c.valor_contrato FROM contratistas c
     WHERE c.tenant_id = v_tenant AND c.activo AND c.valor_contrato IS NOT NULL
       AND (c.vigencia_contrato_fin IS NULL OR c.vigencia_contrato_fin >= v_hoy)
       AND (NOT v_filtrado OR EXISTS (SELECT 1 FROM vig WHERE vig.mantenedor_id = c.id))
  ),
  plan_anual AS (
    SELECT p.id, p.costo_estimado,
           CASE p.periodicidad
             WHEN 'SEMANAL' THEN 52 WHEN 'QUINCENAL' THEN 24 WHEN 'MENSUAL' THEN 12 WHEN 'BIMESTRAL' THEN 6
             WHEN 'TRIMESTRAL' THEN 4 WHEN 'SEMESTRAL' THEN 2 WHEN 'ANUAL' THEN 1
             ELSE greatest(1, (SELECT count(*) FROM mto JOIN actividades_programadas x ON x.id = mto.actividad_id
                                WHERE x.plan_id = p.id AND mto.fecha_ejecucion > v_hoy - 365))
           END AS veces
      FROM planes_preventivos p JOIN vig ON vig.id = p.activo_id
     WHERE p.tenant_id = v_tenant AND p.activo AND p.aprobado_at IS NOT NULL AND p.costo_estimado IS NOT NULL
       AND (p.contratista_id IS NULL OR p.contratista_id NOT IN (SELECT id FROM contratos))
  )
  SELECT jsonb_build_object(
    'periodo', to_char(v_ini, 'YYYY-MM'),
    'hoy', v_hoy,
    'activos', jsonb_build_object(
      'total', (SELECT count(*) FROM vig),
      'por_estado', (SELECT coalesce(jsonb_object_agg(estado, n), '{}') FROM (SELECT estado, count(*) n FROM vig GROUP BY estado) x),
      'por_categoria', (SELECT coalesce(jsonb_agg(jsonb_build_object('categoria', c.nombre, 'total', x.n, 'fuera_de_servicio', x.fuera) ORDER BY c.nombre), '[]')
                          FROM (SELECT categoria_id, count(*) n, count(*) FILTER (WHERE estado = 'FUERA_DE_SERVICIO') fuera
                                  FROM vig GROUP BY categoria_id) x
                          JOIN categorias_activos c ON c.id = x.categoria_id),
      'para_reemplazo', (SELECT count(*) FROM vig WHERE vida_util_anios IS NOT NULL AND fecha_instalacion IS NOT NULL
                            AND (v_hoy - fecha_instalacion) >= vida_util_anios * 365 * 0.9)
    ),
    'semaforo', jsonb_build_object(
      'VERDE', (SELECT count(*) FROM pend WHERE dias > v_umbral),
      'AMARILLO', (SELECT count(*) FROM pend WHERE dias BETWEEN 0 AND v_umbral),
      'ROJO', (SELECT count(*) FROM pend WHERE dias < 0)
    ),
    'cumplimiento', jsonb_build_object(
      'mes', (SELECT jsonb_build_object('programadas', count(*), 'ejecutadas', count(*) FILTER (WHERE estado = 'EJECUTADA'),
                                        'a_tiempo', count(*) FILTER (WHERE a_tiempo))
                FROM venc WHERE fecha_programada >= v_ini AND fecha_programada < v_fin),
      'anio', (SELECT jsonb_build_object('programadas', count(*), 'ejecutadas', count(*) FILTER (WHERE estado = 'EJECUTADA'),
                                         'a_tiempo', count(*) FILTER (WHERE a_tiempo)) FROM venc)
    ),
    'mantenimientos_mes', (SELECT coalesce(jsonb_object_agg(tipo, n), '{}')
                             FROM (SELECT tipo, count(*) n FROM mto WHERE fecha_ejecucion >= v_ini AND fecha_ejecucion < v_fin GROUP BY tipo) x),
    'costos', jsonb_build_object(
      'mes', (SELECT coalesce(sum(costo_total), 0) FROM mto WHERE fecha_ejecucion >= v_ini AND fecha_ejecucion < v_fin),
      'anio', (SELECT coalesce(sum(costo_total), 0) FROM mto WHERE fecha_ejecucion >= v_ini_anio AND fecha_ejecucion < v_fin_anio),
      'anio_preventivo', (SELECT coalesce(sum(costo_total), 0) FROM mto WHERE NOT es_correctivo AND fecha_ejecucion >= v_ini_anio AND fecha_ejecucion < v_fin_anio),
      'anio_correctivo', (SELECT coalesce(sum(costo_total), 0) FROM mto WHERE es_correctivo AND fecha_ejecucion >= v_ini_anio AND fecha_ejecucion < v_fin_anio),
      'serie', (SELECT jsonb_agg(jsonb_build_object(
                  'mes', g.m,
                  'preventivo', (SELECT coalesce(sum(costo_total), 0) FROM mto WHERE NOT es_correctivo
                                    AND fecha_ejecucion >= make_date(p_anio, g.m, 1) AND fecha_ejecucion < make_date(p_anio, g.m, 1) + interval '1 month'),
                  'correctivo', (SELECT coalesce(sum(costo_total), 0) FROM mto WHERE es_correctivo
                                    AND fecha_ejecucion >= make_date(p_anio, g.m, 1) AND fecha_ejecucion < make_date(p_anio, g.m, 1) + interval '1 month')
                ) ORDER BY g.m) FROM generate_series(1, 12) AS g(m)),
      'por_categoria', (SELECT coalesce(jsonb_agg(jsonb_build_object('categoria', c.nombre, 'total', x.total) ORDER BY x.total DESC), '[]')
                          FROM (SELECT act.categoria_id, sum(mto.costo_total) total FROM mto JOIN act ON act.id = mto.activo_id
                                 WHERE mto.fecha_ejecucion >= v_ini_anio AND mto.fecha_ejecucion < v_fin_anio
                                 GROUP BY act.categoria_id) x
                          JOIN categorias_activos c ON c.id = x.categoria_id)
    ),
    'novedades', jsonb_build_object(
      'abiertas_por_prioridad', (SELECT coalesce(jsonb_object_agg(prioridad, n), '{}')
                                   FROM (SELECT prioridad, count(*) n FROM nov WHERE estado NOT IN ('CERRADA', 'DESCARTADA') GROUP BY prioridad) x),
      'sin_atender', (SELECT count(*) FROM nov WHERE estado = 'REPORTADA'),
      'reportadas_anio', (SELECT count(*) FROM nov WHERE fecha_reporte >= v_ini_anio AND fecha_reporte < v_fin_anio),
      'respuesta_media_horas', (SELECT round((avg(extract(epoch FROM fecha_atencion - fecha_reporte)) / 3600)::numeric, 1)
                                  FROM nov WHERE fecha_atencion IS NOT NULL AND fecha_reporte >= v_ini_anio AND fecha_reporte < v_fin_anio),
      'cierre_medio_dias', (SELECT round((avg(extract(epoch FROM cerrada_at - fecha_reporte)) / 86400)::numeric, 1)
                              FROM nov WHERE estado = 'CERRADA' AND fecha_reporte >= v_ini_anio AND fecha_reporte < v_fin_anio)
    ),
    'recomendaciones', jsonb_build_object(
      'pendientes', (SELECT count(*) FROM rec),
      'alta_pendientes', (SELECT count(*) FROM rec WHERE prioridad = 'ALTA'),
      'vencidas', (SELECT count(*) FROM rec WHERE fecha_limite < v_hoy),
      'costo_pendiente', (SELECT coalesce(sum(costo_estimado), 0) FROM rec)
    ),
    -- Proyección de la siguiente vigencia: plan + recomendaciones ponderadas por prioridad + contratos
    'proyeccion', jsonb_build_object(
      'anio', p_anio + 1,
      'plan', (SELECT coalesce(sum(costo_estimado * veces), 0) FROM plan_anual),
      'recomendaciones', (SELECT coalesce(round(sum(costo_estimado * CASE prioridad WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 0.6 ELSE 0.3 END)), 0) FROM rec),
      'contratos', (SELECT coalesce(sum(valor_contrato), 0) FROM contratos)
    )
  ) INTO v_r;

  v_r := jsonb_set(v_r, '{proyeccion,total}', to_jsonb(
    (v_r #>> '{proyeccion,plan}')::numeric + (v_r #>> '{proyeccion,recomendaciones}')::numeric + (v_r #>> '{proyeccion,contratos}')::numeric));
  RETURN v_r;
END $$;

REVOKE ALL ON FUNCTION resumen_mantenimiento(int, int, uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resumen_mantenimiento(int, int, uuid, text) TO app_user;
