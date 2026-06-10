"""
Formulare WTForms pentru banca de preturi de resurse.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DecimalField, DateField
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class PretResursaForm(FlaskForm):
    tip = SelectField('Tip resursa', validators=[DataRequired()], choices=[
        ('material', 'Material (C6)'),
        ('manopera', 'Manopera (C7)'),
        ('utilaj', 'Utilaj (C8)'),
        ('transport', 'Transport (C9)'),
        ('echipament', 'Echipament (F4)'),
    ])
    cod = StringField('Cod resursa', validators=[
        DataRequired(message='Codul resursei este obligatoriu.'), Length(max=80)])
    denumire = StringField('Denumire', validators=[
        DataRequired(message='Denumirea este obligatorie.'), Length(max=400)])
    um = StringField('U.M.', validators=[Optional(), Length(max=20)])
    categorie = StringField('Categorie de lucrare', validators=[Optional(), Length(max=60)],
                            description='Gol = se clasifica automat din denumire.')
    pret_unitar = DecimalField('Pret unitar (fara TVA)', places=4, validators=[
        DataRequired(message='Pretul unitar este obligatoriu.'),
        NumberRange(min=0, message='Pretul nu poate fi negativ.')])
    furnizor = StringField('Furnizor', validators=[Optional(), Length(max=150)])
    sursa = StringField('Sursa (proiect/oferta)', validators=[Optional(), Length(max=200)])
    data_pret = DateField('Data pretului', validators=[Optional()])
