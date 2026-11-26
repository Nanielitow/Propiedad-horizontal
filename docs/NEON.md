# Base de datos en Neon (producción)

La base de producción vive en [Neon](https://neon.com) (PostgreSQL administrado). En local, Docker sigue
trayendo su propio PostgreSQL para desarrollar y para las pruebas, que **nunca** corren contra Neon (el
`conftest` de integración se detiene si `DATABASE_URL` apunta a una base remota).

## Por qué Neon y qué le exige la aplicación

| Requisito | Motivo | En Neon |
|---|---|---|
| PostgreSQL 17 | Misma versión que en local | Se elige al crear el proyecto |
| Extensiones `vector`, `citext`, `unaccent` | Buscador con IA, correos sin mayúsculas, búsquedas sin tildes | Disponibles |
| Dueño del esquema con `BYPASSRLS` | Las tablas usan `FORCE ROW LEVEL SECURITY` y ~20 funciones `SECURITY DEFINER` (quórum, disponibilidad de zonas, paneles) deben ver todos los datos del conjunto | `neondb_owner` lo tiene |
| Rol de la aplicación **sin** `BYPASSRLS` (`app_user`) | Cada copropiedad y cada rol solo ve lo suyo | Lo crea `deploy/neon/migrar.sh` |
| Nada que exija superusuario | En Neon no lo somos | La restauración de la demo apaga los triggers con `ALTER TABLE … DISABLE TRIGGER USER` (basta con ser dueño), no con `session_replication_role` |

Se ensayó en local con un dueño **no superusuario** con `BYPASSRLS` y `CREATEROLE` (igual que `neondb_owner`):
copia completa (70 tablas, mismas filas), restauración nocturna de la demo y RLS correcta (el residente ve
el quórum completo por la función y solo sus votos por consulta directa).

## Pasos

1. **Crear el proyecto** en neon.com: plan Launch, **PostgreSQL 17**, región **AWS São Paulo
   (sa-east-1)**, base `neondb`.
2. **Copiar la cadena de conexión del dueño**: Dashboard → *Connect* → rol `neondb_owner`, **desactivar
   "Connection pooling"** (conexión directa: el agrupador de Neon en modo transacción no es compatible con las
   sentencias preparadas de asyncpg). Pegarla en `.env`, entre comillas:
   `NEON_OWNER_URL="postgresql://neondb_owner:…@ep-….sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"`.
   `NEON_APP_PASSWORD` ya está generada en `.env`. **No pegue estas cadenas en chats ni commits.**
3. **Migrar** (desde la raíz del repo, con Docker encendido): `sh deploy/neon/migrar.sh`. Verifica el dueño,
   crea `app_user`, copia esquema + datos + instantánea de la demo, da permisos y compara filas tabla por
   tabla. Se niega a sobrescribir una base con datos; para repetir: `FORZAR=1 sh deploy/neon/migrar.sh`.
4. **Cadenas de la aplicación** (ya generadas en `.env` a partir de las dos anteriores):
   `NEON_DATABASE_URL` (`postgresql+asyncpg://app_user:…?ssl=require`: asyncpg usa `ssl`, no `sslmode`),
   `NEON_SYNC_DATABASE_URL` (`postgresql+psycopg://app_user:…?sslmode=require`) y
   `NEON_MIGRATIONS_DATABASE_URL` (el dueño, para migraciones y el reinicio nocturno de la demo).

Hecho el 2026-11-25: proyecto en **PostgreSQL 18** (Neon lo creó así; la copia desde 17 funcionó). Ojo: el
`pg_dump` 17 del Docker local no puede respaldar un servidor 18; para respaldos usar el restablecimiento a
un punto en el tiempo de Neon, y alinear el Docker local a 18 antes de producción.

## Demo pública en el PC (retirada)

Antes de Railway, la demo pública corría en el PC con un túnel de Cloudflare (`docker-compose.tunnel.yml`). Se retiró
el 26 de noviembre de 2026: la app corre en Railway (`docs/RAILWAY.md`) y los conjuntos de demostración conviven con
los reales en producción (`docs/CUENTAS.md`).

## Costo esperado

Plan Launch, por uso: ~US$0,106 por hora de cómputo (CU-hora) y ~US$0,35 por GB-mes. El worker de Celery
consulta la base periódicamente, así que la base casi no se suspende: con el tamaño mínimo (0,25 CU) son
unos **US$20/mes**. Los datos actuales ocupan menos de 1 GB.
