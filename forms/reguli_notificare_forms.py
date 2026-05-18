"""
Formulare WTForms pentru ReguliNotificareProiect (Faza 14).
"""

from flask_wtf import FlaskForm
from wtforms import (
    HiddenField, SelectField, IntegerField, BooleanField, TextAreaField,
)
from wtforms.validators import DataRequired, NumberRange, Optional


TIPURI_EVENIMENT = [
    ('termen_apropiat',       'Termen apropiat de scadenta'),
    ('termen_depasit',        'Termen depasit'),
    ('revendicare_actualizata', 'Revendicare actualizata'),
    ('corespondenta_noua',    'Corespondenta noua'),
    ('situatie_aprobata',     'Situatie lunara aprobata'),
    ('proces_verbal_emis',    'Proces verbal emis'),
    ('generic',               'Notificare generica'),
]


class ReguliNotificareForm(FlaskForm):
    regula_id = HiddenField('ID')

    tip_eveniment = SelectField('Tip eveniment',
                                choices=TIPURI_EVENIMENT,
                                validators=[DataRequired()])
    zile_anticipare = IntegerField('Zile anticipare',
                                   default=7,
                                   validators=[DataRequired(),
                                               NumberRange(min=0, max=365)])
    in_app_activ = BooleanField('Notificari in-app active', default=True)
    email_activ = BooleanField('Trimite email', default=False)
    email_destinatari_text = TextAreaField(
        'Emails destinatari (cate unul pe linie)',
        validators=[Optional()])


def parse_emails_text(text: str) -> list[str]:
    """Parser pentru textarea emailuri (cate un email per linie)."""
    if not text:
        return []
    result = []
    for line in text.splitlines():
        email = line.strip()
        if email and '@' in email:
            result.append(email)
    return result


def format_emails_text(emails: list[str]) -> str:
    """Round-trip: list -> textarea text."""
    return '\n'.join(emails or [])
