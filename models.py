"""
INNOVA WORKFORCE - Modele SQLAlchemy
Toate modelele bazei de date pentru managementul fortei de munca in constructii.
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


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
    nume = db.Column(db.String(100), nullable=False)
    prenume = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    parola_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='operator')  # admin, manager, operator
    activ = db.Column(db.Boolean, default=True)
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
