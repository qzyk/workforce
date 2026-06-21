"""
Formulare WTForms pentru modulul Competente (skill matrix).

Modulul e gated pe feature flag 'competente' (default OFF) - vezi routes/competente.py.
Doua formulare:
- CompetentaForm: nomenclatorul de competente (nume, categorie, descriere, certificare).
- AtribuireCompetentaForm: atribuirea unei competente unui angajat (nivel, valabilitate).
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, DateField,
    BooleanField, IntegerField, HiddenField
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class CompetentaForm(FlaskForm):
    """Formular de creare / editare a unei competente din nomenclator."""

    nume = StringField('Denumire competenta', validators=[
        DataRequired(message='Denumirea este obligatorie.'),
        Length(max=150),
    ])
    categorie = StringField('Categorie', validators=[Optional(), Length(max=80)])
    descriere = TextAreaField('Descriere', validators=[Optional()])
    necesita_certificare = BooleanField('Necesita certificare')
    valabilitate_luni = IntegerField('Valabilitate certificare (luni)', validators=[
        Optional(), NumberRange(min=1, max=600,
                                message='Valabilitatea trebuie sa fie intre 1 si 600 luni.')
    ])
    activ = BooleanField('Activa', default=True)


class AtribuireCompetentaForm(FlaskForm):
    """Formular de atribuire a unei competente catre un angajat."""

    competenta_id = SelectField('Competenta', coerce=int, validators=[
        DataRequired(message='Selectati o competenta.')
    ])
    nivel = SelectField('Nivel', coerce=int, validators=[
        DataRequired(message='Selectati nivelul.')
    ])
    data_obtinere = DateField('Data obtinerii', format='%Y-%m-%d', validators=[Optional()])
    data_expirare = DateField('Data expirarii', format='%Y-%m-%d', validators=[Optional()])
    observatii = TextAreaField('Observatii', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Competenta, AngajatCompetenta
        self.nivel.choices = AngajatCompetenta.NIVELURI
        self.competenta_id.choices = [(0, '-- Selectati competenta --')] + [
            (c.id, c.nume + (f' ({c.categorie})' if c.categorie else ''))
            for c in Competenta.query.filter_by(activ=True)
            .order_by(Competenta.nume).all()
        ]
