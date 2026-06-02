#!/usr/bin/env bash
# CI local — ruleaza aceleasi verificari ca workflow-ul GitHub Actions
# (docs/ci-templates/github-actions-test.yml), fara sa ai nevoie de GitHub.
#
# Util inainte de push: "e verde local?" => probabil verde si in CI.
#
# Utilizare:
#   ./scripts/ci_local.sh                 # python3 din PATH
#   PY=/cale/spre/python3 ./scripts/ci_local.sh
#
# Joburile MySQL si E2E din CI NU ruleaza aici (cer MySQL / Playwright);
# testele marcate mysql se sar automat pe SQLite.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
PY="${PY:-python3}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '\033[32m[OK]\033[0m %s\n' "$1"; }
fail() { printf '\033[31m[FAIL]\033[0m %s\n' "$1"; }

RC=0

bold "== 1/3 Teste (SQLite, fara E2E) =="
if "${PY}" -m pytest tests/ --ignore=tests/e2e -q; then
    ok "Teste verzi"
else
    fail "Teste picate"; RC=1
fi

bold "== 2/3 Alembic upgrade head pe DB gol =="
ALEMBIC_DB="${REPO_ROOT}/.ci_alembic_local.db"
rm -f "${ALEMBIC_DB}"
if DATABASE_URL="sqlite:///${ALEMBIC_DB}" SECRET_KEY="ci-local" "${PY}" -m alembic upgrade head \
   && DATABASE_URL="sqlite:///${ALEMBIC_DB}" SECRET_KEY="ci-local" "${PY}" -m alembic current | grep -q '(head)'; then
    ok "Migratii la head"
else
    fail "Alembic upgrade/parity esuat"; RC=1
fi
rm -f "${ALEMBIC_DB}"

bold "== 3/3 Teste paritate baseline Alembic =="
if SECRET_KEY="ci-local" "${PY}" -m pytest tests/integration/test_alembic_baseline.py -q; then
    ok "Paritate schema OK"
else
    fail "Paritate schema esuata"; RC=1
fi

echo ""
if [ "${RC}" -eq 0 ]; then
    bold "CI LOCAL: VERDE ✓"
else
    bold "CI LOCAL: ROSU ✗  (vezi mai sus)"
fi
exit "${RC}"
