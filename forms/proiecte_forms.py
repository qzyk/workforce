"""
Formulare WTForms pentru modulul Proiecte
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, DecimalField,
    DateField, HiddenField
)
from wtforms.validators import DataRequired, Optional, Length, ValidationError


JUDETE_ROMANIA = [
    ('', 'Selectati judetul'),
    ('Alba', 'Alba'), ('Arad', 'Arad'), ('Arges', 'Arges'), ('Bacau', 'Bacau'),
    ('Bihor', 'Bihor'), ('Bistrita-Nasaud', 'Bistrita-Nasaud'), ('Botosani', 'Botosani'),
    ('Brasov', 'Brasov'), ('Braila', 'Braila'), ('Bucuresti', 'Bucuresti'),
    ('Buzau', 'Buzau'), ('Caras-Severin', 'Caras-Severin'), ('Calarasi', 'Calarasi'),
    ('Cluj', 'Cluj'), ('Constanta', 'Constanta'), ('Covasna', 'Covasna'),
    ('Dambovita', 'Dambovita'), ('Dolj', 'Dolj'), ('Galati', 'Galati'),
    ('Giurgiu', 'Giurgiu'), ('Gorj', 'Gorj'), ('Harghita', 'Harghita'),
    ('Hunedoara', 'Hunedoara'), ('Ialomita', 'Ialomita'), ('Iasi', 'Iasi'),
    ('Ilfov', 'Ilfov'), ('Maramures', 'Maramures'), ('Mehedinti', 'Mehedinti'),
    ('Mures', 'Mures'), ('Neamt', 'Neamt'), ('Olt', 'Olt'), ('Prahova', 'Prahova'),
    ('Satu Mare', 'Satu Mare'), ('Salaj', 'Salaj'), ('Sibiu', 'Sibiu'),
    ('Suceava', 'Suceava'), ('Teleorman', 'Teleorman'), ('Timis', 'Timis'),
    ('Tulcea', 'Tulcea'), ('Vaslui', 'Vaslui'), ('Valcea', 'Valcea'),
    ('Vrancea', 'Vrancea'),
]


class ProiectForm(FlaskForm):
    proiect_id = HiddenField('ID')

    # Identificare
    cod_proiect = StringField('Cod proiect', validators=[
        DataRequired(message='Codul proiectului este obligatoriu.'),
        Length(max=50)
    ])
    nume = StringField('Nume proiect', validators=[
        DataRequired(message='Numele proiectului este obligatoriu.'),
        Length(max=200)
    ])
    descriere = TextAreaField('Descriere', validators=[Optional()])

    # Locatie si Beneficiar
    judet = SelectField('Judet', choices=JUDETE_ROMANIA, validators=[Optional()])
    localitate = StringField('Localitate', validators=[Optional(), Length(max=100)])
    adresa_santier = StringField('Adresa santier', validators=[Optional(), Length(max=300)])
    beneficiar = StringField('Beneficiar', validators=[Optional(), Length(max=200)])
    nr_contract_beneficiar = StringField('Nr. contract beneficiar', validators=[Optional(), Length(max=100)])

    # Planificare
    data_start = DateField('Data start', format='%Y-%m-%d', validators=[
        DataRequired(message='Data de start este obligatorie.')
    ])
    data_sfarsit_planificat = DateField('Data sfarsit planificata', format='%Y-%m-%d', validators=[Optional()])
    data_sfarsit_real = DateField('Data sfarsit reala', format='%Y-%m-%d', validators=[Optional()])
    manager_id = SelectField('Manager proiect', coerce=int, validators=[Optional()])
    status = SelectField('Status', validators=[DataRequired()])

    # Buget
    buget_total = DecimalField('Buget total (RON)', validators=[Optional()], places=2)
    buget_manopera = DecimalField('Buget manopera (RON)', validators=[Optional()], places=2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from models import Proiect, Utilizator
        self.status.choices = Proiect.STATUSURI
        # Populate manager dropdown
        manageri = Utilizator.query.filter(
            Utilizator.rol.in_(['admin', 'manager']),
            Utilizator.activ == True
        ).all()
        self.manager_id.choices = [(0, '-- Selectati --')] + [
            (m.id, m.get_full_name()) for m in manageri
        ]

    def validate_cod_proiect(self, field):
        from models import Proiect
        existing = Proiect.query.filter_by(cod_proiect=field.data.strip()).first()
        if existing:
            pid = self.proiect_id.data
            if not pid or int(pid) != existing.id:
                raise ValidationError('Exista deja un proiect cu acest cod.')

    def validate_data_sfarsit_planificat(self, field):
        if field.data and self.data_start.data:
            if field.data < self.data_start.data:
                raise ValidationError('Data sfarsit nu poate fi anterioara datei de start.')
