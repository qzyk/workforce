"""
Formulare WTForms pentru modulul Contract Controls (Faza 10).

3 forms:
  - ContractForm           - Contract principal sau act aditional
  - TermenContractForm     - Termen contractual (in context contract)
  - ProcesVerbalForm       - PV (predare amplasament, receptii, etc.)

Choices pentru status/tip se incarca dinamic din clasele-model
(STATUSES, TIPURI, MONEDE) ca sa nu duplicam liste.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, DecimalField,
    DateField, HiddenField, BooleanField, IntegerField,
)
from wtforms.validators import (
    DataRequired, Optional, Length, NumberRange, ValidationError,
)


def _utilizatori_responsabili_vizibili(tenant_id=None):
    """Utilizatori activi vizibili tenantului curent pentru termene contractuale."""
    from models import Utilizator
    from services.security.tenant_access import query_for_tenant

    return query_for_tenant(Utilizator, tenant_id=tenant_id).filter(
        Utilizator.activ == True
    ).order_by(Utilizator.nume, Utilizator.prenume).all()


# ============================================================
# ContractForm
# ============================================================

class ContractForm(FlaskForm):
    contract_id = HiddenField('ID')

    # Asociere
    proiect_id = SelectField('Proiect', coerce=int, validators=[
        DataRequired(message='Proiectul este obligatoriu.')
    ])
    parinte_contract_id = SelectField('Contract parinte (pentru acte aditionale)',
                                      coerce=int, validators=[Optional()])

    # Identificare
    nr_contract = StringField('Nr. contract', validators=[
        DataRequired(message='Numarul contractului este obligatoriu.'),
        Length(max=100),
    ])
    data_semnare = DateField('Data semnare', format='%Y-%m-%d', validators=[
        DataRequired(message='Data semnarii este obligatorie.')
    ])

    # Date-cheie
    data_inceput_referinta = DateField(
        'Data inceput referinta (NTP proiectare)',
        format='%Y-%m-%d', validators=[Optional()])
    data_inceput_executie = DateField(
        'Data inceput executie (NTP executie)',
        format='%Y-%m-%d', validators=[Optional()])
    data_finalizare_planificata = DateField(
        'Data finalizare planificata',
        format='%Y-%m-%d', validators=[Optional()])

    # Valori
    valoare_totala = DecimalField('Valoare totala', validators=[
        Optional(), NumberRange(min=0, message='Valoarea trebuie sa fie pozitiva.')
    ], places=2)
    moneda = SelectField('Moneda', validators=[DataRequired()])

    # Parti contractante
    beneficiar = StringField('Beneficiar', validators=[Optional(), Length(max=255)])
    antreprenor = StringField('Antreprenor', validators=[Optional(), Length(max=255)])

    # Continut
    obiect_contract = TextAreaField('Obiectul contractului', validators=[Optional()])
    observatii = TextAreaField('Observatii', validators=[Optional()])

    # Status
    status = SelectField('Status', validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Proiect, Contract
        self.status.choices = Contract.STATUSES
        self.moneda.choices = Contract.MONEDE
        proiecte_act = Proiect.query.order_by(Proiect.cod_proiect).all()
        self.proiect_id.choices = [
            (p.id, f'{p.cod_proiect} - {p.nume}') for p in proiecte_act
        ]
        # parinte = doar contractele principale (parinte_contract_id IS NULL)
        contracte_principale = Contract.query.filter_by(
            parinte_contract_id=None
        ).order_by(Contract.nr_contract).all()
        self.parinte_contract_id.choices = [(0, '-- Niciunul (contract principal) --')] + [
            (c.id, f'{c.nr_contract} ({c.proiect.cod_proiect if c.proiect else "?"})')
            for c in contracte_principale
        ]

    def validate_nr_contract(self, field):
        """Unicitate nr_contract per tenant (NULL-aware). Sariem propriul ID la edit."""
        from models import Contract
        from tenant import get_current_tenant_id
        try:
            tid = get_current_tenant_id()
        except Exception:
            tid = None
        q = Contract.query.filter_by(nr_contract=field.data.strip())
        if tid is not None:
            q = q.filter(Contract.tenant_id == tid)
        else:
            q = q.filter(Contract.tenant_id.is_(None))
        existing = q.first()
        if existing:
            cid = self.contract_id.data
            if not cid or int(cid) != existing.id:
                raise ValidationError('Exista deja un contract cu acest numar in acest tenant.')

    def validate_data_finalizare_planificata(self, field):
        if field.data and self.data_semnare.data:
            if field.data < self.data_semnare.data:
                raise ValidationError('Data finalizare nu poate fi anterioara semnarii.')


# ============================================================
# TermenContractForm
# ============================================================

class TermenContractForm(FlaskForm):
    termen_id = HiddenField('ID')
    # contract_id si proiect_id se preiau din URL/context, nu din form
    contract_id_hidden = HiddenField('Contract')

    denumire = StringField('Denumire termen', validators=[
        DataRequired(message='Denumirea este obligatorie.'),
        Length(max=255),
    ])
    tip = SelectField('Tip termen', validators=[DataRequired()])
    descriere = TextAreaField('Descriere', validators=[Optional()])

    data_scadenta = DateField('Data scadenta', format='%Y-%m-%d', validators=[
        DataRequired(message='Data scadenta este obligatorie.')
    ])
    data_realizare = DateField('Data realizare', format='%Y-%m-%d',
                               validators=[Optional()])
    zile_alerta_inainte = IntegerField(
        'Zile alerta inainte de scadenta',
        validators=[Optional(), NumberRange(min=0, max=365)],
        default=7,
    )

    status = SelectField('Status', validators=[DataRequired()])
    responsabil_id = SelectField('Responsabil', coerce=int, validators=[Optional()])

    def __init__(self, *args, responsabili=None, tenant_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        from models import TermenContract
        self.tip.choices = TermenContract.TIPURI
        self.status.choices = TermenContract.STATUSES
        useri = responsabili
        if useri is None:
            useri = _utilizatori_responsabili_vizibili(tenant_id=tenant_id)
        self.responsabil_id.choices = [(0, '-- Niciun responsabil --')] + [
            (u.id, u.get_full_name()) for u in useri
        ]


# ============================================================
# ProcesVerbalForm
# ============================================================

class ProcesVerbalForm(FlaskForm):
    pv_id = HiddenField('ID')
    proiect_id = SelectField('Proiect', coerce=int, validators=[
        DataRequired(message='Proiectul este obligatoriu.')
    ])
    contract_id = SelectField('Contract (optional)', coerce=int,
                              validators=[Optional()])

    tip = SelectField('Tip proces verbal', validators=[DataRequired()])
    numar = StringField('Numar PV', validators=[Optional(), Length(max=100)])
    data_emitere = DateField('Data emitere', format='%Y-%m-%d', validators=[
        DataRequired(message='Data emiterii este obligatorie.')
    ])

    obiect = TextAreaField('Obiectul PV', validators=[Optional()])
    concluzii = TextAreaField('Concluzii', validators=[Optional()])

    # Participanti: format text "Nume | Functie | Organizatie" - cate unul pe linie
    # Parser-ul converteste in JSON list[dict] inainte de salvare.
    participanti_text = TextAreaField(
        'Participanti (cate unul pe linie: Nume | Functie | Organizatie)',
        validators=[Optional()],
    )

    semnat = BooleanField('PV semnat', default=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Proiect, Contract, ProcesVerbal
        self.tip.choices = ProcesVerbal.TIPURI
        proiecte_act = Proiect.query.order_by(Proiect.cod_proiect).all()
        self.proiect_id.choices = [
            (p.id, f'{p.cod_proiect} - {p.nume}') for p in proiecte_act
        ]
        # Toate contractele (pre-filtrate optional la salvare daca difera de proiect)
        contracte_act = Contract.query.order_by(Contract.nr_contract).all()
        self.contract_id.choices = [(0, '-- Fara contract specific --')] + [
            (c.id, f'{c.nr_contract}') for c in contracte_act
        ]


def parse_participanti_text(text: str) -> list[dict]:
    """
    Parser pentru textarea participanti -> JSON list[dict].

    Format asteptat (1 participant per linie):
        Nume Prenume | Functie | Organizatie
    Liniile goale si separator-ele lipsa sunt tolerate (campurile lipsa -> '').
    """
    if not text:
        return []
    result = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split('|')]
        result.append({
            'nume': parts[0] if len(parts) >= 1 else '',
            'functie': parts[1] if len(parts) >= 2 else '',
            'organizatie': parts[2] if len(parts) >= 3 else '',
        })
    return result


def format_participanti_text(participanti: list[dict]) -> str:
    """Serializare inversa: JSON list[dict] -> text pentru textarea."""
    if not participanti:
        return ''
    lines = []
    for p in participanti:
        lines.append(
            f"{p.get('nume', '')} | {p.get('functie', '')} | {p.get('organizatie', '')}"
        )
    return '\n'.join(lines)
