-- 0011 · Quórum y votos agregados para cualquier rol de la copropiedad.
-- El residente solo puede LEER sus propias asistencias y votos (RLS), pero el quórum y el
-- resultado de cada votación son públicos para la asamblea. Estas funciones devuelven solo
-- agregados: coeficiente presente y, por voto, la opción y su coeficiente (sin la unidad).

CREATE FUNCTION asamblea_presentes(p_asamblea uuid)
RETURNS TABLE (coeficiente numeric, unidades bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT coalesce(sum(p.coeficiente), 0), count(*)
    FROM asamblea_asistencias x
    JOIN asamblea_padron p ON p.asamblea_id = x.asamblea_id AND p.unidad_id = x.unidad_id
   WHERE x.tenant_id = app_tenant_id() AND x.asamblea_id = p_asamblea AND x.retiro_at IS NULL
$$;

CREATE FUNCTION asamblea_votos_punto(p_punto uuid)
RETURNS TABLE (opcion text, coeficiente numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT v.opcion, v.coeficiente
    FROM asamblea_votos v
   WHERE v.tenant_id = app_tenant_id() AND v.punto_id = p_punto
$$;

REVOKE ALL ON FUNCTION asamblea_presentes(uuid), asamblea_votos_punto(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION asamblea_presentes(uuid), asamblea_votos_punto(uuid) TO app_user;
