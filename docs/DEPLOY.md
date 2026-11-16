# Despliegue en producción

Guía paso a paso para publicar PH Gestión en un servidor propio (VPS) con Docker, como **demo pública** y preparado para pasar a **uso real**.

```
Internet ──HTTPS──► Caddy (certificado automático) ──► Next.js (web + BFF)
                                                         │  red interna de Docker
                                          ┌──────────────┼──────────────┐
                                          ▼              ▼              ▼
                                     FastAPI API    Celery worker   Celery beat
                                          └─────► Postgres + Redis ◄────┘   (sin puertos públicos)
Navegador ──URL firmada──► Cloudflare R2 (PDF)        Resend (correo) · Gemini (IA)
```

Solo Caddy recibe tráfico de internet (puertos 80 y 443). La API, Postgres y Redis no son accesibles desde fuera.

## Costos aproximados

| Pieza | Servicio | Costo |
|---|---|---|
| Servidor (2–4 vCPU, 4–8 GB) | Hetzner Cloud | ~€4–6 al mes |
| Archivos y copias de seguridad | Cloudflare R2 | Gratis hasta 10 GB, sin costo de descarga |
| Correo | Resend | Gratis hasta ~3.000 correos al mes (100 al día) |
| Dominio | Cloudflare Registrar | ~10–15 USD al año |
| IA | Gemini | Plan gratuito para la demo; pago con alerta de presupuesto para uso real |

Confirme los precios en cada proveedor: cambian con frecuencia.

---

## 1. Dominio

1. Cree una cuenta en [Cloudflare](https://dash.cloudflare.com) y compre un dominio en **Domain Registration → Register Domains** (se vende a precio de costo).
2. La app vivirá en un subdominio, por ejemplo **`app.su-dominio.com`**. El dominio principal queda libre para una web de presentación.

## 2. Servidor (Hetzner)

1. **Cree una llave SSH** en su equipo (PowerShell). Acepte la ruta propuesta y ponga una contraseña:
   ```powershell
   ssh-keygen -t ed25519 -C "ph-gestion"
   Get-Content $HOME\.ssh\id_ed25519.pub   # copie esta línea (llave PÚBLICA)
   ```
2. En [Hetzner Cloud](https://console.hetzner.cloud) cree un proyecto y luego **Add Server**:
   - **Ubicación:** Ashburn (EE. UU.), la más cercana a Colombia.
   - **Imagen:** Ubuntu 24.04.
   - **Tipo:** shared vCPU con **al menos 4 GB de RAM**. Se recomiendan 8 GB si habrá muchos escaneados (el OCR consume memoria).
   - **SSH keys:** pegue la llave pública del paso 1. Así no habrá contraseña de root.
3. Anote la **IP** del servidor.

## 3. DNS

En Cloudflare, **DNS → Records → Add record**:

| Tipo | Nombre | Contenido | Proxy |
|---|---|---|---|
| A | `app` | IP del servidor | **DNS only** (nube gris) |

Con la nube gris, Caddy obtiene el certificado HTTPS de Let's Encrypt directamente. Compruebe que el registro ya funciona con `nslookup app.su-dominio.com`.

## 4. Cloudflare R2 (archivos y copias)

1. En **R2 Object Storage**, cree dos buckets: `ph-gestion-documentos` y `ph-gestion-backups`.
2. En `ph-gestion-backups`, vaya a **Settings → Object lifecycle rules** y cree una regla que **borre los objetos después de 30 días**.
3. En **R2 → Manage API Tokens → Create API Token**, elija permisos *Object Read & Write* sobre esos dos buckets. Guarde el **Access Key ID**, el **Secret Access Key** y el **endpoint** (`https://<ID_DE_CUENTA>.r2.cloudflarestorage.com`).

El CORS del bucket (necesario para que el navegador suba los PDF) se configura con un comando en el paso 9.

## 5. Correo (Resend)

1. Cree una cuenta en [Resend](https://resend.com) y en **Domains → Add Domain** registre su dominio.
2. Resend le mostrará unos registros DNS (SPF, DKIM y MX de retorno). Añádalos en Cloudflare **exactamente** como aparecen y espere a que Resend muestre *Verified*. Sin esto, los recordatorios caerían en spam.
3. En **API Keys**, cree una key con permiso *Sending access*. Esa key es la contraseña SMTP.

## 6. Gemini

1. En [Google AI Studio](https://aistudio.google.com/apikey), **cree una API key nueva** exclusiva para producción. No reutilice la de desarrollo.
2. **Para la demo:** el plan gratuito basta. Si se agota la cuota del modelo de extracción, el sistema pasa solo al modelo Lite.
3. **Para uso real:** active la facturación y cree una **alerta de presupuesto** en Google Cloud Billing (por ejemplo, $10 al mes). En el plan gratuito, Google puede usar el contenido enviado para mejorar sus productos.

## 7. Preparar el servidor

Desde PowerShell, entre como root y ejecute el script de preparación:

```powershell
ssh root@IP_DEL_SERVIDOR
```
```bash
curl -fsSL https://raw.githubusercontent.com/Nanielitow/Propiedad-horizontal/main/deploy/server-setup.sh | bash
```

El script hace lo siguiente:
- Instala Docker.
- Crea el usuario `deploy`.
- Deja SSH **solo con llave** y activa el firewall (puertos 22, 80 y 443).
- Configura 2 GB de swap y las actualizaciones de seguridad automáticas.
- Clona el repositorio en `/opt/ph-gestion` y programa la copia de seguridad diaria.

Desde ahora, entre siempre con el usuario `deploy`:
```powershell
ssh deploy@IP_DEL_SERVIDOR
```

## 8. Secretos

```bash
cd /opt/ph-gestion
./deploy/generate-secrets.sh     # crea .env.production con contraseñas aleatorias
nano .env.production             # complete los valores (Ctrl+O guarda, Ctrl+X sale)
```

Valores que debe completar:

| Variable | Valor |
|---|---|
| `SITE_ADDRESS` | `app.su-dominio.com` |
| `APP_URL`, `CORS_ORIGINS` | `https://app.su-dominio.com` |
| `S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL` | El endpoint de R2 (paso 4) |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Las llaves de R2 |
| `GEMINI_API_KEY` | La key de producción (paso 6) |
| `SMTP_PASSWORD` | La API key de Resend |
| `SMTP_FROM` | `PH Gestión <recordatorios@su-dominio.com>` |

`.env.production` queda con permisos `600` (solo lo lee su dueño) y **nunca** se sube a Git.

## 9. Primer despliegue

Las imágenes Docker las publica GitHub Actions en GHCR con cada *push* a `main` (workflow **Publicar y desplegar**). Compruebe en la pestaña **Actions** del repositorio que terminó bien y luego despliegue:

```bash
./deploy/deploy.sh
```

> Si `docker pull` responde *denied*, el paquete quedó privado. Hay dos soluciones: hacerlo público en GitHub (**perfil → Packages → el paquete → Package settings → Change visibility → Public**) o ejecutar `docker login ghcr.io` en el servidor con un token de solo lectura (`read:packages`).

Después, prepare los datos de la demo:

```bash
alias dc='docker compose -f docker-compose.prod.yml --env-file .env.production'
dc exec api python -m app.scripts.demo configure-bucket   # CORS de R2 para su dominio
dc exec api python -m app.scripts.seed                    # copropiedades y cuentas demo
dc exec api python -m app.scripts.demo load               # sube y procesa los documentos (unos minutos)
```

Abra `https://app.su-dominio.com`, entre con las cuentas demo y revise todo: buscador, vencimientos, cotizaciones y actas. Si todo está bien, guarde ese estado como la "demo limpia":

```bash
dc exec api python -m app.scripts.demo snapshot
```

Desde ahora, **cada noche a las 04:00 (hora de Bogotá)** la demo vuelve a ese estado y se borran los archivos que hayan subido los visitantes.

## 10. Despliegue automático

Para que cada *push* a `main` se publique solo:

1. Cree en su equipo una llave **exclusiva para GitHub**, sin contraseña:
   ```powershell
   ssh-keygen -t ed25519 -f $HOME\.ssh\ph_deploy -N '""' -C "github-actions"
   ```
2. Autorícela en el servidor (como `deploy`): añada el contenido de `ph_deploy.pub` al final de `~/.ssh/authorized_keys`.
3. En GitHub, vaya a **Settings → Secrets and variables → Actions → New repository secret** y cree estos tres:
   - `DEPLOY_HOST`: la IP del servidor.
   - `DEPLOY_USER`: `deploy`.
   - `DEPLOY_SSH_KEY`: el contenido completo de `ph_deploy`, la llave **privada**.

El flujo queda así: haces *push*, pasa el CI, se publican las imágenes y el servidor ejecuta `deploy.sh` con esa versión. Si la app no responde tras desplegar, el script muestra los logs.

## 11. Monitoreo

- **Disponibilidad:** cree un monitor gratuito en [UptimeRobot](https://uptimerobot.com) o [Better Stack](https://betterstack.com) contra `https://app.su-dominio.com/api/health`. Esa ruta comprueba la web, la API, Postgres y Redis, y avisa por correo si algo cae.
- **Gasto de IA:** use la alerta de presupuesto de Google Cloud (paso 6).
- **Logs:** `dc logs -f api worker` (se rotan solos: máximo 30 MB por servicio).

## 12. Copias de seguridad

Cada día a las 03:30 UTC, `deploy/backup.sh` vuelca la base de datos y la sube a `ph-gestion-backups/postgres/`. Se conservan 7 días en el servidor y 30 en R2.

```bash
./deploy/backup.sh                       # ejecutar una copia ahora
tail /var/log/ph-gestion-backup.log      # historial
```

**Restaurar** (pruébelo al menos una vez antes de necesitarlo):

```bash
dc stop api worker beat web
dc exec -T postgres pg_restore -U ph_owner -d ph_saas --clean --if-exists < /var/backups/ph-gestion/ph_saas-AAAAMMDD-HHMMSS.dump
dc up -d
```

Para recuperar una copia que solo está en R2, descárguela antes con el mismo `aws s3 cp` que usa `backup.sh`, pero en sentido inverso.

## 13. Operación diaria

| Tarea | Comando (en `/opt/ph-gestion`) |
|---|---|
| Estado de los servicios | `dc ps` |
| Logs en vivo | `dc logs -f api worker` |
| Actualizar a la última versión | `./deploy/deploy.sh` |
| **Volver a una versión anterior** | `./deploy/deploy.sh <SHA de 12 caracteres>` (aparece en **Actions** o con `git log --oneline`) |
| Reiniciar un servicio | `dc restart worker` |
| Reiniciar la demo ahora | `dc exec api python -m app.scripts.demo restore` |
| Consola de la base de datos | `dc exec postgres psql -U ph_owner -d ph_saas` |

## 14. De la demo al uso real

Antes de cargar documentos de un edificio real:

- [ ] `DEMO_MODE=false` en `.env.production` y la **variable** `DEMO_MODE=false` en GitHub (**Settings → Variables**), para quitar el aviso y las cuentas demo del login. Vuelva a desplegar.
- [ ] Eliminar las copropiedades y cuentas demo, o crear una base limpia.
- [ ] Gemini con **facturación activa** y alerta de presupuesto (privacidad de los datos).
- [ ] Copia de seguridad **probada**: restaurarla al menos una vez.
- [ ] Política de tratamiento de datos personales (Ley 1581 de 2012) y aviso de privacidad visible.
- [ ] Alta de usuarios reales. Hoy se hace con un script; el flujo de **invitación por correo** está en el roadmap.
- [ ] Pasar el registro DNS a *Proxied* (nube naranja) con SSL en modo **Full (strict)**, si se quiere la protección DDoS de Cloudflare.
