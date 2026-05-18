"""
Formulare WTForms pentru situatii lunare + rapoarte de lucrari (Faza 12).
"""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    HiddenField, IntegerField, StringField, SelectField, TextAreaField, DateField,
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange


LUNI_CHOICES = [
    (1, 'Ianuarie'), (2, 'Februarie'), (3, 'Martie'),
    (4, 'Aprilie'), (5, 'Mai'), (6, 'Iunie'),
    (7, 'Iulie'), (8, 'August'), (9, 'Septembrie'),
    (10, 'Octombrie'), (11, 'Noiembrie'), (12, 'Decembrie'),
]


class SituatieLunaraForm(FlaskForm):
    """
    Form pentru creare/editare SituatieLunara.

    Genereaza automat din cantitatile validate ale lunii X.
    Workflow status: draft -> emisa -> aprobata_beneficiar -> platita | respinsa.
    """
    situatie_id = HiddenField('ID')

    an = IntegerField('An', validators=[
        DataRequired(message='Anul este obligatoriu.'),
        NumberRange(min=2020, max=2050),
    ])
    luna = SelectField('Luna', coerce=int, choices=LUNI_CHOICES,
                       validators=[DataRequired()])
    data_emitere = DateField('Data emitere', format='%Y-%m-%d',
                             validators=[Optional()])
    numar_situatie = StringField('Numar situatie', validators=[
        Optional(), Length(max=50)
    ])
    status = SelectField('Status', validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import SituatieLunara
        self.status.choices = SituatieLunara.STATUSES


class SchimbaStatusSituatieForm(FlaskForm):
    """Form simplu pentru schimbarea statusului unei situatii (un singur camp)."""
    situatie_id = HiddenField('ID')
    nou_status = SelectField('Nou status', validators=[DataRequired()])
    observatii = TextAreaField('Observatii tranzitie', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import SituatieLunara
        self.nou_status.choices = SituatieLunara.STATUSES


class RaportLucrariForm(FlaskForm):
    """Form pentru creare/regenerare RaportLucrariProiect."""
    raport_id = HiddenField('ID')
    an = IntegerField('An', validators=[
        DataRequired(), NumberRange(min=2020, max=2050)
    ])
    luna = SelectField('Luna', coerce=int, choices=LUNI_CHOICES,
                       validators=[DataRequired()])
    progres_descriere = TextAreaField('Progres descriere',
                                      validators=[Optional()])
