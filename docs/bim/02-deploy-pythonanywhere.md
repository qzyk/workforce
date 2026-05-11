# Deploy `feat/bim-foundation` pe PythonAnywhere

Acest ghid descrie procedura sigură de aplicare a branch-ului `feat/bim-foundation`
pe instanța PythonAnywhere existentă, **fără pierderea datelor**.

## Pre-checklist

- [ ] DB-ul tău de producție e backup-uit (vezi `~/workforce_safe_*` din intervențiile anterioare)
- [ ] Aplicația rulează corect pe `main` (login + activitățile merg)
- [ ] Ai acces la consola Bash de pe PythonAnywhere

## Pas 1 — Pregătire backup explicit

Pe PythonAnywhere (consolă Bash):

```
cd ~/workforce
SAFE=~/workforce_safe_$(date +%s)_pre_bim
mkdir -p "$SAFE"
cp database/workforce.db "$SAFE/" 2>/dev/null && echo "DB salvat in $SAFE"
cp database/*.json "$SAFE/" 2>/dev/null
cp -r uploads "$SAFE/" 2>/dev/null
echo "BACKUP COMPLET: $SAFE"
```

## Pas 2 — Pull branch BIM

```
cd ~/workforce
git fetch origin
git checkout feat/bim-foundation
git reset --hard origin/feat/bim-foundation
git log --oneline -5
```

Verifică că ultimul commit e `1127b17 BIM Phase 4` sau mai recent.

## Pas 3 — Instalare dependențe noi

Dependențele noi față de `main`:
- `pytest`, `pytest-cov` (dev)
- `ifcopenshell` (opțional — pentru import IFC; dacă lipsește, importul afișează mesaj clar)

```
~/.virtualenvs/workforce-env/bin/pip install -r requirements.txt
```

Notă: `ifcopenshell` poate eșua la instalare pe PythonAnywhere (cere wheel pre-compilat).
Dacă eșuează, sare peste — restul aplicației funcționează fără el.

## Pas 4 — Migrare schema BIM

```
cd ~/workforce
export FLASK_APP=app.py
flask migrate-bim
```

Comanda creează 10 tabele BIM noi și adaugă coloane FK pe `utilizatori`,
`angajati`, `proiecte`, `rapoarte_activitati`, `pontaje`. **Idempotentă** —
poate fi rulată de mai multe ori fără efect secundar.

## Pas 5 — Reload WSGI

```
WSGI=$(ls /var/www/*_wsgi.py 2>/dev/null | head -1)
[ -n "$WSGI" ] && touch "$WSGI" && echo "Reloaded: $WSGI"
```

Apoi: tab **Web** → buton verde **Reload**.

## Pas 6 — Verificare în browser

1. Login cu contul tău admin
2. Verifică în sidebar: link nou **BIM** cu sub-items Tree / Santiere / Elemente / Issues
3. În header (sus dreapta): switch limbă **RO** / **EN**
4. Click pe **BIM** → ar trebui să vezi dashboard cu 0 șantiere și mesaj "Niciun șantier încă"
5. Click pe **Santier nou** → completează un șantier de test → Salvează

## Rollback (dacă ceva nu merge)

```
cd ~/workforce
git checkout main
git reset --hard origin/main
# Restaurez DB din backup (path-ul $SAFE de la Pas 1)
cp ~/workforce_safe_<timestamp>_pre_bim/workforce.db database/
WSGI=$(ls /var/www/*_wsgi.py | head -1)
touch "$WSGI"
# Apoi Reload pe Web tab
```

Tabelele `bim_*` rămân în DB (nu produc efect dacă codul nu le folosește),
dar pot fi șterse manual cu:
```
sqlite3 database/workforce.db "DROP TABLE bim_assets; DROP TABLE bim_issues; ..."
```

## Migrare ulterioară spre PostgreSQL

Când ești gata pentru PostgreSQL pe PA:

1. Comandă pe PythonAnywhere → tab **Databases** → "Create a Postgres database"
   (necesită cont plătit Hacker sau mai mare)
2. Setezi variabila de mediu:
   ```
   export DATABASE_URL='postgresql://username:pass@host:port/dbname'
   ```
3. Folosești `pgloader` sau scriptul ad-hoc din `scripts/sqlite_to_postgres.py`
   (a fi adăugat ulterior).

## Branch merge în main

Când totul e verificat:

Pe PythonAnywhere:
```
git checkout main
git merge feat/bim-foundation
git push origin main
```

Sau pe GitHub: **Open Pull Request** și merge prin UI.

## Post-deploy: verificări recomandate

- [ ] Login cu admin → OK
- [ ] Dashboard workforce (Activități, Pontaje) → OK, fără erori
- [ ] BIM dashboard → 0 entități, mesaj curat
- [ ] Switch RO ↔ EN funcționează
- [ ] Crearea unui șantier de test → funcționează
- [ ] Editare/ștergere șantier → funcționează
- [ ] Tab Activități → exportul EDIFICO continuă să meargă
- [ ] Pontaje → continuă să se salveze fără erori (nullable FK BIM)
