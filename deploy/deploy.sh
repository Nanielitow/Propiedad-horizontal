#!/usr/bin/env bash
# =============================================================================
#  Despliega (o vuelve a) una versión:
#    ./deploy/deploy.sh               # la última (tag "latest")
#    ./deploy/deploy.sh 1a2b3c4d5e6f  # una versión concreta (SHA corto del commit)
#  Lo ejecuta GitHub Actions por SSH en cada push a main, o usted a mano.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:-latest}"
[ -f .env.production ] || { echo "Falta .env.production (ejecute ./deploy/generate-secrets.sh)"; exit 1; }
grep -q "__GENERAR__" .env.production && { echo "Quedan valores __GENERAR__ en .env.production"; exit 1; }

COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.production)

echo "==> Código de despliegue (compose, Caddyfile, scripts)"
git pull --ff-only

echo "==> Imágenes: $TAG"
export IMAGE_TAG="$TAG" # tiene prioridad sobre el valor de .env.production
"${COMPOSE[@]}" pull

echo "==> Arrancando (migraciones primero; la API no arranca si fallan)"
"${COMPOSE[@]}" up -d --remove-orphans

echo "==> Comprobando la salud"
for _ in $(seq 1 40); do
  if "${COMPOSE[@]}" exec -T web wget -q -O - http://127.0.0.1:3000/api/health 2>/dev/null; then
    echo
    echo "==> Despliegue correcto ($TAG)"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 5
done

echo "La aplicación no respondió a tiempo. Últimos logs:"
"${COMPOSE[@]}" logs --tail 40 api web migrate
echo "Para volver a la versión anterior: ./deploy/deploy.sh <SHA anterior>"
exit 1
