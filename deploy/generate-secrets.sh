#!/usr/bin/env bash
# Crea .env.production (si no existe) y reemplaza cada __GENERAR__ por un valor
# aleatorio distinto. Hexadecimal: seguro dentro de URLs de conexión.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env.production ]; then
  cp .env.production.example .env.production
  echo "Creado .env.production a partir de la plantilla"
fi

count=0
while grep -q "__GENERAR__" .env.production; do
  sed -i "0,/__GENERAR__/s//$(openssl rand -hex 24)/" .env.production
  count=$((count + 1))
done
chmod 600 .env.production  # solo el dueño puede leer los secretos

echo "Secretos generados: $count"
echo "Complete ahora a mano: SITE_ADDRESS, APP_URL, CORS_ORIGINS, S3_* (R2), GEMINI_API_KEY, SMTP_PASSWORD y SMTP_FROM"
