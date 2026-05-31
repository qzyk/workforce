"""
Teste de integrare pentru pagina de administrare Gantt (Faza 2d): /gantt/config.
Adaugare / dezactivare / stergere de sinonime, reguli si profiluri, cu efect
imediat in overlay-ul de configurare.
"""
import pytest

from services.gantt import store


@pytest.fixture(autouse=True)
def _curata_config(app):
    """Goleste tabelele de config dupa fiecare test (nu sunt in wipe-ul global)."""
    yield
    from models import (db, GanttSinonimColoana, GanttClasificareRegula,
                        GanttProfilMapare)
    with app.app_context():
        try:
            for M in (GanttSinonimColoana, GanttClasificareRegula, GanttProfilMapare):
                for row in M.query.all():
                    db.session.delete(row)
            db.session.commit()
        except Exception:
            db.session.rollback()


def test_config_pagina_se_incarca(authenticated_client):
    r = authenticated_client.get('/gantt/config')
    assert r.status_code == 200
    assert b'Sinonime coloane' in r.data
    assert b'Reguli de clasificare' in r.data
    assert b'Profiluri de mapare' in r.data


def test_adauga_sinonim_apare_in_overlay(authenticated_client, app):
    r = authenticated_client.post('/gantt/config/sinonim', data={
        'camp': 'denumire', 'sinonim': 'specificatia lucrarii'})
    assert r.status_code == 302
    with app.app_context():
        assert 'specificatia lucrarii' in store.coloane().get('denumire', [])


def test_dezactivare_scoate_din_overlay(authenticated_client, app):
    authenticated_client.post('/gantt/config/sinonim', data={
        'camp': 'tronson', 'sinonim': 'lot unic test'})
    from models import GanttSinonimColoana
    with app.app_context():
        row = GanttSinonimColoana.query.filter_by(sinonim='lot unic test').first()
        assert row is not None and row.activ
        sid = row.id
    # dezactiveaza -> dispare din overlay (campul tronson cade pe JSON)
    authenticated_client.post(f'/gantt/config/sinonim/{sid}/comuta')
    with app.app_context():
        assert 'lot unic test' not in store.coloane().get('tronson', [])
    # sterge definitiv
    r = authenticated_client.post(f'/gantt/config/sinonim/{sid}/sterge')
    assert r.status_code == 302
    with app.app_context():
        assert GanttSinonimColoana.query.filter_by(sinonim='lot unic test').first() is None


def test_adauga_regula_categorie_noua(authenticated_client, app):
    authenticated_client.post('/gantt/config/regula', data={
        'categorie': 'IZOLATII', 'tip_regula': 'cuvant',
        'valoare': 'hidroizolatie', 'prioritate': '50'})
    with app.app_context():
        cl = store.clasificare()
        assert 'IZOLATII' in cl
        assert 'hidroizolatie' in cl['IZOLATII']


def test_sterge_profil(authenticated_client, app):
    from models import GanttProfilMapare
    with app.app_context():
        store.salveaza_profil('Profil X', 'sig-test-123',
                              {'denumire': 1, 'um': 2, 'cantitate': 3}, rand_antet=0)
        pid = GanttProfilMapare.query.filter_by(semnatura='sig-test-123').first().id
    r = authenticated_client.post(f'/gantt/config/profil/{pid}/sterge')
    assert r.status_code == 302
    with app.app_context():
        assert GanttProfilMapare.query.get(pid) is None
