"""
Formulare WTForms pentru modulul Corespondenta (Faza 13).
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, DateField, HiddenField,
    BooleanField,
)
from wtforms.validators import DataRequired, Optional, Length, ValidationError


class CorespondentaForm(FlaskForm):
    corespondenta_id = HiddenField('ID')

    # Asociere
    proiect_id = SelectField('Proiect', coerce=int, validators=[
        DataRequired(message='Proiectul este obligatoriu.')
    ])
    contract_id = SelectField('Contract (optional)', coerce=int,
                              validators=[Optional()])

    # Identificare
    numar_inregistrare = StringField('Numar inregistrare', validators=[
        DataRequired(message='Numarul de inregistrare este obligatoriu.'),
        Length(max=100),
    ])
    data_inregistrare = DateField('Data inregistrare', format='%Y-%m-%d',
                                  validators=[DataRequired()])

    # Tipologie
    tip = SelectField('Tip', validators=[DataRequired()])
    subtip = SelectField('Subtip', validators=[Optional()])
    directie = SelectField('Directie', validators=[DataRequired()])

    # Parti
    expeditor = StringField('Expeditor', validators=[Optional(), Length(max=255)])
    destinatar = StringField('Destinatar', validators=[Optional(), Length(max=255)])

    # Continut
    subiect = StringField('Subiect', validators=[Optional(), Length(max=500)])
    continut_text = TextAreaField('Continut', validators=[Optional()])

    # Legaturi
    raspuns_la_id = SelectField('Raspuns la (corespondenta anterioara)',
                                coerce=int, validators=[Optional()])
    genereaza_termen = BooleanField('Genereaza termen 30 zile (regula notificare)',
                                    default=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Proiect, Contract, Corespondenta
        self.tip.choices = Corespondenta.TIPURI
        self.subtip.choices = [('', '-- Niciunul --')] + Corespondenta.SUBTIPURI
        self.directie.choices = Corespondenta.DIRECTII
        proiecte_act = Proiect.query.order_by(Proiect.cod_proiect).all()
        self.proiect_id.choices = [
            (p.id, f'{p.cod_proiect} - {p.nume}') for p in proiecte_act
        ]
        contracte = Contract.query.order_by(Contract.nr_contract).all()
        self.contract_id.choices = [(0, '-- Fara contract specific --')] + [
            (c.id, c.nr_contract) for c in contracte
        ]
        # Pentru raspuns_la_id, populate la nivel proiect ulterior in route
        # (depinde de proiect_id selectat)
        self.raspuns_la_id.choices = [(0, '-- Nu este raspuns --')]

    def populeaza_raspuns_la(self, proiect_id: int):
        """Helper apelat din route ca sa populeaza raspuns_la cu corespondentele proiectului."""
        from models import Corespondenta
        corespondente = Corespondenta.query.filter_by(
            proiect_id=proiect_id
        ).order_by(Corespondenta.data_inregistrare.desc()).limit(100).all()
        self.raspuns_la_id.choices = [(0, '-- Nu este raspuns --')] + [
            (c.id, f'{c.numar_inregistrare} ({c.tip})')
            for c in corespondente
        ]

    def validate_numar_inregistrare(self, field):
        """Unicitate nr_inregistrare per tenant. Skip self la edit."""
        from models import Corespondenta
        from tenant import get_current_tenant_id
        try:
            tid = get_current_tenant_id()
        except Exception:
            tid = None
        q = Corespondenta.query.filter_by(numar_inregistrare=field.data.strip())
        if tid is not None:
            q = q.filter(Corespondenta.tenant_id == tid)
        else:
            q = q.filter(Corespondenta.tenant_id.is_(None))
        existing = q.first()
        if existing:
            cid = self.corespondenta_id.data
            if not cid or int(cid) != existing.id:
                raise ValidationError(
                    'Exista deja o corespondenta cu acest numar in acest tenant.'
                )
