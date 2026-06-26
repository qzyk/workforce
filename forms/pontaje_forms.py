"""
Formulare WTForms pentru modulul Pontaje
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, DateField,
    HiddenField, TimeField
)
from wtforms.validators import DataRequired, Optional, ValidationError


class PontajForm(FlaskForm):
    pontaj_id = HiddenField('ID')

    angajat_id = SelectField('Angajat', coerce=int, validators=[
        DataRequired(message='Selectati un angajat.')
    ])
    proiect_id = SelectField('Proiect', coerce=int, validators=[
        DataRequired(message='Selectati un proiect.')
    ])
    data = DateField('Data', format='%Y-%m-%d', validators=[
        DataRequired(message='Data este obligatorie.')
    ])
    ora_start = StringField('Ora start', validators=[
        DataRequired(message='Ora de start este obligatorie.')
    ], default='08:00')
    ora_sfarsit = StringField('Ora sfarsit', validators=[
        DataRequired(message='Ora de sfarsit este obligatorie.')
    ], default='16:00')
    tip_zi = SelectField('Tip zi', validators=[DataRequired()])
    observatii = TextAreaField('Observatii', validators=[Optional()])
    actiune = HiddenField('Actiune', default='draft')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Pontaj, Angajat, Proiect
        from services.security.tenant_access import query_for_tenant

        self.tip_zi.choices = Pontaj.TIPURI_ZI

        angajati = query_for_tenant(Angajat).filter_by(status='activ').order_by(Angajat.nume).all()
        self.angajat_id.choices = [(0, '-- Selectati angajat --')] + [
            (a.id, f'{a.nume_complet} ({a.functie})') for a in angajati
        ]

        proiecte = query_for_tenant(Proiect).filter(
            Proiect.status.in_(['activ', 'planificat'])
        ).order_by(Proiect.cod_proiect).all()
        self.proiect_id.choices = [(0, '-- Selectati proiect --')] + [
            (p.id, f'{p.cod_proiect} - {p.nume}') for p in proiecte
        ]

    def validate_ora_sfarsit(self, field):
        if field.data and self.ora_start.data:
            try:
                h1, m1 = map(int, self.ora_start.data.split(':'))
                h2, m2 = map(int, field.data.split(':'))
                total_min = (h2 * 60 + m2) - (h1 * 60 + m1)
                if total_min <= 0:
                    total_min += 24 * 60
                if total_min > 12 * 60:
                    raise ValidationError('Nu se pot inregistra mai mult de 12 ore pe zi.')
            except (ValueError, AttributeError):
                raise ValidationError('Format ora invalid.')
