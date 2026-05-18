"""
Formulare WTForms pentru modulul Revendicari (Faza 13).
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, DecimalField, IntegerField,
    DateField, HiddenField,
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange, ValidationError


class RevendicareForm(FlaskForm):
    revendicare_id = HiddenField('ID')

    # Asociere
    proiect_id = SelectField('Proiect', coerce=int, validators=[
        DataRequired(message='Proiectul este obligatoriu.')
    ])
    contract_id = SelectField('Contract', coerce=int, validators=[
        DataRequired(message='Contractul este obligatoriu.')
    ])
    corespondenta_initiatoare_id = SelectField(
        'Corespondenta initiatoare (optional)', coerce=int,
        validators=[Optional()])

    # Identificare
    numar_revendicare = StringField('Numar revendicare', validators=[
        DataRequired(message='Numarul revendicarii este obligatoriu.'),
        Length(max=100),
    ])
    data_emitere = DateField('Data emitere', format='%Y-%m-%d',
                             validators=[DataRequired()])

    # Tipologie + continut
    tip = SelectField('Tip revendicare', validators=[DataRequired()])
    descriere = TextAreaField('Descriere', validators=[Optional()])

    # Valori
    valoare_solicitata = DecimalField('Valoare solicitata (RON)',
                                      validators=[Optional(),
                                                  NumberRange(min=0)],
                                      places=2)
    zile_prelungire_solicitate = IntegerField(
        'Zile prelungire solicitate',
        validators=[Optional(), NumberRange(min=0, max=3650)])

    # Status si decizie
    status = SelectField('Status', validators=[DataRequired()])
    data_decizie = DateField('Data decizie', format='%Y-%m-%d',
                             validators=[Optional()])
    motivare_decizie = TextAreaField('Motivare decizie', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Proiect, Contract, Corespondenta, Revendicare
        self.tip.choices = Revendicare.TIPURI
        self.status.choices = Revendicare.STATUSES
        proiecte_act = Proiect.query.order_by(Proiect.cod_proiect).all()
        self.proiect_id.choices = [
            (p.id, f'{p.cod_proiect} - {p.nume}') for p in proiecte_act
        ]
        contracte = Contract.query.order_by(Contract.nr_contract).all()
        self.contract_id.choices = [
            (c.id, c.nr_contract) for c in contracte
        ]
        # Corespondenta initiatoare - populate dynamic in route
        self.corespondenta_initiatoare_id.choices = [(0, '-- Niciuna --')]

    def populeaza_corespondenta(self, proiect_id: int):
        """Helper apelat din route ca sa populeaza corespondentele proiectului."""
        from models import Corespondenta
        corespondente = Corespondenta.query.filter_by(
            proiect_id=proiect_id
        ).order_by(Corespondenta.data_inregistrare.desc()).limit(100).all()
        self.corespondenta_initiatoare_id.choices = [(0, '-- Niciuna --')] + [
            (c.id, f'{c.numar_inregistrare} ({c.tip})')
            for c in corespondente
        ]

    def validate_numar_revendicare(self, field):
        from models import Revendicare
        from tenant import get_current_tenant_id
        try:
            tid = get_current_tenant_id()
        except Exception:
            tid = None
        q = Revendicare.query.filter_by(numar_revendicare=field.data.strip())
        if tid is not None:
            q = q.filter(Revendicare.tenant_id == tid)
        else:
            q = q.filter(Revendicare.tenant_id.is_(None))
        existing = q.first()
        if existing:
            rid = self.revendicare_id.data
            if not rid or int(rid) != existing.id:
                raise ValidationError(
                    'Exista deja o revendicare cu acest numar in acest tenant.'
                )


class LinkRevendicareTermenForm(FlaskForm):
    """Form pentru adaugare link M:N Revendicare <-> TermenContract."""
    termen_contract_id = SelectField('Termen contractual', coerce=int,
                                     validators=[DataRequired()])
    tip_legatura = SelectField('Tip legatura', validators=[DataRequired()])
    observatii = TextAreaField('Observatii', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import RevendicareTermen
        self.tip_legatura.choices = RevendicareTermen.TIPURI_LEGATURA
        # termen_contract_id - populate dynamic in route

    def populeaza_termene(self, contract_id: int):
        from models import TermenContract
        termene = TermenContract.query.filter_by(
            contract_id=contract_id
        ).order_by(TermenContract.data_scadenta).all()
        self.termen_contract_id.choices = [
            (t.id, f'{t.denumire} ({t.tip}, scadenta {t.data_scadenta})')
            for t in termene
        ]


class LinkRevendicareTaskForm(FlaskForm):
    """Form pentru adaugare link M:N Revendicare <-> TaskProgram."""
    task_program_id = SelectField('Task program', coerce=int,
                                  validators=[DataRequired()])
    tip_legatura = SelectField('Tip legatura', validators=[DataRequired()])
    observatii = TextAreaField('Observatii', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import RevendicareTermen  # reutilizez TIPURI_LEGATURA
        self.tip_legatura.choices = RevendicareTermen.TIPURI_LEGATURA

    def populeaza_taskuri(self, proiect_id: int):
        from models import TaskProgram, ProgramReferinta
        # Doar din programul cel mai recent
        program = ProgramReferinta.query.filter_by(
            proiect_id=proiect_id
        ).order_by(ProgramReferinta.versiune.desc()).first()
        if program:
            taskuri = TaskProgram.query.filter_by(
                program_id=program.id
            ).order_by(TaskProgram.data_start_planificat).limit(500).all()
            self.task_program_id.choices = [
                (t.id, f'{t.cod_extern or t.id} - {t.denumire[:50]}')
                for t in taskuri
            ]
        else:
            self.task_program_id.choices = []


class LinkRevendicareCantitateForm(FlaskForm):
    """Form pentru adaugare link M:N Revendicare <-> CantitateExecutataLunara."""
    cantitate_lunara_id = SelectField('Cantitate lunara', coerce=int,
                                      validators=[DataRequired()])
    observatii = TextAreaField('Observatii', validators=[Optional()])

    def populeaza_cantitati(self, proiect_id: int, limit: int = 200):
        from models import CantitateExecutataLunara, PozitieBoQ
        # Cele mai recente cantitati pe proiect
        cantitati = CantitateExecutataLunara.query.filter_by(
            proiect_id=proiect_id
        ).order_by(
            CantitateExecutataLunara.an.desc(),
            CantitateExecutataLunara.luna.desc(),
        ).limit(limit).all()
        choices = []
        for c in cantitati:
            pz = c.pozitie_boq
            label = (f'{pz.cod_articol if pz else "?"} '
                     f'({c.an}-{c.luna:02d}, '
                     f'cant={c.cantitate_executata})')
            choices.append((c.id, label))
        self.cantitate_lunara_id.choices = choices
