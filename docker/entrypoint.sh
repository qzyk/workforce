#!/bin/sh
# Entrypoint container Edifico: pregateste DB + seed, apoi porneste gunicorn.
set -e

echo "[entrypoint] Edifico - init DB + seed..."
python scripts/docker_init.py

echo "[entrypoint] pornesc gunicorn pe :${PORT:-8000} (workers=${WORKERS:-1}, threads=${THREADS:-8})"
# WORKERS implicit 1: APScheduler ruleaza in proces; mai multi workers ar porni
# mai multe scheduler-e. Pentru trafic mare, extrage scheduler-ul separat (Faza 3)
# si creste WORKERS. gthread + threads acopera concurenta per-client.
exec gunicorn \
  --worker-class gthread \
  --workers "${WORKERS:-1}" \
  --threads "${THREADS:-8}" \
  --timeout 120 \
  --bind "0.0.0.0:${PORT:-8000}" \
  --access-logfile - \
  --error-logfile - \
  app:app
