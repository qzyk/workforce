# Edifico - imagine de productie (instanta-per-client)
# Build:  docker build -t edifico:latest .
# Run:    docker run --env-file .env -p 8000:8000 -v edifico_data:/app/data -v edifico_uploads:/app/uploads edifico:latest
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# curl pentru HEALTHCHECK. psycopg2-binary isi aduce propriul libpq (fara build).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependinte aplicatie + server (gunicorn) + driver Postgres.
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install "gunicorn>=21.2" "psycopg2-binary>=2.9"

# Codul aplicatiei
COPY . .

# Directoare persistente (montate ca volume in productie)
RUN mkdir -p /app/data /app/uploads /app/exports \
    && chmod +x docker/entrypoint.sh

VOLUME ["/app/data", "/app/uploads"]

EXPOSE 8000

# Healthcheck pe o ruta publica (login). NB: /home exista doar dupa merge-ul
# branch-ului de marketing; pe baza curenta /auth/login e ruta publica sigura.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT:-8000}/auth/login" || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
