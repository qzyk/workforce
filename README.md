# INNOVA WORKFORCE v2.0

Sistem de Management al Fortei de Munca in Constructii

## Cerinte Sistem

- Python 3.10+
- pip (package manager Python)

## Instalare

```bash
# 1. Navigare in directorul aplicatiei
cd workforce_app

# 2. Creare mediu virtual
python -m venv venv

# 3. Activare mediu virtual
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 4. Instalare dependente
pip install flask flask-sqlalchemy flask-login flask-wtf werkzeug openpyxl pillow

# Optional (pentru rapoarte PDF):
pip install reportlab

# 5. Initializare baza de date cu date demo
flask init-db --demo

# 6. (DB existent) Marcheaza schema ca aliniata la baseline-ul Alembic
#    NU ruleaza acest pas pe DB-uri noi.
alembic stamp head

# 7. Pornire server
python app.py
```

Serverul porneste la `http://localhost:5000`

## Migratii Alembic

Schema bazei de date este versionata cu Alembic incepand din Faza 1 BIM foundation.

### Pe DB-uri NOI (CI, dev proaspat)
```bash
alembic upgrade head    # creeaza schema completa (echivalent cu db.create_all())
```

### Pe DB-uri EXISTENTE (productie, dev care exista deja)
**Important: nu rula `alembic upgrade head` pe un DB cu date - schema e deja la zi.**
```bash
# 1. Backup intai (script furnizat)
./scripts/backup_before_alembic.sh

# 2. Marcheaza DB-ul ca fiind la baseline (nu modifica datele)
alembic stamp head

# 3. De-aici inainte, fiecare migratie noua se aplica cu:
alembic upgrade head
```

### Generare migratie noua dupa modificari de modele
```bash
alembic revision --autogenerate -m "descriere_scurta"
# Verifica fisierul generat in migrations/versions/, apoi:
alembic upgrade head
```

Testul `tests/integration/test_alembic_baseline.py` verifica automat ca schema
produsa de Alembic e identica cu `db.create_all()` din models.py.

## Conturi Demo

| Rol       | Email                | Parola      |
|-----------|----------------------|-------------|
| Admin     | admin@innova.ro      | admin123    |
| Manager   | manager@innova.ro    | manager123  |
| Operator  | operator@innova.ro   | op123       |

## Module

### Dashboard
- Statistici generale (angajati, proiecte, pontaje)
- Grafice interactive Chart.js
- Alerte documente expirate si pontaje in asteptare

### Angajati (`/angajati`)
- Lista cu filtre, cautare, paginare
- Adaugare/editare cu validare WTForms
- Profil detaliat cu tab-uri (date, proiecte, pontaje, documente)
- Export/import Excel
- Upload poza profil cu resize automat

### Proiecte (`/proiecte`)
- Gestionare proiecte cu cod, buget, echipa
- Asociere angajati pe proiecte cu tarif negociat
- Progres automat si zile ramase
- Raport financiar per proiect

### Pontaje (`/pontaje`)
- Introducere pontaj zilnic cu ora start/sfarsit
- Calcul automat ore normale, suplimentare 50%, suplimentare 100%
- Flux aprobare: draft -> trimis -> aprobat/respins
- Calendar vizualizare luna
- Validare zile lucratoare, sambata, duminica, sarbatori legale

### Documente (`/documente`)
- Panou cu alerte (expirate, expira curand)
- Upload fisiere (PDF, JPG, PNG, DOCX, max 10MB)
- Auto-calcul data expirare per tip document
- Documente obligatorii per functie
- Raport expirate cu export Excel

### Rapoarte (`/rapoarte`)
- 8 tipuri rapoarte Excel + 3 PDF:
  - Foaie Colectiva Prezenta (A3)
  - Stat de Plata
  - Situatie Proiect (multi-sheet)
  - Centralizator Ore
  - Raport Documente
  - Pontaj Individual
  - Prezenta Zilnica
  - Raport SSM
- Istoric rapoarte cu descarcare

### Setari Administrative (`/setari`) - doar Admin
- Date firma (CUI, adresa, IBAN, reprezentant)
- Gestionare utilizatori (CRUD, reset parola, activare/dezactivare)
- Sarbatori legale (import Romania, adaugare manuala)
- Backup & Restore (DB + uploads in ZIP)
- Jurnal activitate (log actiuni cu cautare)
- Setari generale (ore lucru, salariu minim, alerte)

## Roadmap BIM / Digital Twin

Evolutia platformei catre BIM/Digital Twin se face in 8 faze incrementale, fiecare un PR safe.

| Faza | Tema | Status |
|------|------|--------|
| 1 | Foundation: Alembic + audit log + feature flags + CI | **Live** |
| 2 | 3D Viewer xeokit-sdk + APS adapter (stub) | **Live** |
| 3 | Model versioning + Federation (CDE workflow) | **Live (branch)** |
| 4 | Clash detection + Rule engine | **Live (branch)** |
| 5 | 4D/5D - Schedule + Cost | **In curs (acest PR)** |
| 5 | 4D/5D - Schedule + Cost | Planificat |
| 6 | Digital Twin / IoT layer (sensori, time-series) | Planificat |
| 7 | Real-time collab via SSE + Kanban issue board | Planificat |
| 8 | Governance, COBie, BCF complet, RBAC fin | Planificat |

Feature-urile noi se activeaza prin `feature_flags` (default OFF).
Vezi catalogul flag-urilor in `services/feature_flags.py:KNOWN_FLAGS`.

### Viewer 3D BIM (Faza 2)

Aplicatia suporta 3 viewere pentru modelele IFC, in ordinea prioritatii:

1. **Autodesk APS Viewer** (cel mai bun pentru clienti enterprise)
   - Activare: `APS_CLIENT_ID` + `APS_CLIENT_SECRET` env vars + flag `bim-aps-adapter` ON
   - Modelul trebuie sa aiba URN APS in `extern_id` (source_system='autodesk') sau in tabela `bim_external_mappings`
   - Redirect la `viewer.autodesk.com` cu URN

2. **xeokit-sdk** (open source, recomandat pentru self-hosted)
   - Activare: flag `bim-viewer-3d` ON
   - Foloseste xeokit-sdk + WebIFCLoaderPlugin (CDN jsDelivr)
   - Performanta net superioara fata de viewer-ul legacy pe modele &gt;50MB

3. **web-ifc-viewer** (legacy, default)
   - Activ daca niciun flag de mai sus nu e setat
   - Forteaza override cu `?legacy=1` in URL

Activeaza viewer-ul nou prin Python REPL sau scripts/init_seed:
```python
from services.feature_flags import set_flag
set_flag('bim-viewer-3d', True)  # global, pentru toti tenant-ii
```

### CDE Workflow + Federation (Faza 3)

Inspirat din **ISO 19650** (Common Data Environment). Fiecare model BIM
poate avea N versiuni cu workflow de status:

```
WIP → SHARED → PUBLISHED → ARCHIVED
              ↘ REJECTED → WIP
```

- **WIP** (Work In Progress): in dezvoltare, vizibil doar pentru autor
- **SHARED**: partajat pentru coordonare cu alte discipline
- **PUBLISHED**: aprobat oficial (folosibil pentru executie). Doar admin/manager poate publica.
- **REJECTED**: respins (cu comentariu obligatoriu in flow tipic). Poate fi reluat in WIP.
- **ARCHIVED**: terminal (versiune veche pastrata pentru istoric)

**Federation** = viewer xeokit care incarca simultan toate versiunile `published` ale unui santier (multi-disciplina, filtrabil prin pillule per disciplina: ARH/STR/MEP/ELE/HVAC/SAN/GEN).

**Activare** (default OFF):
```python
from services.feature_flags import set_flag
set_flag('bim-model-versioning', True)  # Activeaza versionare + workflow CDE
set_flag('bim-federation', True)         # Activeaza viewer federat pe santier
```

**Pagini noi** (vizibile dupa activare flag):
- `/bim/model/<id>/versiuni` — lista versiuni cu butoane de tranzitie
- `/bim/model/<id>/versiune-noua` — formular creare versiune
- `/bim/santier/<id>/viewer-federat` — viewer multi-model overlap (necesita versiuni `published`)

Toate tranzitiile de status se loaheaza in `audit_log` (entity_type=`bim_model_version`).

### Rule Engine + Clash Detection (Faza 4)

**Rule Engine**: model checking declarativ. Reguli scrise in JSON cu pattern selector + constraint:

```json
{
  "selector": {"tip_element": "wall"},
  "constraint": {"required_properties": ["fire_rating", "thickness"]}
}
```

Tipuri suportate (toate ruleaza prin `services/bim_rules.py`):
- `required_properties` — element trebuie sa aiba toate proprietatile listate
- `naming_convention` — numele trebuie sa respecte un regex
- `forbidden_in_zone` — element interzis in zone cu anumite categorii (zona.tip_zona)
- `min_clearance` — distanta minima fata de alt tip element (placeholder, geometric)

Engine-ul ruleaza toate regulile active si genereaza **RuleViolation**-uri. Admin/manager poate
**promova** o violare in **IssueBIM** oficial (cu tip='neconformitate').

**Clash Detection**: detectie automata de coliziuni (`services/clash_detection.py`):
- **geometric** — AABB intersection (intersectie de bounding boxes; necesita `proprietati_json.bbox`)
- **logic** — fara geometrie:
  - GUID IFC duplicat (federation conflict)
  - Spatii supraincarcate (>20 elemente per spatiu)
- **mixed** — ambele (default)

Severitate auto: critic/mare/medie/mica in functie de volumul overlap-ului.

**Activare**:
```python
from services.feature_flags import set_flag
set_flag('bim-rule-engine', True)
set_flag('bim-clash-detection', True)
```

**Pagini noi**:
- `/bim/rules` — lista reguli + buton "Ruleaza toate"
- `/bim/rule/nou` — formular creare regula (cu exemple JSON per tip)
- `/bim/violations` — violari curente, cu buton "Promoveaza in issue"
- `/bim/clash` — istoric rulari clash detection
- `/bim/clash/<id>` — detalii rulare (lista clash-uri, filtru severitate)
- `/bim/api/clash/<id>` — JSON pentru integrari externe

Toate rularile se loaheaza in `audit_log` (`run_rules`, `run_clash_detection`).

### 4D Schedule + 5D Cost (Faza 5)

**4D Schedule**: link element BIM ↔ task cu interval planificat. Vizualizare timeline
Gantt + filtru "ce e construit la data X" pentru construction sequencing.

Tabel: `bim_task_schedules` (1 element → N intrari pe faze: excavatie, fundatie,
structura, finisaje, MEP, etc.). Status: `planificat → in_curs → finalizat | amanat`.
Auto-update progres (0..100%) cu auto-tranzitie status.

**5D Cost**: cost per element BIM (cantitate * pret_unitar) cu categorii:
material / manopera / echipament / transport / utilitati / altul. Tip:
`planificat` (deviz) sau `real` (facturat). Agregare per disciplina, cladire,
tip element. Comparatie planificat vs real (delta + delta_pct).

**Activare**:
```python
from services.feature_flags import set_flag
set_flag('bim-4d-schedule', True)
set_flag('bim-5d-cost', True)
```

**Pagini noi**:
- `/bim/element/<id>/schedule` — adauga schedule entries pentru un element
- `/bim/element/<id>/cost` — adauga cost items + breakdown pe categorii
- `/bim/santier/<id>/4d-timeline` — Gantt chart cu progres per task
- `/bim/santier/<id>/5d-dashboard` — KPI plan vs real + breakdown
- `/bim/api/santier/<id>/visible-at?data=YYYY-MM-DD` — JSON: ce elemente sunt
  vizibile la o data (pentru construction sequencing in 3D viewer)
- `/bim/api/element/<id>/cost` — JSON: total + breakdown categorii

Toate operatiile (creare schedule, update progres, creare cost) se loaheaza in `audit_log`.

## Securitate

- CSRF protection (Flask-WTF)
- Rate limiting login (5 incercari, blocare 15 min)
- Security headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection)
- Decorator `@admin_required` si `@manager_or_admin`
- Parole hashuite cu Werkzeug
- Validare fisiere upload (extensie, marime)

## Structura Proiect

```
workforce_app/
├── app.py              # Aplicatie principala Flask
├── config.py           # Configurare
├── models.py           # Modele SQLAlchemy
├── README.md
├── database/           # SQLite DB + config JSON
├── uploads/            # Fisiere incarcate
├── exports/            # Rapoarte generate
├── backups/            # Backup-uri ZIP
├── forms/              # WTForms
│   ├── angajati_forms.py
│   └── documente_forms.py
├── routes/             # Blueprints
│   ├── auth.py         # Autentificare, login, profil
│   ├── dashboard.py    # Panou de control
│   ├── angajati.py     # CRUD angajati
│   ├── proiecte.py     # CRUD proiecte
│   ├── pontaje.py      # Gestionare pontaje
│   ├── documente.py    # Upload si gestionare documente
│   ├── rapoarte.py     # Generare rapoarte
│   └── setari.py       # Setari administrative
├── rapoarte/           # Generatoare rapoarte
│   ├── excel_generator.py  # 8 generatoare Excel
│   └── pdf_generator.py    # 3 generatoare PDF
├── templates/          # Jinja2 templates
│   ├── base.html
│   ├── dashboard.html
│   ├── errors/         # 403, 404, 500
│   ├── auth/           # login, profil, schimba_parola
│   ├── angajati/       # lista, formular, fisa
│   ├── proiecte/       # lista, formular, detalii
│   ├── pontaje/        # lista, formular, calendar
│   ├── documente/      # panou, upload, lista, expirate
│   ├── rapoarte/       # panou, istoric
│   └── setari/         # firma, utilizatori, sarbatori, backup, jurnal, generale
└── static/
    ├── css/style.css   # Stiluri personalizate
    └── js/main.js      # JavaScript client
```

## Tehnologii

- **Backend**: Python 3, Flask, SQLAlchemy, Flask-Login, Flask-WTF
- **Baza de date**: SQLite
- **Frontend**: HTML5, CSS3 (custom properties), JavaScript vanilla
- **Biblioteci**: Chart.js 4.4.1, Font Awesome 6.5.1, Google Fonts Inter
- **Rapoarte**: openpyxl (Excel), ReportLab (PDF - optional)
- **Imagini**: Pillow (resize, crop)

## Versiune

**v2.0.0** - Martie 2026
