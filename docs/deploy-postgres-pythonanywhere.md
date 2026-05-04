# Migrare PostgreSQL pe PythonAnywhere

Ghid pas-cu-pas pentru migrarea workforce-app de la SQLite la PostgreSQL pe PythonAnywhere,
**fara pierderea datelor de productie**.

## Cerinte

- Cont **PythonAnywhere Hacker plan sau mai mare** (PG necesita plan platit)
- DB-ul SQLite curent functional (`~/workforce/database/workforce.db`)
- Acces la consola Bash + tab Web pe PA

## Pasi

### 1. Backup SQLite (obligatoriu inainte de orice)

```
cd ~/workforce
SAFE=~/workforce_safe_$(date +%s)_pre_postgres
mkdir -p "$SAFE"
cp database/workforce.db "$SAFE/"
cp -r uploads "$SAFE/" 2>/dev/null
echo "Backup la: $SAFE"
```

### 2. Creare bază PostgreSQL pe PythonAnywhere

1. Web → **Databases** tab
2. Click **Postgres** → **Create a new database**
3. Notezi credentialele:
   - Host: `your-username-XXX.postgres.pythonanywhere-services.com`
   - Port: `XXXX`
   - User: `your-username`
   - Password: `<generated>`
   - Database name: `your-username$default` sau cel ales

### 3. Construire URL conexiune PG

```
postgresql://USER:PASSWORD@HOST:PORT/DBNAME
```

Exemplu (`qzyk97` ar fi):
```
postgresql://qzyk97:mypass@qzyk97-1234.postgres.pythonanywhere-services.com:12345/qzyk97$default
```

⚠ **Atentie**: caracterele speciale din parola (ex: `@`, `:`, `/`) trebuie URL-encoded.

### 4. Update branch pe PA

```
cd ~/workforce
git fetch origin
git reset --hard origin/feat/bim-foundation
~/.virtualenvs/workforce-env/bin/pip install psycopg2-binary
```

### 5. Migrare cod schema + date

```
cd ~/workforce
export PG_URL='postgresql://USER:PASSWORD@HOST:PORT/DBNAME'
export FLASK_APP=app.py

# Dry-run intai (nu salveaza nimic, doar verifica)
flask migrate-to-postgres --pg-url="$PG_URL" --dry-run

# Daca dry-run e OK, migrarea reala:
flask migrate-to-postgres --pg-url="$PG_URL"
```

Output asteptat:
```
[1/5] Conectez la SQLite source...
[2/5] Conectez la Postgres target...
[3/5] Creez schema pe Postgres (db.create_all)
[4/5] Migrez datele...
  [OK] tenants:                   0 randuri
  [OK] utilizatori:               3 randuri
  [OK] angajati:                 62 randuri
  [OK] proiecte:                  9 randuri
  [OK] pontaje:                  23 randuri
  [OK] documente:                15 randuri
  [OK] rapoarte_activitati:       5 randuri
  ...
[5/5] Resetez sequences pe PG...
  [OK] utilizatori_id_seq
  [OK] angajati_id_seq
  ...

Total randuri migrate: 117
```

### 6. Switch aplicatia spre PG

Pe PythonAnywhere → tab **Web** → secțiunea **Environment variables**:

Adauga / modifica:
```
DATABASE_URL = postgresql://USER:PASSWORD@HOST:PORT/DBNAME
```

⚠ **Nu** lași URL-ul cu credentiale in fișiere de cod sau git.

### 7. Reload + verificare

```
# Pe PA bash
WSGI=$(ls /var/www/*_wsgi.py | head -1)
touch "$WSGI"
```

Apoi tab **Web** → **Reload**.

Test:
- Login cu admin → verifica dashboard
- `/activitati/` → vezi activitatile (numele Ciolacu Albert etc.)
- `/bim/` → arhitectura BIM

### 8. (Opțional) Activare multi-tenant

Dacă vrei să activezi modul multi-tenant pe PG:

```
# Web → Environment variables
MULTI_TENANT_MODE = strict
```

Reload. Acum:
1. Login ca super-admin (admin fără tenant)
2. Mergi la **Setari → Tenants** (apare în sidebar)
3. Creezi un tenant pentru fiecare organizație
4. Atribui utilizatorii la tenants

## Rollback

Dacă ceva nu merge:

```
# 1. Sterge env DATABASE_URL (sau il setezi inapoi la sqlite)
# Web → Environment variables → DATABASE_URL = sqlite:///home/USER/workforce/database/workforce.db

# 2. Restaureaza DB SQLite din backup
cp ~/workforce_safe_<timestamp>_pre_postgres/workforce.db ~/workforce/database/

# 3. Reload
touch /var/www/$(whoami)_pythonanywhere_com_wsgi.py
```

PG-ul ramane cu datele migrate dar e ignorat. Poti retesta migrarea oricand.

## Considerații performance

| Aspect | SQLite | PostgreSQL pe PA |
|---|---|---|
| Concurrency | Single-writer | Multi-writer |
| Backup | Copy fisier | `pg_dump` |
| Performance reads | Foarte rapid local | Latency network ~5-20ms |
| Performance writes | Lock pe DB | Concurrent OK |
| Storage | Disk PA | DB plan PA (limita) |

Pentru o aplicatie cu **<100 useri concurenti**, SQLite e ok. PostgreSQL e indicat cand:
- Ai mai mult de 1 server PA worker
- Ai concurrent writes (ex: pontaje multi-user simultan)
- Vrei multi-tenant strict
- Ai > 500MB date

## Pool tuning

Config-ul actual seteaza automat pentru PG:
```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_pre_ping': True,    # detecteaza conexiuni stale
    'pool_recycle': 280,      # recicleaza la 280s (sub limita PA de 300s)
}
```

Daca observi erori `connection has been closed unexpectedly`, ajusteaza `pool_recycle` mai mic (200s).

## Tabele migrate

Lista din `scripts/migrate_sqlite_to_postgres.py`:

**Workforce core**: tenants, utilizatori, angajati, proiecte, angajat_proiect, pontaje,
documente, concedii, rapoarte, sarbatori_legale, tipuri_instalatii, tipuri_documente_proiect,
documente_proiect, revizii_documente, categorii_activitati, rapoarte_activitati.

**Masini**: masini, documente_masini, atribuiri_masini, conduceri_masini, defectiuni_masini.

**BIM**: bim_santiere, bim_cladiri, bim_niveluri, bim_zone, bim_spatii, bim_elemente,
bim_assets, bim_issues, bim_modele, bim_external_mappings.

Total: 31 tabele.

## Probleme cunoscute

### "Already migrated"

Dacă rulezi `flask migrate-to-postgres` de două ori, a doua oară spune `[SKIP] tabel are deja date`.
Asta e by design (idempotent). Pentru re-migrare completă, șterge manual din PG sau folosește un PG nou.

### "permission denied for sequence"

Pe PA, user-ul tău e owner-ul DB-ului. Dacă apare asta, verifică că PG_URL e corect.

### `psycopg2` failed to install

Pe PA folosește **`psycopg2-binary`** (deja în requirements.txt) — nu necesită compilare:
```
~/.virtualenvs/workforce-env/bin/pip install psycopg2-binary
```

## Multi-tenant cu PostgreSQL — workflow complet

1. Migrare SQLite → PG (pasii 1-7 de mai sus)
2. Activare multi-tenant: `MULTI_TENANT_MODE=strict`
3. Creare super-admin (admin cu `tenant_id=NULL`):
   ```python
   # In consola Python pe PA
   from app import create_app
   from models import db, Utilizator
   app = create_app('default')
   with app.app_context():
       u = Utilizator.query.filter_by(email='supert@admin.local').first()
       if not u:
           u = Utilizator(nume='Super', prenume='Admin', email='super@admin.local',
                          rol='admin', activ=True, tenant_id=None)
           u.set_password('CHANGE_ME')
           db.session.add(u)
           db.session.commit()
   ```
4. Login ca super-admin → **Setari → Tenants**:
   - Creezi tenant `innova` (Innova Construct SRL)
   - Creezi tenant `acme` (alt client, daca aplicabil)
5. Atribui utilizatorii existenți:
   - Tab "Utilizatori in `innova`" → click "Adauga la tenant" pe fiecare user
6. Toate datele existente (proiecte, angajati, activitati) raman cu `tenant_id=NULL`
   pana le mutati explicit. In MODE=strict, doar super-admin le mai vede.

## Referinte

- [PythonAnywhere Postgres docs](https://help.pythonanywhere.com/pages/PostgresGettingStarted)
- [SQLAlchemy PG dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [psycopg2-binary](https://pypi.org/project/psycopg2-binary/)
