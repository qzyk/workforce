#!/bin/sh
# Provisioning instanta noua de client (Faza 2).
#   ./scripts/provision_client.sh <slug> <domeniu> [flag1,flag2,...]
# Ex:
#   ./scripts/provision_client.sh acme acme.edifico.space controale-contract,bim-viewer-3d
#
# Genereaza clients/<slug>/.env (SECRET_KEY + parola DB unice), apoi porneste
# stack-ul docker-compose pentru clientul respectiv (proiect edifico-<slug>).
set -e

SLUG="$1"
DOMAIN="$2"
FLAGS="${3:-}"

if [ -z "$SLUG" ] || [ -z "$DOMAIN" ]; then
  echo "Utilizare: $0 <slug> <domeniu> [flag1,flag2,...]" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/clients/$SLUG"
ENVF="$DIR/.env"

if [ -f "$ENVF" ]; then
  echo "Exista deja $ENVF - opresc (nu suprascriu secrete). Sterge-l manual daca vrei re-provision." >&2
  exit 1
fi

gen()  { python3 -c "import secrets; print(secrets.token_hex(24))"; }
genpw(){ python3 -c "import secrets; print(secrets.token_urlsafe(12))"; }

SECRET="$(gen)"
PGPASS="$(gen)"
ADMINPASS="$(genpw)"
ADMIN_EMAIL="admin@$DOMAIN"

mkdir -p "$DIR"
umask 077
cat > "$ENVF" <<EOF
CLIENT_SLUG=$SLUG
CLIENT_DOMAIN=$DOMAIN
POSTGRES_USER=edifico
POSTGRES_PASSWORD=$PGPASS
POSTGRES_DB=edifico
SECRET_KEY=$SECRET
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMINPASS
ADMIN_NUME=Admin
ADMIN_PRENUME=$SLUG
FEATURE_FLAGS=$FLAGS
MAPBOX_PUBLIC_TOKEN=
MAPBOX_SECRET_TOKEN=
PORT=8000
WORKERS=1
THREADS=8
EOF
chmod 600 "$ENVF"

echo "Pornesc stack-ul pentru '$SLUG' ($DOMAIN)..."
docker compose --env-file "$ENVF" -f "$ROOT/docker-compose.yml" up -d --build

cat <<EOF

============================================================
 GATA - client provizionat: $SLUG
------------------------------------------------------------
 URL:        https://$DOMAIN
             (asigura-te ca DNS-ul pointeaza la acest host)
 Admin:      $ADMIN_EMAIL
 Parola:     $ADMINPASS
             ^-- NOTEAZ-O ACUM (nu se mai afiseaza)
 Module:     ${FLAGS:-(niciunul - activeaza din .env + reload)}
 Config:     $ENVF
============================================================
EOF
