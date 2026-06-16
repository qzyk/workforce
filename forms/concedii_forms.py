"""
Formulare WTForms pentru modulul Concedii (gestiune absente).

Modulul e gated pe feature flag 'concedii' (default OFF) - vezi routes/concedii.py.
Numarul de zile (nr_zile) se calculeaza pe server, nu in formular.
"""

from flask_wtf import FlaskForm
from wtforms import (
    SelectField, TextAreaField, DateField, HiddenField
)
from wtforms.validators import DataRequired, Optional, ValidationError


class ConcediuForm(FlaskForm):
    """Formular de creare / editare a unei cereri de concediu."""

    concediu_id = HiddenField('ID')

    angajat_id = SelectField('Angajat', coerce=int, validators=[
        DataRequired(message='Selectati un angajat.')
    ])
    tip = SelectField('Tip concediu', validators=[
        DataRequired(message='Selectati tipul de concediu.')
    ])
    data_start = DateField('Data inceput', format='%Y-%m-%d', validators=[
        DataRequired(message='Data de inceput este obligatorie.')
    ])
    data_sfarsit = DateField('Data sfarsit', format='%Y-%m-%d', validators=[
        DataRequired(message='Data de sfarsit este obligatorie.')
    ])
    observatii = TextAreaField('Observatii', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Angajat, Concediu
        self.tip.choices = Concediu.TIPURI

        angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()
        self.angajat_id.choices = [(0, '-- Selectati angajat --')] + [
            (a.id, f'{a.nume_complet} ({a.functie})') for a in angajati
        ]

    def validate_data_sfarsit(self, field):
        """Sfarsitul nu poate fi inaintea inceputului."""
        if field.data and self.data_start.data:
            if field.data < self.data_start.data:
                raise ValidationError(
                    'Data de sfarsit nu poate fi anterioara datei de inceput.'
                )
