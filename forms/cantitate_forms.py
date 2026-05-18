"""
Formulare WTForms pentru cantitati executate lunare (Faza 12).

Pentru matricea bulk-edit (ofertă × luna), NU folosim FieldList clasic
(prea greoi pentru 50+ randuri pe pagina). In schimb, route-ul parseaza
direct request.form cu chei dinamice "cantitate_<pozitie_id>" si
"note_<pozitie_id>". Helper-ul parse_bulk_cantitati() face conversia
in lista de dict-uri ready-to-save.

Form-ul CantitateLunaraForm e pentru editare single (rar folosit).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask_wtf import FlaskForm
from wtforms import (
    HiddenField, IntegerField, DecimalField, TextAreaField, SelectField,
)
from wtforms.validators import DataRequired, Optional, NumberRange


class CantitateLunaraForm(FlaskForm):
    """Editare single cantitate executata lunar (fallback / use case rar)."""
    cantitate_id = HiddenField('ID')
    pozitie_boq_id = HiddenField('PozitieBoQ ID')
    an = IntegerField('An', validators=[
        DataRequired(), NumberRange(min=2020, max=2050)
    ])
    luna = SelectField('Luna', coerce=int, validators=[DataRequired()])
    cantitate_executata = DecimalField('Cantitate executata', validators=[
        DataRequired(), NumberRange(min=0)
    ], places=4)
    note = TextAreaField('Note', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.luna.choices = [
            (1, 'Ianuarie'), (2, 'Februarie'), (3, 'Martie'),
            (4, 'Aprilie'), (5, 'Mai'), (6, 'Iunie'),
            (7, 'Iulie'), (8, 'August'), (9, 'Septembrie'),
            (10, 'Octombrie'), (11, 'Noiembrie'), (12, 'Decembrie'),
        ]


LUNI_RO = {
    1: 'Ianuarie', 2: 'Februarie', 3: 'Martie', 4: 'Aprilie',
    5: 'Mai', 6: 'Iunie', 7: 'Iulie', 8: 'August',
    9: 'Septembrie', 10: 'Octombrie', 11: 'Noiembrie', 12: 'Decembrie',
}


def parse_bulk_cantitati(form_data, prefix_cantitate: str = 'cantitate_',
                         prefix_note: str = 'note_') -> list[dict]:
    """
    Extrage din request.form lista de cantitati per pozitie BoQ.

    Cauta chei de forma "cantitate_<pozitie_id>" si "note_<pozitie_id>".
    Returneaza lista de dict-uri:
        [{'pozitie_boq_id': int, 'cantitate_executata': Decimal, 'note': str}, ...]
    Sare peste valorile goale sau invalide (cu warning intern in caller).
    """
    results: list[dict] = []
    seen_ids: set[int] = set()
    for key, raw_value in form_data.items():
        if not key.startswith(prefix_cantitate):
            continue
        if not raw_value or not str(raw_value).strip():
            continue
        try:
            pid = int(key[len(prefix_cantitate):])
        except (ValueError, TypeError):
            continue
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        try:
            val = Decimal(str(raw_value).strip().replace(',', '.'))
        except (InvalidOperation, ValueError):
            continue
        if val < 0:
            continue
        note = form_data.get(f'{prefix_note}{pid}', '').strip() or None
        results.append({
            'pozitie_boq_id': pid,
            'cantitate_executata': val,
            'note': note,
        })
    return results
