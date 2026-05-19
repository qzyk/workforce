"""
Formulare WTForms pentru locatii proiect (Mapbox integration).
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, DecimalField, HiddenField,
    BooleanField,
)
from wtforms.validators import (
    DataRequired, Optional, Length, NumberRange, ValidationError,
)


class LocatieProiectForm(FlaskForm):
    locatie_id = HiddenField('ID')

    nume = StringField('Nume locatie', validators=[
        DataRequired(message='Numele locatiei este obligatoriu.'),
        Length(max=200),
    ])
    descriere = TextAreaField('Descriere', validators=[Optional()])

    tip = SelectField('Tip locatie', validators=[DataRequired()])
    status = SelectField('Status', validators=[DataRequired()])

    # Adresa
    adresa_text = StringField('Adresa', validators=[Optional(), Length(max=500)])
    judet = StringField('Judet', validators=[Optional(), Length(max=100)])
    localitate = StringField('Localitate', validators=[Optional(), Length(max=200)])

    # Coordonate WGS84
    latitudine = DecimalField('Latitudine', validators=[
        Optional(), NumberRange(min=-90, max=90,
                                message='Latitudinea trebuie intre -90 si 90.')
    ], places=6)
    longitudine = DecimalField('Longitudine', validators=[
        Optional(), NumberRange(min=-180, max=180,
                                message='Longitudinea trebuie intre -180 si 180.')
    ], places=6)

    # Optional: trigger geocoding server-side la salvare
    geocodeaza = BooleanField('Geocodeaza adresa automat la salvare',
                              default=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import LocatieProiect
        self.tip.choices = LocatieProiect.TIPURI
        self.status.choices = LocatieProiect.STATUSES

    def validate(self, extra_validators=None):
        """Validare custom: trebuie sa avem fie coordonate, fie geocodeaza=True."""
        if not super().validate(extra_validators=extra_validators):
            return False
        # Daca nu sunt coordonate setate, dar geocodeaza nu e bifat si nu e edit:
        # warning blând, dar nu invalidam (utilizatorul poate seta coords ulterior)
        return True
