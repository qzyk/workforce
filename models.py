"""
EDIFICO WORKFORCE - Modele SQLAlchemy
Toate modelele bazei de date pentru managementul fortei de munca in constructii.
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ============================================================
# MODEL TENANT (multi-tenant infrastructure)
# Initial: NULL pe randuri existente (single-tenant mode default).
# Cand multi-tenant e activat, fiecare org are tenant_id unic.
# ============================================================

class Tenant(db.Model):
    __tablename__ = 'tenants'
    id = db.Column(db.Integer, primary_key=True)
    cod = db.Column(db.String(50), unique=True, nullable=False)  # ex: 'edifico', 'beta-srl'
    nume = db.Column(db.String(200), nullable=False)
    activ = db.Column(db.Boolean, default=True, nullable=False)
    config_json = db.Column(db.Text, nullable=True)  # setari per-tenant in JSON
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Tenant {self.cod}>'


# ============================================================
# TABEL ASOCIATIV ANGAJAT-PROIECT (many-to-many)
# ============================================================

class AngajatProiect(db.Model):
    __tablename__ = 'angajat_proiect'
    id = db.Column(db.Integer, primary_key=True)
    angajat_id = db.Column(db.Integer, db.ForeignKey('angajati.id'), nullable=False)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=False)
    data_start = db.Column(db.Date, nullable=False, default=date.today)
    data_sfarsit = db.Column(db.Date)
    functie_pe_proiect = db.Column(db.String(100))
    tarif_negociat = db.Column(db.Numeric(10, 2))

    angajat = db.relationship('Angajat', backref=db.backref('asocieri_proiecte', lazy='dynamic'))
    proiect = db.relationship('Proiect', backref=db.backref('asocieri_angajati', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('angajat_id', 'proiect_id', 'data_start', name='uix_angajat_proiect_data'),
    )


# ============================================================
# MODEL UTILIZATOR
# ============================================================

class Utilizator(UserMixin, db.Model):
    __tablename__ = 'utilizatori'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    nume = db.Column(db.String(100), nullable=False)
    prenume = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    parola_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='operator')  # admin, manager, operator
    activ = db.Column(db.Boolean, default=True)
    limba = db.Column(db.String(5), nullable=True, default='ro')  # ro, en (i18n)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_conectare = db.Column(db.DateTime)

    def set_password(self, parola):
        self.parola_hash = generate_password_hash(parola)

    def check_password(self, parola):
        return check_password_hash(self.parola_hash, parola)

    def get_full_name(self):
        return f"{self.nume} {self.prenume}"

    @property
    def is_admin(self):
        return self.rol == 'admin'

    @property
    def is_manager(self):
        return self.rol in ('admin', 'manager')

    def __repr__(self):
        return f'<Utilizator {self.email}>'


# ============================================================
# MODEL ANGAJAT
# ============================================================

class Angajat(db.Model):
    __tablename__ = 'angajati'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    nume = db.Column(db.String(100), nullable=False)
    prenume = db.Column(db.String(100), nullable=False)
    cnp = db.Column(db.String(13), unique=True)
    telefon = db.Column(db.String(20))
    email = db.Column(db.String(150))
    adresa = db.Column(db.Text)

    # Functie - enum
    functie = db.Column(db.String(50), nullable=False, default='Muncitor')
    # Muncitor, Maistru, Sef_echipa, Inginer, Tehnician,
    # Conducator_auto, Macaragiu, Sudor, Electrician, Alte
    specializari = db.Column(db.Text)  # separate prin virgula

    data_nasterii = db.Column(db.Date)
    data_angajare = db.Column(db.Date, nullable=False)
    data_incetare = db.Column(db.Date)

    tip_contract = db.Column(db.String(30), default='nedeterminat')
    # determinat, nedeterminat, zilier
    salariu_baza = db.Column(db.Numeric(10, 2))
    nr_contract = db.Column(db.String(50))
    serie_bi = db.Column(db.String(10))
    nr_bi = db.Column(db.String(10))

    status = db.Column(db.String(20), default='activ')  # activ, inactiv, suspendat
    poza_profil = db.Column(db.String(255))
    observatii = db.Column(db.Text)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_actualizare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relatii
    pontaje = db.relationship('Pontaj', backref='angajat', lazy='dynamic')
    documente = db.relationship('Document', backref='angajat', lazy='dynamic')
    concedii = db.relationship('Concediu', backref='angajat', lazy='dynamic')

    FUNCTII = [
        ('Muncitor', 'Muncitor'),
        ('Maistru', 'Maistru'),
        ('Sef_echipa', 'Sef echipa'),
        ('Sef_santier', 'Sef santier'),
        ('Inginer', 'Inginer'),
        ('Tehnician', 'Tehnician'),
        ('Manager_calitate', 'Manager Calitate'),
        ('Director', 'Director'),
        ('Conducator_auto', 'Conducator auto'),
        ('Macaragiu', 'Macaragiu'),
        ('Sudor', 'Sudor'),
        ('Electrician', 'Electrician'),
        ('Alte', 'Alte functii'),
    ]

    @property
    def nume_complet(self):
        return f"{self.nume} {self.prenume}"

    @property
    def tarif_orar(self):
        if self.salariu_baza:
            return round(float(self.salariu_baza) / 168, 2)  # 21 zile * 8 ore
        return 0

    @property
    def varsta(self):
        if self.data_nasterii:
            today = date.today()
            return today.year - self.data_nasterii.year - (
                (today.month, today.day) < (self.data_nasterii.month, self.data_nasterii.day)
            )
        return None

    def get_proiecte_active(self):
        return AngajatProiect.query.filter(
            AngajatProiect.angajat_id == self.id,
            AngajatProiect.data_sfarsit.is_(None) | (AngajatProiect.data_sfarsit >= date.today())
        ).all()

    def __repr__(self):
        return f'<Angajat {self.nume_complet}>'


# ============================================================
# MODEL PROIECT
# ============================================================

class Proiect(db.Model):
    __tablename__ = 'proiecte'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    cod_proiect = db.Column(db.String(50), unique=True, nullable=False)
    nume = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)
    locatie = db.Column(db.String(200))
    adresa_santier = db.Column(db.String(300))
    beneficiar = db.Column(db.String(200))
    nr_contract_beneficiar = db.Column(db.String(100))

    data_start = db.Column(db.Date, nullable=False)
    data_sfarsit_planificat = db.Column(db.Date)
    data_sfarsit_real = db.Column(db.Date)

    buget_total = db.Column(db.Numeric(12, 2))
    buget_manopera = db.Column(db.Numeric(12, 2))

    status = db.Column(db.String(20), default='planificat')
    # planificat, activ, suspendat, finalizat, anulat
    manager_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_actualizare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relatii
    manager = db.relationship('Utilizator', backref='proiecte_gestionate')
    pontaje = db.relationship('Pontaj', backref='proiect', lazy='dynamic')

    STATUSURI = [
        ('planificat', 'Planificat'),
        ('activ', 'Activ'),
        ('suspendat', 'Suspendat'),
        ('finalizat', 'Finalizat'),
        ('anulat', 'Anulat'),
    ]

    @property
    def progres(self):
        if self.data_start and self.data_sfarsit_planificat:
            total_days = (self.data_sfarsit_planificat - self.data_start).days
            if total_days <= 0:
                return 100
            elapsed = (date.today() - self.data_start).days
            return min(100, max(0, int(elapsed / total_days * 100)))
        return 0

    @property
    def zile_ramase(self):
        if self.data_sfarsit_planificat:
            delta = (self.data_sfarsit_planificat - date.today()).days
            return max(0, delta)
        return None

    def get_angajati_activi(self):
        return AngajatProiect.query.filter(
            AngajatProiect.proiect_id == self.id,
            AngajatProiect.data_sfarsit.is_(None) | (AngajatProiect.data_sfarsit >= date.today())
        ).all()

    def get_total_ore(self):
        result = db.session.query(db.func.sum(Pontaj.ore_lucrate)).filter(
            Pontaj.proiect_id == self.id
        ).scalar()
        return float(result) if result else 0

    def __repr__(self):
        return f'<Proiect {self.cod_proiect}>'


# ============================================================
# MODEL PONTAJ
# ============================================================

class Pontaj(db.Model):
    __tablename__ = 'pontaje'
    id = db.Column(db.Integer, primary_key=True)
    angajat_id = db.Column(db.Integer, db.ForeignKey('angajati.id'), nullable=False)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=False)
    # Linkare BIM (optional)
    element_bim_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'), nullable=True, index=True)
    spatiu_id = db.Column(db.Integer, db.ForeignKey('bim_spatii.id'), nullable=True, index=True)
    data = db.Column(db.Date, nullable=False)
    ora_start = db.Column(db.String(5))   # HH:MM
    ora_sfarsit = db.Column(db.String(5))  # HH:MM

    ore_lucrate = db.Column(db.Numeric(5, 2), default=0)
    ore_normale = db.Column(db.Numeric(5, 2), default=0)         # max 8
    ore_suplimentare_50 = db.Column(db.Numeric(5, 2), default=0)  # ore suplim. 50%
    ore_suplimentare_100 = db.Column(db.Numeric(5, 2), default=0) # ore suplim. 100%

    tip_zi = db.Column(db.String(30), default='lucratoare')
    # lucratoare, sambata, duminica, sarbatoare_legala, co, cm, invoiere
    status = db.Column(db.String(20), default='draft')
    # draft, trimis, aprobat, respins

    aprobat_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    data_aprobare = db.Column(db.DateTime)
    observatii = db.Column(db.Text)
    motiv_respingere = db.Column(db.Text)

    introdus_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    data_introducere = db.Column(db.DateTime, default=datetime.utcnow)

    aprobator = db.relationship('Utilizator', foreign_keys=[aprobat_de], backref='pontaje_aprobate')
    operator = db.relationship('Utilizator', foreign_keys=[introdus_de], backref='pontaje_introduse')
    # Relatii BIM (link optional spre element/spatiu)
    element_bim = db.relationship('ElementBIM', foreign_keys=[element_bim_id],
                                  backref=db.backref('pontaje', lazy='dynamic'))
    spatiu = db.relationship('Spatiu', foreign_keys=[spatiu_id],
                             backref=db.backref('pontaje', lazy='dynamic'))

    TIPURI_ZI = [
        ('lucratoare', 'Lucratoare'),
        ('sambata', 'Sambata'),
        ('duminica', 'Duminica'),
        ('sarbatoare_legala', 'Sarbatoare legala'),
        ('co', 'Concediu odihna'),
        ('cm', 'Concediu medical'),
        ('invoiere', 'Invoiere'),
    ]

    STATUSURI = [
        ('draft', 'Draft'),
        ('trimis', 'Trimis'),
        ('aprobat', 'Aprobat'),
        ('respins', 'Respins'),
    ]

    __table_args__ = (
        db.UniqueConstraint('angajat_id', 'data', name='uix_pontaj_angajat_data'),
    )

    def calculeaza_ore(self):
        """Calculeaza automat orele lucrate din ora_start si ora_sfarsit."""
        if self.ora_start and self.ora_sfarsit:
            h1, m1 = map(int, self.ora_start.split(':'))
            h2, m2 = map(int, self.ora_sfarsit.split(':'))
            total_min = h2 * 60 + m2 - h1 * 60 - m1
            if total_min < 0:
                total_min += 24 * 60  # tura de noapte
            self.ore_lucrate = round(total_min / 60, 2)
            self.ore_normale = min(8, self.ore_lucrate)
            extra = max(0, float(self.ore_lucrate) - 8)
            if self.tip_zi in ('sambata', 'duminica', 'sarbatoare_legala'):
                self.ore_suplimentare_100 = round(extra, 2)
                self.ore_suplimentare_50 = 0
            else:
                self.ore_suplimentare_50 = round(extra, 2)
                self.ore_suplimentare_100 = 0

    def __repr__(self):
        return f'<Pontaj {self.angajat_id} {self.data}>'


# ============================================================
# MODEL DOCUMENT
# ============================================================

class Document(db.Model):
    __tablename__ = 'documente'
    id = db.Column(db.Integer, primary_key=True)
    angajat_id = db.Column(db.Integer, db.ForeignKey('angajati.id'), nullable=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=True)

    tip = db.Column(db.String(50), nullable=False)
    # BI_CI, contract_munca, act_aditional, adeverinta_medicala,
    # certificat_calificare, autorizatie_ISCIR, permis_inaltime,
    # instructaj_SSM, fisa_aptitudini, alte
    nume_document = db.Column(db.String(255), nullable=False)
    fisier_path = db.Column(db.String(500))
    marime_fisier = db.Column(db.Integer)  # bytes

    data_emitere = db.Column(db.Date)
    data_expirare = db.Column(db.Date)
    emitent = db.Column(db.String(200))
    serie_numar = db.Column(db.String(100))

    status = db.Column(db.String(20), default='valabil')  # valabil, expirat, in_curand
    data_upload = db.Column(db.DateTime, default=datetime.utcnow)
    incarcat_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    observatii = db.Column(db.Text)

    proiect = db.relationship('Proiect', backref='documente')
    uploader = db.relationship('Utilizator', backref='documente_incarcate')

    TIPURI = [
        ('BI_CI', 'Buletin / Carte de identitate'),
        ('contract_munca', 'Contract de munca'),
        ('act_aditional', 'Act aditional'),
        ('adeverinta_medicala', 'Adeverinta medicala'),
        ('certificat_calificare', 'Certificat calificare'),
        ('autorizatie_ISCIR', 'Autorizatie ISCIR'),
        ('permis_inaltime', 'Permis lucru la inaltime'),
        ('instructaj_SSM', 'Instructaj SSM'),
        ('fisa_aptitudini', 'Fisa de aptitudini'),
        ('alte', 'Alte documente'),
    ]

    @property
    def status_calculat(self):
        if self.data_expirare:
            if self.data_expirare < date.today():
                return 'expirat'
            elif self.data_expirare < date.today() + timedelta(days=30):
                return 'in_curand'
        return 'valabil'

    @property
    def marime_formatata(self):
        if self.marime_fisier:
            if self.marime_fisier < 1024:
                return f"{self.marime_fisier} B"
            elif self.marime_fisier < 1024 * 1024:
                return f"{self.marime_fisier / 1024:.1f} KB"
            else:
                return f"{self.marime_fisier / (1024*1024):.1f} MB"
        return '-'

    def __repr__(self):
        return f'<Document {self.nume_document}>'


# ============================================================
# MODEL RAPORT
# ============================================================

class Raport(db.Model):
    __tablename__ = 'rapoarte'
    id = db.Column(db.Integer, primary_key=True)
    tip_raport = db.Column(db.String(50), nullable=False)
    titlu = db.Column(db.String(200), nullable=False)
    parametri = db.Column(db.Text)  # JSON
    fisier_path = db.Column(db.String(500))
    format = db.Column(db.String(10), default='xlsx')  # xlsx, pdf
    data_generare = db.Column(db.DateTime, default=datetime.utcnow)
    generat_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    dimensiune_fisier = db.Column(db.Integer)

    generator = db.relationship('Utilizator', backref='rapoarte_generate')

    TIPURI = [
        ('pontaj_lunar', 'Pontaj lunar'),
        ('situatie_angajati', 'Situatie angajati'),
        ('situatie_proiect', 'Situatie proiect'),
        ('documente_expirate', 'Documente expirate'),
        ('ore_suplimentare', 'Ore suplimentare'),
        ('concedii', 'Situatie concedii'),
    ]

    def __repr__(self):
        return f'<Raport {self.titlu}>'


# ============================================================
# MODEL CONCEDIU
# ============================================================

class Concediu(db.Model):
    __tablename__ = 'concedii'
    id = db.Column(db.Integer, primary_key=True)
    angajat_id = db.Column(db.Integer, db.ForeignKey('angajati.id'), nullable=False)
    tip = db.Column(db.String(30), nullable=False)
    # CO, CM, fara_plata, maternitate, paternitate
    data_start = db.Column(db.Date, nullable=False)
    data_sfarsit = db.Column(db.Date, nullable=False)
    nr_zile = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='cerut')
    # cerut, aprobat, respins
    aprobat_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    aprobator = db.relationship('Utilizator', backref='concedii_aprobate')

    TIPURI = [
        ('CO', 'Concediu de odihna'),
        ('CM', 'Concediu medical'),
        ('fara_plata', 'Concediu fara plata'),
        ('maternitate', 'Concediu maternitate'),
        ('paternitate', 'Concediu paternitate'),
    ]

    STATUSURI = [
        ('cerut', 'Cerut'),
        ('aprobat', 'Aprobat'),
        ('respins', 'Respins'),
    ]

    def __repr__(self):
        return f'<Concediu {self.angajat_id} {self.tip}>'


# ============================================================
# MODEL SARBATOARE LEGALA
# ============================================================

class SarbatoareLegala(db.Model):
    __tablename__ = 'sarbatori_legale'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    denumire = db.Column(db.String(200), nullable=False)
    an = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('data', name='uix_sarbatoare_data'),
    )

    def __repr__(self):
        return f'<Sarbatoare {self.denumire} {self.data}>'


# ============================================================
# MODEL TIP INSTALATIE
# ============================================================

class TipInstalatie(db.Model):
    __tablename__ = 'tipuri_instalatii'
    id = db.Column(db.Integer, primary_key=True)
    cod = db.Column(db.String(20), unique=True, nullable=False)
    denumire = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)
    culoare_hex = db.Column(db.String(7), default='#546E7A')
    icon_css = db.Column(db.String(50), default='fa-file')
    activ = db.Column(db.Boolean, default=True)
    ordine = db.Column(db.Integer, default=0)

    # Relatii
    tipuri_documente = db.relationship('TipDocumentProiect', backref='tip_instalatie',
                                       lazy='dynamic', order_by='TipDocumentProiect.ordine')
    documente_proiect = db.relationship('DocumentProiect', backref='tip_instalatie', lazy='dynamic')

    def __repr__(self):
        return f'<TipInstalatie {self.cod}>'


# ============================================================
# MODEL TIP DOCUMENT PROIECT
# ============================================================

class TipDocumentProiect(db.Model):
    __tablename__ = 'tipuri_documente_proiect'
    id = db.Column(db.Integer, primary_key=True)
    tip_instalatie_id = db.Column(db.Integer, db.ForeignKey('tipuri_instalatii.id'), nullable=False)
    cod = db.Column(db.String(50), nullable=False)
    denumire = db.Column(db.String(300), nullable=False)
    descriere = db.Column(db.Text)
    obligatoriu = db.Column(db.Boolean, default=False)
    exemple = db.Column(db.Text)
    ordine = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint('tip_instalatie_id', 'cod', name='uix_tip_doc_inst_cod'),
    )

    def __repr__(self):
        return f'<TipDocumentProiect {self.cod}>'


# ============================================================
# MODEL DOCUMENT PROIECT
# ============================================================

class DocumentProiect(db.Model):
    __tablename__ = 'documente_proiect'
    id = db.Column(db.Integer, primary_key=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=False)
    tip_instalatie_id = db.Column(db.Integer, db.ForeignKey('tipuri_instalatii.id'), nullable=False)
    tip_document_id = db.Column(db.Integer, db.ForeignKey('tipuri_documente_proiect.id'), nullable=True)

    denumire_document = db.Column(db.String(500), nullable=False)
    nr_document = db.Column(db.String(100))
    revizie = db.Column(db.String(20), default='Rev.0')
    emitent = db.Column(db.String(200))
    elaborat_de = db.Column(db.String(200))

    data_emitere = db.Column(db.Date)
    data_aprobare = db.Column(db.Date)
    data_expirare = db.Column(db.Date)

    versiune_curenta = db.Column(db.Boolean, default=True)
    fisier_path = db.Column(db.String(500))
    marime_fisier = db.Column(db.Integer)  # bytes
    tip_fisier = db.Column(db.String(20))  # extensia

    status = db.Column(db.String(20), default='draft')
    # draft, emis, aprobat, in_revizie, anulat, arhivat

    aprobat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    observatii = db.Column(db.Text)

    etapa_proiect = db.Column(db.String(30), default='executie')
    # proiectare, executie, receptie, garantie

    data_upload = db.Column(db.DateTime, default=datetime.utcnow)
    incarcat_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))

    # Relatii
    proiect = db.relationship('Proiect', backref=db.backref('documente_proiect', lazy='dynamic'))
    tip_document = db.relationship('TipDocumentProiect', backref='documente')
    aprobat_de = db.relationship('Utilizator', foreign_keys=[aprobat_de_id],
                                  backref='documente_proiect_aprobate')
    uploader = db.relationship('Utilizator', foreign_keys=[incarcat_de],
                                backref='documente_proiect_incarcate')
    revizii = db.relationship('RevizieDocument', backref='document_proiect',
                               lazy='dynamic', order_by='RevizieDocument.nr_revizie.desc()')

    STATUSURI = [
        ('draft', 'Draft'),
        ('emis', 'Emis'),
        ('aprobat', 'Aprobat'),
        ('in_revizie', 'In revizie'),
        ('anulat', 'Anulat'),
        ('arhivat', 'Arhivat'),
    ]

    ETAPE = [
        ('proiectare', 'Proiectare'),
        ('executie', 'Executie'),
        ('receptie', 'Receptie'),
        ('garantie', 'Garantie'),
    ]

    @property
    def status_badge_class(self):
        mapping = {
            'draft': 'badge-draft',
            'emis': 'badge-trimis',
            'aprobat': 'badge-aprobat',
            'in_revizie': 'badge-warning-custom',
            'anulat': 'badge-respins',
            'arhivat': 'badge-draft',
        }
        return mapping.get(self.status, 'badge-draft')

    @property
    def marime_formatata(self):
        if self.marime_fisier:
            if self.marime_fisier < 1024:
                return f"{self.marime_fisier} B"
            elif self.marime_fisier < 1024 * 1024:
                return f"{self.marime_fisier / 1024:.1f} KB"
            else:
                return f"{self.marime_fisier / (1024*1024):.1f} MB"
        return '-'

    @property
    def is_expirat(self):
        if self.data_expirare:
            return self.data_expirare < date.today()
        return False

    def __repr__(self):
        return f'<DocumentProiect {self.denumire_document}>'


# ============================================================
# MODEL REVIZIE DOCUMENT
# ============================================================

class RevizieDocument(db.Model):
    __tablename__ = 'revizii_documente'
    id = db.Column(db.Integer, primary_key=True)
    document_proiect_id = db.Column(db.Integer, db.ForeignKey('documente_proiect.id'), nullable=False)
    nr_revizie = db.Column(db.Integer, nullable=False, default=0)
    motiv_revizie = db.Column(db.Text)
    fisier_path = db.Column(db.String(500))
    data_revizie = db.Column(db.DateTime, default=datetime.utcnow)
    realizat_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))

    autor = db.relationship('Utilizator', backref='revizii_realizate')

    def __repr__(self):
        return f'<RevizieDocument Rev.{self.nr_revizie}>'


# ============================================================
# MODEL CATEGORIE ACTIVITATE
# ============================================================

class CategorieActivitate(db.Model):
    __tablename__ = 'categorii_activitati'
    id = db.Column(db.Integer, primary_key=True)
    denumire = db.Column(db.String(200), nullable=False)
    tip_instalatie_id = db.Column(db.Integer, db.ForeignKey('tipuri_instalatii.id'), nullable=True)
    unitate_masura_default = db.Column(db.String(20))
    activa = db.Column(db.Boolean, default=True)
    ordine = db.Column(db.Integer, default=0)

    tip_instalatie = db.relationship('TipInstalatie', backref=db.backref('categorii_activitati', lazy='dynamic'))

    def __repr__(self):
        return f'<CategorieActivitate {self.denumire}>'


# ============================================================
# MODEL RAPORT ACTIVITATE ZILNICA
# ============================================================

class RaportActivitate(db.Model):
    __tablename__ = 'rapoarte_activitati'
    id = db.Column(db.Integer, primary_key=True)
    angajat_id = db.Column(db.Integer, db.ForeignKey('angajati.id'), nullable=False)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=False)
    # Linkare BIM (optional)
    element_bim_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'), nullable=True, index=True)
    spatiu_id = db.Column(db.Integer, db.ForeignKey('bim_spatii.id'), nullable=True, index=True)
    zona_id = db.Column(db.Integer, db.ForeignKey('bim_zone.id'), nullable=True, index=True)
    data = db.Column(db.Date, nullable=False)  # data inceput (start_date)

    tip_instalatie_id = db.Column(db.Integer, db.ForeignKey('tipuri_instalatii.id'), nullable=True)
    categorie_activitate_id = db.Column(db.Integer, db.ForeignKey('categorii_activitati.id'), nullable=True)

    zona_lucru = db.Column(db.String(200))
    activitate_principala = db.Column(db.String(500), nullable=False)  # title
    activitate_detaliata = db.Column(db.Text)  # description (max 2000 chars)

    # === EXTENSIE: tip activitate (zilnica/saptamanala/lunara) ===
    tip_activitate = db.Column(db.String(20), default='zilnica', nullable=False)
    data_sfarsit = db.Column(db.Date, nullable=True)  # end_date
    numar_saptamana = db.Column(db.Integer, nullable=True)  # ISO week
    luna_an = db.Column(db.String(7), nullable=True)         # 'YYYY-MM'

    # === EXTENSIE: supervisor + subordonati ===
    supervisor_id = db.Column(db.Integer, db.ForeignKey('angajati.id'), nullable=True)
    subordonati_ids = db.Column(db.Text, nullable=True)  # JSON array de IDs angajati

    # === EXTENSIE: multi-proiect (proiect_id ramane primarul) ===
    proiecte_ids = db.Column(db.Text, nullable=True)  # JSON array de IDs proiecte

    # === EXTENSIE: marcaj zile lucrate suplimentar ===
    include_sambata = db.Column(db.Boolean, default=False, nullable=False)
    include_duminica = db.Column(db.Boolean, default=False, nullable=False)

    # === EXTENSIE: detalii pe zi (pentru activitati saptamanale/lunare) ===
    # JSON array de obiecte: [{data, proiect_id, text, ore}, ...]
    detalii_pe_zi = db.Column(db.Text, nullable=True)

    # === EXTENSIE: ore + status executie ===
    ore_lucrate = db.Column(db.Numeric(5, 2), nullable=True)
    status_executie = db.Column(db.String(20), default='planificata', nullable=False)
    # planificata, in_desfasurare, finalizata

    materiale_folosite = db.Column(db.Text)      # JSON array [{denumire, cantitate, um}]
    echipamente_folosite = db.Column(db.Text)     # lista echipamente/scule

    cantitate_executata = db.Column(db.Numeric(12, 2), nullable=True)
    unitate_masura = db.Column(db.String(20))     # ml, mp, buc, kg, etc.
    procent_realizare = db.Column(db.Integer, nullable=True)  # 0-100

    probleme_intampinate = db.Column(db.Text)
    solutii_aplicate = db.Column(db.Text)
    observatii = db.Column(db.Text)

    necesita_aprobare_tehnica = db.Column(db.Boolean, default=False)

    status = db.Column(db.String(20), default='draft')
    # draft, trimis, aprobat, respins (workflow aprobare)

    aprobat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_aprobare = db.Column(db.DateTime, nullable=True)
    motiv_respingere = db.Column(db.Text)

    introdus_la = db.Column(db.DateTime, default=datetime.utcnow)
    modificat_la = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relatii
    angajat = db.relationship('Angajat', foreign_keys=[angajat_id],
                              backref=db.backref('rapoarte_activitati', lazy='dynamic'))
    supervisor = db.relationship('Angajat', foreign_keys=[supervisor_id],
                                 backref=db.backref('activitati_supervizate', lazy='dynamic'))
    proiect = db.relationship('Proiect', backref=db.backref('rapoarte_activitati', lazy='dynamic'))
    tip_instalatie = db.relationship('TipInstalatie', backref=db.backref('rapoarte_activitati', lazy='dynamic'))
    categorie_activitate = db.relationship('CategorieActivitate', backref=db.backref('rapoarte', lazy='dynamic'))
    aprobat_de = db.relationship('Utilizator', foreign_keys=[aprobat_de_id],
                                  backref='activitati_aprobate')
    # Relatii BIM (link spre context spatial)
    element_bim = db.relationship('ElementBIM', foreign_keys=[element_bim_id],
                                  backref=db.backref('rapoarte_workforce', lazy='dynamic'))
    spatiu = db.relationship('Spatiu', foreign_keys=[spatiu_id],
                             backref=db.backref('rapoarte_workforce', lazy='dynamic'))
    zona = db.relationship('Zona', foreign_keys=[zona_id],
                           backref=db.backref('rapoarte_workforce', lazy='dynamic'))

    STATUSURI = [
        ('draft', 'Draft'),
        ('trimis', 'Trimis'),
        ('aprobat', 'Aprobat'),
        ('respins', 'Respins'),
    ]

    TIPURI_ACTIVITATE = [
        ('zilnica', 'Zilnica'),
        ('saptamanala', 'Saptamanala'),
        ('lunara', 'Lunara'),
    ]

    STATUSURI_EXECUTIE = [
        ('planificata', 'Planificata'),
        ('in_desfasurare', 'In desfasurare'),
        ('finalizata', 'Finalizata'),
    ]

    UNITATI_MASURA = [
        ('ml', 'metri lineari'),
        ('mp', 'metri patrati'),
        ('mc', 'metri cubi'),
        ('buc', 'bucati'),
        ('kg', 'kilograme'),
        ('set', 'seturi'),
        ('ore', 'ore'),
        ('km', 'kilometri'),
        ('t', 'tone'),
    ]

    @property
    def status_badge_class(self):
        mapping = {
            'draft': 'badge-draft',
            'trimis': 'badge-trimis',
            'aprobat': 'badge-aprobat',
            'respins': 'badge-respins',
        }
        return mapping.get(self.status, 'badge-draft')

    @property
    def activitate_scurta(self):
        """Returneaza un rezumat scurt al activitatii."""
        if len(self.activitate_principala) > 80:
            return self.activitate_principala[:77] + '...'
        return self.activitate_principala

    @property
    def materiale_lista(self):
        """Parseaza JSON materiale."""
        import json
        if self.materiale_folosite:
            try:
                return json.loads(self.materiale_folosite)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @property
    def echipamente_lista(self):
        """Returneaza lista echipamente."""
        if self.echipamente_folosite:
            return [e.strip() for e in self.echipamente_folosite.split(',') if e.strip()]
        return []

    @property
    def subordonati_lista(self):
        """Parseaza JSON subordonati_ids -> lista de IDs (int)."""
        import json
        if self.subordonati_ids:
            try:
                data = json.loads(self.subordonati_ids)
                return [int(x) for x in data if str(x).strip()]
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return []

    @property
    def subordonati_obiecte(self):
        """Returneaza obiecte Angajat pentru subordonatii setati."""
        ids = self.subordonati_lista
        if not ids:
            return []
        return Angajat.query.filter(Angajat.id.in_(ids)).all()

    @property
    def proiecte_lista(self):
        """Lista de IDs proiecte (din JSON sau fallback la proiect_id)."""
        import json
        if self.proiecte_ids:
            try:
                data = json.loads(self.proiecte_ids)
                ids = [int(x) for x in data if str(x).strip()]
                if ids:
                    return ids
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return [self.proiect_id] if self.proiect_id else []

    @property
    def proiecte_obiecte(self):
        """Obiecte Proiect asociate cu activitatea (multi-proiect)."""
        ids = self.proiecte_lista
        if not ids:
            return []
        return Proiect.query.filter(Proiect.id.in_(ids)).all()

    @property
    def detalii_pe_zi_lista(self):
        """Parseaza JSON detalii_pe_zi -> lista de dict-uri [{data, proiect_id, text, ore}, ...]"""
        import json
        if not self.detalii_pe_zi:
            return []
        try:
            data = json.loads(self.detalii_pe_zi)
            if not isinstance(data, list):
                return []
            curate = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                # Convert date string to date object daca e nevoie
                d_str = item.get('data')
                if d_str:
                    try:
                        from datetime import datetime as _dt
                        item['_data_obj'] = _dt.strptime(d_str, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        item['_data_obj'] = None
                curate.append(item)
            return curate
        except (json.JSONDecodeError, TypeError):
            return []

    def detalii_pentru_data(self, zi_date):
        """Returneaza detaliul pentru o anumita zi (sau None)."""
        for d in self.detalii_pe_zi_lista:
            if d.get('_data_obj') == zi_date:
                return d
        return None

    @property
    def status_executie_badge_class(self):
        mapping = {
            'planificata': 'badge-draft',
            'in_desfasurare': 'badge-trimis',
            'finalizata': 'badge-aprobat',
        }
        return mapping.get(self.status_executie, 'badge-draft')

    @property
    def tip_badge_class(self):
        """Clasa CSS pentru badge tip activitate."""
        mapping = {
            'zilnica': 'badge-tip-zilnica',
            'saptamanala': 'badge-tip-saptamanala',
            'lunara': 'badge-tip-lunara',
        }
        return mapping.get(self.tip_activitate, 'badge-tip-zilnica')

    @property
    def perioada_text(self):
        """Returneaza un text descriptiv pentru perioada activitatii."""
        if self.tip_activitate == 'saptamanala' and self.numar_saptamana:
            return f'Saptamana {self.numar_saptamana}'
        if self.tip_activitate == 'lunara' and self.luna_an:
            try:
                y, m = self.luna_an.split('-')
                LUNI_RO = ['Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
                           'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']
                return f'{LUNI_RO[int(m)-1]} {y}'
            except (ValueError, IndexError):
                return self.luna_an
        return self.data.strftime('%d.%m.%Y') if self.data else '-'

    def calculeaza_perioada(self):
        """Auto-completeaza numar_saptamana / luna_an din data si tip_activitate."""
        if not self.data:
            return
        if self.tip_activitate == 'saptamanala':
            self.numar_saptamana = self.data.isocalendar()[1]
        elif self.tip_activitate == 'lunara':
            self.luna_an = self.data.strftime('%Y-%m')

    def __repr__(self):
        return f'<RaportActivitate {self.angajat_id} {self.data} {self.tip_activitate}>'


# ============================================================
# MODEL MASINA (Flota auto)
# ============================================================

class Masina(db.Model):
    __tablename__ = 'masini'
    id = db.Column(db.Integer, primary_key=True)
    numar_inmatriculare = db.Column(db.String(20), unique=True, nullable=False)
    marca = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    an_fabricatie = db.Column(db.Integer)
    vin = db.Column(db.String(17), unique=True)
    culoare = db.Column(db.String(30))
    tip_combustibil = db.Column(db.String(20), default='motorina')  # motorina, benzina, electric, hybrid, gpl
    capacitate_cilindrica = db.Column(db.Integer)  # cmc
    putere_kw = db.Column(db.Integer)

    tip_vehicul = db.Column(db.String(30), default='autoturism')
    # autoturism, autoutilitara, basculanta, duba, autocamion, autospeciala

    nr_locuri = db.Column(db.Integer, default=5)
    masa_maxima = db.Column(db.Integer)  # kg
    categorie_permis = db.Column(db.String(5), default='B')  # B, C, CE, D

    km_bord = db.Column(db.Integer, default=0)
    consum_mediu = db.Column(db.Numeric(5, 2))  # litri/100km

    serie_civ = db.Column(db.String(20))  # Certificat inmatriculare
    nr_carte_identitate = db.Column(db.String(20))

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'))  # proiect alocat curent
    angajat_responsabil_id = db.Column(db.Integer, db.ForeignKey('angajati.id'))  # sofer principal

    status = db.Column(db.String(20), default='disponibila')
    # disponibila, atribuita, service, casata, vanduta
    poza = db.Column(db.String(255))
    observatii = db.Column(db.Text)

    data_achizitie = db.Column(db.Date)
    data_prima_inmatriculare = db.Column(db.Date)
    data_itp_expirare = db.Column(db.Date)
    data_rca_expirare = db.Column(db.Date)
    data_casco_expirare = db.Column(db.Date)
    data_rovinieta_expirare = db.Column(db.Date)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_actualizare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relatii
    proiect = db.relationship('Proiect', backref=db.backref('masini', lazy='dynamic'))
    angajat_responsabil = db.relationship('Angajat', backref=db.backref('masini_responsabil', lazy='dynamic'))
    documente_masina = db.relationship('DocumentMasina', backref='masina', lazy='dynamic', cascade='all, delete-orphan')
    atribuiri = db.relationship('AtribuireMasina', backref='masina', lazy='dynamic', cascade='all, delete-orphan')
    conduceri = db.relationship('ConducereMasina', backref='masina', lazy='dynamic', cascade='all, delete-orphan')
    defectiuni = db.relationship('DefectiuneMasina', backref='masina', lazy='dynamic', cascade='all, delete-orphan')

    TIPURI_COMBUSTIBIL = [
        ('motorina', 'Motorina'),
        ('benzina', 'Benzina'),
        ('electric', 'Electric'),
        ('hybrid', 'Hybrid'),
        ('gpl', 'GPL'),
    ]

    TIPURI_VEHICUL = [
        ('autoturism', 'Autoturism'),
        ('autoutilitara', 'Autoutilitara'),
        ('basculanta', 'Basculanta'),
        ('duba', 'Duba'),
        ('autocamion', 'Autocamion'),
        ('autospeciala', 'Autospeciala'),
    ]

    STATUSURI = [
        ('disponibila', 'Disponibila'),
        ('atribuita', 'Atribuita'),
        ('service', 'In Service'),
        ('casata', 'Casata'),
        ('vanduta', 'Vanduta'),
    ]

    @property
    def denumire_completa(self):
        return f"{self.marca} {self.model} ({self.numar_inmatriculare})"

    @property
    def status_badge_class(self):
        mapping = {
            'disponibila': 'badge-aprobat',
            'atribuita': 'badge-trimis',
            'service': 'badge-draft',
            'casata': 'badge-respins',
            'vanduta': 'badge-respins',
        }
        return mapping.get(self.status, 'badge-draft')

    @property
    def alerte_documente(self):
        """Returneaza lista alertelor de documente expirabile."""
        alerte = []
        today = date.today()
        docs = [
            ('ITP', self.data_itp_expirare),
            ('RCA', self.data_rca_expirare),
            ('CASCO', self.data_casco_expirare),
            ('Rovinieta', self.data_rovinieta_expirare),
        ]
        for doc_name, exp_date in docs:
            if exp_date:
                delta = (exp_date - today).days
                if delta < 0:
                    alerte.append({'doc': doc_name, 'zile': delta, 'tip': 'expirat'})
                elif delta <= 30:
                    alerte.append({'doc': doc_name, 'zile': delta, 'tip': 'expira_curand'})
        return alerte

    @property
    def are_alerte(self):
        return len(self.alerte_documente) > 0

    def __repr__(self):
        return f'<Masina {self.numar_inmatriculare}>'


class DocumentMasina(db.Model):
    __tablename__ = 'documente_masini'
    id = db.Column(db.Integer, primary_key=True)
    masina_id = db.Column(db.Integer, db.ForeignKey('masini.id'), nullable=False)
    tip = db.Column(db.String(50), nullable=False)
    # itp, rca, casco, rovinieta, asigurare_persoane, contract_leasing, fisa_tehnica, altele
    nume_document = db.Column(db.String(200))
    numar_document = db.Column(db.String(100))
    emitent = db.Column(db.String(200))
    data_emitere = db.Column(db.Date)
    data_expirare = db.Column(db.Date)
    cost = db.Column(db.Numeric(10, 2))
    fisier = db.Column(db.String(255))  # cale fisier upload
    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    TIPURI = [
        ('itp', 'ITP'),
        ('rca', 'RCA'),
        ('casco', 'CASCO'),
        ('rovinieta', 'Rovinieta'),
        ('asigurare_persoane', 'Asigurare Persoane'),
        ('contract_leasing', 'Contract Leasing'),
        ('fisa_tehnica', 'Fisa Tehnica'),
        ('altele', 'Altele'),
    ]

    def __repr__(self):
        return f'<DocumentMasina {self.tip} - {self.masina_id}>'


class AtribuireMasina(db.Model):
    __tablename__ = 'atribuiri_masini'
    id = db.Column(db.Integer, primary_key=True)
    masina_id = db.Column(db.Integer, db.ForeignKey('masini.id'), nullable=False)
    angajat_id = db.Column(db.Integer, db.ForeignKey('angajati.id'), nullable=False)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'))
    data_atribuire = db.Column(db.Date, nullable=False, default=date.today)
    data_returnare = db.Column(db.Date)
    km_preluare = db.Column(db.Integer)
    km_returnare = db.Column(db.Integer)
    stare_preluare = db.Column(db.String(20), default='buna')  # buna, acceptabila, deteriorata
    stare_returnare = db.Column(db.String(20))
    motiv = db.Column(db.Text)
    observatii = db.Column(db.Text)
    atribuit_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    angajat = db.relationship('Angajat', backref=db.backref('atribuiri_masini', lazy='dynamic'))
    proiect = db.relationship('Proiect', backref=db.backref('atribuiri_masini', lazy='dynamic'))
    utilizator = db.relationship('Utilizator', backref=db.backref('atribuiri_efectuate', lazy='dynamic'))

    @property
    def activa(self):
        return self.data_returnare is None

    @property
    def km_parcursi(self):
        if self.km_preluare is not None and self.km_returnare is not None:
            return self.km_returnare - self.km_preluare
        return None

    def __repr__(self):
        return f'<AtribuireMasina {self.masina_id} -> {self.angajat_id}>'


class ConducereMasina(db.Model):
    __tablename__ = 'conduceri_masini'
    id = db.Column(db.Integer, primary_key=True)
    masina_id = db.Column(db.Integer, db.ForeignKey('masini.id'), nullable=False)
    angajat_id = db.Column(db.Integer, db.ForeignKey('angajati.id'), nullable=False)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'))
    data = db.Column(db.Date, nullable=False, default=date.today)
    km_start = db.Column(db.Integer, nullable=False)
    km_sfarsit = db.Column(db.Integer)
    ruta = db.Column(db.String(300))  # ex: Bucuresti -> Ploiesti -> Bucuresti
    scop = db.Column(db.String(200))
    combustibil_alimentat = db.Column(db.Numeric(6, 2))  # litri
    cost_combustibil = db.Column(db.Numeric(8, 2))
    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    angajat = db.relationship('Angajat', backref=db.backref('conduceri_masini', lazy='dynamic'))
    proiect = db.relationship('Proiect', backref=db.backref('conduceri_masini', lazy='dynamic'))

    @property
    def km_parcursi(self):
        if self.km_start is not None and self.km_sfarsit is not None:
            return self.km_sfarsit - self.km_start
        return 0

    def __repr__(self):
        return f'<ConducereMasina {self.masina_id} {self.data}>'


class DefectiuneMasina(db.Model):
    __tablename__ = 'defectiuni_masini'
    id = db.Column(db.Integer, primary_key=True)
    masina_id = db.Column(db.Integer, db.ForeignKey('masini.id'), nullable=False)
    raportat_de = db.Column(db.Integer, db.ForeignKey('angajati.id'))
    data_raportare = db.Column(db.Date, nullable=False, default=date.today)
    descriere = db.Column(db.Text, nullable=False)
    gravitate = db.Column(db.String(20), default='medie')  # mica, medie, mare, critica
    status = db.Column(db.String(20), default='raportata')  # raportata, in_lucru, rezolvata, amanata
    data_rezolvare = db.Column(db.Date)
    cost_reparatie = db.Column(db.Numeric(10, 2))
    service_extern = db.Column(db.String(200))  # unde s-a reparat
    detalii_reparatie = db.Column(db.Text)
    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    angajat_raportor = db.relationship('Angajat', backref=db.backref('defectiuni_raportate', lazy='dynamic'))

    GRAVITATI = [
        ('mica', 'Mica'),
        ('medie', 'Medie'),
        ('mare', 'Mare'),
        ('critica', 'Critica'),
    ]

    STATUSURI = [
        ('raportata', 'Raportata'),
        ('in_lucru', 'In lucru'),
        ('rezolvata', 'Rezolvata'),
        ('amanata', 'Amanata'),
    ]

    @property
    def gravitate_badge_class(self):
        mapping = {
            'mica': 'badge-aprobat',
            'medie': 'badge-trimis',
            'mare': 'badge-draft',
            'critica': 'badge-respins',
        }
        return mapping.get(self.gravitate, 'badge-draft')

    @property
    def status_badge_class(self):
        mapping = {
            'raportata': 'badge-trimis',
            'in_lucru': 'badge-draft',
            'rezolvata': 'badge-aprobat',
            'amanata': 'badge-respins',
        }
        return mapping.get(self.status, 'badge-draft')

    def __repr__(self):
        return f'<DefectiuneMasina {self.masina_id} {self.gravitate}>'


class ConsumUtilaj(db.Model):
    """Consum real de utilaj pe proiect (Faza 3 - C: utilaj planificat vs real).

    Inchide bucla pe utilaje, analog manopera<->pontaje: planificatul vine din
    plan/deviz (cost_utilaj), realul de aici. Optional legat de o masina din flota.
    cost = valoarea explicita daca > 0, altfel ore x tarif_ora.
    """
    __tablename__ = 'consum_utilaj'
    id = db.Column(db.Integer, primary_key=True)   # Integer (SQLite auto-increment)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)
    masina_id = db.Column(db.Integer, db.ForeignKey('masini.id'),
                          nullable=True, index=True)   # optional: utilaj din flota
    denumire = db.Column(db.String(150), nullable=False)   # ex: Excavator CAT 320
    data = db.Column(db.Date, nullable=False, default=date.today, index=True)
    ore = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tarif_ora = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cost = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    categorie_lucrare = db.Column(db.String(60), nullable=True)   # F2 optional
    observatii = db.Column(db.Text, nullable=True)
    introdus_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    proiect = db.relationship('Proiect', backref=db.backref('consum_utilaj', lazy='dynamic'))
    masina = db.relationship('Masina', backref=db.backref('consum_utilaj', lazy='dynamic'))

    def calc_cost(self) -> float:
        """Costul efectiv: explicit daca > 0, altfel ore x tarif_ora."""
        if self.cost and float(self.cost) > 0:
            return float(self.cost)
        return float(self.ore or 0) * float(self.tarif_ora or 0)

    def __repr__(self):
        return f'<ConsumUtilaj {self.denumire} p{self.proiect_id} {self.data}>'


class ExtrasResursa(db.Model):
    """Extras de resurse din deviz (Formular C6 materiale / C7 manopera / C8 utilaje),
    importat pe proiect (Faza 2 - F3/C). Listele PLANIFICATE de resurse pe proiect:
    materiale (aprovizionare), manopera pe meserii, utilaje pe ore. Distinct de
    ConsumUtilaj (consum REAL)."""
    __tablename__ = 'extras_resursa'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)
    tip = db.Column(db.String(12), nullable=False, index=True)   # material | manopera | utilaj
    cod = db.Column(db.String(60), nullable=True)
    denumire = db.Column(db.String(400), nullable=False)
    um = db.Column(db.String(20), nullable=True)
    cantitate = db.Column(db.Numeric(16, 3), nullable=False, default=0)   # consum / ore
    tarif_unitar = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    valoare = db.Column(db.Numeric(16, 2), nullable=False, default=0)
    furnizor = db.Column(db.String(150), nullable=True)          # doar C6
    nume_fisier = db.Column(db.String(255), nullable=True)
    introdus_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    proiect = db.relationship('Proiect',
                              backref=db.backref('extrase_resurse', lazy='dynamic'))

    TIPURI = [('material', 'Materiale (C6)'), ('manopera', 'Manopera (C7)'),
              ('utilaj', 'Utilaje (C8)')]

    def __repr__(self):
        return f'<ExtrasResursa {self.tip} {self.denumire[:30]!r} p{self.proiect_id}>'


class PretResursa(db.Model):
    """Banca de preturi de resurse - referinta din extrase REALE (C6 materiale /
    C7 manopera / C8 utilaje / C9 transport / F4 echipamente).

    Distinct de ExtrasResursa (consum PLANIFICAT pe un proiect) si de
    TarifCategorie (tarif pe categorie de lucrare, pt auto-pricing). Aici tinem
    pretul UNITAR pe cod-resursa, cu sursa (proiect/oferta) si data, ca sa
    putem face benchmark (P25/P50/P75) pe acelasi cod intre proiecte.
    Un rand per (tip, cod, sursa). Strict aditiv, optional (flag 'banca-preturi')."""
    __tablename__ = 'pret_resursa'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    tip = db.Column(db.String(12), nullable=False, index=True)   # material|manopera|utilaj|transport|echipament
    cod = db.Column(db.String(80), nullable=False, index=True)
    denumire = db.Column(db.String(400), nullable=False)
    um = db.Column(db.String(20), nullable=True)
    categorie = db.Column(db.String(60), nullable=True, index=True)  # categorie de lucrare (clasificata auto, editabila)
    pret_unitar = db.Column(db.Numeric(16, 4), nullable=False, default=0)
    moneda = db.Column(db.String(8), nullable=False, default='RON')
    sursa = db.Column(db.String(200), nullable=True, index=True)  # ex: nume proiect / fisier
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=True, index=True)
    data_pret = db.Column(db.Date, nullable=True)                 # data ofertei / extrasului
    furnizor = db.Column(db.String(150), nullable=True)           # doar materiale (C6)
    introdus_de = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    TIPURI = [('material', 'Materiale (C6)'), ('manopera', 'Manopera (C7)'),
              ('utilaj', 'Utilaje (C8)'), ('transport', 'Transport (C9)'),
              ('echipament', 'Echipamente (F4)')]

    def __repr__(self):
        return f'<PretResursa {self.tip} {self.cod} {self.pret_unitar}>'


# ============================================================
# ============================================================
# === MODULUL BIM (Building Information Modeling)         ===
# === Extinde workforce cu structura ierarhica spatiala   ===
# === si elemente fizice (walls/doors/equipment/MEP).     ===
# ============================================================
# Ierarhie:
#   Santier (Site) -> Cladire (Building) -> Nivel (Storey)
#                  \-> Zona (Zone) ----------|
#                                            \-> Spatiu (Room) -> ElementBIM (Wall/Door/AHU/...)
#                                                                  \-> Asset (component instalat)
# Plus:
#   ModelBIM (referinta IFC/Revit/extern)
#   IssueBIM (probleme legate de element/spatiu)
# Linkare workforce:
#   RaportActivitate.element_bim_id, Pontaj.element_bim_id, Proiect.santier_id
# ============================================================
# ============================================================


class Santier(db.Model):
    """BIM Site - locatie geografica a unui complex de cladiri."""
    __tablename__ = 'bim_santiere'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=True, index=True)

    cod = db.Column(db.String(50), nullable=False)  # ex: SITE-001
    nume = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)

    adresa = db.Column(db.String(300))
    oras = db.Column(db.String(100))
    judet = db.Column(db.String(50))
    tara = db.Column(db.String(50), default='Romania')

    # Coordonate geografice (optionale, pentru viewer harta)
    latitudine = db.Column(db.Numeric(10, 7), nullable=True)
    longitudine = db.Column(db.Numeric(10, 7), nullable=True)

    # Identificator extern (IFC IfcSite.GlobalId, Revit ElementId, etc.)
    extern_id = db.Column(db.String(100), nullable=True, index=True)
    source_system = db.Column(db.String(30), nullable=True)
    # ifc, revit, bcf, trimble, autodesk, manual

    last_synced_at = db.Column(db.DateTime, nullable=True)  # ultima sincronizare cu sistem extern

    status = db.Column(db.String(20), default='activ')  # activ, finalizat, suspendat
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    # Relatii
    proiect = db.relationship('Proiect', backref=db.backref('santiere', lazy='dynamic'))
    cladiri = db.relationship('Cladire', backref='santier', lazy='dynamic',
                              cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'cod', name='uix_santier_tenant_cod'),
        # extern_id unic per sursa - permite acelasi GUID din 2 sisteme diferite
        db.Index('uix_santier_source_extern', 'source_system', 'extern_id', unique=False),
    )

    def __repr__(self):
        return f'<Santier {self.cod}>'


class Cladire(db.Model):
    """BIM Building - cladire individuala in cadrul unui santier."""
    __tablename__ = 'bim_cladiri'
    id = db.Column(db.Integer, primary_key=True)
    santier_id = db.Column(db.Integer, db.ForeignKey('bim_santiere.id'), nullable=False, index=True)

    cod = db.Column(db.String(50), nullable=False)  # ex: BLD-A, CORP-1
    nume = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)

    tip_constructie = db.Column(db.String(50))  # rezidential, comercial, industrial, mixt, public
    nr_niveluri = db.Column(db.Integer)
    suprafata_totala = db.Column(db.Numeric(12, 2))  # mp

    extern_id = db.Column(db.String(100), nullable=True, index=True)  # IFC GlobalId
    source_system = db.Column(db.String(30), nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    # Relatii
    niveluri = db.relationship('Nivel', backref='cladire', lazy='dynamic',
                               cascade='all, delete-orphan',
                               order_by='Nivel.ordine')
    zone = db.relationship('Zona', backref='cladire', lazy='dynamic',
                           cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('santier_id', 'cod', name='uix_cladire_santier_cod'),
    )

    def __repr__(self):
        return f'<Cladire {self.cod}>'


class Nivel(db.Model):
    """BIM Storey/Level - nivel/etaj intr-o cladire."""
    __tablename__ = 'bim_niveluri'
    id = db.Column(db.Integer, primary_key=True)
    cladire_id = db.Column(db.Integer, db.ForeignKey('bim_cladiri.id'), nullable=False, index=True)

    cod = db.Column(db.String(50), nullable=False)  # ex: N00, N01, BSM, ROOF
    nume = db.Column(db.String(100), nullable=False)  # ex: Parter, Etaj 1, Subsol
    ordine = db.Column(db.Integer, default=0)  # pentru sortare (0 = parter, 1 = etaj 1, -1 = subsol)

    elevatie_m = db.Column(db.Numeric(8, 2))  # cota fata de 0.00
    inaltime_m = db.Column(db.Numeric(8, 2))  # inaltimea nivelului

    extern_id = db.Column(db.String(100), nullable=True, index=True)  # IFC GlobalId
    source_system = db.Column(db.String(30), nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)

    # Relatii
    spatii = db.relationship('Spatiu', backref='nivel', lazy='dynamic',
                             cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('cladire_id', 'cod', name='uix_nivel_cladire_cod'),
    )

    def __repr__(self):
        return f'<Nivel {self.cladire_id}/{self.cod}>'


class Zona(db.Model):
    """BIM Zone - grupare logica de spatii (nu neaparat geometrica)."""
    __tablename__ = 'bim_zone'
    id = db.Column(db.Integer, primary_key=True)
    cladire_id = db.Column(db.Integer, db.ForeignKey('bim_cladiri.id'), nullable=False, index=True)
    nivel_id = db.Column(db.Integer, db.ForeignKey('bim_niveluri.id'), nullable=True, index=True)

    cod = db.Column(db.String(50), nullable=False)
    nume = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)
    tip_zona = db.Column(db.String(50))  # functional, securitate, hvac, etc.

    extern_id = db.Column(db.String(100), nullable=True, index=True)
    source_system = db.Column(db.String(30), nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)

    # Relatii
    nivel = db.relationship('Nivel', backref=db.backref('zone', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('cladire_id', 'cod', name='uix_zona_cladire_cod'),
    )

    def __repr__(self):
        return f'<Zona {self.cod}>'


class Spatiu(db.Model):
    """BIM Space/Room - camera/incapere individuala."""
    __tablename__ = 'bim_spatii'
    id = db.Column(db.Integer, primary_key=True)
    nivel_id = db.Column(db.Integer, db.ForeignKey('bim_niveluri.id'), nullable=False, index=True)
    zona_id = db.Column(db.Integer, db.ForeignKey('bim_zone.id'), nullable=True, index=True)

    cod = db.Column(db.String(50), nullable=False)  # ex: 3.21, P.05
    nume = db.Column(db.String(200), nullable=False)  # ex: Birou director
    tip_spatiu = db.Column(db.String(50))  # birou, sala, hol, casa scarii, tehnic, sanitar, etc.

    suprafata_mp = db.Column(db.Numeric(10, 2))
    inaltime_m = db.Column(db.Numeric(8, 2))
    volum_mc = db.Column(db.Numeric(12, 2))

    extern_id = db.Column(db.String(100), nullable=True, index=True)  # IFC IfcSpace.GlobalId
    source_system = db.Column(db.String(30), nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)

    # Relatii
    zona = db.relationship('Zona', backref=db.backref('spatii', lazy='dynamic'))
    elemente = db.relationship('ElementBIM', backref='spatiu', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('nivel_id', 'cod', name='uix_spatiu_nivel_cod'),
    )

    def __repr__(self):
        return f'<Spatiu {self.cod}>'


class ElementBIM(db.Model):
    """
    Element fizic generic (perete, usa, fereastra, echipament, conducta, etc.).
    Tip e un cod IFC standard (IfcWall, IfcDoor, IfcUnitaryEquipment, etc.) -
    folosim notatie EN pentru interoperabilitate, label-urile RO sunt in TIPURI.
    """
    __tablename__ = 'bim_elemente'
    id = db.Column(db.Integer, primary_key=True)
    spatiu_id = db.Column(db.Integer, db.ForeignKey('bim_spatii.id'), nullable=True, index=True)
    nivel_id = db.Column(db.Integer, db.ForeignKey('bim_niveluri.id'), nullable=True, index=True)
    cladire_id = db.Column(db.Integer, db.ForeignKey('bim_cladiri.id'), nullable=True, index=True)

    cod = db.Column(db.String(100), nullable=False)  # ex: AHU-03, DOOR-3.21-01
    nume = db.Column(db.String(200))
    tip_element = db.Column(db.String(50), nullable=False, index=True)
    # Valori standard IFC (EN): wall, door, window, slab, beam, column, stair,
    # railing, AHU, fan, pump, valve, pipe, duct, cable_tray, light, sensor, etc.

    descriere = db.Column(db.Text)

    # Geometrie / dimensiuni (optional)
    cantitate = db.Column(db.Numeric(12, 3))
    unitate_masura = db.Column(db.String(20))  # ml, mp, mc, buc, kg

    # Identificator IFC (cheie de unicitate cross-system)
    ifc_global_id = db.Column(db.String(100), nullable=True, index=True)
    extern_id = db.Column(db.String(100), nullable=True, index=True)
    source_system = db.Column(db.String(30), nullable=True)
    # Linkul catre modelul BIM din care a venit elementul (pentru re-import selectiv)
    model_bim_id = db.Column(db.Integer, db.ForeignKey('bim_modele.id'), nullable=True, index=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)

    # Status executie
    status = db.Column(db.String(30), default='proiectat')
    # proiectat, in_executie, executat, verificat, receptionat, defect

    # JSON cu proprietati custom (PSet IFC sau alte atribute)
    proprietati_json = db.Column(db.Text, nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_actualizare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relatii
    nivel = db.relationship('Nivel', backref=db.backref('elemente', lazy='dynamic'))
    cladire = db.relationship('Cladire', backref=db.backref('elemente', lazy='dynamic'))
    asset = db.relationship('Asset', backref='element', uselist=False,
                            cascade='all, delete-orphan')

    TIPURI = [
        # IFC code, label_RO, categorie
        ('wall', 'Perete', 'structural'),
        ('door', 'Usa', 'arhitectural'),
        ('window', 'Fereastra', 'arhitectural'),
        ('slab', 'Placa', 'structural'),
        ('beam', 'Grinda', 'structural'),
        ('column', 'Stalp', 'structural'),
        ('stair', 'Scara', 'arhitectural'),
        ('railing', 'Balustrada', 'arhitectural'),
        ('AHU', 'CTA - Centrala tratare aer', 'mep_hvac'),
        ('chiller', 'Chiller', 'mep_hvac'),
        ('fan', 'Ventilator', 'mep_hvac'),
        ('pump', 'Pompa', 'mep_sanitare'),
        ('valve', 'Vana / Robinet', 'mep_sanitare'),
        ('pipe', 'Conducta', 'mep_sanitare'),
        ('duct', 'Tubulatura', 'mep_hvac'),
        ('cable_tray', 'Pat cabluri', 'mep_electric'),
        ('light', 'Corp iluminat', 'mep_electric'),
        ('outlet', 'Priza', 'mep_electric'),
        ('switch', 'Intrerupator', 'mep_electric'),
        ('panel', 'Tablou electric', 'mep_electric'),
        ('sensor', 'Senzor', 'mep_automatizari'),
        ('sprinkler', 'Sprinkler', 'mep_pci'),
        ('extinguisher', 'Stingator', 'mep_pci'),
        ('elevator', 'Lift', 'mep_transport'),
        ('alte', 'Alte elemente', 'general'),
    ]

    @property
    def tip_label(self):
        """Returneaza eticheta in romana pentru tipul de element."""
        for cod, label, _cat in self.TIPURI:
            if cod == self.tip_element:
                return label
        return self.tip_element

    @property
    def tip_categorie(self):
        for cod, _label, cat in self.TIPURI:
            if cod == self.tip_element:
                return cat
        return 'general'

    @property
    def cale_completa(self):
        """Returneaza calea ierarhica: Santier > Cladire > Nivel > Spatiu > Element."""
        parts = []
        if self.cladire and self.cladire.santier:
            parts.append(self.cladire.santier.cod)
        if self.cladire:
            parts.append(self.cladire.cod)
        if self.nivel:
            parts.append(self.nivel.nume)
        if self.spatiu:
            parts.append(self.spatiu.cod)
        parts.append(self.cod)
        return ' / '.join(parts)

    @property
    def validation_warnings(self):
        """
        Returneaza lista de avertismente de calitate:
        - spatiu si nivel din cladiri diferite
        - nivel si cladire mismatch
        - lipsa IFC GlobalId pentru elemente importate via IFC
        """
        warnings = []
        if self.spatiu and self.nivel and self.spatiu.nivel_id != self.nivel.id:
            warnings.append('Spatiu si nivel din locatii diferite')
        if self.spatiu and self.spatiu.nivel and self.cladire and self.spatiu.nivel.cladire_id != self.cladire.id:
            warnings.append('Spatiu si cladire mismatch')
        if self.nivel and self.cladire and self.nivel.cladire_id != self.cladire.id:
            warnings.append('Nivel si cladire mismatch')
        if self.source_system == 'ifc' and not self.ifc_global_id:
            warnings.append('Element importat din IFC fara GlobalId')
        return warnings

    def __repr__(self):
        return f'<ElementBIM {self.cod} ({self.tip_element})>'


class Asset(db.Model):
    """
    Asset - component fizic instalat (cu serial, garantie, mentenanta).
    Asociat 1:1 cu un ElementBIM (un AHU este si element BIM si asset).
    """
    __tablename__ = 'bim_assets'
    id = db.Column(db.Integer, primary_key=True)
    element_bim_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'),
                               nullable=False, unique=True, index=True)

    producator = db.Column(db.String(150))
    model = db.Column(db.String(150))
    serial = db.Column(db.String(150), index=True)
    cod_intern = db.Column(db.String(100))

    data_punere_functiune = db.Column(db.Date)
    data_garantie_pana = db.Column(db.Date)
    interval_mentenanta_zile = db.Column(db.Integer)  # ex: 90, 180, 365

    ultima_mentenanta = db.Column(db.Date)
    urmatoarea_mentenanta = db.Column(db.Date)

    cost_achizitie = db.Column(db.Numeric(12, 2))
    moneda = db.Column(db.String(5), default='RON')

    fisa_tehnica_path = db.Column(db.String(500))  # cale fisier upload
    manual_path = db.Column(db.String(500))

    # Identificator extern (CMMS, asset management system)
    extern_id = db.Column(db.String(100), nullable=True, index=True)
    source_system = db.Column(db.String(30), nullable=True)

    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def in_garantie(self):
        if not self.data_garantie_pana:
            return None
        return self.data_garantie_pana >= date.today()

    @property
    def zile_pana_mentenanta(self):
        if not self.urmatoarea_mentenanta:
            return None
        return (self.urmatoarea_mentenanta - date.today()).days

    def __repr__(self):
        return f'<Asset {self.serial or self.id}>'


class IssueBIM(db.Model):
    """
    Issue / Problema legata de un element BIM, spatiu sau zona.
    Compatibil conceptual cu BCF (BIM Collaboration Format).
    """
    __tablename__ = 'bim_issues'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    # Locatie - cel putin unul trebuie completat
    element_bim_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'), nullable=True, index=True)
    spatiu_id = db.Column(db.Integer, db.ForeignKey('bim_spatii.id'), nullable=True, index=True)
    nivel_id = db.Column(db.Integer, db.ForeignKey('bim_niveluri.id'), nullable=True, index=True)
    cladire_id = db.Column(db.Integer, db.ForeignKey('bim_cladiri.id'), nullable=True, index=True)

    cod = db.Column(db.String(50))  # ex: ISS-001
    titlu = db.Column(db.String(300), nullable=False)
    descriere = db.Column(db.Text)

    tip = db.Column(db.String(50), default='defect')
    # defect, conflict_proiectare, lipsa_executie, neconformitate, observatie, sugestie
    severitate = db.Column(db.String(20), default='medie')
    # mica, medie, mare, critica

    status = db.Column(db.String(30), default='deschis')
    # deschis, in_lucru, rezolvat, verificat, inchis, anulat

    raportat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    asignat_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_raportare = db.Column(db.Date, default=date.today)
    data_termen = db.Column(db.Date, nullable=True)
    data_rezolvare = db.Column(db.Date, nullable=True)

    # Camp BCF compatibil - pentru export/import .bcf
    bcf_topic_guid = db.Column(db.String(100), nullable=True, index=True)
    extern_id = db.Column(db.String(100), nullable=True, index=True)  # ID in alt issue tracker
    source_system = db.Column(db.String(30), nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_actualizare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relatii
    element = db.relationship('ElementBIM', backref=db.backref('issues', lazy='dynamic'))
    spatiu = db.relationship('Spatiu', backref=db.backref('issues', lazy='dynamic'))
    nivel = db.relationship('Nivel', backref=db.backref('issues', lazy='dynamic'))
    cladire = db.relationship('Cladire', backref=db.backref('issues', lazy='dynamic'))
    raportor = db.relationship('Utilizator', foreign_keys=[raportat_de_id],
                               backref='bim_issues_raportate')
    asignat = db.relationship('Utilizator', foreign_keys=[asignat_id],
                              backref='bim_issues_asignate')

    TIPURI = [
        ('defect', 'Defect'),
        ('conflict_proiectare', 'Conflict proiectare'),
        ('lipsa_executie', 'Lipsa executie'),
        ('neconformitate', 'Neconformitate'),
        ('observatie', 'Observatie'),
        ('sugestie', 'Sugestie'),
    ]

    SEVERITATI = [
        ('mica', 'Mica'),
        ('medie', 'Medie'),
        ('mare', 'Mare'),
        ('critica', 'Critica'),
    ]

    STATUSURI = [
        ('deschis', 'Deschis'),
        ('in_lucru', 'In lucru'),
        ('rezolvat', 'Rezolvat'),
        ('verificat', 'Verificat'),
        ('inchis', 'Inchis'),
        ('anulat', 'Anulat'),
    ]

    def __repr__(self):
        return f'<IssueBIM {self.cod or self.id} - {self.titlu[:40]}>'


class ModelBIM(db.Model):
    """
    Referinta catre un model BIM extern (IFC, Revit, viewer).
    Stocam path-ul sau URL-ul; modelul propriu-zis poate fi pe disk, S3, BIM server, etc.
    """
    __tablename__ = 'bim_modele'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    santier_id = db.Column(db.Integer, db.ForeignKey('bim_santiere.id'), nullable=True, index=True)
    cladire_id = db.Column(db.Integer, db.ForeignKey('bim_cladiri.id'), nullable=True, index=True)

    nume = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)
    tip = db.Column(db.String(20), default='ifc')
    # ifc, revit, dwg, navisworks, bcf, viewer_extern

    versiune = db.Column(db.String(50))  # ex: '1.0', 'rev. C'
    autor = db.Column(db.String(150))
    data_emitere = db.Column(db.Date)

    # Stocare
    fisier_path = db.Column(db.String(500))  # cale relativa in /uploads/
    fisier_marime = db.Column(db.Integer)  # bytes
    extern_url = db.Column(db.String(500))  # daca e gazduit extern (BIMx, Trimble Connect, etc.)

    # Statistici (populate dupa import)
    nr_elemente = db.Column(db.Integer, default=0)
    nr_spatii = db.Column(db.Integer, default=0)
    extern_id = db.Column(db.String(100), nullable=True, index=True)
    source_system = db.Column(db.String(30), nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    procesare_status = db.Column(db.String(20), default='nou')
    # nou, in_procesare, procesat, eroare
    procesare_log = db.Column(db.Text)

    incarcat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_incarcare = db.Column(db.DateTime, default=datetime.utcnow)

    # Relatii
    santier = db.relationship('Santier', backref=db.backref('modele', lazy='dynamic'))
    cladire = db.relationship('Cladire', backref=db.backref('modele', lazy='dynamic'))
    incarcat_de = db.relationship('Utilizator', backref='bim_modele_incarcate')

    TIPURI = [
        ('ifc', 'IFC (open standard, viewer intern)'),
        ('revit', 'Revit (.rvt)'),
        ('dwg', 'AutoCAD (.dwg)'),
        ('navisworks', 'Navisworks (.nwd)'),
        ('bcf', 'BCF (issues)'),
        ('viewer_extern', 'Viewer extern (URL)'),
    ]

    # Template-uri preset pentru viewere externe populare
    VIEWERE_EXTERNE = [
        ('Trimble Connect', 'https://web.connect.trimble.com/projects/PROJECT_ID/viewer?select={guid}'),
        ('Autodesk Viewer',  'https://viewer.autodesk.com/?urn=URN&select={guid}'),
        ('BIMx (Graphisoft)', 'https://bimx.graphisoft.com/m/MODEL_ID#guid={guid}'),
        ('BIMcollab',         'https://example.bimcollab.com/issue/{guid}'),
        ('Generic (custom)',  ''),
    ]

    @property
    def label_tip(self):
        for cod, label in self.TIPURI:
            if cod == self.tip:
                return label
        return self.tip

    @property
    def is_viewer_intern(self):
        """True daca modelul e IFC procesabil cu viewer-ul nostru intern."""
        return self.tip == 'ifc' and bool(self.fisier_path)

    @property
    def is_viewer_extern(self):
        """True daca modelul are URL extern."""
        return bool(self.extern_url)

    def get_external_url_for_guid(self, guid=None):
        """
        Returneaza URL-ul extern cu placeholder-ul {guid} substituit.
        Daca template-ul nu are {guid}, returneaza URL-ul ca atare.
        """
        if not self.extern_url:
            return None
        if guid and '{guid}' in self.extern_url:
            return self.extern_url.replace('{guid}', guid)
        return self.extern_url

    def __repr__(self):
        return f'<ModelBIM {self.nume} ({self.tip})>'


# ============================================================
# === LINKARE WORKFORCE - BIM ===
# Adaugam coloane FK opt. pe modelele workforce ca sa pot lega
# o activitate / un pontaj de un element BIM, spatiu sau zona.
# Aceste coloane sunt nullable - workforce continua sa functioneze
# si fara BIM activat.
# ============================================================
# NOTA: Coloanele se adauga programatic prin CLI flask migrate-bim,
# nu prin definitii in clasele de mai sus, ca sa NU rupem migrarile
# existente. Mapping-ul SQLAlchemy se face in app initialization.
# ============================================================


# ============================================================
# === EXTERNAL MAPPING - mapping cross-system polymorphic ===
# Permite ca aceeasi entitate BIM sa aiba identificatori
# in mai multe sisteme externe simultan:
#   ElementBIM #42 ->
#     IFC GUID (sursa: model X.ifc)
#     Revit ElementId (sursa: model Y.rvt)
#     Trimble Connect Object ID
#     CMMS asset code
# ============================================================

class ExternalMapping(db.Model):
    __tablename__ = 'bim_external_mappings'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    # Tip + ID al entitatii interne (pattern polymorphic, NU FK strict ca sa
    # mergem peste mai multe tabele)
    entity_type = db.Column(db.String(30), nullable=False, index=True)
    # 'santier', 'cladire', 'nivel', 'zona', 'spatiu', 'element_bim', 'asset', 'issue_bim', 'model_bim'
    entity_id = db.Column(db.Integer, nullable=False, index=True)

    # Sistem extern + identificator
    source_system = db.Column(db.String(30), nullable=False, index=True)
    # 'ifc', 'revit', 'bcf', 'trimble_connect', 'autodesk_bim360', 'bimx', 'graphisoft',
    # 'navisworks', 'solibri', 'bimcollab', 'plannerly', 'cmms_<name>', 'manual'
    extern_id = db.Column(db.String(200), nullable=False, index=True)

    # Referinta opt. catre modelul BIM din care s-a importat (daca e relevant)
    model_bim_id = db.Column(db.Integer, db.ForeignKey('bim_modele.id'), nullable=True, index=True)

    # Metadata extra (URL, label, source file, etc.) - JSON pentru flexibilitate
    metadata_json = db.Column(db.Text, nullable=True)

    last_synced_at = db.Column(db.DateTime, nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    # Relatii
    model_bim = db.relationship('ModelBIM', backref=db.backref('mappings', lazy='dynamic'))

    __table_args__ = (
        # Unicitate: aceeasi entitate nu poate avea 2 mapping-uri identice in acelasi sistem
        db.UniqueConstraint('entity_type', 'entity_id', 'source_system', 'extern_id',
                            name='uix_extmap_unique'),
        # Index pentru lookup rapid: cauta entitatea X dupa GUID Y
        db.Index('ix_extmap_lookup', 'source_system', 'extern_id'),
        db.Index('ix_extmap_entity', 'entity_type', 'entity_id'),
    )

    ENTITY_TYPES = [
        ('santier', 'Santier'),
        ('cladire', 'Cladire'),
        ('nivel', 'Nivel'),
        ('zona', 'Zona'),
        ('spatiu', 'Spatiu'),
        ('element_bim', 'ElementBIM'),
        ('asset', 'Asset'),
        ('issue_bim', 'IssueBIM'),
        ('model_bim', 'ModelBIM'),
    ]

    SOURCE_SYSTEMS = [
        ('ifc', 'IFC (open standard)'),
        ('revit', 'Autodesk Revit'),
        ('bcf', 'BCF (issues)'),
        ('trimble_connect', 'Trimble Connect'),
        ('autodesk_bim360', 'Autodesk BIM 360 / ACC'),
        ('bimx', 'Graphisoft BIMx'),
        ('archicad', 'Graphisoft ArchiCAD'),
        ('navisworks', 'Autodesk Navisworks'),
        ('solibri', 'Solibri Model Checker'),
        ('bimcollab', 'BIMcollab'),
        ('plannerly', 'Plannerly'),
        ('cmms', 'CMMS (asset management)'),
        ('manual', 'Manual'),
        ('other', 'Alt sistem'),
    ]

    @classmethod
    def find_entity(cls, source_system, extern_id):
        """
        Lookup invers: gaseste entitatea interna care corespunde unui ID extern.
        Returneaza tuple (entity_type, entity_id) sau (None, None).
        """
        m = cls.query.filter_by(source_system=source_system, extern_id=extern_id).first()
        if m:
            return (m.entity_type, m.entity_id)
        return (None, None)

    @classmethod
    def add_or_update(cls, entity_type, entity_id, source_system, extern_id,
                      model_bim_id=None, metadata=None, tenant_id=None):
        """Helper idempotent pentru a stoca mapping (UPSERT)."""
        existing = cls.query.filter_by(
            entity_type=entity_type, entity_id=entity_id,
            source_system=source_system, extern_id=extern_id,
        ).first()
        if existing:
            existing.last_synced_at = datetime.utcnow()
            if model_bim_id:
                existing.model_bim_id = model_bim_id
            if metadata is not None:
                import json as _json
                existing.metadata_json = _json.dumps(metadata, ensure_ascii=False) if isinstance(metadata, dict) else str(metadata)
            return existing
        m = cls(
            tenant_id=tenant_id,
            entity_type=entity_type, entity_id=entity_id,
            source_system=source_system, extern_id=extern_id,
            model_bim_id=model_bim_id,
            last_synced_at=datetime.utcnow(),
        )
        if metadata is not None:
            import json as _json
            m.metadata_json = _json.dumps(metadata, ensure_ascii=False) if isinstance(metadata, dict) else str(metadata)
        db.session.add(m)
        return m

    def __repr__(self):
        return f'<ExternalMapping {self.entity_type}:{self.entity_id} -> {self.source_system}:{self.extern_id[:20]}>'


# ============================================================
# AUDIT LOG (Faza 1 BIM foundation)
# Inregistreaza modificari pe entitatile BIM principale (start mic).
# Permite raportare "cine a modificat ce, cand" - precondititie pentru
# CDE workflow (status approval / change tracking) din Faza 3.
# ============================================================

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True, index=True)

    # Tinta actiunii
    entity_type = db.Column(db.String(50), nullable=False, index=True)  # 'element_bim', 'issue_bim', etc.
    entity_id = db.Column(db.Integer, nullable=True, index=True)

    # Tipul actiunii: create | update | delete | login | import | sync | other
    action = db.Column(db.String(30), nullable=False, index=True)

    # Diff (JSON serializat). Pentru update: doar campurile modificate.
    old_values_json = db.Column(db.Text, nullable=True)
    new_values_json = db.Column(db.Text, nullable=True)

    # Context optional (ex: IP, user-agent, request_id)
    context_json = db.Column(db.Text, nullable=True)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('Utilizator', foreign_keys=[user_id])
    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])

    __table_args__ = (
        db.Index('ix_audit_entity', 'entity_type', 'entity_id'),
        db.Index('ix_audit_tenant_ts', 'tenant_id', 'timestamp'),
    )

    def __repr__(self):
        return f'<AuditLog {self.action} {self.entity_type}:{self.entity_id} by user {self.user_id}>'


# ============================================================
# FEATURE FLAGS (Faza 1 BIM foundation)
# Permite activarea progresiva a feature-urilor noi (Fazele 2-8) per
# tenant sau global, fara redeploy. Default off pentru orice flag nou.
# ============================================================

class FeatureFlag(db.Model):
    __tablename__ = 'feature_flags'
    id = db.Column(db.Integer, primary_key=True)

    # Cheia flag-ului (kebab-case, prefixat cu modulul)
    # ex: 'bim-viewer-3d', 'bim-clash-detection', 'bim-iot-sensors'
    key = db.Column(db.String(80), nullable=False, index=True)

    # Scope: NULL = global; altfel se aplica per tenant
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    enabled = db.Column(db.Boolean, default=False, nullable=False)
    descriere = db.Column(db.String(300), nullable=True)
    config_json = db.Column(db.Text, nullable=True)  # parametri optionali per flag

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_modificare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])

    __table_args__ = (
        db.UniqueConstraint('key', 'tenant_id', name='uix_feature_flag_key_tenant'),
    )

    def __repr__(self):
        scope = f'tenant={self.tenant_id}' if self.tenant_id else 'global'
        return f'<FeatureFlag {self.key} {scope} enabled={self.enabled}>'


# ============================================================
# CDE WORKFLOW + VERSIONING (Faza 3 BIM Digital Twin)
# Inspirat din ISO 19650 (Common Data Environment).
# 1 ModelBIM (logic) -> N BIMModelVersion (fisiere fizice cu istoric).
# ============================================================

class BIMModelVersion(db.Model):
    """
    O versiune a unui model BIM. Suporta workflow CDE:
        wip -> shared -> published -> archived
        oricand: -> rejected
    """
    __tablename__ = 'bim_model_versions'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    model_id = db.Column(db.Integer, db.ForeignKey('bim_modele.id'), nullable=False, index=True)

    # Eticheta versiunii (ex: 'v1.0', 'rev. C', '2026-05-06_AS_BUILT')
    versiune = db.Column(db.String(50), nullable=False)

    # Disciplina (ARH, STR, MEP, ELE, ...) - util pentru federation pe disciplina
    disciplina = db.Column(db.String(20), nullable=True, index=True)

    descriere = db.Column(db.Text, nullable=True)

    # Status CDE workflow ISO 19650
    # wip       - work in progress (in dezvoltare, nu se vede pentru altii)
    # shared    - partajat (vizibil pentru disciplinele coordonate)
    # published - publicat (oficial, folosit pentru executie)
    # rejected  - respins (nu trece la published)
    # archived  - arhivat (versiune veche, pastrata istoric)
    status = db.Column(db.String(20), default='wip', nullable=False, index=True)

    # Stocare
    fisier_path = db.Column(db.String(500), nullable=True)  # cale relativa
    fisier_marime = db.Column(db.Integer, nullable=True)
    fisier_hash = db.Column(db.String(64), nullable=True)  # SHA-256 pentru verificare integritate

    # Externe
    extern_url = db.Column(db.String(500), nullable=True)
    extern_id = db.Column(db.String(100), nullable=True, index=True)
    source_system = db.Column(db.String(30), nullable=True)

    # Audit/workflow timestamps
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_share = db.Column(db.DateTime, nullable=True)
    data_publicare = db.Column(db.DateTime, nullable=True)
    data_respingere = db.Column(db.DateTime, nullable=True)
    data_arhivare = db.Column(db.DateTime, nullable=True)

    # Cine a uploadat / aprobat
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True, index=True)
    aprobat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True, index=True)

    # Comentariu opțional la respingere
    comentariu_aprobare = db.Column(db.Text, nullable=True)

    # Relatii
    model = db.relationship('ModelBIM', backref=db.backref('versiuni', lazy='dynamic',
                                                            cascade='all, delete-orphan',
                                                            order_by='BIMModelVersion.data_creare.desc()'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])
    aprobat_de = db.relationship('Utilizator', foreign_keys=[aprobat_de_id])

    STATUSURI = [
        ('wip', 'Work in Progress'),
        ('shared', 'Partajat (Shared)'),
        ('published', 'Publicat'),
        ('rejected', 'Respins'),
        ('archived', 'Arhivat'),
    ]

    # Tranzitii valide (status_curent -> set status posibili)
    # Conform ISO 19650 simplificat
    TRANZITII_VALIDE = {
        'wip':       {'shared', 'archived'},
        'shared':    {'published', 'rejected', 'wip', 'archived'},
        'published': {'archived'},
        'rejected':  {'wip', 'archived'},
        'archived':  set(),  # terminal
    }

    __table_args__ = (
        db.UniqueConstraint('model_id', 'versiune', name='uix_model_version_label'),
        db.Index('ix_model_version_status', 'model_id', 'status'),
    )

    @property
    def label_status(self):
        for cod, label in self.STATUSURI:
            if cod == self.status:
                return label
        return self.status

    @property
    def is_terminal(self):
        return self.status == 'archived'

    @property
    def is_visible_to_others(self):
        """True daca versiunea e vizibila pentru alti utilizatori (in afara autorului)."""
        return self.status in ('shared', 'published')

    @property
    def is_official(self):
        """True daca versiunea e considerata oficiala (folosibila in executie)."""
        return self.status == 'published'

    def can_transition_to(self, new_status: str) -> bool:
        """Verifica daca tranzitia status_curent -> new_status e permisa."""
        return new_status in self.TRANZITII_VALIDE.get(self.status, set())

    def __repr__(self):
        return f'<BIMModelVersion {self.versiune} of model {self.model_id} [{self.status}]>'


# ============================================================
# RULE ENGINE (Faza 4 BIM Digital Twin)
# Reguli declarative pentru model checking (analog Solibri/BIM Collab).
# DSL JSON simplu: selector + constraint. Engine genereaza RuleViolation.
# ============================================================

class BIMRule(db.Model):
    """
    O regula declarativa de model checking. Stocata ca JSON pentru
    flexibilitate, dar cu cod si nume strict typed pentru UI.

    Exemplu definitie_json:
        {
          "selector": {"tip_element": "wall"},
          "constraint": {"required_properties": ["fire_rating"]}
        }
    """
    __tablename__ = 'bim_rules'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    cod = db.Column(db.String(50), nullable=False, index=True)  # ex: 'RULE-001-WALL-FIRE'
    nume = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text, nullable=True)

    # 'mandatory' / 'best_practice' / 'naming' / 'safety' / 'mep' / 'arh' / 'str'
    categorie = db.Column(db.String(30), default='best_practice', nullable=False, index=True)
    severitate = db.Column(db.String(20), default='medie', nullable=False)
    # mica | medie | mare | critica (mapping cu IssueBIM)

    # Tipul regulii (controleaza ce evaluator se foloseste)
    # 'required_properties' | 'forbidden_in_zone' | 'naming_convention' | 'min_clearance'
    tip = db.Column(db.String(30), default='required_properties', nullable=False)

    # Definitia full a regulii in JSON (selector + constraint)
    definitie_json = db.Column(db.Text, nullable=False)

    activa = db.Column(db.Boolean, default=True, nullable=False, index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_modificare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    SEVERITATI = [('mica', 'Mica'), ('medie', 'Medie'), ('mare', 'Mare'), ('critica', 'Critica')]
    CATEGORII = [
        ('mandatory', 'Obligatoriu'),
        ('best_practice', 'Best practice'),
        ('naming', 'Conventie denumire'),
        ('safety', 'Siguranta'),
        ('arh', 'Arhitectura'),
        ('str', 'Structura'),
        ('mep', 'MEP'),
    ]
    TIPURI = [
        ('required_properties', 'Proprietati obligatorii'),
        ('naming_convention', 'Conventie denumire (regex)'),
        ('forbidden_in_zone', 'Element interzis in zona'),
        ('min_clearance', 'Distanta minima'),
    ]

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'cod', name='uix_rule_tenant_cod'),
    )

    def get_definition(self):
        """Parseaza definitie_json -> dict."""
        import json
        try:
            return json.loads(self.definitie_json or '{}')
        except (ValueError, TypeError):
            return {}

    def __repr__(self):
        return f'<BIMRule {self.cod} {self.tip}>'


class RuleViolation(db.Model):
    """
    O violare a unei reguli, detectata la rularea engine-ului.
    Poate fi convertita in IssueBIM daca admin/manager confirma.
    """
    __tablename__ = 'bim_rule_violations'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    rule_id = db.Column(db.Integer, db.ForeignKey('bim_rules.id'), nullable=False, index=True)
    element_bim_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'), nullable=True, index=True)
    spatiu_id = db.Column(db.Integer, db.ForeignKey('bim_spatii.id'), nullable=True, index=True)

    # Run-ul care a produs violarea (pentru a putea filtra ultima rulare)
    run_id = db.Column(db.String(36), nullable=True, index=True)

    # 'noua' | 'confirmata' | 'rezolvata' | 'falsa'
    status = db.Column(db.String(20), default='noua', nullable=False, index=True)

    mesaj = db.Column(db.String(500), nullable=False)
    detalii_json = db.Column(db.Text, nullable=True)

    issue_id = db.Column(db.Integer, db.ForeignKey('bim_issues.id'), nullable=True)
    # FK populat cand violarea e convertita in IssueBIM oficial

    data_detectie = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    rule = db.relationship('BIMRule', foreign_keys=[rule_id], backref=db.backref('violari', lazy='dynamic'))
    element_bim = db.relationship('ElementBIM', foreign_keys=[element_bim_id])
    spatiu = db.relationship('Spatiu', foreign_keys=[spatiu_id])
    issue = db.relationship('IssueBIM', foreign_keys=[issue_id])

    __table_args__ = (
        db.Index('ix_violation_rule_status', 'rule_id', 'status'),
    )

    def __repr__(self):
        return f'<RuleViolation rule={self.rule_id} elem={self.element_bim_id} status={self.status}>'


# ============================================================
# CLASH DETECTION (Faza 4)
# ClashRun = o sesiune de detectie. ClashResult = un clash concret
# intre 2 elemente. Pe modele fara geometrie completa, fallback la
# logic checks (GUID duplicat, suprasaturare spatii, etc.).
# ============================================================

class ClashRun(db.Model):
    """O sesiune de detectie clash-uri pe un model/santier."""
    __tablename__ = 'bim_clash_runs'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    # Scope: model individual sau santier
    model_id = db.Column(db.Integer, db.ForeignKey('bim_modele.id'), nullable=True, index=True)
    santier_id = db.Column(db.Integer, db.ForeignKey('bim_santiere.id'), nullable=True, index=True)

    # Tipul detectiei: 'geometric' (AABB) | 'logic' (GUID/spatiu/props) | 'mixed'
    tip = db.Column(db.String(20), default='mixed', nullable=False)

    # Statistici rezultate (populate la finalul rularii)
    nr_clash_uri = db.Column(db.Integer, default=0)
    nr_critica = db.Column(db.Integer, default=0)
    nr_mare = db.Column(db.Integer, default=0)
    nr_medie = db.Column(db.Integer, default=0)
    nr_mica = db.Column(db.Integer, default=0)

    # Status: 'rulare' | 'finalizat' | 'eroare'
    status = db.Column(db.String(20), default='finalizat', nullable=False)

    durata_ms = db.Column(db.Integer, nullable=True)
    log = db.Column(db.Text, nullable=True)

    data_rulare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    rulat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    rulat_de = db.relationship('Utilizator', foreign_keys=[rulat_de_id])
    model = db.relationship('ModelBIM', foreign_keys=[model_id])
    santier = db.relationship('Santier', foreign_keys=[santier_id])

    def __repr__(self):
        return f'<ClashRun {self.id} tip={self.tip} clash-uri={self.nr_clash_uri}>'


class ClashResult(db.Model):
    """Un clash concret intre 2 elemente."""
    __tablename__ = 'bim_clash_results'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    run_id = db.Column(db.Integer, db.ForeignKey('bim_clash_runs.id'), nullable=False, index=True)

    element_a_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'), nullable=False, index=True)
    element_b_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'), nullable=False, index=True)

    # 'hard' (intersectie reala) | 'soft' (sub clearance) | 'duplicate' (GUID dublu)
    tip = db.Column(db.String(20), default='hard', nullable=False, index=True)
    severitate = db.Column(db.String(20), default='medie', nullable=False, index=True)

    # 'noua' | 'rezolvata' | 'ignorata' | 'falsa'
    status = db.Column(db.String(20), default='noua', nullable=False, index=True)

    mesaj = db.Column(db.String(500), nullable=False)
    detalii_json = db.Column(db.Text, nullable=True)
    # ex: {"overlap_volume": 0.04, "axes": ["x", "z"]}

    # Daca a fost convertit in IssueBIM
    issue_id = db.Column(db.Integer, db.ForeignKey('bim_issues.id'), nullable=True)

    data_detectie = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    run = db.relationship('ClashRun', foreign_keys=[run_id], backref=db.backref('rezultate', lazy='dynamic',
                                                                                 cascade='all, delete-orphan'))
    element_a = db.relationship('ElementBIM', foreign_keys=[element_a_id])
    element_b = db.relationship('ElementBIM', foreign_keys=[element_b_id])
    issue = db.relationship('IssueBIM', foreign_keys=[issue_id])

    __table_args__ = (
        db.Index('ix_clash_run_severity', 'run_id', 'severitate'),
        db.Index('ix_clash_status', 'status'),
    )

    def __repr__(self):
        return f'<ClashResult run={self.run_id} {self.element_a_id}<->{self.element_b_id} {self.tip}>'


# ============================================================
# 4D SCHEDULE (Faza 5 BIM Digital Twin)
# Link element BIM <-> task cu interval planificat (4D = time).
# Vizualizare construction sequencing + progres.
# ============================================================

class BIMTaskSchedule(db.Model):
    """
    Schedule entry pentru un element BIM. Reprezinta planificarea
    constructiei elementului (cand se construieste, cand e gata).
    Pentru un element pot exista mai multe entries (excavatie, fundatie,
    structura, finisaje), folosind 'faza' pentru a le diferentia.
    """
    __tablename__ = 'bim_task_schedules'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    element_bim_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'),
                                nullable=False, index=True)

    # Faza constructiei (decoupling de RaportActivitate.activitate_principala)
    faza = db.Column(db.String(50), nullable=False)
    # ex: 'excavatie', 'fundatie', 'structura', 'finisaje', 'mep', 'finisaje_finale'

    # Disciplina (pentru filtrare in timeline)
    disciplina = db.Column(db.String(20), nullable=True, index=True)

    descriere = db.Column(db.Text, nullable=True)

    # Planificat
    data_start_plan = db.Column(db.Date, nullable=False, index=True)
    data_sfarsit_plan = db.Column(db.Date, nullable=False, index=True)

    # Real (populate pe parcurs cu actuals din pontaje sau manual)
    data_start_real = db.Column(db.Date, nullable=True)
    data_sfarsit_real = db.Column(db.Date, nullable=True)

    # Progres % (0..100)
    progres_pct = db.Column(db.Integer, default=0, nullable=False)

    # Status: 'planificat' | 'in_curs' | 'finalizat' | 'amanat' | 'anulat'
    status = db.Column(db.String(20), default='planificat', nullable=False, index=True)

    # FK opt. catre raport activitate (pentru link cu pontajele)
    raport_activitate_id = db.Column(db.Integer,
                                      db.ForeignKey('rapoarte_activitati.id'),
                                      nullable=True, index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_modificare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    element = db.relationship('ElementBIM', foreign_keys=[element_bim_id],
                              backref=db.backref('task_schedules', lazy='dynamic'))
    raport = db.relationship('RaportActivitate', foreign_keys=[raport_activitate_id])
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    STATUSURI = [
        ('planificat', 'Planificat'),
        ('in_curs', 'In curs'),
        ('finalizat', 'Finalizat'),
        ('amanat', 'Amanat'),
        ('anulat', 'Anulat'),
    ]

    FAZE_TIPICE = [
        'excavatie', 'fundatie', 'structura', 'inchideri',
        'mep_grobschnitt', 'mep_final',
        'finisaje_brute', 'finisaje_fine', 'punere_in_functiune',
    ]

    __table_args__ = (
        db.Index('ix_schedule_element_faza', 'element_bim_id', 'faza'),
        db.Index('ix_schedule_dates', 'data_start_plan', 'data_sfarsit_plan'),
    )

    @property
    def durata_zile_plan(self) -> int:
        if self.data_start_plan and self.data_sfarsit_plan:
            return (self.data_sfarsit_plan - self.data_start_plan).days
        return 0

    @property
    def este_intarziat(self) -> bool:
        if self.status == 'finalizat' or not self.data_sfarsit_plan:
            return False
        return date.today() > self.data_sfarsit_plan and self.progres_pct < 100

    def is_visible_at(self, data: 'date') -> bool:
        """True daca elementul e (partial sau total) construit la data data."""
        if not self.data_start_plan:
            return False
        return data >= self.data_start_plan

    def __repr__(self):
        return f'<BIMTaskSchedule {self.element_bim_id} {self.faza} [{self.status}]>'


# ============================================================
# 5D COST (Faza 5)
# Cost per element BIM (cantitate * pret unitar). Agregare pe
# disciplina, faza, cladire, santier. Comparatie cu manopera
# reala din Pontaj.
# ============================================================

class BIMCostItem(db.Model):
    """
    Un item de cost asociat unui element BIM. Permite breakdown
    detaliat (material/manopera/echipament/transport).
    """
    __tablename__ = 'bim_cost_items'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    element_bim_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'),
                                nullable=False, index=True)

    # Categorie cost: 'material' | 'manopera' | 'echipament' | 'transport' | 'utilitati' | 'altul'
    categorie = db.Column(db.String(30), default='material', nullable=False, index=True)

    # Faza la care apare costul (pentru integrare cu BIMTaskSchedule)
    faza = db.Column(db.String(50), nullable=True, index=True)

    descriere = db.Column(db.String(300), nullable=False)
    unitate = db.Column(db.String(20), nullable=False, default='buc')
    # buc, m, m2, m3, kg, ml, ora, etc.

    cantitate = db.Column(db.Numeric(12, 3), default=1, nullable=False)
    pret_unitar = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    # Valuta: implicit RON; per tenant config in viitor
    valuta = db.Column(db.String(3), default='RON', nullable=False)

    # Tip cost: 'planificat' (din deviz) sau 'real' (din facturi/pontaje)
    tip = db.Column(db.String(20), default='planificat', nullable=False, index=True)

    referinta_extern = db.Column(db.String(100), nullable=True)
    # ex: cod articol din SAP, cod ofertă, etc.

    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_modificare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    element = db.relationship('ElementBIM', foreign_keys=[element_bim_id],
                              backref=db.backref('cost_items', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    CATEGORII = [
        ('material', 'Material'),
        ('manopera', 'Manopera'),
        ('echipament', 'Echipament'),
        ('transport', 'Transport'),
        ('utilitati', 'Utilitati'),
        ('altul', 'Altul'),
    ]
    TIPURI = [
        ('planificat', 'Planificat (deviz)'),
        ('real', 'Real (facturat/realizat)'),
    ]
    UNITATI = ['buc', 'm', 'm2', 'm3', 'kg', 'ml', 'ora', 't', 'set']

    __table_args__ = (
        db.Index('ix_cost_element_categorie', 'element_bim_id', 'categorie'),
    )

    @property
    def total(self):
        """Cantitate * pret_unitar."""
        try:
            return float(self.cantitate or 0) * float(self.pret_unitar or 0)
        except (ValueError, TypeError):
            return 0.0

    def __repr__(self):
        return (f'<BIMCostItem {self.element_bim_id} {self.categorie}'
                f' {self.cantitate}{self.unitate}*{self.pret_unitar}={self.total}>')


# ============================================================
# DIGITAL TWIN / IoT (Faza 6 BIM Digital Twin)
# Sensori live, time-series readings, alerte automate.
# ============================================================

class Senzor(db.Model):
    """
    Definirea unui senzor IoT atasat unui element BIM sau spatiu.
    Senzorul are un token unic (api_key) folosit pentru ingest.
    """
    __tablename__ = 'bim_senzori'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    # Locatia: cel putin unul trebuie completat (element / spatiu / cladire)
    element_bim_id = db.Column(db.Integer, db.ForeignKey('bim_elemente.id'),
                                nullable=True, index=True)
    spatiu_id = db.Column(db.Integer, db.ForeignKey('bim_spatii.id'),
                           nullable=True, index=True)
    cladire_id = db.Column(db.Integer, db.ForeignKey('bim_cladiri.id'),
                            nullable=True, index=True)

    # Identificare
    cod = db.Column(db.String(80), nullable=False, index=True)  # ex: TEMP-A-101
    nume = db.Column(db.String(200), nullable=False)

    # Tipul si unitatea masurate
    # 'temperatura' | 'umiditate' | 'co2' | 'energie' | 'vibratie' |
    # 'ocupare' | 'presiune' | 'debit' | 'altul'
    tip = db.Column(db.String(30), nullable=False, index=True)
    unitate = db.Column(db.String(20), nullable=False, default='-')
    # ex: '°C', '%', 'ppm', 'kWh', 'm/s²', 'persoane', 'bar', 'l/min'

    # Threshold-uri pentru auto-alert (NULL = inactiv)
    threshold_min = db.Column(db.Numeric(15, 4), nullable=True)
    threshold_max = db.Column(db.Numeric(15, 4), nullable=True)

    # Token auth pentru ingest (generat la creare; rotabil)
    api_key = db.Column(db.String(64), nullable=False, unique=True, index=True)

    # Activ / sterso logic
    activ = db.Column(db.Boolean, default=True, nullable=False, index=True)

    descriere = db.Column(db.Text, nullable=True)
    producator = db.Column(db.String(100), nullable=True)
    model_hardware = db.Column(db.String(100), nullable=True)
    serial = db.Column(db.String(100), nullable=True)

    # Ultima citire cache (pentru afisare rapida fara JOIN)
    ultima_valoare = db.Column(db.Numeric(15, 4), nullable=True)
    ultima_citire_at = db.Column(db.DateTime, nullable=True, index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_modificare = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    element_bim = db.relationship('ElementBIM', foreign_keys=[element_bim_id],
                                   backref=db.backref('senzori', lazy='dynamic'))
    spatiu = db.relationship('Spatiu', foreign_keys=[spatiu_id],
                             backref=db.backref('senzori', lazy='dynamic'))
    cladire = db.relationship('Cladire', foreign_keys=[cladire_id],
                              backref=db.backref('senzori', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    TIPURI = [
        ('temperatura', 'Temperatura'),
        ('umiditate', 'Umiditate'),
        ('co2', 'CO2'),
        ('energie', 'Energie'),
        ('vibratie', 'Vibratie'),
        ('ocupare', 'Ocupare'),
        ('presiune', 'Presiune'),
        ('debit', 'Debit'),
        ('altul', 'Altul'),
    ]

    UNITATI_DEFAULT = {
        'temperatura': '°C',
        'umiditate': '%',
        'co2': 'ppm',
        'energie': 'kWh',
        'vibratie': 'm/s²',
        'ocupare': 'persoane',
        'presiune': 'bar',
        'debit': 'l/min',
    }

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'cod', name='uix_senzor_tenant_cod'),
        db.Index('ix_senzor_tip_activ', 'tip', 'activ'),
    )

    @property
    def is_alarming(self) -> bool:
        """True daca ultima valoare e in afara threshold-urilor."""
        if self.ultima_valoare is None:
            return False
        try:
            v = float(self.ultima_valoare)
            if self.threshold_min is not None and v < float(self.threshold_min):
                return True
            if self.threshold_max is not None and v > float(self.threshold_max):
                return True
        except (ValueError, TypeError):
            pass
        return False

    @property
    def label_tip(self):
        for cod, label in self.TIPURI:
            if cod == self.tip:
                return label
        return self.tip

    def __repr__(self):
        return f'<Senzor {self.cod} ({self.tip}) elem={self.element_bim_id}>'


class SensorReading(db.Model):
    """
    Citire individuala de la un senzor. Append-only (insert frecvent,
    update niciodata). Indexat pe (senzor_id, ts DESC) pentru query
    rapid de "ultimele N citiri" si range queries.

    Pe MySQL pe PythonAnywhere: scaleaza pana la cateva milioane de
    randuri fara probleme. Cleanup retentiv via CLI sau cron daca e
    nevoie de retentie limitata.
    """
    __tablename__ = 'bim_sensor_readings'
    # Integer e suficient pentru >2 mld randuri si auto-increment functioneaza
    # cross-dialect (BigInteger pe SQLite nu auto-increment-eaza).
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    senzor_id = db.Column(db.Integer, db.ForeignKey('bim_senzori.id'),
                           nullable=False, index=True)

    ts = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    valoare = db.Column(db.Numeric(15, 4), nullable=False)
    # Calitate citire: 'ok' | 'estimat' | 'eroare' | 'maintenance'
    calitate = db.Column(db.String(20), default='ok', nullable=False)
    # Metadata raw (json) - util pentru debugging
    meta_json = db.Column(db.Text, nullable=True)

    senzor = db.relationship('Senzor', foreign_keys=[senzor_id],
                             backref=db.backref('readings', lazy='dynamic'))

    __table_args__ = (
        db.Index('ix_reading_senzor_ts', 'senzor_id', 'ts'),
    )

    def __repr__(self):
        return f'<SensorReading senzor={self.senzor_id} {self.ts.isoformat() if self.ts else ""} val={self.valoare}>'


class SensorAlert(db.Model):
    """
    Alerta generata automat cand o citire iese din threshold.
    Status workflow: 'noua' -> 'confirmata' / 'falsa' -> 'rezolvata'.
    """
    __tablename__ = 'bim_sensor_alerts'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    senzor_id = db.Column(db.Integer, db.ForeignKey('bim_senzori.id'),
                           nullable=False, index=True)

    # Tipul alertei
    # 'sub_min' | 'peste_max' | 'offline' | 'eroare_calitate'
    tip = db.Column(db.String(20), nullable=False)
    severitate = db.Column(db.String(20), default='medie', nullable=False, index=True)

    valoare = db.Column(db.Numeric(15, 4), nullable=True)
    threshold_violat = db.Column(db.Numeric(15, 4), nullable=True)

    mesaj = db.Column(db.String(500), nullable=False)

    # Status: 'noua' | 'confirmata' | 'falsa' | 'rezolvata'
    status = db.Column(db.String(20), default='noua', nullable=False, index=True)

    # Promovare la IssueBIM oficial (opt)
    issue_id = db.Column(db.Integer, db.ForeignKey('bim_issues.id'), nullable=True)

    data_alerta = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    data_confirmare = db.Column(db.DateTime, nullable=True)
    data_rezolvare = db.Column(db.DateTime, nullable=True)
    confirmat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    senzor = db.relationship('Senzor', foreign_keys=[senzor_id],
                             backref=db.backref('alerte', lazy='dynamic'))
    issue = db.relationship('IssueBIM', foreign_keys=[issue_id])
    confirmat_de = db.relationship('Utilizator', foreign_keys=[confirmat_de_id])

    __table_args__ = (
        db.Index('ix_alert_senzor_status', 'senzor_id', 'status'),
    )

    def __repr__(self):
        return f'<SensorAlert senzor={self.senzor_id} {self.tip} {self.status}>'


# ============================================================
# REAL-TIME COLLAB + KANBAN (Faza 7)
# Comments pe issues, presence heartbeat, event stream pentru SSE.
# ============================================================

class BIMComment(db.Model):
    """
    Comentariu pe un IssueBIM. Poate fi sub-thread (parent_id) sau root.
    """
    __tablename__ = 'bim_comments'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    issue_id = db.Column(db.Integer, db.ForeignKey('bim_issues.id'),
                          nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('bim_comments.id'),
                           nullable=True, index=True)

    autor_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'),
                          nullable=False, index=True)

    text = db.Column(db.Text, nullable=False)
    mentions = db.Column(db.String(500), nullable=True)
    # JSON list cu ID-uri @mentions: '[2, 5, 8]'

    # Soft delete
    sters = db.Column(db.Boolean, default=False, nullable=False)
    sters_la = db.Column(db.DateTime, nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow,
                             nullable=False, index=True)
    data_editare = db.Column(db.DateTime, default=datetime.utcnow,
                              onupdate=datetime.utcnow)

    issue = db.relationship('IssueBIM', foreign_keys=[issue_id],
                            backref=db.backref('comentarii', lazy='dynamic',
                                               order_by='BIMComment.data_creare'))
    autor = db.relationship('Utilizator', foreign_keys=[autor_id])
    parent = db.relationship('BIMComment', remote_side='BIMComment.id',
                             backref=db.backref('replies', lazy='dynamic'))

    __table_args__ = (
        db.Index('ix_comment_issue_data', 'issue_id', 'data_creare'),
    )

    def __repr__(self):
        return f'<BIMComment issue={self.issue_id} autor={self.autor_id}>'


class UserPresence(db.Model):
    """
    Presence heartbeat per user. Update la fiecare 30s pe parcursul
    timpului in care user-ul are pagina deschisa.
    """
    __tablename__ = 'bim_user_presence'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'),
                         nullable=False, unique=True, index=True)

    # Contextul curent (ce vede user-ul)
    context_type = db.Column(db.String(30), nullable=True)
    # 'kanban' | 'viewer_federat' | 'sensor_detaliu' | etc.
    context_id = db.Column(db.Integer, nullable=True)
    # ex: santier_id pentru kanban, model_id pentru viewer

    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow,
                              nullable=False, index=True)

    # Cache cu numele user-ului (pentru a evita JOIN frecvent)
    user_nume = db.Column(db.String(150), nullable=True)

    user = db.relationship('Utilizator', foreign_keys=[user_id])

    def __repr__(self):
        return f'<UserPresence user={self.user_id} context={self.context_type}:{self.context_id}>'


class RealtimeEvent(db.Model):
    """
    Eveniment publicat pentru consum prin SSE stream.
    Append-only; cleanup periodic (cron sau la limit).

    Tipuri:
        'issue_status_change' | 'comment_new' | 'sensor_alert' |
        'presence_join' | 'presence_leave' | 'model_version_changed'
    """
    __tablename__ = 'bim_realtime_events'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    # Scope: project_id (proiect) sau santier_id (santier)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                            nullable=True, index=True)
    santier_id = db.Column(db.Integer, db.ForeignKey('bim_santiere.id'),
                            nullable=True, index=True)

    event_type = db.Column(db.String(40), nullable=False, index=True)

    # Payload JSON cu detalii (issue_id, comment_id, sensor_id, etc.)
    payload_json = db.Column(db.Text, nullable=True)

    # Cine a generat evenimentul (poate fi None pentru system events)
    user_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow,
                            nullable=False, index=True)

    user = db.relationship('Utilizator', foreign_keys=[user_id])
    proiect = db.relationship('Proiect', foreign_keys=[proiect_id])
    santier = db.relationship('Santier', foreign_keys=[santier_id])

    __table_args__ = (
        db.Index('ix_event_scope', 'proiect_id', 'santier_id', 'id'),
        db.Index('ix_event_created', 'created_at'),
    )

    def __repr__(self):
        return f'<RealtimeEvent #{self.id} {self.event_type} santier={self.santier_id}>'


# ============================================================
# RBAC FIN (Faza 8) — roluri pe scope BIM
# Conform ISO 19650: Information Manager, Lead Designer per disciplina,
# Task Team Manager, Reviewer, Viewer.
# ============================================================

class BIMRoleAssignment(db.Model):
    """
    Asignare rol pentru un user pe un scope BIM specific.
    Un user poate avea mai multe asignari (ex: Lead Designer pe ARH la
    santier 1 + Reviewer global pe tenant).
    """
    __tablename__ = 'bim_role_assignments'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'),
                         nullable=False, index=True)

    # Numele rolului (din ROLURI sau custom)
    rol = db.Column(db.String(40), nullable=False, index=True)
    # 'information_manager' | 'lead_designer' | 'task_team_manager' |
    # 'reviewer' | 'viewer' | 'cost_manager' | 'iot_operator'

    # Scope: ce scope acopera rolul
    # 'global' (orice) | 'santier' | 'cladire' | 'disciplina' | 'proiect'
    scope_type = db.Column(db.String(20), default='global', nullable=False, index=True)
    scope_id = db.Column(db.Integer, nullable=True, index=True)
    # Pentru scope_type='disciplina' folosim scope_disciplina (codul ARH/STR/etc.)
    scope_disciplina = db.Column(db.String(20), nullable=True, index=True)

    activ = db.Column(db.Boolean, default=True, nullable=False, index=True)
    data_start = db.Column(db.Date, nullable=True)
    data_sfarsit = db.Column(db.Date, nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    user = db.relationship('Utilizator', foreign_keys=[user_id],
                           backref=db.backref('bim_role_assignments', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    ROLURI = [
        ('information_manager', 'Information Manager (project lead)'),
        ('lead_designer',       'Lead Designer (per disciplina)'),
        ('task_team_manager',   'Task Team Manager'),
        ('reviewer',            'Reviewer (read-only published)'),
        ('viewer',              'Viewer (read-only general)'),
        ('cost_manager',        'Cost Manager (5D)'),
        ('iot_operator',        'IoT Operator (ingest only)'),
    ]
    SCOPE_TYPES = [
        ('global',     'Global (tot tenant-ul)'),
        ('proiect',    'Proiect specific'),
        ('santier',    'Santier specific'),
        ('cladire',    'Cladire specifica'),
        ('disciplina', 'Disciplina (ARH, STR, ...)'),
    ]

    __table_args__ = (
        db.Index('ix_rba_user_rol_scope', 'user_id', 'rol', 'scope_type'),
    )

    def is_in_force(self, today=None) -> bool:
        """True daca rolul e activ azi (intre data_start si data_sfarsit)."""
        if not self.activ:
            return False
        today = today or date.today()
        if self.data_start and today < self.data_start:
            return False
        if self.data_sfarsit and today > self.data_sfarsit:
            return False
        return True

    def __repr__(self):
        scope = f'{self.scope_type}:{self.scope_id or self.scope_disciplina or "*"}'
        return f'<BIMRoleAssignment user={self.user_id} {self.rol} {scope}>'


# ============================================================
# API TOKENS (Faza 8) — token-auth pentru API publica
# ============================================================

class ApiToken(db.Model):
    """
    Token API pentru integrari externe (BI tools, mobile apps, automation).
    Scope-uri JSON lista de actiuni permise.
    """
    __tablename__ = 'bim_api_tokens'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    # Token-ul propriu-zis (64 hex chars). Stocat plain — invalidam prin
    # rotatie / dezactivare. Tokenul nu trebuie sa fie inghitit usor.
    token = db.Column(db.String(64), nullable=False, unique=True, index=True)

    # Etichete pentru UI
    nume = db.Column(db.String(150), nullable=False)
    descriere = db.Column(db.Text, nullable=True)

    # Owner: user-ul care a creat (vine in 'authenticated_user' la auth via token)
    owner_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'),
                          nullable=False, index=True)

    # Lista de scope-uri permise (JSON list of strings).
    # ex: ["bim:read", "bim:write_issues", "iot:ingest"]
    scopes_json = db.Column(db.Text, nullable=False, default='[]')

    activ = db.Column(db.Boolean, default=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)
    last_used_at = db.Column(db.DateTime, nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owner = db.relationship('Utilizator', foreign_keys=[owner_id])

    SCOPES_DISPONIBILE = [
        ('bim:read',           'Citire BIM (toate datele)'),
        ('bim:write_issues',   'Scriere issues + comentarii'),
        ('iot:ingest',         'Ingest date senzori (token per-senzor recomandat)'),
        ('iot:read',           'Citire date senzori'),
        ('cost:read',          'Citire date cost (5D)'),
        ('schedule:read',      'Citire date schedule (4D)'),
        ('admin:tokens',       'Management tokens (admin)'),
    ]

    @property
    def scopes(self) -> list[str]:
        import json as _json
        try:
            return _json.loads(self.scopes_json or '[]')
        except (ValueError, TypeError):
            return []

    @scopes.setter
    def scopes(self, value: list[str]):
        import json as _json
        self.scopes_json = _json.dumps(list(value), ensure_ascii=False)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and datetime.utcnow() > self.expires_at)

    def has_scope(self, scope: str) -> bool:
        scopes = self.scopes
        return scope in scopes or '*' in scopes

    def __repr__(self):
        return f'<ApiToken {self.nume} owner={self.owner_id} scopes={len(self.scopes)}>'


# ============================================================
# FAZA 9 - CONTRACT & PROJECT CONTROLS
#
# Modul aditional (gated pe feature flag 'controale-contract', default OFF):
#   A. Contract + termene contractuale + termene urmarite (alerte 30-zile)
#   B. Program de referinta (import MS Project XML) + taskuri ierarhice
#   C. Oferta + BoQ (deviz) + cantitati executate lunar + situatii lunare
#      + raport lucrari lunar la nivel proiect (aggregator)
#   D. Corespondenta + revendicari + 3 tabele M:N
#      (revendicari_termeni / revendicari_taskuri / revendicari_cantitati)
#   E. Procese verbale + anexe polimorfice + inbox notificari + reguli notificare
#
# Conventii respectate (identic cu fazele 1-8):
#   - tenant_id nullable FK pe TOATE tabelele
#   - data_creare + creat_de_id pe entitatile editabile
#   - status / tip fields ca String(20-40) + class attr STATUSES/TIPURI
#   - JSON serializat manual via Text + property (NU db.JSON)
#   - PK Integer (NU BigInteger - SQLite safety, lectie Faza 6)
#   - Indexes composite pentru query-uri lunare / status / scadenta
#   - Strict aditiv: 0 ALTER pe tabele existente
# ============================================================


# ---- A. CONTRACT + TERMENE ----

class Contract(db.Model):
    """
    Contract de lucrari intre beneficiar si antreprenor.

    Un proiect are un contract principal (parinte_contract_id=None) si
    optional N acte aditionale (parinte_contract_id=contract_principal.id).
    Statusul 'activ' se aplica doar contractului in vigoare la momentul T.
    """
    __tablename__ = 'contracte'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)
    parinte_contract_id = db.Column(db.Integer, db.ForeignKey('contracte.id'),
                                    nullable=True, index=True)

    nr_contract = db.Column(db.String(100), nullable=False)
    data_semnare = db.Column(db.Date, nullable=False)
    # Notice to Proceed pentru proiectare
    data_inceput_referinta = db.Column(db.Date, nullable=True)
    # Notice to Proceed pentru executie
    data_inceput_executie = db.Column(db.Date, nullable=True)
    data_finalizare_planificata = db.Column(db.Date, nullable=True)

    valoare_totala = db.Column(db.Numeric(14, 2), nullable=True)
    moneda = db.Column(db.String(3), nullable=False, default='RON')

    beneficiar = db.Column(db.String(255), nullable=True)
    antreprenor = db.Column(db.String(255), nullable=True)
    obiect_contract = db.Column(db.Text, nullable=True)
    observatii = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(20), nullable=False, default='activ', index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('contracte', lazy='dynamic'))
    parinte_contract = db.relationship('Contract', remote_side=[id],
                                       backref=db.backref('acte_aditionale', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    STATUSES = [
        ('draft',      'Draft'),
        ('activ',      'Activ'),
        ('suspendat',  'Suspendat'),
        ('reziliat',   'Reziliat'),
        ('finalizat',  'Finalizat'),
    ]
    MONEDE = [('RON', 'Leu (RON)'), ('EUR', 'Euro (EUR)')]

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'nr_contract',
                            name='uix_contract_nr_per_tenant'),
        db.Index('ix_contract_proiect_status', 'proiect_id', 'status'),
        db.Index('ix_contract_finalizare', 'data_finalizare_planificata'),
    )

    def __repr__(self):
        return f'<Contract {self.nr_contract} proiect={self.proiect_id} {self.status}>'


class TermenContract(db.Model):
    """
    Termen contractual (milestone) cu data scadenta, tip si responsabil.

    Tipuri principale: proiectare, executie, predare_amplasament,
    receptie_*, emitere_program_referinta, raspuns_notificare, altul.
    """
    __tablename__ = 'termeni_contract'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    contract_id = db.Column(db.Integer, db.ForeignKey('contracte.id'),
                            nullable=False, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)  # denorm pentru query rapid

    denumire = db.Column(db.String(255), nullable=False)
    tip = db.Column(db.String(40), nullable=False, index=True)
    descriere = db.Column(db.Text, nullable=True)

    data_scadenta = db.Column(db.Date, nullable=False)
    data_realizare = db.Column(db.Date, nullable=True)
    zile_alerta_inainte = db.Column(db.Integer, nullable=False, default=7)

    status = db.Column(db.String(20), nullable=False, default='planificat', index=True)
    responsabil_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    contract = db.relationship('Contract',
                               backref=db.backref('termeni', lazy='dynamic'))
    proiect = db.relationship('Proiect',
                              backref=db.backref('termeni_contract', lazy='dynamic'))
    responsabil = db.relationship('Utilizator', foreign_keys=[responsabil_id])
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    TIPURI = [
        ('proiectare',                 'Proiectare'),
        ('executie',                   'Executie'),
        ('predare_amplasament',        'Predare amplasament'),
        ('receptie_proiectare',        'Receptie proiectare'),
        ('receptie_partiala',          'Receptie partiala'),
        ('receptie_finala',            'Receptie finala'),
        ('emitere_program_referinta',  'Emitere program de referinta'),
        ('raspuns_notificare',         'Raspuns la notificare'),
        ('altul',                      'Altul'),
    ]
    STATUSES = [
        ('planificat', 'Planificat'),
        ('in_curs',    'In curs'),
        ('realizat',   'Realizat'),
        ('intarziat',  'Intarziat'),
        ('anulat',     'Anulat'),
    ]

    __table_args__ = (
        db.Index('ix_termen_proiect_data', 'proiect_id', 'data_scadenta'),
        db.Index('ix_termen_status_data',  'status',     'data_scadenta'),
    )

    def __repr__(self):
        return f'<TermenContract {self.tip} {self.data_scadenta} {self.status}>'


class TermenUrmarit(db.Model):
    """
    Termen generat automat de o regula (ex: 30 zile raspuns la notificare,
    30 zile emitere program de referinta).

    Polymorphic source: (entitate_sursa, id_entitate_sursa) — fara FK strict,
    pentru a permite legarea la diverse entitati (corespondenta, revendicare,
    contract).

    Folosit de jobul APScheduler care emite NotificareApp + email cand
    data_scadenta - zile_anticipare <= today si status='activ'.
    """
    __tablename__ = 'termeni_urmariti'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)

    entitate_sursa = db.Column(db.String(30), nullable=False)
    id_entitate_sursa = db.Column(db.Integer, nullable=False)

    tip_regula = db.Column(db.String(40), nullable=False, index=True)

    data_start = db.Column(db.Date, nullable=False)
    data_scadenta = db.Column(db.Date, nullable=False, index=True)
    zile_grace = db.Column(db.Integer, nullable=False, default=30)
    zile_anticipare = db.Column(db.Integer, nullable=False, default=7)

    status = db.Column(db.String(20), nullable=False, default='activ', index=True)
    data_indeplinire = db.Column(db.Date, nullable=True)
    note = db.Column(db.Text, nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    proiect = db.relationship('Proiect',
                              backref=db.backref('termeni_urmariti', lazy='dynamic'))

    STATUSES = [
        ('activ',       'Activ'),
        ('indeplinit',  'Indeplinit'),
        ('expirat',     'Expirat'),
        ('anulat',      'Anulat'),
    ]
    TIPURI_REGULA = [
        ('raspuns_30_zile',          'Raspuns 30 zile la notificare'),
        ('emitere_program_30_zile',  'Emitere program referinta in 30 zile'),
        ('custom',                   'Regula custom'),
    ]
    ENTITATI_SURSA = [
        ('corespondenta',  'Corespondenta'),
        ('revendicare',    'Revendicare'),
        ('contract',       'Contract'),
    ]

    __table_args__ = (
        db.Index('ix_termen_urm_sursa',       'entitate_sursa', 'id_entitate_sursa'),
        db.Index('ix_termen_urm_status_data', 'status',         'data_scadenta'),
    )

    def __repr__(self):
        return (f'<TermenUrmarit {self.tip_regula} scadenta={self.data_scadenta} '
                f'{self.status}>')


# ---- B. PROGRAM DE REFERINTA + TASKURI (MS Project import) ----

class ProgramReferinta(db.Model):
    """
    Program de referinta (graficul de executie) - versionat.

    Importat din MS Project XML (sau introdus manual). O versiune e
    'aprobata=True' la momentul T; restul raman istoric.
    """
    __tablename__ = 'programe_referinta'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracte.id'),
                            nullable=True, index=True)

    versiune = db.Column(db.Integer, nullable=False, default=1)
    denumire = db.Column(db.String(255), nullable=False)

    data_emitere = db.Column(db.Date, nullable=False)
    data_inceput_program = db.Column(db.Date, nullable=True)
    data_sfarsit_program = db.Column(db.Date, nullable=True)

    sursa_import = db.Column(db.String(30), nullable=False, default='manual')
    fisier_sursa_path = db.Column(db.String(500), nullable=True)

    aprobat = db.Column(db.Boolean, nullable=False, default=False, index=True)
    aprobat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_aprobare = db.Column(db.DateTime, nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('programe_referinta', lazy='dynamic'))
    contract = db.relationship('Contract',
                               backref=db.backref('programe_referinta', lazy='dynamic'))
    aprobat_de = db.relationship('Utilizator', foreign_keys=[aprobat_de_id])
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    SURSE_IMPORT = [
        ('msproject_xml', 'MS Project XML'),
        ('msproject_mpp', 'MS Project MPP (necesita conversie XML)'),
        ('manual',        'Introdus manual'),
    ]

    __table_args__ = (
        db.UniqueConstraint('proiect_id', 'versiune',
                            name='uix_program_proiect_versiune'),
        db.Index('ix_program_proiect_aprobat', 'proiect_id', 'aprobat'),
    )

    def __repr__(self):
        return f'<ProgramReferinta proiect={self.proiect_id} v{self.versiune}>'


class TaskProgram(db.Model):
    """
    Task din programul de referinta (line item din MS Project).

    Ierarhic via parinte_task_id (summary tasks). Predecesori stocati ca JSON
    pentru a permite tipuri de dependinta (FS/SS/FF/SF) + lag.

    Hook optional catre BIMTaskSchedule (Faza 5) pentru integrare 4D BIM
    viitoare (un task program <-> N task-uri BIM la nivel de element).
    """
    __tablename__ = 'taskuri_program'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    program_id = db.Column(db.Integer, db.ForeignKey('programe_referinta.id'),
                           nullable=False, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)  # denorm
    parinte_task_id = db.Column(db.Integer, db.ForeignKey('taskuri_program.id'),
                                nullable=True, index=True)

    cod_extern = db.Column(db.String(100), nullable=True)  # UID din MS Project
    cod_wbs = db.Column(db.String(100), nullable=True)
    denumire = db.Column(db.String(500), nullable=False)
    nivel_ierarhie = db.Column(db.Integer, nullable=False, default=1)

    data_start_planificat = db.Column(db.Date, nullable=False)
    data_sfarsit_planificat = db.Column(db.Date, nullable=False)
    data_start_real = db.Column(db.Date, nullable=True)
    data_sfarsit_real = db.Column(db.Date, nullable=True)

    durata_zile = db.Column(db.Integer, nullable=True)
    procent_realizare = db.Column(db.Numeric(5, 2), nullable=False, default=0)

    tip_task = db.Column(db.String(20), nullable=False, default='task', index=True)
    predecesori_json = db.Column(db.Text, nullable=False, default='[]')

    # Hook optional catre BIMTaskSchedule (Faza 5)
    bim_task_schedule_id = db.Column(db.Integer,
                                     db.ForeignKey('bim_task_schedules.id'),
                                     nullable=True, index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    program = db.relationship('ProgramReferinta',
                              backref=db.backref('taskuri', lazy='dynamic'))
    proiect = db.relationship('Proiect',
                              backref=db.backref('taskuri_program', lazy='dynamic'))
    parinte = db.relationship('TaskProgram', remote_side=[id],
                              backref=db.backref('copii', lazy='dynamic'))

    TIPURI_TASK = [
        ('milestone', 'Milestone'),
        ('summary',   'Summary task'),
        ('task',      'Task normal'),
    ]

    __table_args__ = (
        db.UniqueConstraint('program_id', 'cod_extern',
                            name='uix_task_program_codext'),
        db.Index('ix_task_program_data',    'program_id', 'data_start_planificat'),
        db.Index('ix_task_proiect_sfarsit', 'proiect_id', 'data_sfarsit_planificat'),
    )

    @property
    def predecesori(self) -> list:
        """Lista predecesorilor: [{'uid_extern': str, 'tip': 'FS'|'SS'|'FF'|'SF',
        'lag_zile': int}, ...]"""
        import json as _json
        try:
            return _json.loads(self.predecesori_json or '[]')
        except (ValueError, TypeError):
            return []

    @predecesori.setter
    def predecesori(self, value: list):
        import json as _json
        self.predecesori_json = _json.dumps(list(value), ensure_ascii=False)

    def __repr__(self):
        return f'<TaskProgram {self.cod_extern or self.id} {self.denumire[:30]}>'


# ---- C. TEHNICO-ECONOMIC (Oferta + BoQ + Cantitati + Situatii) ----

class OfertaContract(db.Model):
    """
    Oferta tehnico-economica asociata unui contract - versionata.

    Aggregate top-level cu valori totale; line items in PozitieBoQ.
    Sursa import: eDevize (XML / ALDOC), Excel (XLSX), sau manual.
    """
    __tablename__ = 'oferte_contract'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    contract_id = db.Column(db.Integer, db.ForeignKey('contracte.id'),
                            nullable=False, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)  # denorm

    versiune = db.Column(db.Integer, nullable=False, default=1)
    data_emitere = db.Column(db.Date, nullable=False)

    valoare_totala = db.Column(db.Numeric(14, 2), nullable=True)
    valoare_manopera = db.Column(db.Numeric(14, 2), nullable=True)
    valoare_materiale = db.Column(db.Numeric(14, 2), nullable=True)
    valoare_utilaje = db.Column(db.Numeric(14, 2), nullable=True)
    valoare_transport = db.Column(db.Numeric(14, 2), nullable=True)

    sursa_import = db.Column(db.String(30), nullable=False, default='manual')
    fisier_sursa_path = db.Column(db.String(500), nullable=True)

    aprobata = db.Column(db.Boolean, nullable=False, default=False, index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    contract = db.relationship('Contract',
                               backref=db.backref('oferte', lazy='dynamic'))
    proiect = db.relationship('Proiect',
                              backref=db.backref('oferte_contract', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    SURSE_IMPORT = [
        ('edevize_xml',   'eDevize XML'),
        ('edevize_aldoc', 'eDevize ALDOC'),
        ('excel_xlsx',    'Excel XLSX'),
        ('manual',        'Introdusa manual'),
    ]

    __table_args__ = (
        db.UniqueConstraint('contract_id', 'versiune',
                            name='uix_oferta_contract_versiune'),
    )

    def __repr__(self):
        return f'<OfertaContract contract={self.contract_id} v{self.versiune}>'


class PozitieBoQ(db.Model):
    """
    Pozitie din Bill of Quantities (deviz) - line item al unei oferte.

    Ierarhic via parinte_pozitie_id (capitole / subcapitole / articole).
    Hook optional catre BIMCostItem (Faza 5) pentru rollup BIM <-> deviz.
    """
    __tablename__ = 'pozitii_boq'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    oferta_id = db.Column(db.Integer, db.ForeignKey('oferte_contract.id'),
                          nullable=False, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)  # denorm
    parinte_pozitie_id = db.Column(db.Integer, db.ForeignKey('pozitii_boq.id'),
                                   nullable=True, index=True)

    cod_articol = db.Column(db.String(50), nullable=False)  # ex eDevize: 'CA01A1'
    cod_capitol = db.Column(db.String(50), nullable=True)
    denumire = db.Column(db.Text, nullable=False)
    um = db.Column(db.String(20), nullable=False)  # mc, mp, kg, ora, buc, ...

    cantitate_oferta = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    pret_unitar = db.Column(db.Numeric(14, 4), nullable=False, default=0)

    valoare_materiale_unitar = db.Column(db.Numeric(14, 4), nullable=True)
    valoare_manopera_unitar = db.Column(db.Numeric(14, 4), nullable=True)
    valoare_utilaj_unitar = db.Column(db.Numeric(14, 4), nullable=True)
    valoare_transport_unitar = db.Column(db.Numeric(14, 4), nullable=True)

    categorie = db.Column(db.String(20), nullable=False, default='mixt', index=True)
    ordine = db.Column(db.Integer, nullable=False, default=0)

    # Auto-pricing devize (categoria de LUCRARE, distinct de `categorie`=tip cost)
    # ex: 'terasamente', 'beton', 'armatura', 'cofraje' - cu tarif per categorie.
    # Atribuit de services/deviz_pricing.py (keyword classifier), editabil.
    categorie_lucrare = db.Column(db.String(60), nullable=True, index=True)
    # Factorul aleator folosit la ultima distributie (transparenta/reproducere)
    factor_aleator = db.Column(db.Numeric(6, 4), nullable=True)

    # Hook optional catre BIMCostItem (Faza 5)
    bim_cost_item_id = db.Column(db.Integer, db.ForeignKey('bim_cost_items.id'),
                                 nullable=True, index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    oferta = db.relationship('OfertaContract',
                             backref=db.backref('pozitii', lazy='dynamic'))
    proiect = db.relationship('Proiect',
                              backref=db.backref('pozitii_boq', lazy='dynamic'))
    parinte_pozitie = db.relationship('PozitieBoQ', remote_side=[id],
                                      backref=db.backref('subpozitii', lazy='dynamic'))

    CATEGORII = [
        ('materiale', 'Materiale'),
        ('manopera',  'Manopera'),
        ('utilaje',   'Utilaje'),
        ('transport', 'Transport'),
        ('mixt',      'Mixt (compus)'),
    ]

    __table_args__ = (
        db.Index('ix_pozitie_oferta_ordine',  'oferta_id',  'ordine'),
        db.Index('ix_pozitie_proiect_cod',    'proiect_id', 'cod_articol'),
        db.Index('ix_pozitie_capitol',        'cod_capitol'),
    )

    def __repr__(self):
        return f'<PozitieBoQ {self.cod_articol} {self.um} qty={self.cantitate_oferta}>'


class CantitateExecutataLunara(db.Model):
    """
    Cantitate executata in luna X anul Y pentru o pozitie BoQ.

    Validare in 2 pasi: inregistrare (operator) -> validare (manager).
    Unic per (pozitie, an, luna) pentru a evita dublarile.
    """
    __tablename__ = 'cantitati_executate_lunare'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    pozitie_boq_id = db.Column(db.Integer, db.ForeignKey('pozitii_boq.id'),
                               nullable=False, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)  # denorm

    luna = db.Column(db.Integer, nullable=False)  # 1-12
    an = db.Column(db.Integer, nullable=False)

    cantitate_executata = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    valoare_calculata = db.Column(db.Numeric(14, 2), nullable=True)
    procent_din_oferta = db.Column(db.Numeric(5, 2), nullable=True)

    note = db.Column(db.Text, nullable=True)

    inregistrat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_inregistrare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    validat = db.Column(db.Boolean, nullable=False, default=False, index=True)
    validat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_validare = db.Column(db.DateTime, nullable=True)

    pozitie_boq = db.relationship('PozitieBoQ',
                                  backref=db.backref('cantitati_lunare', lazy='dynamic'))
    proiect = db.relationship('Proiect',
                              backref=db.backref('cantitati_executate_lunare', lazy='dynamic'))
    inregistrat_de = db.relationship('Utilizator', foreign_keys=[inregistrat_de_id])
    validat_de = db.relationship('Utilizator', foreign_keys=[validat_de_id])

    __table_args__ = (
        db.UniqueConstraint('pozitie_boq_id', 'an', 'luna',
                            name='uix_cantitate_pozitie_lunaan'),
        db.Index('ix_cant_proiect_anluna', 'proiect_id', 'an', 'luna'),
    )

    def __repr__(self):
        return (f'<CantitateExecutataLunara pozitie={self.pozitie_boq_id} '
                f'{self.an}-{self.luna:02d} qty={self.cantitate_executata}>')


class SituatieLunara(db.Model):
    """
    Situatie de lucrari lunara (valorificare cantitati + costuri).

    Aggregata din CantitateExecutataLunara pentru (proiect, an, luna).
    Exportabila ca PDF/Excel pentru beneficiar. Workflow: draft -> emisa ->
    aprobata_beneficiar -> platita.
    """
    __tablename__ = 'situatii_lunare'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracte.id'),
                            nullable=False, index=True)

    luna = db.Column(db.Integer, nullable=False)
    an = db.Column(db.Integer, nullable=False)
    data_emitere = db.Column(db.Date, nullable=False, default=date.today)
    numar_situatie = db.Column(db.String(50), nullable=True)

    valoare_totala_luna = db.Column(db.Numeric(14, 2), nullable=True)
    valoare_cumulat_la_zi = db.Column(db.Numeric(14, 2), nullable=True)
    procent_avans_total = db.Column(db.Numeric(5, 2), nullable=True)

    status = db.Column(db.String(25), nullable=False, default='draft', index=True)

    fisier_export_pdf_path = db.Column(db.String(500), nullable=True)
    fisier_export_xlsx_path = db.Column(db.String(500), nullable=True)

    aprobat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_aprobare = db.Column(db.DateTime, nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('situatii_lunare', lazy='dynamic'))
    contract = db.relationship('Contract',
                               backref=db.backref('situatii_lunare', lazy='dynamic'))
    aprobat_de = db.relationship('Utilizator', foreign_keys=[aprobat_de_id])
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    STATUSES = [
        ('draft',               'Draft'),
        ('emisa',               'Emisa'),
        ('aprobata_beneficiar', 'Aprobata de beneficiar'),
        ('platita',             'Platita'),
        ('respinsa',            'Respinsa'),
    ]

    __table_args__ = (
        db.UniqueConstraint('proiect_id', 'an', 'luna',
                            name='uix_situatie_proiect_anluna'),
        db.Index('ix_situatie_status', 'status'),
    )

    def __repr__(self):
        return f'<SituatieLunara proiect={self.proiect_id} {self.an}-{self.luna:02d} {self.status}>'


class RaportLucrariProiect(db.Model):
    """
    Raport lunar de lucrari la nivel de proiect (aggregator, nu duplica date).

    Citeste din Pontaj (ore) + RaportActivitate (progres) + TaskProgram
    (acoperire) pentru a sintetiza progresul lunii. Snapshot la momentul T,
    poate fi re-generat oricand.
    """
    __tablename__ = 'rapoarte_lucrari_proiect'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)

    luna = db.Column(db.Integer, nullable=False)
    an = db.Column(db.Integer, nullable=False)
    data_intocmire = db.Column(db.Date, nullable=False, default=date.today)

    ore_totale_manopera = db.Column(db.Numeric(10, 2), nullable=True)
    progres_descriere = db.Column(db.Text, nullable=True)
    task_program_acoperite_json = db.Column(db.Text, nullable=False, default='[]')

    intocmit_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    proiect = db.relationship('Proiect',
                              backref=db.backref('rapoarte_lucrari_proiect', lazy='dynamic'))
    intocmit_de = db.relationship('Utilizator', foreign_keys=[intocmit_de_id])

    __table_args__ = (
        db.Index('ix_raport_lucr_proiect_anluna', 'proiect_id', 'an', 'luna'),
    )

    @property
    def taskuri_acoperite(self) -> list:
        """Lista UID-uri externe MS Project tratate in raportul lunar."""
        import json as _json
        try:
            return _json.loads(self.task_program_acoperite_json or '[]')
        except (ValueError, TypeError):
            return []

    @taskuri_acoperite.setter
    def taskuri_acoperite(self, value: list):
        import json as _json
        self.task_program_acoperite_json = _json.dumps(list(value), ensure_ascii=False)

    def __repr__(self):
        return f'<RaportLucrariProiect proiect={self.proiect_id} {self.an}-{self.luna:02d}>'


# ---- D. CORESPONDENTA + REVENDICARI + LEGATURI M:N ----

class Corespondenta(db.Model):
    """
    Inregistrare corespondenta corporate per proiect.

    Tip: scrisoare / email / notificare / adresa_oficiala / raspuns.
    Subtip 'notificare_cerinte_beneficiar' + genereaza_termen=True declanseaza
    auto-crearea unui TermenUrmarit (regula 30 zile).
    """
    __tablename__ = 'corespondente'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracte.id'),
                            nullable=True, index=True)

    numar_inregistrare = db.Column(db.String(100), nullable=False)
    data_inregistrare = db.Column(db.Date, nullable=False)

    tip = db.Column(db.String(30), nullable=False, index=True)
    subtip = db.Column(db.String(50), nullable=True, index=True)
    directie = db.Column(db.String(10), nullable=False, default='primita', index=True)

    expeditor = db.Column(db.String(255), nullable=True)
    destinatar = db.Column(db.String(255), nullable=True)
    subiect = db.Column(db.String(500), nullable=True)
    continut_text = db.Column(db.Text, nullable=True)
    fisier_path = db.Column(db.String(500), nullable=True)

    genereaza_termen = db.Column(db.Boolean, nullable=False, default=False, index=True)

    raspuns_la_id = db.Column(db.Integer, db.ForeignKey('corespondente.id'),
                              nullable=True, index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('corespondente', lazy='dynamic'))
    contract = db.relationship('Contract',
                               backref=db.backref('corespondente', lazy='dynamic'))
    raspuns_la = db.relationship('Corespondenta', remote_side=[id],
                                 backref=db.backref('raspunsuri', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    TIPURI = [
        ('scrisoare',         'Scrisoare'),
        ('email',             'Email'),
        ('notificare',        'Notificare'),
        ('adresa_oficiala',   'Adresa oficiala'),
        ('raspuns',           'Raspuns'),
    ]
    SUBTIPURI = [
        ('notificare_cerinte_beneficiar', 'Notificare privind cerintele beneficiarului'),
        ('notificare_intarziere',         'Notificare intarziere'),
        ('solicitare_clarificare',        'Solicitare clarificare'),
        ('raspuns',                       'Raspuns'),
        ('altul',                         'Altul'),
    ]
    DIRECTII = [
        ('primita', 'Primita'),
        ('emisa',   'Emisa'),
    ]

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'numar_inregistrare',
                            name='uix_coresp_nr_per_tenant'),
        db.Index('ix_coresp_proiect_data',    'proiect_id', 'data_inregistrare'),
        db.Index('ix_coresp_subtip_genereaza','subtip',     'genereaza_termen'),
    )

    def __repr__(self):
        return f'<Corespondenta {self.numar_inregistrare} {self.tip} {self.directie}>'


class Revendicare(db.Model):
    """
    Revendicare (Claim) - cerere de prelungire / costuri suplimentare /
    schimbare scop / perturbare.

    Se leaga M:N catre termene contractuale, taskuri program si cantitati
    lunare (tabele revendicari_termeni / revendicari_taskuri /
    revendicari_cantitati) pentru a permite detectia automata a conflictelor.
    """
    __tablename__ = 'revendicari'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracte.id'),
                            nullable=False, index=True)

    numar_revendicare = db.Column(db.String(100), nullable=False)
    data_emitere = db.Column(db.Date, nullable=False)

    tip = db.Column(db.String(30), nullable=False, index=True)
    descriere = db.Column(db.Text, nullable=True)

    valoare_solicitata = db.Column(db.Numeric(14, 2), nullable=True)
    zile_prelungire_solicitate = db.Column(db.Integer, nullable=True)

    status = db.Column(db.String(20), nullable=False, default='draft', index=True)
    data_decizie = db.Column(db.Date, nullable=True)
    motivare_decizie = db.Column(db.Text, nullable=True)

    corespondenta_initiatoare_id = db.Column(db.Integer, db.ForeignKey('corespondente.id'),
                                             nullable=True, index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('revendicari', lazy='dynamic'))
    contract = db.relationship('Contract',
                               backref=db.backref('revendicari', lazy='dynamic'))
    corespondenta_initiatoare = db.relationship('Corespondenta', foreign_keys=[corespondenta_initiatoare_id])
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    TIPURI = [
        ('intarziere',            'Intarziere'),
        ('schimbare_scop',        'Schimbare scop'),
        ('perturbare',            'Perturbare'),
        ('costuri_suplimentare',  'Costuri suplimentare'),
        ('prelungire_termen',     'Prelungire termen'),
    ]
    STATUSES = [
        ('draft',       'Draft'),
        ('emisa',       'Emisa'),
        ('in_analiza',  'In analiza'),
        ('negociere',   'Negociere'),
        ('aprobata',    'Aprobata'),
        ('respinsa',    'Respinsa'),
    ]

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'numar_revendicare',
                            name='uix_revend_nr_per_tenant'),
        db.Index('ix_revend_proiect_status', 'proiect_id', 'status'),
        db.Index('ix_revend_emitere',        'data_emitere'),
    )

    def __repr__(self):
        return f'<Revendicare {self.numar_revendicare} {self.tip} {self.status}>'


class RevendicareTermen(db.Model):
    """Legatura M:N: Revendicare <-> TermenContract."""
    __tablename__ = 'revendicari_termeni'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    revendicare_id = db.Column(db.Integer, db.ForeignKey('revendicari.id'),
                               nullable=False, index=True)
    termen_contract_id = db.Column(db.Integer, db.ForeignKey('termeni_contract.id'),
                                   nullable=False, index=True)

    tip_legatura = db.Column(db.String(20), nullable=False, default='consecinta')
    observatii = db.Column(db.Text, nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    revendicare = db.relationship('Revendicare',
                                  backref=db.backref('legaturi_termeni', lazy='dynamic'))
    termen = db.relationship('TermenContract',
                             backref=db.backref('legaturi_revendicari', lazy='dynamic'))

    TIPURI_LEGATURA = [
        ('cauza',      'Cauza'),
        ('consecinta', 'Consecinta'),
        ('referinta',  'Referinta'),
    ]

    __table_args__ = (
        db.UniqueConstraint('revendicare_id', 'termen_contract_id',
                            name='uix_revend_termen'),
    )


class RevendicareTask(db.Model):
    """Legatura M:N: Revendicare <-> TaskProgram (task din MS Project)."""
    __tablename__ = 'revendicari_taskuri'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    revendicare_id = db.Column(db.Integer, db.ForeignKey('revendicari.id'),
                               nullable=False, index=True)
    task_program_id = db.Column(db.Integer, db.ForeignKey('taskuri_program.id'),
                                nullable=False, index=True)

    tip_legatura = db.Column(db.String(20), nullable=False, default='consecinta')
    observatii = db.Column(db.Text, nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    revendicare = db.relationship('Revendicare',
                                  backref=db.backref('legaturi_taskuri', lazy='dynamic'))
    task = db.relationship('TaskProgram',
                           backref=db.backref('legaturi_revendicari', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('revendicare_id', 'task_program_id',
                            name='uix_revend_task'),
    )


class RevendicareCantitate(db.Model):
    """Legatura M:N: Revendicare <-> CantitateExecutataLunara."""
    __tablename__ = 'revendicari_cantitati'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    revendicare_id = db.Column(db.Integer, db.ForeignKey('revendicari.id'),
                               nullable=False, index=True)
    cantitate_lunara_id = db.Column(db.Integer,
                                    db.ForeignKey('cantitati_executate_lunare.id'),
                                    nullable=False, index=True)

    observatii = db.Column(db.Text, nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    revendicare = db.relationship('Revendicare',
                                  backref=db.backref('legaturi_cantitati', lazy='dynamic'))
    cantitate = db.relationship('CantitateExecutataLunara',
                                backref=db.backref('legaturi_revendicari', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('revendicare_id', 'cantitate_lunara_id',
                            name='uix_revend_cantitate'),
    )


# ---- E. PROCESE VERBALE + ANEXE + NOTIFICARI ----

class ProcesVerbal(db.Model):
    """
    Proces verbal (PV) - documente formale de receptie / predare-primire.

    Tipuri: predare_amplasament, receptie_proiectare, receptie_partiala,
    receptie_finala, altul. Template-based: generat via python-docx + reportlab
    (Faza 14).
    """
    __tablename__ = 'procese_verbale'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracte.id'),
                            nullable=True, index=True)

    tip = db.Column(db.String(30), nullable=False, index=True)
    numar = db.Column(db.String(100), nullable=True)
    data_emitere = db.Column(db.Date, nullable=False)

    participanti_json = db.Column(db.Text, nullable=False, default='[]')
    obiect = db.Column(db.Text, nullable=True)
    concluzii = db.Column(db.Text, nullable=True)

    template_folosit = db.Column(db.String(100), nullable=True)
    fisier_pdf_path = db.Column(db.String(500), nullable=True)
    fisier_docx_path = db.Column(db.String(500), nullable=True)
    semnat = db.Column(db.Boolean, nullable=False, default=False, index=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('procese_verbale', lazy='dynamic'))
    contract = db.relationship('Contract',
                               backref=db.backref('procese_verbale', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    TIPURI = [
        ('predare_amplasament',  'Predare-primire amplasament'),
        ('receptie_proiectare',  'Receptie proiectare'),
        ('receptie_partiala',    'Receptie partiala (stadiu fizic)'),
        ('receptie_finala',      'Receptie finala'),
        ('altul',                'Altul'),
    ]

    __table_args__ = (
        db.Index('ix_pv_proiect_tip', 'proiect_id', 'tip'),
        db.Index('ix_pv_emitere',     'data_emitere'),
    )

    @property
    def participanti(self) -> list:
        """Lista participantilor: [{'nume': str, 'functie': str, 'organizatie': str}, ...]"""
        import json as _json
        try:
            return _json.loads(self.participanti_json or '[]')
        except (ValueError, TypeError):
            return []

    @participanti.setter
    def participanti(self, value: list):
        import json as _json
        self.participanti_json = _json.dumps(list(value), ensure_ascii=False)

    def __repr__(self):
        return f'<ProcesVerbal {self.tip} {self.numar or self.id} {self.data_emitere}>'


class Anexa(db.Model):
    """
    Atasament polimorfic (foto santier, schita, PDF rapid).

    Se leaga la diverse entitati: cantitate_executata, revendicare,
    corespondenta, proces_verbal, task_program. Pentru fisiere "grele" cu
    versionare (contract original, oferta originala, PV final semnat) se
    foloseste DocumentProiect + RevizieDocument (existente).
    """
    __tablename__ = 'anexe'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    entitate_tinta = db.Column(db.String(30), nullable=False)
    id_entitate_tinta = db.Column(db.Integer, nullable=False)

    tip_fisier = db.Column(db.String(20), nullable=False, default='foto', index=True)

    fisier_path = db.Column(db.String(500), nullable=False)
    nume_original = db.Column(db.String(255), nullable=True)
    dimensiune_bytes = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    descriere = db.Column(db.Text, nullable=True)

    incarcat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_incarcare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    incarcat_de = db.relationship('Utilizator', foreign_keys=[incarcat_de_id])

    TIPURI_FISIER = [
        ('foto',             'Fotografie'),
        ('pdf',              'PDF'),
        ('schita',           'Schita / desen'),
        ('document_semnat',  'Document semnat'),
        ('altul',            'Altul'),
    ]
    ENTITATI_TINTA = [
        ('cantitate_executata', 'Cantitate executata lunara'),
        ('revendicare',         'Revendicare'),
        ('corespondenta',       'Corespondenta'),
        ('proces_verbal',       'Proces verbal'),
        ('task_program',        'Task program'),
    ]

    __table_args__ = (
        db.Index('ix_anexa_tinta', 'entitate_tinta', 'id_entitate_tinta'),
    )

    def __repr__(self):
        return f'<Anexa {self.tip_fisier} {self.entitate_tinta}:{self.id_entitate_tinta}>'


class NotificareApp(db.Model):
    """
    Notificare in-app per utilizator (inbox bell-icon).

    Generate de jobul APScheduler din TermenUrmarit, de evenimente
    importante (Corespondenta noua, Revendicare actualizata, Situatie aprobata)
    sau de reguli configurate.
    """
    __tablename__ = 'notificari_app'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    utilizator_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'),
                              nullable=False, index=True)

    tip = db.Column(db.String(40), nullable=False, index=True)
    titlu = db.Column(db.String(255), nullable=False)
    mesaj = db.Column(db.Text, nullable=True)
    link_url = db.Column(db.String(500), nullable=True)

    entitate_referinta = db.Column(db.String(30), nullable=True)
    id_entitate_referinta = db.Column(db.Integer, nullable=True)

    citita = db.Column(db.Boolean, nullable=False, default=False, index=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_citire = db.Column(db.DateTime, nullable=True)

    utilizator = db.relationship('Utilizator',
                                 backref=db.backref('notificari_app', lazy='dynamic'))

    TIPURI = [
        ('termen_apropiat',       'Termen apropiat de scadenta'),
        ('termen_depasit',        'Termen depasit'),
        ('revendicare_actualizata','Revendicare actualizata'),
        ('corespondenta_noua',    'Corespondenta noua'),
        ('situatie_aprobata',     'Situatie lunara aprobata'),
        ('proces_verbal_emis',    'Proces verbal emis'),
        ('generic',               'Notificare generica'),
    ]

    __table_args__ = (
        db.Index('ix_notif_user_citita_data', 'utilizator_id', 'citita', 'data_creare'),
    )

    def __repr__(self):
        return f'<NotificareApp user={self.utilizator_id} {self.tip} citita={self.citita}>'


class ReguliNotificareProiect(db.Model):
    """
    Configurare reguli de notificare per proiect (cine primeste ce, cand).

    Email destinatari ca JSON list (decuplat de Utilizator pentru emails
    externe). Anticipare = zile inainte de scadenta cand se emite prima
    notificare.
    """
    __tablename__ = 'reguli_notificare_proiect'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)

    tip_eveniment = db.Column(db.String(40), nullable=False, index=True)
    email_destinatari_json = db.Column(db.Text, nullable=False, default='[]')
    zile_anticipare = db.Column(db.Integer, nullable=False, default=7)

    email_activ = db.Column(db.Boolean, nullable=False, default=False)
    in_app_activ = db.Column(db.Boolean, nullable=False, default=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('reguli_notificare', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    __table_args__ = (
        db.UniqueConstraint('proiect_id', 'tip_eveniment',
                            name='uix_regula_proiect_eveniment'),
    )

    @property
    def email_destinatari(self) -> list:
        """Lista emails destinatari."""
        import json as _json
        try:
            return _json.loads(self.email_destinatari_json or '[]')
        except (ValueError, TypeError):
            return []

    @email_destinatari.setter
    def email_destinatari(self, value: list):
        import json as _json
        self.email_destinatari_json = _json.dumps(list(value), ensure_ascii=False)

    def __repr__(self):
        return (f'<ReguliNotificareProiect proiect={self.proiect_id} '
                f'{self.tip_eveniment} email={self.email_activ} app={self.in_app_activ}>')


# ============================================================
# LOCATII PROIECT (Mapbox integration)
#
# Locatii generice per proiect (santiere, birouri, depozite) cu
# coordonate geografice + geocoding server-side. Paralel cu Santier
# (BIM site) - acolo e ierarhia BIM, aici e punctul de lucru simplu.
# Strict aditiv: zero touch pe Santier sau alte tabele existente.
# ============================================================

class LocatieProiect(db.Model):
    """
    Locatie generica per proiect cu coordonate Mapbox.

    Distinct fata de Santier (BIM site cu cladiri/niveluri/spatii) -
    aici stocam puncte de lucru simple: santier temporar, birou,
    depozit, alt punct relevant pentru proiect.

    Coordonatele pot fi setate manual sau via geocoding server-side
    (services/geocoding.py cu Mapbox Geocoding API + token secret).
    """
    __tablename__ = 'locatii_proiect'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'),
                          nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=False, index=True)

    nume = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text, nullable=True)

    tip = db.Column(db.String(20), nullable=False, default='santier', index=True)
    status = db.Column(db.String(20), nullable=False, default='activ', index=True)

    # Coordonate WGS84 (latitude -90..90, longitude -180..180)
    # Numeric 9,6 = precizie ~10cm la ecuator
    latitudine = db.Column(db.Numeric(9, 6), nullable=True)
    longitudine = db.Column(db.Numeric(9, 6), nullable=True)

    # Adresa text input + adresa normalizata de la Mapbox
    adresa_text = db.Column(db.String(500), nullable=True)
    adresa_normalizata = db.Column(db.String(500), nullable=True)
    judet = db.Column(db.String(100), nullable=True)
    localitate = db.Column(db.String(200), nullable=True)

    geocoded_at = db.Column(db.DateTime, nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'),
                            nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('locatii', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    TIPURI = [
        ('santier',  'Santier'),
        ('birou',    'Birou'),
        ('depozit',  'Depozit'),
        ('altul',    'Altul'),
    ]
    STATUSES = [
        ('activ',    'Activ'),
        ('inactiv',  'Inactiv'),
    ]

    __table_args__ = (
        db.Index('ix_locatie_proiect_status', 'proiect_id', 'status'),
        db.Index('ix_locatie_proiect_tip',    'proiect_id', 'tip'),
        db.Index('ix_locatie_coord',          'latitudine', 'longitudine'),
    )

    @property
    def are_coordonate(self) -> bool:
        return self.latitudine is not None and self.longitudine is not None

    def to_geojson_feature(self) -> dict:
        """Serializare GeoJSON Feature pentru harti Mapbox."""
        if not self.are_coordonate:
            return None
        return {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [float(self.longitudine), float(self.latitudine)],
            },
            'properties': {
                'id': self.id,
                'nume': self.nume,
                'tip': self.tip,
                'status': self.status,
                'adresa': self.adresa_normalizata or self.adresa_text or '',
                'descriere': self.descriere or '',
            },
        }

    def __repr__(self):
        return (f'<LocatieProiect {self.nume} proiect={self.proiect_id} '
                f'{self.tip} {self.status}>')


# ============================================================
# TARIF CATEGORIE (Auto-pricing devize)
#
# Tarif de baza per categorie de lucrare, folosit la distribuirea unui
# total global pe pozitiile dintr-o oferta (metoda validata pondere =
# cantitate x tarif x factor). proiect_id NULL = tarif global default;
# proiect_id setat = override per proiect.
# ============================================================

class TarifCategorie(db.Model):
    """
    Tarif de baza per (disciplina, categorie_lucrare) pentru auto-pricing.

    Folosit de services/deviz_pricing.py: pondere pozitie = cantitate x
    tarif_baza x factor_aleator. Tarifele sunt EDITABILE din UI.

    proiect_id == None  -> tarif global default (seed la prima rulare)
    proiect_id == <id>   -> override specific proiectului
    """
    __tablename__ = 'tarife_categorie'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'),
                          nullable=True, index=True)

    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'),
                           nullable=True, index=True)

    disciplina = db.Column(db.String(40), nullable=False, index=True)
    categorie_lucrare = db.Column(db.String(60), nullable=False)
    tarif_baza = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    um_referinta = db.Column(db.String(20), nullable=True)

    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'),
                            nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('tarife_categorie', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    DISCIPLINE = [
        ('structural',  'Structural / Rezistenta'),
        ('arhitectura', 'Arhitectura'),
        ('electrice',   'Instalatii electrice'),
        ('hvac',        'HVAC / Termice / Ventilatii'),
        ('sanitare',    'Instalatii sanitare'),
        ('drumuri',     'Drumuri / Terasamente exterioare'),
        ('organizare',  'Organizare de santier'),
        ('general',     'General / Diverse'),
    ]

    __table_args__ = (
        db.UniqueConstraint('proiect_id', 'disciplina', 'categorie_lucrare',
                            name='uix_tarif_proiect_disc_cat'),
        db.Index('ix_tarif_disc_cat', 'disciplina', 'categorie_lucrare'),
    )

    def __repr__(self):
        scope = f'proiect={self.proiect_id}' if self.proiect_id else 'global'
        return (f'<TarifCategorie {self.disciplina}/{self.categorie_lucrare} '
                f'{self.tarif_baza} {scope}>')


# ============================================================
# FAZA 2 - IMPORT GANTT: configurare in DB (overlay peste config/gantt/*.json)
# Principiu: daca exista randuri (pe tenant sau global), motorul le foloseste;
# daca tabelul e gol, se cade pe JSON-ul din config (zero regresie).
# Toate au tenant_id nullable (multi-tenant) + audit prin services/audit.py.
# ============================================================

class GanttProfilMapare(db.Model):
    """Profil de mapare a coloanelor, invatat din wizard si reaplicat automat.

    `semnatura` = amprenta randului de antet (celule normalizate, sortate, unite)
    -> la un upload viitor cu acelasi antet, maparea se aplica automat.
    `mapare_json` = {camp_logic: nume_coloana} (ex {"cod_articol":"Nr.", ...}).
    """
    __tablename__ = 'gantt_profil_mapare'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    nume = db.Column(db.String(120), nullable=False)
    semnatura = db.Column(db.String(255), nullable=False, index=True)
    mapare_json = db.Column(db.Text, nullable=False)          # JSON {camp: coloana}
    sursa = db.Column(db.String(20), default='wizard', nullable=False)  # auto|wizard|manual
    nr_utilizari = db.Column(db.Integer, default=0, nullable=False)
    activ = db.Column(db.Boolean, default=True, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    data_actualizare = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'semnatura', name='uix_gantt_profil_semnatura'),
    )

    def __repr__(self):
        return f'<GanttProfilMapare {self.nume!r} sig={self.semnatura[:16]}...>'


class GanttSinonimColoana(db.Model):
    """Sinonim de antet pentru o coloana logica (overlay peste setari.json -> coloane)."""
    __tablename__ = 'gantt_sinonim_coloana'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    camp = db.Column(db.String(30), nullable=False, index=True)   # cod_articol|denumire|um|...
    sinonim = db.Column(db.String(120), nullable=False)
    activ = db.Column(db.Boolean, default=True, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'camp', 'sinonim', name='uix_gantt_sinonim'),
    )

    def __repr__(self):
        return f'<GanttSinonimColoana {self.camp}={self.sinonim!r}>'


class GanttClasificareRegula(db.Model):
    """Regula de clasificare tehnologica (overlay peste clasificare.json).

    `tip_regula` = 'cuvant' (potrivire pe denumire) | 'prefix_cod' (prefix cod articol).
    `prioritate` mai mica = incercata prima (specific inainte de generic).
    """
    __tablename__ = 'gantt_clasificare_regula'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    categorie = db.Column(db.String(40), nullable=False, index=True)
    tip_regula = db.Column(db.String(16), default='cuvant', nullable=False)  # cuvant|prefix_cod
    valoare = db.Column(db.String(120), nullable=False)
    prioritate = db.Column(db.Integer, default=100, nullable=False)
    activ = db.Column(db.Boolean, default=True, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'categorie', 'tip_regula', 'valoare',
                            name='uix_gantt_clasif'),
        db.Index('ix_gantt_clasif_tip_prio', 'tip_regula', 'prioritate'),
    )

    def __repr__(self):
        return f'<GanttClasificareRegula {self.categorie}:{self.tip_regula}={self.valoare!r}>'


class GanttRelatieTemplate(db.Model):
    """Relatie tehnologica intre doua categorii (overlay peste dependinte.json).

    `rang_din` = pozitia categoriei-sursa in ordinea tehnologica (reconstruieste
    `ordine_categorii`). `tip` = FS|SS|FF|SF, `decalaj` = lag in zile.
    """
    __tablename__ = 'gantt_relatie_template'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    categorie_din = db.Column(db.String(40), nullable=False)
    categorie_in = db.Column(db.String(40), nullable=False)
    tip = db.Column(db.String(2), default='FS', nullable=False)   # FS|SS|FF|SF
    decalaj = db.Column(db.Integer, default=0, nullable=False)    # lag in zile
    rang_din = db.Column(db.Integer, nullable=True)              # ordine tehnologica
    activ = db.Column(db.Boolean, default=True, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'categorie_din', 'categorie_in',
                            name='uix_gantt_relatie'),
    )

    def __repr__(self):
        return (f'<GanttRelatieTemplate {self.categorie_din}->{self.categorie_in} '
                f'{self.tip}+{self.decalaj}>')


class Obiectiv(db.Model):
    """Obiectiv de investitie (nivel F1 - centralizator pe obiectiv).

    Radacina ierarhiei de devize: Obiectiv (F1) -> Obiect (F2) -> GanttPlan (F3).
    Se poate lega optional de un Proiect existent (proiect_id). Strict aditiv."""
    __tablename__ = 'obiectiv'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=True, index=True)
    cod = db.Column(db.String(50), nullable=True)
    nume = db.Column(db.String(250), nullable=False)
    descriere = db.Column(db.Text, nullable=True)
    valoare_constructii = db.Column(db.Numeric(16, 2), nullable=True)  # cap 4.1 din F1
    valoare_totala = db.Column(db.Numeric(16, 2), nullable=True)       # cap 4 / total
    valoare_cm = db.Column(db.Numeric(16, 2), nullable=True)           # din care C+M
    data = db.Column(db.Date, nullable=True)
    nume_fisier_f1 = db.Column(db.String(255), nullable=True)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    proiect = db.relationship('Proiect',
                              backref=db.backref('obiective', lazy='dynamic'))

    def __repr__(self):
        return f'<Obiectiv {self.id} {self.nume[:30]!r}>'


class Obiect(db.Model):
    """Obiect de investitie (nivel F2 - centralizator pe obiect / disciplina).

    Apartine unui Obiectiv; grupeaza listele F3 (GanttPlan). `valoare_f2` =
    valoarea declarata in F2 (sau linia obiectului din F1). Strict aditiv."""
    __tablename__ = 'obiect'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    obiectiv_id = db.Column(db.Integer, db.ForeignKey('obiectiv.id'),
                            nullable=False, index=True)
    cod = db.Column(db.String(20), nullable=True)            # ex '001'
    nume = db.Column(db.String(250), nullable=False)
    disciplina = db.Column(db.String(40), nullable=True)     # arhitectura/structural/...
    valoare_f2 = db.Column(db.Numeric(16, 2), nullable=True)
    valoare_f1 = db.Column(db.Numeric(16, 2), nullable=True)  # linia obiectului in F1 (constructii)
    ordine = db.Column(db.Integer, nullable=False, default=0)
    nume_fisier_f2 = db.Column(db.String(255), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    obiectiv = db.relationship('Obiectiv',
                               backref=db.backref('obiecte', lazy='dynamic',
                                                  order_by='Obiect.ordine'))
    planuri = db.relationship('GanttPlan', backref='obiect', lazy='dynamic')

    def __repr__(self):
        return f'<Obiect {self.cod} {self.nume[:30]!r} obiectiv={self.obiectiv_id}>'


class GanttCalendar(db.Model):
    """Calendar de lucru pentru planificarea Gantt (Faza 1 - calendar real).

    `zile_lucratoare` = string de 7 caractere Luni..Duminica ('1' = lucratoare),
    implicit '1111100' (Lu-Vi). `implicit` = calendarul folosit cand planul nu
    are unul propriu. Exceptiile pe date (sarbatori, sambete lucratoare) stau in
    GanttCalendarExceptie. Folosit DOAR cand flag-ul 'gantt-calendar' e ON.
    """
    __tablename__ = 'gantt_calendar'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    nume = db.Column(db.String(120), nullable=False)
    zile_lucratoare = db.Column(db.String(7), default='1111100', nullable=False)
    ore_pe_zi = db.Column(db.Integer, default=8, nullable=False)
    implicit = db.Column(db.Boolean, default=False, nullable=False)
    activ = db.Column(db.Boolean, default=True, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)

    exceptii = db.relationship('GanttCalendarExceptie', backref='calendar',
                               lazy='select', cascade='all, delete-orphan',
                               order_by='GanttCalendarExceptie.data')

    def __repr__(self):
        return f'<GanttCalendar {self.id} {self.nume!r} implicit={self.implicit}>'


class GanttCalendarExceptie(db.Model):
    """Exceptie pe data concreta intr-un calendar de lucru Gantt.

    `lucratoare` = False -> zi nelucratoare (ex. sarbatoare legala);
    `lucratoare` = True  -> zi lucratoare (ex. sambata lucratoare / recuperare).
    """
    __tablename__ = 'gantt_calendar_exceptie'

    id = db.Column(db.Integer, primary_key=True)
    calendar_id = db.Column(db.Integer, db.ForeignKey('gantt_calendar.id'),
                            nullable=False, index=True)
    data = db.Column(db.Date, nullable=False)
    lucratoare = db.Column(db.Boolean, default=False, nullable=False)
    descriere = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('calendar_id', 'data', name='uix_gantt_calendar_exceptie'),
    )

    def __repr__(self):
        return f'<GanttCalendarExceptie cal={self.calendar_id} {self.data} lucr={self.lucratoare}>'


class GanttPlan(db.Model):
    """Plan Gantt salvat, legat (optional) de un proiect.

    Pastram SURSA (fisierul F3 + maparea), nu rezultatul calculat: la deschidere
    re-rulam pipeline-ul (rapid, reflecta mereu config-ul curent). `nr_activitati`/
    `durata_zile`/`cost_total` sunt un snapshot pentru afisarea in lista.
    """
    __tablename__ = 'gantt_plan'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=True, index=True)
    obiect_id = db.Column(db.Integer, db.ForeignKey('obiect.id'), nullable=True, index=True)  # F2 (ingestie obiectiv)
    nume = db.Column(db.String(160), nullable=False)
    nume_fisier = db.Column(db.String(255), nullable=True)
    ext = db.Column(db.String(10), nullable=True)
    continut = db.Column(db.LargeBinary, nullable=False)       # bytes-ul F3
    mapare_json = db.Column(db.Text, nullable=True)            # mapare manuala + rand_antet
    data_start = db.Column(db.Date, nullable=True)             # start planificare
    calendar_id = db.Column(db.Integer, db.ForeignKey('gantt_calendar.id'),
                            nullable=True)                     # calendar de lucru (optional)
    nr_activitati = db.Column(db.Integer, default=0, nullable=False)
    durata_zile = db.Column(db.Integer, default=0, nullable=False)
    cost_total = db.Column(db.Numeric(16, 2), default=0, nullable=False)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_actualizare = db.Column(db.DateTime, nullable=True)

    proiect = db.relationship('Proiect',
                              backref=db.backref('planuri_gantt', lazy='dynamic'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    __table_args__ = (
        db.Index('ix_gantt_plan_tenant_proiect', 'tenant_id', 'proiect_id'),
    )

    def __repr__(self):
        return f'<GanttPlan {self.id} {self.nume!r} proiect={self.proiect_id}>'


class GanttWbsNod(db.Model):
    """Nod editabil de WBS pentru un plan salvat (editor WBS, Faza Editor).

    Arborele e seedat din WBS-ul auto la prima editare; apoi utilizatorul il poate
    redenumi / reordona / regrupa. La randare/export, daca planul are arbore salvat,
    el are prioritate fata de WBS-ul auto. Frunzele (tip='activitate') au
    `activitate_ref` = id-ul activitatii (A000001) pentru a lega cost/durata/date.
    """
    __tablename__ = 'gantt_wbs_nod'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('gantt_plan.id'),
                        nullable=False, index=True)
    parinte_id = db.Column(db.Integer, db.ForeignKey('gantt_wbs_nod.id'),
                           nullable=True, index=True)
    tip = db.Column(db.String(20), nullable=False, default='grup')   # 'grup' | 'activitate'
    nume = db.Column(db.String(300), nullable=False)
    ordine = db.Column(db.Integer, nullable=False, default=0)
    activitate_ref = db.Column(db.String(20), nullable=True)   # id activitate (frunza)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    plan = db.relationship('GanttPlan',
                           backref=db.backref('wbs_noduri', lazy='dynamic',
                                              cascade='all, delete-orphan'))
    copii = db.relationship('GanttWbsNod', backref=db.backref('parinte', remote_side=[id]),
                            lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<GanttWbsNod {self.id} {self.tip} {self.nume!r} plan={self.plan_id}>'


class ProiectSantier(db.Model):
    """Asociere many-to-many proiect <-> santier BIM.

    Un proiect poate acoperi mai multe santiere si un santier poate apartine mai
    multor proiecte. Leaga lantul proiect -> santier -> modele -> elemente -> 4D/QTO.
    """
    __tablename__ = 'proiect_santier'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    proiect_id = db.Column(db.Integer, db.ForeignKey('proiecte.id'), nullable=False, index=True)
    santier_id = db.Column(db.Integer, db.ForeignKey('bim_santiere.id'), nullable=False, index=True)
    data_creare = db.Column(db.DateTime, default=datetime.utcnow)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)

    proiect = db.relationship('Proiect', backref=db.backref('legaturi_santiere', lazy='dynamic',
                                                            cascade='all, delete-orphan'))
    santier = db.relationship('Santier', backref=db.backref('legaturi_proiecte', lazy='dynamic',
                                                            cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('proiect_id', 'santier_id', name='uix_proiect_santier'),
    )

    def __repr__(self):
        return f'<ProiectSantier proiect={self.proiect_id} santier={self.santier_id}>'


