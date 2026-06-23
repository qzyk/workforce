"""
Teste de integrare pentru nivelarea de resurse Gantt (Faza 4):
- gating pe flag-ul 'gantt-leveling' (OFF -> sectiune ascunsa + endpoint 404)
- cu flag ON + capacitati setate -> endpoint /gantt/niveleaza/<token> intoarce DELTA
- config: sectiunea Capacitati apare doar cu flag ON
"""
import io
import re

import pytest

# 3 articole de aceeasi categorie (Terasamente), independente -> concureaza pe
# capacitate cand o setam la 1.
SAMPLE = (
    b"cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    b"ART001;Sapatura mecanizata;mc;100;Retea;Strada A;Terasamente\n"
    b"ART002;Sapatura mecanizata;mc;120;Retea;Strada B;Terasamente\n"
    b"ART003;Sapatura mecanizata;mc;140;Retea;Strada C;Terasamente\n"
)


@pytest.fixture(autouse=True)
def _curata(app):
    yield
    from models import db, TarifCategorie
    from services.feature_flags import FeatureFlag
    with app.app_context():
        try:
            for r in TarifCategorie.query.filter_by(disciplina='gantt-capacitate').all():
                db.session.delete(r)
            for ff in FeatureFlag.query.filter_by(key='gantt-leveling').all():
                db.session.delete(ff)
            db.session.commit()
        except Exception:
            db.session.rollback()


def _activeaza(app):
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('gantt-leveling', True)


def _seteaza_capacitate(app, cat, n):
    from services.gantt import store
    with app.app_context():
        store.seteaza_capacitate(cat, n)


def _upload_si_token(client):
    """Upload F3 -> pagina rezultat; extrage token-ul din butonul de nivelare sau
    din actiunea de export (mereu prezent)."""
    r = client.post('/gantt/genereaza',
                    data={'fisier': (io.BytesIO(SAMPLE), 'plan.csv'),
                          'clasifica': 'on'},
                    content_type='multipart/form-data')
    html = r.get_data(as_text=True)
    m = re.search(r'/gantt/export/([0-9a-f]{32})/', html) or \
        re.search(r'data-token="([0-9a-f]{32})"', html)
    return html, (m.group(1) if m else None)


# ------------------------------------------------------------- gating flag OFF
def test_flag_off_endpoint_404(authenticated_client, app):
    _html, token = _upload_si_token(authenticated_client)
    assert token, 'nu am gasit token in pagina rezultat'
    # flag OFF (default) -> endpoint 404, fara sectiune de nivelare
    r = authenticated_client.post(f'/gantt/niveleaza/{token}')
    assert r.status_code == 404


def test_flag_off_fara_sectiune(authenticated_client, app):
    html, _token = _upload_si_token(authenticated_client)
    assert 'btnNiveleaza' not in html
    assert 'Nivelare resurse' not in html


# ------------------------------------------------------------- flag ON
def test_flag_on_fara_capacitati_mesaj(authenticated_client, app):
    """Flag ON dar nicio capacitate setata -> endpoint raspunde ok=False cu mesaj."""
    _activeaza(app)
    _html, token = _upload_si_token(authenticated_client)
    r = authenticated_client.post(f'/gantt/niveleaza/{token}')
    assert r.status_code == 200
    j = r.get_json()
    assert j['ok'] is False
    assert 'capacit' in j['motiv'].lower()


def test_flag_on_cu_capacitate_intoarce_delta(authenticated_client, app):
    """Flag ON + capacitate 1 pe TERASAMENTE -> 3 activitati serializate, delta > 0."""
    _activeaza(app)
    _seteaza_capacitate(app, 'TERASAMENTE', 1)
    html, token = _upload_si_token(authenticated_client)
    # sectiunea trebuie sa apara acum
    assert 'btnNiveleaza' in html
    assert 'Nivelare resurse' in html
    r = authenticated_client.post(f'/gantt/niveleaza/{token}')
    assert r.status_code == 200
    j = r.get_json()
    assert j['ok'] is True
    # 3 activitati durata X cu cap 1 -> nivelat > cpm, 2 mutate
    assert j['durata_nivelata'] > j['durata_cpm']
    assert j['nr_mutate'] == 2
    assert j['intarziere'] > 0
    assert len(j['deltas']) == 2
    for d in j['deltas']:
        assert d['delta'] > 0
        assert d['start_nivelat'] > d['start_cpm']
    # histograma comparativa: nivelat nu depaseste capacitatea
    serie_niv = j['incarcare']['nivelat']['categorii'][0]['serie']
    assert max(serie_niv) <= 1
    # CPM depaseste capacitatea (varf 3 in prima fereastra)
    assert j['incarcare']['cpm']['categorii'][0]['varf'] == 3


def test_config_capacitati_doar_cu_flag(authenticated_client, app):
    # flag OFF -> tab Capacitati absent
    r0 = authenticated_client.get('/gantt/config')
    assert 'Capacitati (nivelare)' not in r0.get_data(as_text=True)
    # flag ON -> tab + sectiune prezente
    _activeaza(app)
    r1 = authenticated_client.get('/gantt/config')
    body = r1.get_data(as_text=True)
    assert 'Capacitati (nivelare)' in body
    assert 'config_capacitate' in body or '/config/capacitate' in body


def test_config_capacitate_404_cu_flag_off(authenticated_client, app):
    """POST la config_capacitate cu flag OFF -> 404."""
    r = authenticated_client.post('/gantt/config/capacitate',
                                  data={'categorie': 'BETON', 'capacitate': '2'})
    assert r.status_code == 404
