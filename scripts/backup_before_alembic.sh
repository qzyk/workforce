#!/usr/bin/env bash
# Backup DB inainte de prima rulare Alembic.
#
# Utilizare:
#   ./scripts/backup_before_alembic.sh
#
# Detecteaza automat tipul DB din DATABASE_URL (sau din config default).
# Pentru SQLite: copiaza fisierul .db cu timestamp.
# Pentru MySQL: ruleaza mysqldump (cere mysqldump in PATH).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${REPO_ROOT}/backups"
TS="$(date +%Y%m%d_%H%M%S)"

mkdir -p "${BACKUP_DIR}"

DB_URL="${DATABASE_URL:-}"
if [ -z "${DB_URL}" ]; then
    DB_URL="sqlite:///${REPO_ROOT}/database/workforce.db"
    echo "[INFO] DATABASE_URL nesetat, folosesc default: ${DB_URL}"
fi

if [[ "${DB_URL}" == sqlite:///* ]]; then
    SQLITE_PATH="${DB_URL#sqlite:///}"
    if [ ! -f "${SQLITE_PATH}" ]; then
        echo "[WARN] Fisierul SQLite nu exista la ${SQLITE_PATH}. Nimic de backup."
        exit 0
    fi
    OUT="${BACKUP_DIR}/workforce_pre_alembic_${TS}.db"
    cp "${SQLITE_PATH}" "${OUT}"
    echo "[OK] Backup SQLite -> ${OUT}"
elif [[ "${DB_URL}" == mysql* ]]; then
    # Format asteptat: mysql+pymysql://user:pass@host:port/dbname
    # Extrag componentele cu regex.
    URL_NOSCHEME="${DB_URL#mysql*://}"
    USER_PASS="${URL_NOSCHEME%%@*}"
    HOST_DB="${URL_NOSCHEME#*@}"
    DB_USER="${USER_PASS%%:*}"
    DB_PASS="${USER_PASS#*:}"
    HOST_PORT="${HOST_DB%%/*}"
    DB_NAME="${HOST_DB#*/}"
    DB_NAME="${DB_NAME%%\?*}"
    DB_HOST="${HOST_PORT%%:*}"
    DB_PORT="${HOST_PORT#*:}"
    if [ "${DB_PORT}" = "${HOST_PORT}" ]; then
        DB_PORT="3306"
    fi

    OUT="${BACKUP_DIR}/workforce_pre_alembic_${TS}.sql"
    if ! command -v mysqldump >/dev/null 2>&1; then
        echo "[ERR] mysqldump nu e in PATH. Instaleaza mysql-client sau ruleaza backup-ul manual." >&2
        exit 1
    fi
    mysqldump --single-transaction --routines --triggers \
        -h "${DB_HOST}" -P "${DB_PORT}" -u "${DB_USER}" -p"${DB_PASS}" \
        "${DB_NAME}" > "${OUT}"
    echo "[OK] Backup MySQL -> ${OUT}"
else
    echo "[ERR] Tip DB necunoscut in DATABASE_URL: ${DB_URL}" >&2
    exit 1
fi

echo "[OK] Backup terminat. Pastreaza acest fisier inainte sa rulezi 'alembic stamp head'."
