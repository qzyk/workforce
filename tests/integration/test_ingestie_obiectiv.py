"""Teste pentru ingestia obiectiv: Obiectiv -> Obiect -> GanttPlan (idempotent)."""

from decimal import Decimal

import pytest

from models import db, Obiectiv, Obiect, GanttPlan
from services.ingestie_obiectiv import construieste_arbore, _nume_plan


DATE = {
    'nume': 'Test Obiectiv',
    'nume_fisier_f1': 'F1.xls',
    'valoare_constructii': Decimal('100.00'),
    'valoare_totala': Decimal('120.00'),
    'obiecte': [
        {'cod': '001', 'nume': 'Arhitectura', 'disciplina': 'arhitectura',
         'valoare_f2': Decimal('70.00'), 'valoare_f1': Decimal('70.00'),
         'nume_fisier_f2': '001_F2.xls', 'planuri': [
             {'nume': 'Lucrari noi', 'nume_fisier': '001_002_F3.xls', 'ext': '.xls',
              'continut': b'x', 'cost_total': Decimal('60.00')},
             {'nume': 'Desfacere', 'nume_fisier': '001_001_F3.xls', 'ext': '.xls',
              'continut': b'y', 'cost_total': Decimal('10.00')},
         ]},
        {'cod': '002', 'nume': 'Structura', 'disciplina': 'structural',
         'valoare_f2': Decimal('30.00'), 'valoare_f1': Decimal('30.00'),
         'planuri': [
             {'nume': 'Corp A', 'nume_fisier': '002_001_F3.xls',
              'continut': b'z', 'cost_total': Decimal('30.00')},
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


def test_construieste_arbore(app):
    with app.app_context():
        stats = construieste_arbore(DATE)
        assert Obiectiv.query.count() == 1
        assert Obiect.query.count() == 2
        assert GanttPlan.query.filter(GanttPlan.obiect_id.isnot(None)).count() == 3
        assert stats['obiecte_create'] == 2 and stats['planuri_create'] == 3

        ob = Obiectiv.query.first()
        assert ob.valoare_constructii == Decimal('100.00')
        assert ob.obiecte.count() == 2
        arh = Obiect.query.filter_by(cod='001').first()
        assert arh.disciplina == 'arhitectura'
        assert arh.valoare_f2 == Decimal('70.00')
        assert arh.planuri.count() == 2
        # cost_total propagat pe planuri
        costuri = sorted(p.cost_total for p in arh.planuri)
        assert costuri == [Decimal('10.00'), Decimal('60.00')]


def test_idempotenta(app):
    with app.app_context():
        construieste_arbore(DATE)
        stats2 = construieste_arbore(DATE)
        # fara duplicate
        assert Obiectiv.query.count() == 1
        assert Obiect.query.count() == 2
        assert GanttPlan.query.filter(GanttPlan.obiect_id.isnot(None)).count() == 3
        assert stats2['obiecte_actualizate'] == 2
        assert stats2['planuri_actualizate'] == 3
        assert stats2['obiecte_create'] == 0 and stats2['planuri_create'] == 0


def test_nume_plan_curatat():
    assert _nume_plan('001_002_Arhitectura_c2_Lucrari_noi_F3_lista_cantitati.xls') == 'Arhitectura c2 Lucrari noi'
    assert _nume_plan('002_001_Lucrări_de_structură_Corp_C2A_F3_lista_cantitati.xls').startswith('Lucr')
