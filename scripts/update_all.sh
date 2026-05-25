#!/bin/sh
# Update etapizat al tuturor instantelor de client (Faza 3).
#   ./scripts/update_all.sh [canary_slug]
# Rebuild imaginea o data, apoi recreeaza fiecare client. Cu un canary, il
# actualizeaza primul si verifica /healthz inainte de a continua cu restul.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANARY="$1"

echo "==> build imagine edifico:latest"
docker build -t edifico:latest "$ROOT"

update_one() {
  slug="$1"
  envf="$ROOT/clients/$slug/.env"
  [ -f "$envf" ] || return 0
  echo "==> update $slug"
  docker compose --env-file "$envf" -f "$ROOT/docker-compose.yml" up -d --no-build

  proj="edifico-$slug"
  cid="$(docker ps -q -f "label=com.docker.compose.project=$proj" -f "label=com.docker.compose.service=app")"
  [ -n "$cid" ] || { echo "    !! container app inexistent ($proj)"; return 1; }
  i=0
  while [ "$i" -lt 30 ]; do
    if docker exec "$cid" curl -fsS "http://localhost:8000/healthz" >/dev/null 2>&1; then
      echo "    OK $slug healthy"
      return 0
    fi
    i=$((i + 1)); sleep 2
  done
  echo "    !! $slug nu raspunde la /healthz"
  return 1
}

if [ -n "$CANARY" ]; then
  update_one "$CANARY" || { echo "Canary $CANARY a esuat - opresc roll-out-ul."; exit 1; }
fi

for d in "$ROOT"/clients/*/; do
  [ -f "$d/.env" ] || continue
  slug="$(basename "$d")"
  [ "$slug" = "$CANARY" ] && continue
  update_one "$slug" || echo "!! update esuat: $slug (continui)"
done

echo "Gata."
