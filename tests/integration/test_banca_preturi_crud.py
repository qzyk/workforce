"""Teste pentru banca de preturi v2: clasificare pe categorie + CRUD din UI
+ ingestie obiectiv din UI (upload)."""

import io
from decimal import Decimal

import pytest

from models import db, PretResursa, Obiectiv, Obiect, GanttPlan
from services import banca_preturi as bp
from services.feature_flags import set_flag


@pytest.fixture(autouse=True)
def _curata(app):
    with app.app_context():
        PretResursa.query.delete()
        GanttPlan.query.filter(GanttPlan.obiect_id.isnot(None)).delete()
        Obiect.query.delete()
        Obiectiv.query.delete()
        set_flag('banca-preturi', True)
        db.session.commit()
    yield
    with app.app_context():
        set_flag('banca-preturi', False)


# ------------------------------------------------------------------ clasificare
def test_import_clasifica_automat(app):
    with app.app_context():
        bp.importa_din_catalog({
            'C6_materiale': [
                {'cod': 'M1', 'denumire': 'Otel beton PC52 fasonat', 'um': 'kg', 'pret_unitar': 4.3},
                {'cod': 'M2', 'denumire': 'Cablu CYY-F 3x2.5', 'um': 'm', 'pret_unitar': 7.1},
            ],
            'C7_manopera': [{'cod': 'W1', 'meserie': 'Betonist', 'tarif_lei_ora': 29.0}],
        }, sursa='T')
        otel = PretResursa.query.filter_by(cod='M1').first()
        cablu = PretResursa.query.filter_by(cod='M2').first()
        man = PretResursa.query.filter_by(cod='W1').first()
        assert otel.categorie == 'armatura'
        assert cablu.categorie == 'cabluri'
        assert man.categorie == 'manopera'


def test_reclasifica_backfill_protejeaza_manualul(app):
    with app.app_context():
        bp.importa_din_catalog({'C6_materiale': [
            {'cod': 'M1', 'denumire': 'Otel beton PC52', 'um': 'kg', 'pret_unitar': 4.3}]},
            sursa='T')
        p = PretResursa.query.first()
        p.categorie = 'editat_manual'
        # una fara categorie
        db.session.add(PretResursa(tip='material', cod='M9', denumire='Teava cupru',
                                   um='m', pret_unitar=Decimal('30'), moneda='RON'))
        db.session.commit()
        stats = bp.reclasifica(doar_lipsa=True)
        assert stats['clasificate'] == 1
        assert PretResursa.query.filter_by(cod='M1').first().categorie == 'editat_manual'
        assert PretResursa.query.filter_by(cod='M9').first().categorie  # clasificat


# ------------------------------------------------------------------ CRUD UI
def test_crud_din_ui(app, authenticated_client):
    c = authenticated_client
    # adauga
    resp = c.post('/banca-preturi/nou', data={
        'tip': 'material', 'cod': 'TEST01', 'denumire': 'Beton C25/30',
        'um': 'mc', 'categorie': '', 'pret_unitar': '550.0',
        'furnizor': 'Local', 'sursa': 'Manual',
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        p = PretResursa.query.filter_by(cod='TEST01').first()
        assert p is not None
        assert p.categorie == 'beton'          # clasificat automat (camp gol)
        pid = p.id
    # editeaza (suprascrie categoria manual)
    resp = c.post(f'/banca-preturi/{pid}/editeaza', data={
        'tip': 'material', 'cod': 'TEST01', 'denumire': 'Beton C25/30',
        'um': 'mc', 'categorie': 'beton_special', 'pret_unitar': '575.0',
        'furnizor': 'Local', 'sursa': 'Manual',
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        p = PretResursa.query.get(pid)
        assert p.pret_unitar == Decimal('575.0')
        assert p.categorie == 'beton_special'
    # sterge
    resp = c.post(f'/banca-preturi/{pid}/sterge', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert PretResursa.query.get(pid) is None


def test_lista_cu_filtru_categorie(app, authenticated_client):
    with app.app_context():
        bp.importa_din_catalog({'C6_materiale': [
            {'cod': 'M1', 'denumire': 'Otel beton PC52', 'um': 'kg', 'pret_unitar': 4.3},
            {'cod': 'M2', 'denumire': 'Cablu CYY', 'um': 'm', 'pret_unitar': 7.0}]},
            sursa='T')
    resp = authenticated_client.get('/banca-preturi/?categorie=armatura')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'M1' in html and 'M2' not in html


# ------------------------------------------------------------------ upload obiectiv UI
def _xlsx_f3_bytes():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['Nr.', 'Capitol de lucrari', 'U.M.', 'Cantitatea', '',
               'Pretul unitar (fara TVA)', 'TOTALUL (fara TVA)'])
    ws.append(['0', '1', '2', '3', '', '4', '5 = 3 x 4'])
    ws.append(['1', 'CA01 - Turnare beton', 'mc', 10, '', 500.0, 5000.0])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_obiectiv_din_ui(app, authenticated_client):
    data = {
        'nume': 'Obiectiv Upload Test',
        'fisiere': [
            (io.BytesIO(_xlsx_f3_bytes()), '001_001_Structura_F3_lista_cantitati.xlsx'),
            (io.BytesIO(_xlsx_f3_bytes()), '002_001_Arhitectura_F3_lista_cantitati.xlsx'),
        ],
    }
    resp = authenticated_client.post('/gantt/obiective/incarca', data=data,
                                     content_type='multipart/form-data',
                                     follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        ob = Obiectiv.query.filter_by(nume='Obiectiv Upload Test').first()
        assert ob is not None
        assert ob.obiecte.count() == 2          # 001 si 002
        planuri = GanttPlan.query.filter(GanttPlan.obiect_id.isnot(None)).count()
        assert planuri == 2
        # costul vine din extractorul de total
        pl = GanttPlan.query.filter(GanttPlan.obiect_id.isnot(None)).first()
        assert pl.cost_total == Decimal('5000.00')
