"""
INNOVA WORKFORCE - Aplicatie principala Flask
Sistem de Management al Fortei de Munca in Constructii
"""

import os
import sys

# Ensure the app directory is in sys.path so imports work from any CWD
_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

import json
import click
from datetime import datetime, date, timedelta
from decimal import Decimal
from random import choice, randint, uniform

from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

from config import config
from models import (
    db, Utilizator, Angajat, Proiect, AngajatProiect,
    Pontaj, Document, Raport, Concediu, SarbatoareLegala,
    TipInstalatie, TipDocumentProiect, DocumentProiect, RevizieDocument,
    RaportActivitate, CategorieActivitate,
    Masina, DocumentMasina, AtribuireMasina, ConducereMasina, DefectiuneMasina
)

# ============================================================
# INITIALIZARE APLICATIE
# ============================================================

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initializare extensii
    db.init_app(app)
    csrf = CSRFProtect(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Trebuie sa fiti autentificat pentru a accesa aceasta pagina.'
    login_manager.login_message_category = 'warning'
    login_manager.remember_cookie_duration = timedelta(days=30)

    @login_manager.user_loader
    def load_user(user_id):
        return Utilizator.query.get(int(user_id))

    # Asigura existenta directoarelor
    for folder in [app.config['UPLOAD_FOLDER'], app.config['EXPORT_FOLDER'],
                   os.path.join(app.root_path, 'database')]:
        os.makedirs(folder, exist_ok=True)

    # --------------------------------------------------------
    # INREGISTRARE BLUEPRINTS
    # --------------------------------------------------------
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.angajati import angajati_bp
    from routes.proiecte import proiecte_bp
    from routes.pontaje import pontaje_bp
    from routes.documente import documente_bp
    from routes.rapoarte import rapoarte_bp
    from routes.setari import setari_bp
    from routes.documente_proiecte import doc_proiecte_bp
    from routes.activitati import activitati_bp
    from routes.masini import masini_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(angajati_bp, url_prefix='/angajati')
    app.register_blueprint(proiecte_bp, url_prefix='/proiecte')
    app.register_blueprint(pontaje_bp, url_prefix='/pontaje')
    app.register_blueprint(documente_bp, url_prefix='/documente')
    app.register_blueprint(rapoarte_bp, url_prefix='/rapoarte')
    app.register_blueprint(setari_bp, url_prefix='/setari')
    app.register_blueprint(doc_proiecte_bp)
    app.register_blueprint(activitati_bp)
    app.register_blueprint(masini_bp)

    # --------------------------------------------------------
    # CONTEXT PROCESSOR - DATE GLOBALE
    # --------------------------------------------------------
    @app.context_processor
    def inject_global_data():
        alerte_count = 0
        badge_counts = {'pontaje_pending': 0, 'documente_alerta': 0, 'activitati_pending': 0, 'activitati_azi': 0, 'masini_alerta': 0, 'total_alerte': 0}

        if current_user.is_authenticated:
            # Documente expirate + expira curand
            doc_expirate = Document.query.filter(
                Document.data_expirare.isnot(None),
                Document.data_expirare < date.today()
            ).count()
            doc_expira = Document.query.filter(
                Document.data_expirare.isnot(None),
                Document.data_expirare >= date.today(),
                Document.data_expirare <= date.today() + timedelta(days=30)
            ).count()
            badge_counts['documente_alerta'] = doc_expirate + doc_expira

            # Pontaje in asteptare (manager/admin)
            if current_user.is_manager:
                badge_counts['pontaje_pending'] = Pontaj.query.filter_by(status='trimis').count()
                badge_counts['activitati_pending'] = RaportActivitate.query.filter_by(status='trimis').count()

            # Activitati planificate azi (intervalul start..end include data curenta)
            try:
                today_d = date.today()
                badge_counts['activitati_azi'] = RaportActivitate.query.filter(
                    RaportActivitate.status_executie == 'planificata',
                    RaportActivitate.data <= today_d,
                    db.or_(
                        RaportActivitate.data_sfarsit.is_(None),
                        RaportActivitate.data_sfarsit >= today_d,
                    ),
                ).count()
            except Exception:
                badge_counts['activitati_azi'] = 0

        # Zile de nastere VIP (Manager_calitate / Director / Inginer / Sef_santier)
        zile_de_nastere = []
        if current_user.is_authenticated:
            try:
                today_d = date.today()
                FUNCTII_VIP = ['Manager_calitate', 'Director', 'Inginer', 'Sef_santier']
                angajati_vip = Angajat.query.filter(
                    Angajat.functie.in_(FUNCTII_VIP),
                    Angajat.status == 'activ',
                    Angajat.data_nasterii.isnot(None),
                    db.extract('month', Angajat.data_nasterii) == today_d.month,
                    db.extract('day', Angajat.data_nasterii) == today_d.day,
                ).all()
                FUNCTIE_LABELS = {
                    'Manager_calitate': 'Manager Calitate',
                    'Director': 'Director',
                    'Inginer': 'Inginer',
                    'Sef_santier': 'Sef Santier',
                }
                for a in angajati_vip:
                    varsta = None
                    if a.data_nasterii:
                        varsta = today_d.year - a.data_nasterii.year
                    zile_de_nastere.append({
                        'id': a.id,
                        'nume_complet': a.nume_complet,
                        'functie': FUNCTIE_LABELS.get(a.functie, a.functie),
                        'varsta': varsta,
                    })
            except Exception:
                zile_de_nastere = []

            # Alerte masini (documente expirate)
            masini_alerta = 0
            for m in Masina.query.filter(Masina.status.notin_(['casata', 'vanduta'])).all():
                masini_alerta += len(m.alerte_documente)
            badge_counts['masini_alerta'] = masini_alerta

            alerte_count = doc_expirate + masini_alerta + (badge_counts['pontaje_pending'] if current_user.is_manager else 0)
            badge_counts['total_alerte'] = alerte_count

        return {
            'now': datetime.utcnow(),
            'today': date.today(),
            'badge_counts': badge_counts,
            'alerte_count': alerte_count,
            'zile_de_nastere': zile_de_nastere,
            'app_version': '2.0.0'
        }

    # --------------------------------------------------------
    # SECURITY HEADERS
    # --------------------------------------------------------
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    # --------------------------------------------------------
    # ERROR HANDLERS
    # --------------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    # --------------------------------------------------------
    # COMANDA CLI: flask init-db
    # --------------------------------------------------------
    @app.cli.command('init-db')
    @click.option('--demo/--no-demo', default=True, help='Incarca date demo')
    def init_db_command(demo):
        """Creeaza tabelele si optional incarca date demo."""
        db.create_all()
        click.echo('[OK] Tabele create cu succes.')

        if demo:
            _incarca_date_demo()
            click.echo('[OK] Date demo incarcate cu succes.')

        click.echo('[OK] Baza de date initializata!')

    # --------------------------------------------------------
    # COMANDA CLI: flask migrate-activitati
    # Adauga coloanele noi din extensia modulului Activitati
    # --------------------------------------------------------
    @app.cli.command('migrate-activitati')
    def migrate_activitati_command():
        """Adauga coloane noi pe tabelul rapoarte_activitati (idempotent)."""
        from sqlalchemy import inspect, text
        insp = inspect(db.engine)
        if 'rapoarte_activitati' not in insp.get_table_names():
            click.echo('[INFO] Tabelul rapoarte_activitati nu exista. Rulez db.create_all().')
            db.create_all()
            click.echo('[OK] Tabele create.')
            return

        existing_cols = {col['name'] for col in insp.get_columns('rapoarte_activitati')}
        coloane_noi = [
            ('tip_activitate', "VARCHAR(20) NOT NULL DEFAULT 'zilnica'"),
            ('data_sfarsit', 'DATE'),
            ('numar_saptamana', 'INTEGER'),
            ('luna_an', 'VARCHAR(7)'),
            ('supervisor_id', 'INTEGER'),
            ('subordonati_ids', 'TEXT'),
            ('ore_lucrate', 'NUMERIC(5,2)'),
            ('status_executie', "VARCHAR(20) NOT NULL DEFAULT 'planificata'"),
            ('proiecte_ids', 'TEXT'),
            ('include_sambata', 'BOOLEAN NOT NULL DEFAULT 0'),
            ('include_duminica', 'BOOLEAN NOT NULL DEFAULT 0'),
        ]

        adaugate = 0
        with db.engine.begin() as conn:
            for col_name, col_def in coloane_noi:
                if col_name in existing_cols:
                    click.echo(f'[SKIP] Coloana {col_name} exista deja.')
                    continue
                try:
                    conn.execute(text(f'ALTER TABLE rapoarte_activitati ADD COLUMN {col_name} {col_def}'))
                    click.echo(f'[OK] Coloana {col_name} adaugata.')
                    adaugate += 1
                except Exception as e:
                    click.echo(f'[EROARE] La adaugarea coloanei {col_name}: {e}')

            # Permite proiect_id NULL (pentru activitati lunare/saptamanale fara proiect specific)
            # SQLite nu suporta ALTER COLUMN; in PostgreSQL/MySQL se face altfel.
            # Pe SQLite, structura noua se preia la urmatoarea recreare.

        click.echo(f'[FINAL] {adaugate} coloane noi adaugate. Migrare completa.')

    def _incarca_date_demo():
        """Incarca date demonstrative in baza de date."""
        if Utilizator.query.first():
            click.echo('[INFO] Datele demo exista deja. Se omite.')
            return

        # === UTILIZATORI ===
        users_data = [
            ('Popescu', 'Adrian', 'admin@innova.ro', 'admin123', 'admin'),
            ('Ionescu', 'Maria', 'manager@innova.ro', 'manager123', 'manager'),
            ('Popa', 'Gheorghe', 'operator@innova.ro', 'op123', 'operator'),
        ]
        users = []
        for nume, prenume, email, parola, rol in users_data:
            u = Utilizator(nume=nume, prenume=prenume, email=email, rol=rol, activ=True)
            u.set_password(parola)
            db.session.add(u)
            users.append(u)
        db.session.flush()

        # === ANGAJATI ===
        angajati_data = [
            ('Marin', 'Ion', '1850412345678', '0721000001', 'Muncitor', 'nedeterminat',
             3200, 'Zidarie, Tencuiala', date(1985, 4, 12), date(2020, 3, 15)),
            ('Dumitrescu', 'Vasile', '1900815345679', '0722000002', 'Maistru', 'nedeterminat',
             4500, 'Constructii civile', date(1990, 8, 15), date(2019, 6, 1)),
            ('Stan', 'Nicolae', '1880220345680', '0723000003', 'Electrician', 'nedeterminat',
             4000, 'Instalatii electrice, Tablouri electrice', date(1988, 2, 20), date(2021, 1, 10)),
            ('Radu', 'Alexandru', '1920605345681', '0724000004', 'Sudor', 'determinat',
             4200, 'Sudura MIG/MAG, TIG', date(1992, 6, 5), date(2022, 4, 1)),
            ('Constantin', 'Mihai', '1870910345682', '0725000005', 'Macaragiu', 'nedeterminat',
             5000, 'Macara turn, Automacara', date(1987, 9, 10), date(2018, 11, 1)),
            ('Gheorghe', 'Florin', '1951103345683', '0726000006', 'Inginer', 'nedeterminat',
             7500, 'Dirigentie santier, RTE', date(1995, 11, 3), date(2023, 2, 1)),
            ('Tudor', 'Daniel', '1930718345684', '0727000007', 'Conducator_auto', 'nedeterminat',
             3800, 'Cat. C+E, Basculanta', date(1993, 7, 18), date(2021, 8, 15)),
            ('Badea', 'Cristian', '1890225345685', '0728000008', 'Sef_echipa', 'nedeterminat',
             5500, 'Constructii, Finisaje', date(1989, 2, 25), date(2017, 5, 1)),
        ]

        angajati = []
        for (nume, prenume, cnp, tel, functie, tip_contract,
             salariu, spec, data_n, data_a) in angajati_data:
            a = Angajat(
                nume=nume, prenume=prenume, cnp=cnp, telefon=tel,
                email=f'{prenume.lower()}.{nume.lower()}@innova.ro',
                functie=functie, tip_contract=tip_contract,
                salariu_baza=salariu, specializari=spec,
                data_nasterii=data_n, data_angajare=data_a,
                nr_contract=f'CIM-{data_a.year}-{len(angajati)+1:03d}',
                status='activ'
            )
            db.session.add(a)
            angajati.append(a)
        db.session.flush()

        # === PROIECTE ===
        proiecte_data = [
            ('PRJ-2024-001', 'Bloc Rezidential Parcul Verde', 'Constructie bloc P+4E',
             'Bucuresti, Sector 3', 'SC Green Residence SRL',
             date(2024, 1, 15), date(2025, 6, 30), 2500000, 800000, 'activ'),
            ('PRJ-2024-002', 'Hala Industriala Logistic Park', 'Constructie hala metalica 5000mp',
             'Ploiesti, Jud. Prahova', 'Logistic Solutions SA',
             date(2024, 3, 1), date(2024, 12, 31), 1800000, 500000, 'activ'),
            ('PRJ-2024-003', 'Renovare Scoala Nr. 15', 'Renovare completa - termoizolatie, acoperis, instalatii',
             'Pitesti, Jud. Arges', 'Primaria Pitesti',
             date(2024, 6, 1), date(2025, 3, 31), 950000, 350000, 'activ'),
        ]

        proiecte = []
        for (cod, nume, desc, loc, benef, ds, dsp, bt, bm, status) in proiecte_data:
            p = Proiect(
                cod_proiect=cod, nume=nume, descriere=desc,
                locatie=loc, beneficiar=benef,
                data_start=ds, data_sfarsit_planificat=dsp,
                buget_total=bt, buget_manopera=bm,
                status=status, manager_id=users[1].id
            )
            db.session.add(p)
            proiecte.append(p)
        db.session.flush()

        # === ASOCIERI ANGAJAT-PROIECT ===
        for i, ang in enumerate(angajati):
            proiect = proiecte[i % len(proiecte)]
            ap = AngajatProiect(
                angajat_id=ang.id, proiect_id=proiect.id,
                data_start=proiect.data_start,
                functie_pe_proiect=ang.functie,
                tarif_negociat=round(ang.tarif_orar * 1.1, 2) if ang.salariu_baza else None
            )
            db.session.add(ap)
        db.session.flush()

        # === PONTAJE - ultimele 45 de zile ===
        today = date.today()
        for day_offset in range(45, 0, -1):
            zi = today - timedelta(days=day_offset)
            day_of_week = zi.weekday()
            if day_of_week >= 5:
                continue
            for ang in angajati:
                proiect = proiecte[angajati.index(ang) % len(proiecte)]
                status_pontaj = choice(['aprobat', 'aprobat', 'aprobat', 'trimis'])
                ora_start_h = choice([6, 7, 7, 8])
                durata = choice([8, 8, 8, 9, 10])
                ora_sf_h = ora_start_h + durata

                pontaj = Pontaj(
                    angajat_id=ang.id, proiect_id=proiect.id,
                    data=zi,
                    ora_start=f'{ora_start_h:02d}:00',
                    ora_sfarsit=f'{ora_sf_h:02d}:00',
                    tip_zi='lucratoare', status=status_pontaj,
                    introdus_de=users[2].id
                )
                pontaj.calculeaza_ore()
                if status_pontaj == 'aprobat':
                    pontaj.aprobat_de = users[1].id
                    pontaj.data_aprobare = datetime.utcnow()
                db.session.add(pontaj)

        # === DOCUMENTE ===
        tipuri_doc = ['BI_CI', 'contract_munca', 'instructaj_SSM', 'fisa_aptitudini',
                      'certificat_calificare']
        for ang in angajati:
            for tip in tipuri_doc[:3]:
                expirare = today + timedelta(days=randint(-30, 365))
                doc = Document(
                    angajat_id=ang.id, tip=tip,
                    nume_document=f'{tip}_{ang.nume}_{ang.prenume}.pdf',
                    data_emitere=today - timedelta(days=randint(30, 730)),
                    data_expirare=expirare,
                    emitent='HR Department',
                    status='valabil' if expirare > today else 'expirat',
                    incarcat_de=users[0].id
                )
                db.session.add(doc)

        # === CONCEDII ===
        concedii_data = [
            (angajati[0].id, 'CO', today + timedelta(days=10), today + timedelta(days=20), 10, 'aprobat'),
            (angajati[2].id, 'CM', today - timedelta(days=5), today + timedelta(days=2), 7, 'aprobat'),
            (angajati[4].id, 'CO', today + timedelta(days=30), today + timedelta(days=40), 10, 'cerut'),
        ]
        for ang_id, tip, ds, dsf, nr, st in concedii_data:
            c = Concediu(
                angajat_id=ang_id, tip=tip,
                data_start=ds, data_sfarsit=dsf,
                nr_zile=nr, status=st,
                aprobat_de=users[1].id if st == 'aprobat' else None
            )
            db.session.add(c)

        # === SARBATORI LEGALE 2024-2025 ===
        sarbatori = [
            (date(2024, 1, 1), 'Anul Nou', 2024),
            (date(2024, 1, 2), 'Anul Nou (ziua 2)', 2024),
            (date(2024, 1, 24), 'Ziua Unirii Principatelor', 2024),
            (date(2024, 5, 1), 'Ziua Muncii', 2024),
            (date(2024, 5, 3), 'Vinerea Mare (Ortodoxa)', 2024),
            (date(2024, 5, 5), 'Pastele Ortodox', 2024),
            (date(2024, 5, 6), 'Pastele Ortodox (ziua 2)', 2024),
            (date(2024, 6, 1), 'Ziua Copilului', 2024),
            (date(2024, 6, 23), 'Rusaliile', 2024),
            (date(2024, 6, 24), 'Rusaliile (ziua 2)', 2024),
            (date(2024, 8, 15), 'Adormirea Maicii Domnului', 2024),
            (date(2024, 11, 30), 'Sfantul Andrei', 2024),
            (date(2024, 12, 1), 'Ziua Nationala a Romaniei', 2024),
            (date(2024, 12, 25), 'Craciunul', 2024),
            (date(2024, 12, 26), 'Craciunul (ziua 2)', 2024),
            (date(2025, 1, 1), 'Anul Nou', 2025),
            (date(2025, 1, 2), 'Anul Nou (ziua 2)', 2025),
            (date(2025, 1, 24), 'Ziua Unirii Principatelor', 2025),
            (date(2025, 4, 18), 'Vinerea Mare (Ortodoxa)', 2025),
            (date(2025, 4, 20), 'Pastele Ortodox', 2025),
            (date(2025, 4, 21), 'Pastele Ortodox (ziua 2)', 2025),
            (date(2025, 5, 1), 'Ziua Muncii', 2025),
            (date(2025, 6, 1), 'Ziua Copilului', 2025),
            (date(2025, 6, 8), 'Rusaliile', 2025),
            (date(2025, 6, 9), 'Rusaliile (ziua 2)', 2025),
            (date(2025, 8, 15), 'Adormirea Maicii Domnului', 2025),
            (date(2025, 11, 30), 'Sfantul Andrei', 2025),
            (date(2025, 12, 1), 'Ziua Nationala a Romaniei', 2025),
            (date(2025, 12, 25), 'Craciunul', 2025),
            (date(2025, 12, 26), 'Craciunul (ziua 2)', 2025),
        ]
        for data_s, den, an in sarbatori:
            s = SarbatoareLegala(data=data_s, denumire=den, an=an)
            db.session.add(s)

        # === TIPURI INSTALATII & TIPURI DOCUMENTE PROIECT ===
        _incarca_tipuri_instalatii()

        # === CATEGORII ACTIVITATI ===
        _incarca_categorii_activitati()

        db.session.commit()
        click.echo(f'  - {len(users)} utilizatori creati')
        click.echo(f'  - {len(angajati)} angajati creati')
        click.echo(f'  - {len(proiecte)} proiecte create')
        click.echo(f'  - Pontaje generate pentru 45 zile')
        click.echo(f'  - Documente, concedii si sarbatori incarcate')
        click.echo(f'  - Tipuri instalatii si tipuri documente proiect incarcate')
        click.echo(f'  - Categorii activitati incarcate')

    # --------------------------------------------------------
    # COMANDA CLI: flask seed-instalatii
    # --------------------------------------------------------
    @app.cli.command('seed-instalatii')
    def seed_instalatii_command():
        """Incarca tipurile de instalatii, documente proiect si categorii activitati."""
        _incarca_tipuri_instalatii()
        _incarca_categorii_activitati()
        click.echo('[OK] Tipuri instalatii, documente proiect si categorii activitati incarcate!')

    return app


def _incarca_tipuri_instalatii():
    """Incarca seed data pentru tipuri instalatii si tipuri documente proiect."""
    if TipInstalatie.query.first():
        return  # Exista deja

    instalatii_data = [
        {
            'cod': 'HVAC', 'denumire': 'Instalatii HVAC (Climatizare-Ventilare)',
            'descriere': 'Sisteme de incalzire, ventilare si aer conditionat',
            'culoare_hex': '#1565C0', 'icon_css': 'fa-wind', 'ordine': 1,
            'documente': [
                ('HVAC-PT', 'Proiect tehnic HVAC', True, 'proiectare'),
                ('HVAC-BRV', 'Breviar calcule termice', True, 'proiectare'),
                ('HVAC-SCH', 'Schema de principiu ventilatie', False, 'proiectare'),
                ('HVAC-PLN', 'Planuri montaj AHU', False, 'proiectare'),
                ('HVAC-FT', 'Fise tehnice echipamente', True, 'executie'),
                ('HVAC-CE', 'Certificate CE echipamente', True, 'executie'),
                ('HVAC-PP', 'Proces verbal probe presiune conducte', True, 'executie'),
                ('HVAC-PF', 'Proces verbal punere in functiune', True, 'receptie'),
                ('HVAC-BAL', 'Raport balansare aer', False, 'receptie'),
                ('HVAC-CT', 'Cartea tehnica instalatie', True, 'receptie'),
            ]
        },
        {
            'cod': 'ELEC', 'denumire': 'Instalatii Electrice',
            'descriere': 'Instalatii electrice de forta si iluminat',
            'culoare_hex': '#F9A825', 'icon_css': 'fa-bolt', 'ordine': 2,
            'documente': [
                ('ELEC-PT', 'Proiect tehnic electric', True, 'proiectare'),
                ('ELEC-MON', 'Schema monofilara', True, 'proiectare'),
                ('ELEC-PLN', 'Planuri instalatii electrice', False, 'proiectare'),
                ('ELEC-SC', 'Calcul scurtcircuit', False, 'proiectare'),
                ('ELEC-CTB', 'Certificate conformitate tablouri electrice', True, 'executie'),
                ('ELEC-PRAM', 'Buletin verificare instalatie (PRAM)', True, 'executie'),
                ('ELEC-PV', 'Proces verbal receptie instalatie electrica', True, 'receptie'),
                ('ELEC-ANRE', 'Autorizatie ANRE', True, 'receptie'),
                ('ELEC-AVIZ', 'Aviz distribuitor energie', False, 'receptie'),
            ]
        },
        {
            'cod': 'SAN', 'denumire': 'Instalatii Sanitare si Termice',
            'descriere': 'Instalatii de alimentare cu apa, canalizare si termice',
            'culoare_hex': '#00838F', 'icon_css': 'fa-faucet', 'ordine': 3,
            'documente': [
                ('SAN-PT', 'Proiect tehnic sanitare', True, 'proiectare'),
                ('SAN-BRV', 'Breviar calcule hidraulice', False, 'proiectare'),
                ('SAN-PLN', 'Planuri instalatii sanitare', False, 'proiectare'),
                ('SAN-COL', 'Schema coloane', False, 'proiectare'),
                ('SAN-PP', 'Probe presiune instalatie sanitara (PV)', True, 'executie'),
                ('SAN-CRT', 'Certificate materiale (tevi, fitinguri)', True, 'executie'),
                ('SAN-PFT', 'Punere in functiune instalatie termica', True, 'receptie'),
                ('SAN-ISCIR', 'Certificat ISCIR centrala termica', False, 'receptie'),
            ]
        },
        {
            'cod': 'GM', 'denumire': 'Instalatii Gaze Medicale',
            'descriere': 'Retele de distributie gaze medicale',
            'culoare_hex': '#6A1B9A', 'icon_css': 'fa-lungs', 'ordine': 4,
            'documente': [
                ('GM-PT', 'Proiect gaze medicale (avizat MS)', True, 'proiectare'),
                ('GM-PLN', 'Planuri retele gaze medicale', False, 'proiectare'),
                ('GM-CE', 'Certificate conformitate echipamente (presiune)', True, 'executie'),
                ('GM-PE', 'Probe etanseitate retele (PV)', True, 'executie'),
                ('GM-AUT', 'Autorizatie functionare instalatie gaze medicale', True, 'receptie'),
                ('GM-RAP', 'Raport analiza calitate gaze medicale', False, 'receptie'),
                ('GM-PV', 'Proces verbal receptie (cu reprezentant MS)', True, 'receptie'),
            ]
        },
        {
            'cod': 'INFRA', 'denumire': 'Infrastructura si Structura',
            'descriere': 'Fundatii, structura de rezistenta, infrastructura',
            'culoare_hex': '#4E342E', 'icon_css': 'fa-building', 'ordine': 5,
            'documente': [
                ('INFRA-GEO', 'Studiu geotehnic', True, 'proiectare'),
                ('INFRA-STR', 'Proiect structura', True, 'proiectare'),
                ('INFRA-AC', 'Autorizatie de construire', True, 'proiectare'),
                ('INFRA-PCC', 'Plan calitate (PCC)', True, 'executie'),
                ('INFRA-PVF', 'Program verificari faze', True, 'executie'),
                ('INFRA-PVFD', 'Procese verbale faze determinante (PVFD)', True, 'executie'),
                ('INFRA-INC', 'Rapoarte de incercare materiale (beton, otel)', True, 'executie'),
                ('INFRA-CC', 'Cartea constructiei', True, 'receptie'),
                ('INFRA-REC', 'Proces verbal receptie finala', True, 'receptie'),
            ]
        },
        {
            'cod': 'PROT', 'denumire': 'Protectie la Incendiu',
            'descriere': 'Sisteme de protectie si prevenire incendii',
            'culoare_hex': '#B71C1C', 'icon_css': 'fa-fire-extinguisher', 'ordine': 6,
            'documente': [
                ('PROT-SSI', 'Scenariu de securitate la incendiu', True, 'proiectare'),
                ('PROT-PT', 'Proiect tehnic PSI', True, 'proiectare'),
                ('PROT-CRT', 'Certificate detectoare, sprinklere', True, 'executie'),
                ('PROT-PV', 'Proces verbal receptie instalatie PSI', True, 'receptie'),
            ]
        },
        {
            'cod': 'AUTO', 'denumire': 'Automatizari si BMS',
            'descriere': 'Sisteme de automatizare, BMS, SCADA',
            'culoare_hex': '#37474F', 'icon_css': 'fa-microchip', 'ordine': 7,
            'documente': [
                ('AUTO-PT', 'Proiect tehnic automatizari', True, 'proiectare'),
                ('AUTO-SCH', 'Schema logica de functionare', False, 'proiectare'),
                ('AUTO-PLC', 'Program PLC / DDC', False, 'executie'),
                ('AUTO-TEST', 'Raport teste functionare BMS', True, 'receptie'),
                ('AUTO-INST', 'Manual operare si intretinere', False, 'receptie'),
            ]
        },
        {
            'cod': 'ALTA', 'denumire': 'Alte Documente',
            'descriere': 'Documente diverse, corespondenta, procese verbale generale',
            'culoare_hex': '#546E7A', 'icon_css': 'fa-file', 'ordine': 8,
            'documente': [
                ('ALTA-PV', 'Proces verbal general', False, 'executie'),
                ('ALTA-CORE', 'Corespondenta proiect', False, 'executie'),
                ('ALTA-DIV', 'Document divers', False, 'executie'),
            ]
        },
    ]

    for inst_data in instalatii_data:
        tip = TipInstalatie(
            cod=inst_data['cod'],
            denumire=inst_data['denumire'],
            descriere=inst_data['descriere'],
            culoare_hex=inst_data['culoare_hex'],
            icon_css=inst_data['icon_css'],
            ordine=inst_data['ordine'],
            activ=True
        )
        db.session.add(tip)
        db.session.flush()

        for idx, (cod, denumire, obligatoriu, etapa) in enumerate(inst_data['documente']):
            td = TipDocumentProiect(
                tip_instalatie_id=tip.id,
                cod=cod,
                denumire=denumire,
                obligatoriu=obligatoriu,
                ordine=idx + 1,
                descriere=f'Etapa: {etapa}'
            )
            db.session.add(td)

    db.session.commit()
    print(f"  [OK] Seed: {TipInstalatie.query.count()} tipuri instalatii, {TipDocumentProiect.query.count()} tipuri documente")


def _incarca_categorii_activitati():
    """Incarca seed data pentru categorii activitati."""
    if CategorieActivitate.query.first():
        return  # Exista deja

    # Mapare cod instalatie -> categorii
    categorii_data = {
        'HVAC': [
            ('Trasare trasee ventilatie', 'ml'),
            ('Montaj canale ventilatie rectangulare', 'ml'),
            ('Montaj canale ventilatie circulare', 'ml'),
            ('Montaj grile/difuzoare', 'buc'),
            ('Montaj unitate de tratare aer (AHU)', 'buc'),
            ('Montaj ventiloconvectoare', 'buc'),
            ('Montaj pompe de caldura', 'buc'),
            ('Izolatie canale ventilatie', 'mp'),
            ('Probe si reglaj instalatie HVAC', None),
            ('Balansare debimat aer', None),
        ],
        'ELEC': [
            ('Trasare trasee electrice', 'ml'),
            ('Montaj jgheaburi/tuburi', 'ml'),
            ('Tragere cabluri', 'ml'),
            ('Montaj tablouri electrice', 'buc'),
            ('Conexiuni tablouri', 'buc'),
            ('Montaj prize/intrerupatoare', 'buc'),
            ('Montaj corpuri iluminat', 'buc'),
            ('Montaj UPS/grup electrogen', 'buc'),
            ('Verificari si masuratori', None),
            ('Punere in functiune instalatie electrica', None),
        ],
        'SAN': [
            ('Trasare trasee sanitare', 'ml'),
            ('Montaj conducte PPR/cupru/inox', 'ml'),
            ('Sudura conducte', 'buc'),
            ('Montaj armaturi (robineti, vane)', 'buc'),
            ('Montaj obiecte sanitare', 'buc'),
            ('Montaj centrale termice/boilere', 'buc'),
            ('Izolatie conducte', 'ml'),
            ('Probe presiune', None),
            ('Spalare si dezinfectie retea', None),
            ('Punere in functiune', None),
        ],
        'GM': [
            ('Trasare retele gaze medicale', 'ml'),
            ('Montaj conducte cupru gaze medicale', 'ml'),
            ('Sudura conducte gaze medicale (brasaj)', 'buc'),
            ('Montaj prize medicale', 'buc'),
            ('Montaj panouri gaze medicale', 'buc'),
            ('Probe etanseitate', None),
            ('Verificare calitate gaze medicale', None),
            ('Marcare si etichetare retele', 'ml'),
        ],
        'INFRA': [
            ('Sapatura manuala/mecanica', 'mc'),
            ('Turnare beton', 'mc'),
            ('Cofrare/decofrare', 'mp'),
            ('Montaj armaturi (fier-beton)', 'kg'),
            ('Zidarie caramida/BCA', 'mp'),
            ('Tencuieli', 'mp'),
            ('Sapa', 'mp'),
            ('Termoizolatii', 'mp'),
            ('Hidroizolatii', 'mp'),
            ('Finisaje', 'mp'),
        ],
        None: [  # Universale
            ('Receptie si depozitare materiale', None),
            ('Pregatire front de lucru', None),
            ('Curatenie si organizare santier', None),
            ('Instructaj SSM', None),
            ('Participare sedinta de coordonare', None),
            ('Deplasare la/de la santier', None),
            ('Documentatie tehnica (schite, masuratori)', None),
        ],
    }

    ordine = 1
    for inst_cod, cats in categorii_data.items():
        tip_inst_id = None
        if inst_cod:
            tip_inst = TipInstalatie.query.filter_by(cod=inst_cod).first()
            if tip_inst:
                tip_inst_id = tip_inst.id

        for denumire, um in cats:
            cat = CategorieActivitate(
                denumire=denumire,
                tip_instalatie_id=tip_inst_id,
                unitate_masura_default=um,
                activa=True,
                ordine=ordine
            )
            db.session.add(cat)
            ordine += 1

    db.session.commit()
    print(f"  [OK] Seed: {CategorieActivitate.query.count()} categorii activitati")


# ============================================================
# PORNIRE APLICATIE
# ============================================================

app = create_app('default')

if __name__ == '__main__':
    print("\n" + "=" * 55)
    print("  INNOVA WORKFORCE v2.0 - Management Forta de Munca")
    print("  Server: http://localhost:5001")
    print("  Cont admin: admin@innova.ro / admin123")
    print("=" * 55 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5001)
