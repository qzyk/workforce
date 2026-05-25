#!/bin/sh
# Backup pentru o instanta de client (Faza 2): dump Postgres + arhiva uploads.
#   ./scripts/backup_client.sh <slug>
# Retentie: ultimele 14 copii. Offsite optional via rclone (seteaza RCLONE_REMOTE).
# Destinatie: $BACKUP_DIR/<slug> (implicit ./backups/<slug>).
set -e

SLUG="$1"
if [ -z "$SLUG" ]; then
  echo "Utilizare: $0 <slug>" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENVF="$ROOT/clients/$SLUG/.env"
[ -f "$ENVF" ] || { echo "Nu gasesc $ENVF" >&2; exit 1; }

PROJECT="edifico-$SLUG"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${BACKUP_DIR:-$ROOT/backups}/$SLUG"
mkdir -p "$DEST"

PGUSER="$(grep '^POSTGRES_USER=' "$ENVF" | cut -d= -f2)"
PGDB="$(grep '^POSTGRES_DB=' "$ENVF" | cut -d= -f2)"
PGUSER="${PGUSER:-edifico}"
PGDB="${PGDB:-edifico}"

# Container-ul db al clientului (dupa label-urile compose)
DBC="$(docker ps -q \
  -f "label=com.docker.compose.project=$PROJECT" \
  -f "label=com.docker.compose.service=db")"
[ -n "$DBC" ] || { echo "Container db inexistent pentru proiectul $PROJECT" >&2; exit 1; }

# 1) Dump DB
docker exec "$DBC" pg_dump -U "$PGUSER" "$PGDB" | gzip > "$DEST/db-$STAMP.sql.gz"

# 2) Arhiva volum uploads
VOL="${PROJECT}_uploads"
docker run --rm -v "${VOL}:/data:ro" -v "$DEST:/backup" alpine \
  tar czf "/backup/uploads-$STAMP.tar.gz" -C /data . 2>/dev/null || \
  echo "(uploads gol sau volum inexistent - sar peste)"

# 3) Retentie: pastreaza ultimele 14
ls -1t "$DEST"/db-*.sql.gz 2>/dev/null      | tail -n +15 | xargs -r rm -f
ls -1t "$DEST"/uploads-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "Backup $SLUG -> $DEST (db-$STAMP.sql.gz)"

# 4) Offsite optional (rclone)
if [ -n "$RCLONE_REMOTE" ]; then
  rclone copy "$DEST" "$RCLONE_REMOTE/$SLUG" && echo "Offsite -> $RCLONE_REMOTE/$SLUG"
fi
