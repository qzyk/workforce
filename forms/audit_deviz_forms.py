"""
Formular WTForms pentru modulul Audit Deviz.

Upload-ul efectiv (ZIP sau fisiere multiple) se citeste din request.files in
ruta; aici tinem doar metadatele + CSRF (nume audit, proiect optional).
"""

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Optional, Length


class AuditDevizForm(FlaskForm):
    nume = StringField('Nume audit', validators=[
        DataRequired(message='Da un nume auditului (ex: "004 Arhitectura 2").'),
        Length(max=200),
    ])
    proiect_id = SelectField('Proiect (optional)', coerce=int,
                             validators=[Optional()], default=0)

    def seteaza_proiecte(self, proiecte):
        """choices = [(0, '- fara proiect -')] + [(p.id, p.nume), ...]."""
        self.proiect_id.choices = [(0, '— fără proiect —')] + [
            (p.id, p.nume) for p in proiecte
        ]
