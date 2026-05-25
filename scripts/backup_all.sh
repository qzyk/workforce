#!/bin/sh
# Backup la TOATE instantele de client (pentru cron).
#   ./scripts/backup_all.sh
# Cron zilnic la 03:00:
#   0 3 * * * cd /home/edifico/workforce && RCLONE_REMOTE=b2:edifico-backups ./scripts/backup_all.sh >> backups/cron.log 2>&1
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -d "$ROOT/clients" ]; then
  echo "Nu exista clients/ - nimic de salvat."
  exit 0
fi

for d in "$ROOT"/clients/*/; do
  [ -f "$d/.env" ] || continue
  slug="$(basename "$d")"
  echo "=== backup $slug ($(date '+%Y-%m-%d %H:%M:%S')) ==="
  "$ROOT/scripts/backup_client.sh" "$slug" || echo "!! backup esuat: $slug"
done
