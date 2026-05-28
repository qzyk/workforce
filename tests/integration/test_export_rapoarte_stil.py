"""
Export rapoarte activitati 'mod edifico' - stilizat cu paleta brand (navy/gold/cream).
Verifica ca exportul se genereaza si ca paleta veche (rosu/albastru/portocaliu) a fost
inlocuita cu navy 0B1426 + gold C9A961.
"""
import io
from datetime import date

from openpyxl import load_workbook


def test_export_paleta_edifico(app, authenticated_client):
    from models import db, Angajat
    with app.app_context():
        a = Angajat.query.filter_by(cnp='1990909090909').first()
        if not a:
            a = Angajat(cnp='1990909090909', nume='Export', prenume='Test',
                        status='activ', data_angajare=date(2020, 1, 1))
            db.session.add(a); db.session.commit()
        aid = a.id

    luna = date.today().strftime('%Y-%m')
    r = authenticated_client.get(f'/activitati/export?angajat_id={aid}&luna={luna}')
    assert r.status_code == 200, r.status_code
    assert r.data[:2] == b'PK'  # xlsx = zip

    wb = load_workbook(io.BytesIO(r.data))
    culori = set()
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                fc = getattr(getattr(c.fill, 'start_color', None), 'rgb', None)
                tc = getattr(getattr(c.font, 'color', None), 'rgb', None)
                if fc:
                    culori.add(str(fc))
                if tc:
                    culori.add(str(tc))
    blob = ' '.join(culori)
    # paleta noua prezenta
    assert 'C9A961' in blob, 'gold lipseste'
    assert '0B1426' in blob, 'navy lipseste'
    # paleta veche disparuta
    assert 'C62828' not in blob, 'rosu vechi inca prezent'
    assert '283593' not in blob, 'albastru vechi inca prezent'
    assert 'FFE0B2' not in blob, 'portocaliu vechi inca prezent'
