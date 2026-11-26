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

## Correo (Resend)

Sin `SMTP_HOST` la aplicación no envía correos (los avisos quedan en la app). En producción se usa **Resend** por
SMTP (`smtp.resend.com:587`, usuario `resend`, la clave de API como contraseña), remitente
`no-responder@propiedadhorizontal.app`.

1. Resend → *Domains* → *Add domain* → `propiedadhorizontal.app`, región **us-east-1**. Agregar en Cloudflare →
   DNS los registros que muestra (DKIM `TXT`, y `MX` + `TXT` de SPF en el subdominio `send`), con la nube **gris**;
   o usar el botón de configuración automática con Cloudflare. Esperar a que diga *Verified*.
2. Resend → *API Keys* → *Create API key*, permiso **Sending access**, solo ese dominio.
3. En `.env`: `RESEND_API_KEY="…"` y `SMTP_DEMO_RECIPIENTS="correo1@…,correo2@…"`.
4. `sh deploy/railway/generar_variables.sh` → pegar `deploy/railway/smtp.env` al final de las variables de
   `api`, `worker` y `beat` (Raw Editor) → borrar los `.env` generados.

Protecciones (`app/services/notifications/email.py`): en producción nunca se escribe a dominios ficticios
(`.demo`, `.local`, `.test`, `.example`, `.invalid`), y con `DEMO_MODE=true` **solo** a `SMTP_DEMO_RECIPIENTS`: los
visitantes comparten cuentas y podrían registrar correos de terceros. Al quitar `DEMO_MODE` los correos llegan a
todos los destinatarios reales.

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

Ya borrados el proyecto de Neon en São Paulo y el túnel de Cloudflare. Pendiente: correo (SMTP).

## Dominio raíz

`propiedadhorizontal.app` y `www.propiedadhorizontal.app` redirigen (301, conservando ruta y parámetros) a
`https://app.propiedadhorizontal.app`. Lo hace Cloudflare, sin pasar por Railway:
- DNS: registros `A` `@` y `www` → `192.0.2.1` (dirección reservada, nunca se usa) con la nube **naranja**.
- *Rules → Redirect Rules* → «Raíz a la app»: si el hostname es el raíz o `www`, redirección dinámica a
  `concat("https://app.propiedadhorizontal.app", http.request.uri.path)`, código 301, conservando la consulta.
