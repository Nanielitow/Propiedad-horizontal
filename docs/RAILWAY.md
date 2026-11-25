# Producción en Railway (nada depende del PC)

| Pieza | Dónde | Notas |
|---|---|---|
| Web (Next.js) | Railway, servicio `web` | Dominio `app.propiedadhorizontal.app` |
| API (FastAPI) | Railway, servicio `api` | Aplica las migraciones antes de cada despliegue (`alembic upgrade head`) |
| Worker (Celery: OCR, IA, correos) | Railway, servicio `worker` | |
| Tareas programadas (Celery beat) | Railway, servicio `beat` | Una sola réplica |
| Cola y caché | Railway, plantilla **Redis** | Red privada del proyecto |
| Base de datos | Neon, **AWS US East 1** | `docs/NEON.md` |
| Archivos | Cloudflare R2 | `docs/R2.md` |

Todo en el este de EE. UU. (Virginia): la API hace varias consultas por pantalla y cada una cruzaría el continente
si la base estuviera en otra región; además, desde Colombia el este de EE. UU. responde más rápido que São Paulo.

La configuración de cada servicio está versionada en `deploy/railway/*.json` (construcción, comando, chequeo de
salud, reinicios). Railway redespliega solo con cada `git push` a `main`, y solo los servicios cuyos archivos
cambiaron.

## 1. Neon en US East

1. En Neon: *New project* → **AWS US East 1 (N. Virginia)**, PostgreSQL 18.
2. Copiar la cadena de `neondb_owner` **sin pooling** y reemplazar `NEON_OWNER_URL` en `.env`.
3. `sh deploy/neon/migrar.sh` (crea `app_user`, copia todo y compara filas).
4. Cuando producción funcione: borrar el proyecto viejo de São Paulo.

## 2. Variables

`sh deploy/railway/generar_variables.sh` escribe `deploy/railway/python.env` y `deploy/railway/web.env` (en
`.gitignore`; borrarlos después de pegarlos). No imprime ningún valor. Genera un `JWT_SECRET` propio de producción.

## 3. Railway (lo hace el dueño de la cuenta)

1. Plan **Pro**. *New Project* → *Deploy from GitHub repo* → este repositorio (autorizar la app de GitHub).
2. Crear **4 servicios** desde el mismo repositorio y, en cada uno, *Settings*:

   | Servicio | Root Directory | Config-as-code (*Railway Config File*) |
   |---|---|---|
   | `api` | `/apps/api` | `/deploy/railway/api.json` |
   | `worker` | `/apps/api` | `/deploy/railway/worker.json` |
   | `beat` | `/apps/api` | `/deploy/railway/beat.json` |
   | `web` | `/apps/web` | `/deploy/railway/web.json` |

   Los nombres importan: `web` llega a la API por `api.railway.internal`.
3. *+ New* → *Database* → **Redis** (debe llamarse `Redis`: las variables lo referencian así).
4. Región de **cada** servicio (y del Redis): *Settings → Deploy → Region* → **US East (Virginia)**.
5. Variables: en `api`, `worker` y `beat` → *Variables* → *Raw Editor* → pegar `python.env`; en `web`, pegar
   `web.env`.
6. Dominio: `web` → *Settings → Networking* → *Custom Domain* → `app.propiedadhorizontal.app`. Railway muestra
   un registro **CNAME**: en Cloudflare → DNS, cambiar el registro `app` (hoy apunta al túnel) por ese CNAME, con la
   nube en **gris** (solo DNS) para que Railway emita el certificado.
7. Apagar la demo del PC: `npm run demo:down` y quitar las rutas del túnel en Cloudflare (Zero Trust → Tunnels).

## Correo (opcional)

Sin `SMTP_HOST` la aplicación no envía correos (los avisos quedan en la app). Para activarlos: una cuenta de un
proveedor SMTP (p. ej. Resend, con el dominio verificado en Cloudflare) y las variables `SMTP_*` en `api` y `worker`.

## Estado (2026-11-25)

En producción. `https://app.propiedadhorizontal.app` lo sirve Railway (US East): web, api, worker, beat y Redis;
base en Neon US East 1 (plan Launch) y archivos en R2. Verificado con la demo del PC apagada: salud de la web
(PostgreSQL y Redis OK), login, descarga firmada desde R2, PUT directo del navegador e ingesta del worker (READY).

Lecciones del primer despliegue:
- Los servicios deben crearse **desde el repositorio** (ícono de GitHub); uno vacío (`>_`) nunca construye.
- Railway rechaza `--mount=type=cache` sin id por servicio: los Dockerfiles no usan cachés de BuildKit.
- Si no se configura *Config-as-code* en un servicio, arranca con el `CMD` del Dockerfile (el worker corría la API).
- `web` necesita `PORT=3000`, el puerto al que apunta el dominio público.
- El registro DNS `app` en Cloudflare va con la nube **gris** para que Railway verifique y emita el certificado.

Pendiente: borrar el proyecto de Neon en São Paulo y el túnel de Cloudflare (ya sin rutas); correo (SMTP).
