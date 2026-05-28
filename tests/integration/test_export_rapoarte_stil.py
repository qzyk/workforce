"""
Export rapoarte activitati 'mod edifico' - stilizat cu paleta brand (navy/gold/cream).
Verifica ca exportul se genereaza si ca paleta veche (rosu/albastru/portocaliu) a fost
inlocuita cu navy 0B1426 + gold C9A961.
"""
import io
from datetime import date, timedelta

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


def test_export_continut_proiect_ore_activitate(app, authenticated_client):
    """Exportul contine coloanele Proiect + Ore + activitatea principala pe zi."""
    from models import db, Angajat, Proiect, RaportActivitate
    today = date.today()
    with app.app_context():
        p = Proiect.query.filter_by(cod_proiect='RA-PRJ').first()
        if not p:
            p = Proiect(cod_proiect='RA-PRJ', nume='Proiect Raport',
                        data_start=date(2026, 1, 1), status='activ')
            db.session.add(p); db.session.commit()
        a = Angajat.query.filter_by(cnp='1991010101010').first()
        if not a:
            a = Angajat(cnp='1991010101010', nume='Raport', prenume='Test',
                        status='activ', data_angajare=date(2020, 1, 1), functie='Inginer')
            db.session.add(a); db.session.commit()
        zi = today.replace(day=1)
        while zi.weekday() >= 5:
            zi += timedelta(days=1)
        if not RaportActivitate.query.filter_by(angajat_id=a.id, data=zi,
                                                tip_activitate='zilnica').first():
            db.session.add(RaportActivitate(
                angajat_id=a.id, proiect_id=p.id, data=zi, tip_activitate='zilnica',
                activitate_principala='Montaj armatura fundatii', ore_lucrate=8,
                status='aprobat'))
            db.session.commit()
        aid = a.id

    luna = today.strftime('%Y-%m')
    r = authenticated_client.get(f'/activitati/export?angajat_id={aid}&luna={luna}')
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.data))
    vals = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for v in row:
                if v is not None:
                    vals.append(str(v))
    blob = ' | '.join(vals)
    assert 'Proiect' in blob                  # header coloana noua
    assert 'Ore' in blob                      # header coloana noua
    assert 'RA-PRJ' in blob                   # proiectul pe zi
    assert 'Montaj armatura fundatii' in blob  # activitatea principala
    assert '8' in blob                        # orele lucrate
