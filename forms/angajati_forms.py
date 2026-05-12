"""
Formulare WTForms pentru modulul Angajati
"""

import re
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, SelectField, SelectMultipleField, TextAreaField, DecimalField,
    DateField, HiddenField
)
from wtforms.validators import (
    DataRequired, Email, Optional, Length, NumberRange, ValidationError
)

SALARIU_MINIM = 3700


def validate_cnp(form, field):
    """Valideaza CNP romanesc: 13 cifre, unicitate."""
    if not field.data:
        return
    cnp = field.data.strip()
    if not re.match(r'^\d{13}$', cnp):
        raise ValidationError('CNP-ul trebuie sa contina exact 13 cifre.')

    # Validare checksum CNP
    weights = [2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9]
    try:
        digits = [int(c) for c in cnp]
        control = sum(d * w for d, w in zip(digits[:12], weights)) % 11
        if control == 10:
            control = 1
        if digits[12] != control:
            raise ValidationError('CNP invalid (cifra de control gresita).')
    except (ValueError, IndexError):
        raise ValidationError('CNP invalid.')

    # Unicitate
    from models import Angajat
    existing = Angajat.query.filter_by(cnp=cnp).first()
    if existing:
        angajat_id = form.angajat_id.data
        if not angajat_id or int(angajat_id) != existing.id:
            raise ValidationError('Exista deja un angajat cu acest CNP.')


def validate_telefon(form, field):
    """Valideaza format telefon romanesc."""
    if not field.data:
        return
    tel = field.data.strip()
    if not re.match(r'^(\+40|0)[0-9]{9}$', tel):
        raise ValidationError('Formatul telefonului este invalid. Exemplu: 0721000001 sau +40721000001')


class AngajatForm(FlaskForm):
    angajat_id = HiddenField('ID')

    # Date personale
    nume = StringField('Nume', validators=[
        DataRequired(message='Numele este obligatoriu.'),
        Length(max=100, message='Maxim 100 caractere.')
    ])
    prenume = StringField('Prenume', validators=[
        DataRequired(message='Prenumele este obligatoriu.'),
        Length(max=100, message='Maxim 100 caractere.')
    ])
    cnp = StringField('CNP', validators=[
        Optional(),
        Length(min=13, max=13, message='CNP-ul trebuie sa aiba exact 13 caractere.'),
        validate_cnp
    ])
    telefon = StringField('Telefon', validators=[Optional(), validate_telefon])
    email = StringField('Email', validators=[
        Optional(),
        Email(message='Adresa de email nu este valida.')
    ])
    adresa = TextAreaField('Adresa', validators=[Optional()])
    data_nasterii = DateField('Data nasterii', format='%Y-%m-%d', validators=[Optional()])

    # Date profesionale
    functie = SelectField('Functie', validators=[
        DataRequired(message='Functia este obligatorie.')
    ])
    specializari = StringField('Specializari', validators=[Optional()])
    data_angajare = DateField('Data angajare', format='%Y-%m-%d', validators=[
        DataRequired(message='Data angajarii este obligatorie.')
    ])
    data_incetare = DateField('Data incetare', format='%Y-%m-%d', validators=[Optional()])
    tip_contract = SelectField('Tip contract', choices=[
        ('nedeterminat', 'Nedeterminat'),
        ('determinat', 'Determinat'),
        ('zilier', 'Zilier'),
    ], default='nedeterminat')
    salariu_baza = DecimalField('Salariu baza (RON)', validators=[
        Optional(),
        NumberRange(min=SALARIU_MINIM,
                    message=f'Salariul minim pe economie este {SALARIU_MINIM} RON.')
    ], places=2)
    nr_contract = StringField('Nr. contract', validators=[Optional(), Length(max=50)])
    serie_bi = StringField('Serie BI/CI', validators=[Optional(), Length(max=10)])
    nr_bi = StringField('Nr. BI/CI', validators=[Optional(), Length(max=10)])

    # Status
    status = SelectField('Status', choices=[
        ('activ', 'Activ'),
        ('inactiv', 'Inactiv'),
        ('suspendat', 'Suspendat'),
    ], default='activ')

    # Altele
    poza_profil = FileField('Poza profil', validators=[
        FileAllowed(['jpg', 'jpeg', 'png'], 'Doar fisiere JPG sau PNG.')
    ])
    observatii = TextAreaField('Observatii', validators=[Optional()])

    # Asignare santiere / proiecte (m2m prin AngajatProiect)
    # In terminologia AEC: un "santier" = un Proiect aici. Pastram numele
    # din UI ("santiere") dar tehnic e Proiect.id.
    proiecte_asignate = SelectMultipleField(
        'Santiere / Proiecte asignate',
        coerce=int,
        validators=[Optional()],
        description='Selecteaza unul sau mai multe santiere pe care angajatul va lucra.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Angajat, Proiect
        self.functie.choices = Angajat.FUNCTII
        # Populez choices pentru proiecte cu cele active + planificate
        proiecte = (Proiect.query
                    .filter(Proiect.status.in_(['activ', 'planificat']))
                    .order_by(Proiect.cod_proiect).all())
        self.proiecte_asignate.choices = [
            (p.id, f'{p.cod_proiect} — {p.nume}') for p in proiecte
        ]

    def validate_data_incetare(self, field):
        if field.data and self.data_angajare.data:
            if field.data < self.data_angajare.data:
                raise ValidationError('Data incetarii nu poate fi anterioara datei angajarii.')
