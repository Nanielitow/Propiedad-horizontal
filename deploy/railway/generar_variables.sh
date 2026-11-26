#!/bin/sh
# Genera las variables de Railway a partir de .env, SIN imprimir ningún valor (docs/RAILWAY.md):
#
#   sh deploy/railway/generar_variables.sh
#
#   deploy/railway/python.env -> pegar en el Raw Editor de las variables de api, worker y beat
#   deploy/railway/web.env    -> pegar en el Raw Editor de las variables de web
#
# Ambos archivos tienen secretos y están en .gitignore: bórrelos después de pegarlos.
# También recalcula en .env las cadenas NEON_*_URL a partir de NEON_OWNER_URL (útil al cambiar de proyecto).
set -eu
cd "$(dirname "$0")/../.."

val() {  # valor de una clave de .env, sin comillas; vacío si no existe
  linea=$(grep -m1 "^$1=" .env || true); v=${linea#*=}
  v=${v%\"}; v=${v#\"}; v=${v%\'}; v=${v#\'}; printf '%s' "$v"
}
exigir() { [ -n "$(val "$1")" ] || { echo "✗ Falta $1 en .env"; exit 1; }; }
for k in NEON_OWNER_URL NEON_APP_PASSWORD R2_ENDPOINT R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET GEMINI_API_KEY; do exigir "$k"; done

# --- Cadenas de Neon derivadas de la del dueño --------------------------------------------------
owner=$(val NEON_OWNER_URL); app_pw=$(val NEON_APP_PASSWORD)
hostdb=${owner#*@}; hostdb=${hostdb%%\?*}
cred=${owner#postgresql://}; cred=${cred%%@*}
db_async="postgresql+asyncpg://app_user:${app_pw}@${hostdb}?ssl=require"
db_sync="postgresql+psycopg://app_user:${app_pw}@${hostdb}?sslmode=require"
db_owner="postgresql+psycopg://${cred}@${hostdb}?sslmode=require"
tmp=$(mktemp)
grep -v -E '^NEON_(DATABASE|SYNC_DATABASE|MIGRATIONS_DATABASE)_URL=' .env > "$tmp"
printf 'NEON_DATABASE_URL="%s"\nNEON_SYNC_DATABASE_URL="%s"\nNEON_MIGRATIONS_DATABASE_URL="%s"\n' "$db_async" "$db_sync" "$db_owner" >> "$tmp"
cat "$tmp" > .env; rm -f "$tmp"

# --- Secreto JWT propio de producción (estable entre ejecuciones) -------------------------------
if [ -z "$(val PROD_JWT_SECRET)" ]; then
  printf '\n# Secreto JWT de producción (Railway). Cambiarlo cierra todas las sesiones.\nPROD_JWT_SECRET="%s"\n' \
    "$(node -e 'process.stdout.write(require("crypto").randomBytes(48).toString("base64url"))')" >> .env
fi

umask 077
copiar() { v=$(val "$1"); [ -n "$v" ] && printf '%s="%s"\n' "$1" "$v"; return 0; }
{
  echo "ENVIRONMENT=\"production\""
  echo "LOG_LEVEL=\"INFO\""
  echo "DEMO_MODE=\"true\""
  echo "PORT=\"8000\""
  echo "APP_URL=\"https://app.propiedadhorizontal.app\""
  echo "CORS_ORIGINS=\"https://app.propiedadhorizontal.app\""
  echo "DATABASE_URL=\"$db_async\""
  echo "SYNC_DATABASE_URL=\"$db_sync\""
  echo "MIGRATIONS_DATABASE_URL=\"$db_owner\""
  # Redis del mismo proyecto de Railway (red privada): bases 0, 1 y 2
  echo 'REDIS_URL="${{Redis.REDIS_URL}}/0"'
  echo 'CELERY_BROKER_URL="${{Redis.REDIS_URL}}/1"'
  echo 'CELERY_RESULT_BACKEND="${{Redis.REDIS_URL}}/2"'
  echo "S3_ENDPOINT_URL=\"$(val R2_ENDPOINT)\""
  echo "S3_PUBLIC_ENDPOINT_URL=\"$(val R2_ENDPOINT)\""
  echo "S3_ACCESS_KEY_ID=\"$(val R2_ACCESS_KEY_ID)\""
  echo "S3_SECRET_ACCESS_KEY=\"$(val R2_SECRET_ACCESS_KEY)\""
  echo "S3_BUCKET=\"$(val R2_BUCKET)\""
  echo "S3_REGION=\"auto\""
  echo "JWT_SECRET=\"$(val PROD_JWT_SECRET)\""
  for k in JWT_ACCESS_TTL_MINUTES JWT_REFRESH_TTL_DAYS MAX_UPLOAD_MB LLM_PROVIDER EMBEDDING_PROVIDER \
           OPENAI_API_KEY GEMINI_API_KEY CHAT_MODEL EXTRACTION_MODEL CHAT_THINKING_LEVEL EMBEDDING_MODEL \
           EMBEDDING_DIMENSIONS; do copiar "$k"; done
  # Sin SMTP_HOST la aplicación no envía correos (solo avisos en la app). Ver docs/RAILWAY.md.
} > deploy/railway/python.env
{
  echo 'API_INTERNAL_URL="http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000"'
  echo "PORT=\"3000\""  # el dominio público de Railway apunta al 3000
  echo "NEXT_PUBLIC_DEMO_MODE=\"true\""
  for k in GOOGLE_CLIENT_ID GOOGLE_API_KEY GOOGLE_PROJECT_NUMBER; do copiar "$k"; done
} > deploy/railway/web.env


# --- Correo por Resend (opcional): solo si RESEND_API_KEY está en .env ------------------------
if [ -n "$(val RESEND_API_KEY)" ]; then
  {
    echo "SMTP_HOST=\"smtp.resend.com\""
    echo "SMTP_PORT=\"587\""
    echo "SMTP_STARTTLS=\"true\""
    echo "SMTP_USER=\"resend\""
    echo "SMTP_PASSWORD=\"$(val RESEND_API_KEY)\""
    echo "SMTP_FROM=\"PH Gestión <no-responder@propiedadhorizontal.app>\""
    # Con DEMO_MODE solo se escribe a estas direcciones (los correos de la demo son ficticios)
    echo "SMTP_DEMO_RECIPIENTS=\"$(val SMTP_DEMO_RECIPIENTS)\""
  } > deploy/railway/smtp.env
  cat deploy/railway/smtp.env >> deploy/railway/python.env
  echo "✓ deploy/railway/smtp.env: $(grep -c . deploy/railway/smtp.env) variables de correo (también incluidas en python.env)"
fi

echo "✓ deploy/railway/python.env: $(grep -c . deploy/railway/python.env) variables (api, worker y beat)"
echo "✓ deploy/railway/web.env: $(grep -c . deploy/railway/web.env) variables (web)"
echo "  Tienen secretos: péguelos en Railway y bórrelos (rm deploy/railway/*.env)."
