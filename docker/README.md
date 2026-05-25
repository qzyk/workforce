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

## Run — opțiunea A: standalone, SQLite (Faza 0, cel mai simplu)
```bash
docker run -d --name edifico-client1 \
  --env-file .env \
  -p 8000:8000 \
  -v edifico_client1_data:/app/data \
  -v edifico_client1_uploads:/app/uploads \
  edifico:latest
```
Aplicația: http://localhost:8000 · login cu `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

## Run — opțiunea B: docker-compose, Postgres + TLS (Faza 1, recomandat în prod)

**Pas 1 — proxy partajat Traefik (o singură dată pe host):**
```bash
docker network create edifico-proxy
cp docker/proxy/.env.example docker/proxy/.env      # completează ACME_EMAIL
docker compose -f docker/proxy/docker-compose.yml up -d
```

**Pas 2 — stack per client:**
```bash
cp .env.example .env
# completează: CLIENT_SLUG, CLIENT_DOMAIN, POSTGRES_PASSWORD, SECRET_KEY, ADMIN_*, FEATURE_FLAGS
docker compose up -d --build
```
Traefik rutează `CLIENT_DOMAIN` → containerul clientului și emite automat certificat Let's Encrypt. Sub compose, `DATABASE_URL` e construit automat din `POSTGRES_*` (Postgres), nu din linia SQLite.

**Alt client** = alt director cu propriul `.env` (alt `CLIENT_SLUG` + `CLIENT_DOMAIN`) → `docker compose up -d`. Volume + DB izolate per proiect compose.

> DNS: `CLIENT_DOMAIN` trebuie să pointeze (A/CNAME) către IP-ul hostului înainte ca Let's Encrypt să emită certificatul.

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

## Provisioning + backup (Faza 2)

**Client nou într-o comandă** (generează `clients/<slug>/.env` cu secrete unice + pornește stack-ul):
```bash
./scripts/provision_client.sh acme acme.edifico.space controale-contract,bim-viewer-3d
```
Afișează la final URL-ul, emailul de admin și **parola generată** (notează-o). Alt client = alt slug/domeniu. `clients/` e în `.gitignore` (conține secrete) — nu se comite.

**Backup** (dump Postgres + arhivă uploads, retenție 14, offsite opțional):
```bash
./scripts/backup_client.sh acme          # un client
./scripts/backup_all.sh                  # toți (pentru cron)
```
Cron zilnic + offsite (rclone):
```bash
0 3 * * * cd /home/edifico/workforce && RCLONE_REMOTE=b2:edifico-backups ./scripts/backup_all.sh >> backups/cron.log 2>&1
```

## Note
- **Postgres** recomandat la trafic mai mare (compose, opțiunea B). SQLite-file e ok pentru clienți mici.
- **PA rămâne neatins** — acest setup e paralel, pentru livrare la alți clienți.
- **APScheduler:** `WORKERS=1` (implicit) ca să nu pornească scheduler-e duplicate. Pentru trafic mare, Faza 3 extrage scheduler-ul într-un container separat și crește workers.
- Următorul pas opțional: **Faza 3** — observabilitate (Sentry/uptime), update etapizat al imaginii, scheduler separat.
