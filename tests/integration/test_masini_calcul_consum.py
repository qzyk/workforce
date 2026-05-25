"""
Integration tests pentru endpoint-ul calculator consum:
    POST /masini/<id>/calcul-consum

Mapbox Directions e mock-uit (monkeypatch pe services.rute_consum.calculeaza_distanta),
tokenul e setat prin env, deci nu se face request real.
"""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def masina_cu_sofer(app):
    """Masina cu consum_mediu 7.5 + un sofer responsabil (pentru salvare)."""
    from models import db, Masina, Angajat, ConducereMasina
    with app.app_context():
        a = Angajat.query.filter_by(cnp='1950505050505').first()
        if not a:
            a = Angajat(cnp='1950505050505', nume='Sofer', prenume='Test', status='activ',
                        data_angajare=date(2020, 1, 1))
            db.session.add(a); db.session.commit()
        m = Masina.query.filter_by(numar_inmatriculare='CJ99TST').first()
        if not m:
            m = Masina(numar_inmatriculare='CJ99TST', marca='Dacia', model='Logan',
                       consum_mediu=Decimal('7.50'), angajat_responsabil_id=a.id, km_bord=10000)
            db.session.add(m); db.session.commit()
        yield {'masina_id': m.id, 'angajat_id': a.id}
        ConducereMasina.query.filter_by(masina_id=m.id).delete()
        Masina.query.filter_by(id=m.id).delete()
        Angajat.query.filter_by(id=a.id).delete()
        db.session.commit()


@pytest.fixture
def calc_flag_on(app):
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('masini-calculator-consum', True, commit=True)
    yield
    with app.app_context():
        set_flag('masini-calculator-consum', False, commit=True)


@pytest.fixture
def fake_directions(monkeypatch):
    """Token setat + Directions mock (Cluj->Turda = 42.31 km)."""
    monkeypatch.setenv('MAPBOX_PUBLIC_TOKEN', 'pk.test')
    from services import rute_consum
    monkeypatch.setattr(
        rute_consum, 'calculeaza_distanta',
        lambda pts: {'distanta_km': 42.31, 'durata_min': 61.0, 'legs': len(pts) - 1},
    )


WP = [[23.5899, 46.7712], [23.7872, 46.5667]]


class TestCalculConsumRoute:
    def test_flag_off_403(self, authenticated_client, masina_cu_sofer):
        r = authenticated_client.post(
            f'/masini/{masina_cu_sofer["masina_id"]}/calcul-consum', json={'waypoints': WP})
        assert r.status_code == 403
        assert r.get_json()['error'] == 'not_enabled'

    def test_calc_fara_salvare(self, authenticated_client, masina_cu_sofer, calc_flag_on, fake_directions):
        r = authenticated_client.post(
            f'/masini/{masina_cu_sofer["masina_id"]}/calcul-consum', json={'waypoints': WP})
        assert r.status_code == 200, r.get_data(as_text=True)
        d = r.get_json()
        assert d['distanta_km'] == 42.31
        # 7.5 * 42.31 / 100 = 3.17
        assert d['litri'] == 3.17
        assert 'salvat' not in d

    def test_waypoints_insuficiente_400(self, authenticated_client, masina_cu_sofer, calc_flag_on, fake_directions):
        r = authenticated_client.post(
            f'/masini/{masina_cu_sofer["masina_id"]}/calcul-consum', json={'waypoints': [[23.6, 46.77]]})
        assert r.status_code == 400
        assert r.get_json()['error'] == 'invalid_waypoints'

    def test_override_consum_mediu(self, authenticated_client, masina_cu_sofer, calc_flag_on, fake_directions):
        r = authenticated_client.post(
            f'/masini/{masina_cu_sofer["masina_id"]}/calcul-consum',
            json={'waypoints': WP, 'consum_mediu': 10})
        assert r.status_code == 200
        # 10 * 42.31 / 100 = 4.231 -> 4.23
        assert r.get_json()['litri'] == 4.23

    def test_salvare_creeaza_conducere(self, app, authenticated_client, masina_cu_sofer,
                                       calc_flag_on, fake_directions):
        from models import ConducereMasina
        r = authenticated_client.post(
            f'/masini/{masina_cu_sofer["masina_id"]}/calcul-consum',
            json={'waypoints': WP, 'salveaza': True, 'data': '2026-05-20',
                  'ruta_text': 'Cluj-Napoca -> Turda', 'scop': 'transport'})
        assert r.status_code == 200, r.get_data(as_text=True)
        d = r.get_json()
        assert d['salvat'] is True
        with app.app_context():
            c = ConducereMasina.query.get(d['conducere_id'])
            assert c is not None
            assert float(c.distanta_km) == 42.31
            assert float(c.combustibil_consumat) == 3.17
            assert c.ruta == 'Cluj-Napoca -> Turda'
            assert c.km_start == 10000
            assert c.km_sfarsit == 10042  # 10000 + round(42.31)
            assert c.waypoints_json is not None

    def test_fisa_render_cu_flag_si_token(self, authenticated_client, masina_cu_sofer,
                                          calc_flag_on, fake_directions):
        """Pagina fisa randeaza tab-ul + harta + JS (url_for-uri valide) cand flag+token."""
        r = authenticated_client.get(f'/masini/{masina_cu_sofer["masina_id"]}')
        assert r.status_code == 200
        assert b'Calculator Consum' in r.data   # buton tab
        assert b'calc-map' in r.data            # container harta (ramura cu token)
        assert b'/calcul-consum' in r.data      # url_for endpoint in JS

    def test_fisa_fara_flag_fara_tab(self, authenticated_client, masina_cu_sofer):
        r = authenticated_client.get(f'/masini/{masina_cu_sofer["masina_id"]}')
        assert r.status_code == 200
        assert b'tab-calculator' not in r.data

    def test_no_consum_400(self, app, authenticated_client, calc_flag_on, fake_directions):
        """Masina fara consum_mediu si fara override -> 400."""
        from models import db, Masina
        with app.app_context():
            m = Masina(numar_inmatriculare='B00NIL', marca='Ford', model='Transit')
            db.session.add(m); db.session.commit()
            mid = m.id
        try:
            r = authenticated_client.post(f'/masini/{mid}/calcul-consum', json={'waypoints': WP})
            assert r.status_code == 400
            assert r.get_json()['error'] == 'no_consum'
        finally:
            with app.app_context():
                Masina.query.filter_by(id=mid).delete()
                db.session.commit()
