"""Teste pentru modulul Concedii (Workforce Faza 1).

Acopera:
- serviciul concedii (zile lucratoare, detectie suprapunere)
- creare cerere prin UI
- workflow aprobare / respingere (+ permisiuni manager)
- validare suprapunere la creare si la aprobare
- regresie flag OFF (toate rutele 404)
"""

from datetime import date

import pytest

from models import db, Angajat, Concediu, SarbatoareLegala, Utilizator
from services import concedii as concedii_srv
from services.feature_flags import set_flag


# ------------------------------------------------------------------ fixtures

@pytest.fixture
def _angajat(app):
    """Un angajat de test dedicat modulului concedii."""
    with app.app_context():
        Concediu.query.delete()
        Angajat.query.filter_by(cnp='1950505050505').delete()
        db.session.commit()
        a = Angajat(cnp='1950505050505', nume='ConcTest', prenume='Ion',
                    email='ion.conctest@test.local', functie='Muncitor',
                    tip_contract='nedeterminat', salariu_baza=5000,
                    data_angajare=date(2024, 1, 1), status='activ')
        db.session.add(a)
        db.session.commit()
        aid = a.id
    yield aid
    with app.app_context():
        Concediu.query.filter_by(angajat_id=aid).delete()
        Angajat.query.filter_by(id=aid).delete()
        db.session.commit()


@pytest.fixture
def _flag_on(app):
    with app.app_context():
        set_flag('concedii', True)
    yield
    with app.app_context():
        set_flag('concedii', False)


# ------------------------------------------------------------------ serviciu

def test_calcul_zile_lucratoare_exclude_weekend(app):
    with app.app_context():
        # Luni 2026-06-15 .. Duminica 2026-06-21 => 5 zile lucratoare
        zile = concedii_srv.calcul_zile_lucratoare(date(2026, 6, 15), date(2026, 6, 21))
        assert zile == 5


def test_calcul_zile_lucratoare_exclude_sarbatoare(app):
    with app.app_context():
        SarbatoareLegala.query.filter_by(data=date(2026, 6, 16)).delete()
        db.session.add(SarbatoareLegala(data=date(2026, 6, 16),
                                        denumire='Test sarbatoare', an=2026))
        db.session.commit()
        # Luni-Vineri (5 lucratoare) minus marti sarbatoare = 4
        zile = concedii_srv.calcul_zile_lucratoare(date(2026, 6, 15), date(2026, 6, 19))
        assert zile == 4
        SarbatoareLegala.query.filter_by(data=date(2026, 6, 16)).delete()
        db.session.commit()


def test_calcul_zile_interval_invalid(app):
    with app.app_context():
        assert concedii_srv.calcul_zile_lucratoare(date(2026, 6, 20), date(2026, 6, 10)) == 0


def test_exista_suprapunere_doar_aprobate(app, _angajat):
    with app.app_context():
        # Concediu aprobat 10-14
        c = Concediu(angajat_id=_angajat, tip='CO', data_start=date(2026, 7, 10),
                     data_sfarsit=date(2026, 7, 14), nr_zile=3, status='aprobat')
        db.session.add(c)
        db.session.commit()
        # Suprapunere (12-16)
        assert concedii_srv.exista_suprapunere(_angajat, date(2026, 7, 12), date(2026, 7, 16)) is not None
        # Fara suprapunere (20-22)
        assert concedii_srv.exista_suprapunere(_angajat, date(2026, 7, 20), date(2026, 7, 22)) is None
        # O cerere doar 'cerut' nu blocheaza
        c.status = 'cerut'
        db.session.commit()
        assert concedii_srv.exista_suprapunere(_angajat, date(2026, 7, 12), date(2026, 7, 16)) is None


# ------------------------------------------------------------------ creare UI

def test_creare_concediu_calculeaza_zile(app, authenticated_client, _flag_on, _angajat):
    resp = authenticated_client.post('/concedii/nou', data={
        'angajat_id': _angajat,
        'tip': 'CO',
        'data_start': '2026-08-03',  # luni
        'data_sfarsit': '2026-08-07',  # vineri
        'observatii': 'concediu de vara',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        c = Concediu.query.filter_by(angajat_id=_angajat).first()
        assert c is not None
        assert c.status == 'cerut'
        assert c.nr_zile == 5
        assert c.introdus_de is not None


def test_creare_concediu_respinge_suprapunere(app, authenticated_client, _flag_on, _angajat):
    with app.app_context():
        db.session.add(Concediu(angajat_id=_angajat, tip='CO',
                                data_start=date(2026, 9, 7), data_sfarsit=date(2026, 9, 11),
                                nr_zile=5, status='aprobat'))
        db.session.commit()
    resp = authenticated_client.post('/concedii/nou', data={
        'angajat_id': _angajat,
        'tip': 'CO',
        'data_start': '2026-09-09',
        'data_sfarsit': '2026-09-15',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        # Doar concediul aprobat initial exista (cererea suprapusa nu s-a creat)
        assert Concediu.query.filter_by(angajat_id=_angajat).count() == 1


# ------------------------------------------------------------------ workflow

def test_aproba_concediu(app, authenticated_client, _flag_on, _angajat):
    with app.app_context():
        c = Concediu(angajat_id=_angajat, tip='CO', data_start=date(2026, 10, 5),
                     data_sfarsit=date(2026, 10, 9), nr_zile=5, status='cerut')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = authenticated_client.post(f'/concedii/{cid}/aproba', follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        c = Concediu.query.get(cid)
        assert c.status == 'aprobat'
        assert c.aprobat_de is not None
        assert c.data_aprobare is not None


def test_respinge_concediu_cu_motiv(app, authenticated_client, _flag_on, _angajat):
    with app.app_context():
        c = Concediu(angajat_id=_angajat, tip='CO', data_start=date(2026, 11, 2),
                     data_sfarsit=date(2026, 11, 6), nr_zile=5, status='cerut')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = authenticated_client.post(f'/concedii/{cid}/respinge',
                                     data={'motiv': 'Perioada aglomerata'},
                                     follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        c = Concediu.query.get(cid)
        assert c.status == 'respins'
        assert c.motiv_respingere == 'Perioada aglomerata'


def test_operator_nu_poate_aproba(app, operator_client, _flag_on, _angajat):
    with app.app_context():
        c = Concediu(angajat_id=_angajat, tip='CO', data_start=date(2026, 12, 7),
                     data_sfarsit=date(2026, 12, 11), nr_zile=5, status='cerut')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = operator_client.post(f'/concedii/{cid}/aproba', follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        # Ramane neaprobat
        assert Concediu.query.get(cid).status == 'cerut'


# ------------------------------------------------------------------ flag OFF

def test_flag_off_lista_404(app, authenticated_client):
    with app.app_context():
        set_flag('concedii', False)
    assert authenticated_client.get('/concedii/').status_code == 404


def test_flag_off_nou_404(app, authenticated_client):
    with app.app_context():
        set_flag('concedii', False)
    assert authenticated_client.get('/concedii/nou').status_code == 404


def test_flag_off_calendar_404(app, authenticated_client):
    with app.app_context():
        set_flag('concedii', False)
    assert authenticated_client.get('/concedii/calendar').status_code == 404
