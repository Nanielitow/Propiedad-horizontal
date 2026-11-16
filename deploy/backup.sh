#!/usr/bin/env bash
# =============================================================================
#  Copia de seguridad de la base de datos -> Cloudflare R2 (bucket BACKUP_BUCKET).
#  cron la ejecuta a diario (ver server-setup.sh). Conserva 7 días en el servidor;
#  en R2 la retención se define con una regla de ciclo de vida (docs/DEPLOY.md).
#
#  Restaurar:  ver la sección "Copias de seguridad" de docs/DEPLOY.md
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

# Se leen solo las variables necesarias (sin "source": algunos valores tienen espacios)
env_get() { grep -E "^$1=" .env.production | head -1 | cut -d= -f2-; }
POSTGRES_USER="$(env_get POSTGRES_USER)"
POSTGRES_DB="$(env_get POSTGRES_DB)"
BUCKET="$(env_get BACKUP_BUCKET)"
ENDPOINT="$(env_get S3_ENDPOINT_URL)"

DIR=/var/backups/ph-gestion
FILE="ph_saas-$(date -u +%Y%m%d-%H%M%S).dump"

echo "$(date -u +%FT%TZ) copia $FILE"
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=9 > "$DIR/$FILE"

# Formato "custom": se restaura con pg_restore y permite recuperar tablas sueltas
[ -s "$DIR/$FILE" ] || { echo "La copia quedó vacía"; exit 1; }

docker run --rm -v "$DIR:/backups:ro" \
  -e AWS_ACCESS_KEY_ID="$(env_get S3_ACCESS_KEY_ID)" \
  -e AWS_SECRET_ACCESS_KEY="$(env_get S3_SECRET_ACCESS_KEY)" \
  -e AWS_DEFAULT_REGION=auto \
  amazon/aws-cli:2.27.0 --endpoint-url "$ENDPOINT" s3 cp "/backups/$FILE" "s3://$BUCKET/postgres/$FILE" --only-show-errors

find "$DIR" -name 'ph_saas-*.dump' -mtime +7 -delete
echo "$(date -u +%FT%TZ) copia subida a s3://$BUCKET/postgres/$FILE ($(du -h "$DIR/$FILE" | cut -f1))"
