"""Teste pentru planificarea Gantt din obiectiv (D): consolidare F3 + drill-down
F1 -> F2 (obiect) -> F3 (lista, pe nivelul tronson) in WBS."""

import io
from decimal import Decimal

import pytest

from models import db, Obiectiv, Obiect, GanttPlan
from services.ingestie_obiectiv import construieste_arbore
from services.gantt import planificare_obiectiv, import_engine
from services.gantt.pipeline import MotorPlanificare


def _xlsx_f3(randuri_articole) -> bytes:
    """Construieste un F3 minimal cu antetul real 'Capitol de lucrari'."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['Nr.', 'Capitol de lucrari', 'U.M.', 'Cantitatea', '',
               'Pretul unitar (fara TVA)', 'TOTALUL (fara TVA)'])
    ws.append(['0', '1', '2', '3', '', '4', '5 = 3 x 4'])
    for r in randuri_articole:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _date_obiectiv():
    f3_arh = _xlsx_f3([
        ['1', 'CG01A - Sapa suport pardoseli', 'mp', 100, '', 50.0, 5000.0],
        ['2', 'CF01 - Tencuieli interioare', 'mp', 200, '', 30.0, 6000.0],
    ])
    f3_str = _xlsx_f3([
        ['1', 'CA01 - Turnare beton C25/30', 'mc', 40, '', 500.0, 20000.0],
    ])
    return {
        'nume': 'Obiectiv Plan Test',
        'valoare_constructii': Decimal('31000.00'),
        'obiecte': [
            {'cod': '001', 'nume': 'Arhitectura', 'disciplina': 'arhitectura',
             'valoare_f2': Decimal('11000.00'), 'planuri': [
                 {'nume': 'Lucrari noi', 'nume_fisier': '001_001_F3.xlsx',
                  'ext': '.xlsx', 'continut': f3_arh, 'cost_total': Decimal('11000.00')},
             ]},
            {'cod': '002', 'nume': 'Structura', 'disciplina': 'structural',
             'valoare_f2': Decimal('20000.00'), 'planuri': [
                 {'nume': 'Corp A', 'nume_fisier': '002_001_F3.xlsx',
                  'ext': '.xlsx', 'continut': f3_str, 'cost_total': Decimal('20000.00')},
             ]},
        ],
    }


@pytest.fixture(autouse=True)
def _curata(app):
    with app.app_context():
        GanttPlan.query.filter(GanttPlan.obiect_id.isnot(None)).delete()
        Obiect.query.delete()
        Obiectiv.query.delete()
        db.session.commit()
    yield


def test_articole_obiectiv_eticheteaza_obiect_si_lista(app):
    with app.app_context():
        construieste_arbore(_date_obiectiv())
        ob = Obiectiv.query.first()
        articole, raport = planificare_obiectiv.articole_obiectiv(ob.id)
        assert raport['nr_articole'] == 3
        assert raport['erori'] == 0
        etichete = {(a.obiect, a.tronson) for a in articole}
        assert ('[001] Arhitectura', 'Lucrari noi') in etichete
        assert ('[002] Structura', 'Corp A') in etichete
        # preturile au supravietuit
        beton = next(a for a in articole if 'beton' in a.denumire.lower())
        assert beton.pret_total == 20000.0


def test_csv_obiectiv_trece_prin_pipeline_cu_wbs_pe_obiecte(app):
    with app.app_context():
        construieste_arbore(_date_obiectiv())
        ob = Obiectiv.query.first()
        csv_bytes, raport = planificare_obiectiv.csv_obiectiv(ob.id)
        # CSV-ul intern e parsabil de motorul existent
        rezultat, raport_import = MotorPlanificare().genereaza_din_fisier(csv_bytes, '.csv')
        assert len(rezultat.activitati) == 3
        # WBS: nivel 1 = obiectele F2 (drill-down F1 -> F2)
        radacini = [n.nume for n in rezultat.noduri_wbs if n.nivel == 1]
        assert '[001] Arhitectura' in radacini
        assert '[002] Structura' in radacini
        # nivel 2 = listele F3
        liste = [n.nume for n in rezultat.noduri_wbs if n.nivel == 2]
        assert 'Lucrari noi' in liste and 'Corp A' in liste
        # costul total consolidat (5D) == suma listelor, din preturi reale (nu tarif)
        cost = sum(a.valoare or 0 for a in rezultat.activitati)
        assert abs(cost - 31000.0) < 0.01
        assert all(not a.cost_estimat for a in rezultat.activitati)


def test_lista_neparsabila_e_sarita_cu_raport(app):
    with app.app_context():
        date = _date_obiectiv()
        date['obiecte'][0]['planuri'].append(
            {'nume': 'Lista corupta', 'nume_fisier': 'corupt.xls',
             'continut': b'nu e xls', 'cost_total': Decimal('0')})
        construieste_arbore(date)
        ob = Obiectiv.query.first()
        articole, raport = planificare_obiectiv.articole_obiectiv(ob.id)
        # cele 3 articole valide raman; lista corupta e raportata, nu fatala
        assert raport['nr_articole'] == 3
        assert raport['erori'] == 1
        err = next(l for l in raport['liste'] if l.get('eroare'))
        assert err['lista'] == 'Lista corupta'
