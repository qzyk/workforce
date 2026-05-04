# Migrare MySQL pe PythonAnywhere

Ghid pas-cu-pas pentru migrarea workforce-app de la SQLite la MySQL pe PythonAnywhere,
**fara pierderea datelor de productie**. MySQL e disponibil pe **toate planurile PA** (inclusiv free).

## Cerinte

- Cont PythonAnywhere (orice plan, inclusiv Beginner free)
- DB-ul SQLite curent functional (`~/workforce/database/workforce.db`)
- Acces la consola Bash + tab Web pe PA

## Pasi

### 1. Backup SQLite (obligatoriu)

```
cd ~/workforce
SAFE=~/workforce_safe_$(date +%s)_pre_mysql
mkdir -p "$SAFE"
cp database/workforce.db "$SAFE/"
cp -r uploads "$SAFE/" 2>/dev/null
echo "Backup la: $SAFE"
```

### 2. Initializare MySQL pe PA

1. Pythonanywhere.com → tab **Databases**
2. Sectiunea **MySQL** (top): daca apare buton **"Create database"**, click pe el
3. Setezi **password** la prompt (memoreaza-o!)
4. Vei vedea informatiile:
   ```
   MySQL host: qzyk97.mysql.pythonanywhere-services.com
   MySQL username: qzyk97
   ```
5. La sectiunea **"Your databases"** -> introduci nume DB (ex: `workforce`) -> Click **"Create"**
6. DB-ul tau real va fi prefixat cu username: **`qzyk97$workforce`**

### 3. Construire URL conexiune MySQL

Format MySQL pentru PA:

```
mysql+pymysql://USERNAME:PASSWORD@USERNAME.mysql.pythonanywhere-services.com/USERNAME$DBNAME
```

Exemplu pentru `qzyk97`:

```
mysql+pymysql://qzyk97:Parol4Ta@qzyk97.mysql.pythonanywhere-services.com/qzyk97$workforce
```

ATENTIE:
- Caracterele speciale din parola trebuie URL-encoded: `@`->`%40`, `:`->`%3A`, `#`->`%23`, `!`->`%21`, `/`->`%2F`
- Caracterul `$` din numele DB trebuie pus intre **single quotes** (`'...'`) ca shell-ul sa nu il interpreteze
- Driverul **PyMySQL** e specificat explicit (nu necesita compilare pe PA)

### 4. Update branch + instalare driver

```
cd ~/workforce
git fetch origin
git reset --hard origin/feat/bim-foundation
~/.virtualenvs/workforce-env/bin/pip install PyMySQL
```

### 5. Test conexiune (rapid, fara migrare)

```
python3 -c "
import pymysql
conn = pymysql.connect(
    host='qzyk97.mysql.pythonanywhere-services.com',
    user='qzyk97',
    password='PAROLA_TA',
    database='qzyk97\$workforce',
)
print('Conexiune OK!')
cur = conn.cursor()
cur.execute('SELECT VERSION()')
print('Versiune MySQL:', cur.fetchone()[0])
conn.close()
"
```

Daca apare `Conexiune OK!`, esti gata.

### 6. Migrare schema + date

```
cd ~/workforce
export FLASK_APP=app.py
export MYSQL_URL='mysql+pymysql://qzyk97:PAROLA@qzyk97.mysql.pythonanywhere-services.com/qzyk97$workforce'

# Dry-run intai (nu salveaza nimic, doar verifica)
flask migrate-to-mysql --mysql-url="$MYSQL_URL" --dry-run

# Daca dry-run e OK, migrarea reala:
flask migrate-to-mysql --mysql-url="$MYSQL_URL"
```

Output asteptat:
```
[1/4] Conectez la SQLite source...
[2/4] Conectez la MySQL target: mysql+pymysql://qzyk97:***@qzyk97.mysql...
[3/4] Creez schema pe MySQL (db.create_all)
[4/4] Migrez datele...
  [OK] tenants:                   0 randuri
  [OK] utilizatori:               3 randuri
  [OK] angajati:                 62 randuri
  [OK] proiecte:                  9 randuri
  [OK] pontaje:                  23 randuri
  ...
[OK] Setez AUTO_INCREMENT...

Total randuri migrate: 117
```

### 7. Switch aplicatia spre MySQL

PythonAnywhere → tab **Web** → secțiunea **Environment variables** (scroll mid-page):

Adauga:
```
DATABASE_URL = mysql+pymysql://qzyk97:PAROLA@qzyk97.mysql.pythonanywhere-services.com/qzyk97$workforce
```

ATENTIE: pune URL-ul intre **single quotes** in interfata web pe PA pentru a evita probleme cu `$`.

### 8. Reload + verificare

```
WSGI=$(ls /var/www/*_wsgi.py | head -1)
touch "$WSGI"
```

Apoi tab **Web** → click **Reload**.

Test in browser:
- Login cu admin
- `/activitati/` → vezi activitatile (Ciolacu Albert etc.)
- `/bim/` → arhitectura BIM completa

## Rollback

Daca ceva nu merge:

1. Web tab → Environment variables → **DELETE** `DATABASE_URL` (sau seteaza inapoi la `sqlite:///home/qzyk97/workforce/database/workforce.db`)
2. Restaureaza DB SQLite din backup:
   ```
   cp ~/workforce_safe_*_pre_mysql/workforce.db ~/workforce/database/
   ```
3. Reload pe Web tab

MySQL ramane cu datele migrate dar e ignorat. Poti retesta migrarea oricand.

## Considerații

| Aspect | SQLite | MySQL pe PA |
|---|---|---|
| Concurrency | Single-writer | Multi-writer |
| Backup | Copy fisier | `mysqldump` |
| Performance reads | Foarte rapid local | Latency ~5-15ms |
| Performance writes | Lock pe DB | Concurrent OK |
| Connection limit | N/A | ~50 conexiuni active |
| Storage limit | 1GB+ disk PA | 1-3GB DB plan PA |

## Connection pooling

Config-ul nostru aplica automat pentru MySQL:
```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_pre_ping': True,    # detecteaza conexiuni stale
    'pool_recycle': 280,      # recicleaza la 280s (sub limita PA de 300s)
}
```

PA inchide conexiuni MySQL idle dupa ~5 min. `pool_recycle` previne eroarea
"MySQL server has gone away".

## Multi-tenant cu MySQL — workflow complet

1. Migrare SQLite → MySQL (pasii 1-8 de mai sus)
2. Activeaza multi-tenant: in Web → Environment variables:
   ```
   MULTI_TENANT_MODE = strict
   ```
3. Creeaza super-admin (admin cu `tenant_id=NULL`):
   ```
   cd ~/workforce
   export DATABASE_URL='mysql+pymysql://...'
   python3 -c "
   import sys; sys.path.insert(0, '.')
   from app import create_app
   from models import db, Utilizator
   app = create_app('default')
   with app.app_context():
       u = Utilizator.query.filter_by(email='super@admin.local').first()
       if not u:
           u = Utilizator(nume='Super', prenume='Admin',
                          email='super@admin.local', rol='admin',
                          activ=True, tenant_id=None)
           u.set_password('CHANGE_ME')
           db.session.add(u); db.session.commit()
           print('Super-admin creat')
       else:
           print('Super-admin deja exista')
   "
   ```
4. Login ca super-admin → vei vedea **Tenants** in sidebar (sub Setari)
5. Creezi tenants:
   - cod `innova` → "Innova Construct SRL"
   - cod `acme` → alt client (daca aplicabil)
6. Atribui utilizatori existenti:
   - Tab "Utilizatori in `innova`" → click "Adauga la tenant" pentru fiecare user
7. Toate datele existente raman cu `tenant_id=NULL` pana le mutati explicit

## Probleme cunoscute

### `Access denied for user '...'`

Parola gresita. Reseteaza din **Databases** → MySQL → "Set password".

### `Unknown database 'qzyk97$workforce'`

DB-ul nu e creat. Cream-l din **Databases** → "Your databases" → introduci nume.

### `Can't connect to MySQL server`

Host gresit sau port. PA foloseste port 3306 default. Format host: `<user>.mysql.pythonanywhere-services.com`.

### `MySQL server has gone away`

Conexiune idle inchisa de PA. Solutie: pool_pre_ping=True (deja setat). Daca apare in continuare, scade `pool_recycle` la 200.

### `(1071) Specified key was too long`

InnoDB are limita de 767 bytes pe index in versiunile vechi. Solutie: utf8mb4 + DYNAMIC row format (default in MySQL 5.7+ pe PA).

## Tabele migrate

Lista completa (31 tabele) din `scripts/migrate_sqlite_to_mysql.py`:

**Workforce core**: tenants, utilizatori, angajati, proiecte, angajat_proiect, pontaje,
documente, concedii, rapoarte, sarbatori_legale, tipuri_instalatii, tipuri_documente_proiect,
documente_proiect, revizii_documente, categorii_activitati, rapoarte_activitati.

**Masini**: masini, documente_masini, atribuiri_masini, conduceri_masini, defectiuni_masini.

**BIM**: bim_santiere, bim_cladiri, bim_niveluri, bim_zone, bim_spatii, bim_elemente,
bim_assets, bim_issues, bim_modele, bim_external_mappings.

## Referinte

- [PythonAnywhere MySQL docs](https://help.pythonanywhere.com/pages/UsingMySQL)
- [SQLAlchemy MySQL dialect](https://docs.sqlalchemy.org/en/20/dialects/mysql.html)
- [PyMySQL](https://pypi.org/project/PyMySQL/)
