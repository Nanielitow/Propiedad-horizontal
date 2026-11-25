#!/bin/sh
# Copia la base local (Docker) a Neon: esquema, datos, instantánea de la demo y permisos.
# Se ejecuta DENTRO del contenedor postgres (trae pg_dump/psql 16), desde la raíz del repo:
#
#   sh deploy/neon/migrar.sh            (lee NEON_OWNER_URL y NEON_APP_PASSWORD de .env)
#
# Nunca imprime las cadenas de conexión ni las contraseñas. Ver docs/NEON.md.
set -eu

if [ -z "${DENTRO_DEL_CONTENEDOR:-}" ]; then
  # En el host: lee de .env SOLO estas variables, línea por línea (no se ejecuta .env: las cadenas
  # de Neon traen '&', que la shell tomaría como "ejecutar en segundo plano"), y vuelve a
  # ejecutarse dentro del contenedor con ellas
  while IFS= read -r linea || [ -n "$linea" ]; do
    case "$linea" in
      NEON_OWNER_URL=* | NEON_APP_PASSWORD=*)
        nombre=${linea%%=*}; valor=${linea#*=}
        valor=${valor%\"}; valor=${valor#\"}; valor=${valor%\'}; valor=${valor#\'}
        export "$nombre=$valor" ;;
    esac
  done < ./.env
  : "${NEON_OWNER_URL:?Falta NEON_OWNER_URL en .env (cadena del rol dueño de Neon, conexión directa)}"
  : "${NEON_APP_PASSWORD:?Falta NEON_APP_PASSWORD en .env}"
  exec docker compose exec -T -e DENTRO_DEL_CONTENEDOR=1 -e NEON_OWNER_URL -e NEON_APP_PASSWORD \
    -e FORZAR="${FORZAR:-}" postgres sh -s < "$0"
fi

LOCAL="-U ${POSTGRES_USER:-ph_owner} -d ${POSTGRES_DB:-ph_saas}"
N() { psql "$NEON_OWNER_URL" -v ON_ERROR_STOP=1 -X -q "$@"; }

echo "1/5 Verificando el rol dueño en Neon"
read -r bypass createrole version <<EOT
$(N -tA -F ' ' -c "SELECT r.rolbypassrls, r.rolcreaterole, current_setting('server_version_num') FROM pg_roles r WHERE r.rolname = current_user")
EOT
[ "$bypass" = "t" ] || { echo "   ✗ El rol no tiene BYPASSRLS: use el rol dueño que crea Neon (neondb_owner)"; exit 1; }
[ "$createrole" = "t" ] || { echo "   ✗ El rol no puede crear roles (CREATEROLE)"; exit 1; }
echo "   ✓ BYPASSRLS y CREATEROLE · PostgreSQL $version"
tablas=$(N -tA -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
if [ "$tablas" != "0" ] && [ -z "$FORZAR" ]; then
  echo "   ✗ La base de Neon ya tiene $tablas tablas. Para reemplazarla: FORZAR=1 sh deploy/neon/migrar.sh"; exit 1
fi
if [ "$tablas" != "0" ]; then
  echo "   · FORZAR=1: se borran los esquemas public y demo_snapshot de Neon"
  N -c "DROP SCHEMA IF EXISTS demo_snapshot CASCADE; DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
fi

echo "2/5 Rol de la aplicación (app_user, SIN BYPASSRLS)"
N -v pw="$NEON_APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE app_user LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', :'pw')
 WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') \gexec
SELECT format('ALTER ROLE app_user LOGIN PASSWORD %L NOBYPASSRLS', :'pw') \gexec
SQL
echo "   ✓ app_user listo"

echo "3/5 Copiando esquema y datos (local → Neon)"
pg_dump $LOCAL --format=custom --no-owner -f /tmp/ph.dump
# Fuera: comentarios de extensiones (solo los puede poner su dueño) y privilegios por defecto del
# dueño local (ph_owner no existe en Neon; los de neondb_owner se fijan en el paso 4)
pg_restore -l /tmp/ph.dump | grep -v -E "COMMENT - EXTENSION|DEFAULT ACL" > /tmp/ph.list
pg_restore --no-owner --exit-on-error --single-transaction -L /tmp/ph.list -d "$NEON_OWNER_URL" /tmp/ph.dump
rm -f /tmp/ph.dump /tmp/ph.list
echo "   ✓ restaurado"

echo "4/5 Permisos de app_user"
N <<'SQL'
SELECT format('GRANT CONNECT ON DATABASE %I TO app_user', current_database()) \gexec
GRANT USAGE ON SCHEMA public TO app_user;
-- Lo que creen las próximas migraciones (las ejecuta este mismo dueño)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO app_user;
SQL
echo "   ✓ permisos (los de cada tabla vienen del respaldo, incluidas las restricciones de borrado)"

echo "5/5 Comparando filas por tabla"
conteo="SELECT string_agg(t || '=' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', t), false, true, '')))[1]::text, ' ' ORDER BY t) FROM unnest(ARRAY(SELECT tablename::text FROM pg_tables WHERE schemaname = 'public')) t"
psql $LOCAL -tAX -c "$conteo" | tr ' ' '\n' > /tmp/local.txt
N -tA -c "$conteo" | tr ' ' '\n' > /tmp/neon.txt
if diff /tmp/local.txt /tmp/neon.txt > /dev/null; then
  echo "   ✓ $(wc -l < /tmp/local.txt) tablas con las mismas filas"
else
  echo "   ✗ Diferencias (local < > neon):"; diff /tmp/local.txt /tmp/neon.txt || true; exit 1
fi
N -tA -c "SELECT 'Migración en Neon: ' || version_num FROM alembic_version"
echo "Listo."
