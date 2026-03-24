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

# 6. Pornire server
python app.py
```

Serverul porneste la `http://localhost:5000`

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
