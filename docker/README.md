# Edifico — Docker (instanță-per-client)

Faza 0: imaginea de bază. O instanță = un container = un client (izolare totală).

## Build
```bash
docker build -t edifico:latest .
```

## Config
```bash
cp .env.example .env
# editează .env: SECRET_KEY unic, ADMIN_EMAIL/PASSWORD, FEATURE_FLAGS (modulele cumpărate)
python -c "import secrets; print(secrets.token_hex(32))"   # pt. SECRET_KEY
```

## Run (SQLite pe volum — cel mai simplu)
```bash
docker run -d --name edifico-client1 \
  --env-file .env \
  -p 8000:8000 \
  -v edifico_client1_data:/app/data \
  -v edifico_client1_uploads:/app/uploads \
  edifico:latest
```
Aplicația: http://localhost:8000 · login cu `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

## Ce face la pornire (`docker/entrypoint.sh` → `scripts/docker_init.py`)
1. **Schema DB** — DB nou: `create_all` + `alembic stamp head`; DB existent: `alembic upgrade head` + `create_all`. Idempotent.
2. **Seed admin** — din `ADMIN_EMAIL`/`ADMIN_PASSWORD`, doar dacă nu există.
3. **Module** — activează flag-urile din `FEATURE_FLAGS`.
4. Pornește **gunicorn** (`WORKERS=1` implicit — vezi nota despre APScheduler în entrypoint).

## Module = feature flags
Setezi în `.env` ce a cumpărat clientul, ex:
```
FEATURE_FLAGS=controale-contract,controale-contract-import-msproject,bim-viewer-3d,bim-clash-detection
```

## Note
- **Postgres** recomandat la trafic mai mare (Faza 1, docker-compose). SQLite-file e ok pentru clienți mici.
- **PA rămâne neatins** — acest setup e paralel, pentru livrare la alți clienți.
- Următorii pași: Faza 1 (docker-compose: app + Postgres + proxy TLS) și Faza 2 (provisioning per subdomeniu).
