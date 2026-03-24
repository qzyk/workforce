"""
Formulare WTForms pentru modulul Documente
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import (
    StringField, SelectField, TextAreaField, DateField,
    HiddenField
)
from wtforms.validators import DataRequired, Optional, Length, ValidationError


# Durate implicite expirare per tip document (zile)
DURATA_EXPIRARE = {
    'BI_CI': 3650,              # 10 ani
    'contract_munca': 0,        # permanent
    'act_aditional': 0,         # permanent
    'adeverinta_medicala': 365,  # 1 an
    'certificat_calificare': 1825,  # 5 ani
    'autorizatie_ISCIR': 730,   # 2 ani
    'permis_inaltime': 365,     # 1 an
    'instructaj_SSM': 180,      # 6 luni
    'fisa_aptitudini': 365,     # 1 an
    'alte': 0,                  # permanent
}

# Documente obligatorii per functie
DOCUMENTE_OBLIGATORII = {
    'default': ['BI_CI', 'contract_munca', 'adeverinta_medicala', 'instructaj_SSM', 'fisa_aptitudini'],
    'Macaragiu': ['BI_CI', 'contract_munca', 'adeverinta_medicala', 'instructaj_SSM', 'fisa_aptitudini', 'autorizatie_ISCIR'],
    'Sudor': ['BI_CI', 'contract_munca', 'adeverinta_medicala', 'instructaj_SSM', 'fisa_aptitudini', 'certificat_calificare'],
    'Electrician': ['BI_CI', 'contract_munca', 'adeverinta_medicala', 'instructaj_SSM', 'fisa_aptitudini', 'certificat_calificare'],
    'Sef_echipa': ['BI_CI', 'contract_munca', 'adeverinta_medicala', 'instructaj_SSM', 'fisa_aptitudini', 'permis_inaltime'],
    'Inginer': ['BI_CI', 'contract_munca', 'adeverinta_medicala', 'instructaj_SSM', 'fisa_aptitudini'],
}


class DocumentUploadForm(FlaskForm):
    angajat_id = SelectField('Angajat', coerce=int, validators=[
        DataRequired(message='Selectati un angajat.')
    ])
    proiect_id = SelectField('Proiect (optional)', coerce=int, validators=[Optional()])
    tip = SelectField('Tip Document', validators=[
        DataRequired(message='Selectati tipul documentului.')
    ])
    nume_document = StringField('Denumire Document', validators=[
        DataRequired(message='Introduceti denumirea documentului.'),
        Length(max=255)
    ])
    fisier = FileField('Fisier', validators=[
        FileRequired(message='Selectati un fisier.'),
        FileAllowed(['pdf', 'jpg', 'jpeg', 'png', 'docx'], 'Doar fisiere PDF, JPG, PNG, DOCX!')
    ])
    data_emitere = DateField('Data Emitere', format='%Y-%m-%d', validators=[Optional()])
    data_expirare = DateField('Data Expirare', format='%Y-%m-%d', validators=[Optional()])
    emitent = StringField('Emitent', validators=[Optional(), Length(max=200)])
    serie_numar = StringField('Serie / Numar', validators=[Optional(), Length(max=100)])
    observatii = TextAreaField('Observatii', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Document, Angajat, Proiect

        self.tip.choices = [('', '-- Selectati tipul --')] + Document.TIPURI

        angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()
        self.angajat_id.choices = [(0, '-- Selectati angajat --')] + [
            (a.id, f'{a.nume_complet} ({a.functie})') for a in angajati
        ]

        proiecte = Proiect.query.filter(
            Proiect.status.in_(['activ', 'planificat'])
        ).order_by(Proiect.cod_proiect).all()
        self.proiect_id.choices = [(0, '-- Niciunul --')] + [
            (p.id, f'{p.cod_proiect} - {p.nume}') for p in proiecte
        ]

    def validate_angajat_id(self, field):
        if field.data == 0:
            raise ValidationError('Selectati un angajat.')


class DocumentEditForm(FlaskForm):
    tip = SelectField('Tip Document', validators=[
        DataRequired(message='Selectati tipul documentului.')
    ])
    nume_document = StringField('Denumire Document', validators=[
        DataRequired(message='Introduceti denumirea documentului.'),
        Length(max=255)
    ])
    data_emitere = DateField('Data Emitere', format='%Y-%m-%d', validators=[Optional()])
    data_expirare = DateField('Data Expirare', format='%Y-%m-%d', validators=[Optional()])
    emitent = StringField('Emitent', validators=[Optional(), Length(max=200)])
    serie_numar = StringField('Serie / Numar', validators=[Optional(), Length(max=100)])
    observatii = TextAreaField('Observatii', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Document
        self.tip.choices = [('', '-- Selectati tipul --')] + Document.TIPURI
