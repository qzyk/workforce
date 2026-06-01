"""
Teste pentru puntea Gantt -> BIM 4D (services/bim_4d_bridge.py):
ferestre de date pe categorie, mapare tip_element, generare schedule-uri,
date pentru player. Tabelele BIM sunt golite de fixture-ul autouse din conftest.
"""
from datetime import date

from services.gantt import import_engine, store
from services.gantt.pipeline import MotorPlanificare
from services import bim_4d_bridge as bridge

SAMPLE_CSV = (
    "cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    "A1;Pozare conducta PEHD;m;800;Retea;Strada A;Conducte\n"
    "A2;Robinet cu obturator;buc;12;Retea;Strada A;Armaturi\n"
    "A3;Sapatura mecanizata;mc;500;Retea;Strada A;Terasamente\n"
).encode('utf-8')


def _rezultat():
    articole, _ = import_engine.importa(SAMPLE_CSV, '.csv')
    return MotorPlanificare().proceseaza(articole)


def test_stare_la_data():
    s, f = date(2026, 1, 10), date(2026, 1, 20)
    assert bridge.stare_la_data(s, f, date(2026, 1, 5)) == 'neinceput'
    assert bridge.stare_la_data(s, f, date(2026, 1, 15)) == 'in_curs'
    assert bridge.stare_la_data(s, f, date(2026, 1, 25)) == 'finalizat'


def test_ferestre_categorii_zile_lucratoare():
    fer = bridge.ferestre_categorii(_rezultat(), date(2026, 6, 1))
    assert 'POZARE_CONDUCTA' in fer and 'ARMATURI' in fer
    ds, de = fer['POZARE_CONDUCTA']
    assert ds <= de and ds.weekday() < 5 and de.weekday() < 5


def test_mapare_tip_element_json():
    m = store.mapare_tip_element()
    assert m.get('pipe') == 'POZARE_CONDUCTA'
    assert m.get('valve') == 'ARMATURI'
    assert 'wall' not in m   # structura nu e mapata


def test_genereaza_si_date_4d(app):
    from models import db, Santier, Cladire, ElementBIM, BIMTaskSchedule
    with app.app_context():
        s = Santier(cod='S-4D', nume='Santier 4D test')
        db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Corp 1')
        db.session.add(c); db.session.flush()
        e_pipe = ElementBIM(cod='P1', tip_element='pipe', ifc_global_id='GUID-P1', cladire_id=c.id)
        e_valve = ElementBIM(cod='V1', tip_element='valve', ifc_global_id='GUID-V1', cladire_id=c.id)
        e_wall = ElementBIM(cod='W1', tip_element='wall', ifc_global_id='GUID-W1', cladire_id=c.id)
        db.session.add_all([e_pipe, e_valve, e_wall]); db.session.commit()

        rez = _rezultat()
        stats = bridge.genereaza_din_rezultat(
            [e_pipe, e_valve, e_wall], rez, date(2026, 6, 1), store.mapare_tip_element())
        assert stats['create'] == 2 and stats['sarite'] == 1   # pipe+valve mapate, wall nu

        # re-rulare = actualizare, nu duplicare
        stats2 = bridge.genereaza_din_rezultat(
            [e_pipe, e_valve], rez, date(2026, 6, 1), store.mapare_tip_element())
        assert stats2['create'] == 0 and stats2['actualizate'] == 2

        scheds = {x.element_bim_id: x for x in BIMTaskSchedule.query.all()}
        perechi = [(e_pipe, scheds[e_pipe.id]), (e_valve, scheds[e_valve.id])]
        d = bridge.date_4d(perechi, date(2026, 6, 15))
        assert d['nr'] == 2 and d['data_min'] and d['data_max']
        assert any(x['guid'] == 'GUID-P1' and x['stare'] in ('neinceput', 'in_curs', 'finalizat')
                   for x in d['elemente'])
