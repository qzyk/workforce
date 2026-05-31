"""
Teste de integrare pentru wizard-ul de mapare Gantt (Faza 2c).

Flux: auto-detectie esueaza -> redirect la /gantt/mapare -> mapare manuala ->
rezultat + profil salvat -> re-upload acelasi fisier -> profilul se aplica automat.
"""
import io

import pytest


# fisier cu antet nerecunoscut -> auto-detectia esueaza, declanseaza wizard-ul
FAIL_CSV = (
    "x;y;z\n"
    "Pozare conducta PEHD De160;m;800\n"
    "Sapatura mecanizata in teren tare;mc;1200\n"
).encode('utf-8')


def _fisier(continut=FAIL_CSV, nume='necunoscut.csv'):
    return {'fisier': (io.BytesIO(continut), nume)}


@pytest.fixture(autouse=True)
def _curata_profiluri(app):
    """Sterge profilurile create de teste (tabelul nu e in wipe-ul autouse global)."""
    yield
    from models import db, GanttProfilMapare
    with app.app_context():
        try:
            for p in GanttProfilMapare.query.all():
                db.session.delete(p)
            db.session.commit()
        except Exception:
            db.session.rollback()


def test_auto_esuat_redirect_la_wizard(authenticated_client):
    r = authenticated_client.post('/gantt/genereaza', data=_fisier(),
                                  content_type='multipart/form-data')
    assert r.status_code == 302
    assert '/gantt/mapare' in r.headers['Location']


def test_wizard_get_arata_grila(authenticated_client):
    authenticated_client.post('/gantt/genereaza', data=_fisier(),
                              content_type='multipart/form-data')
    r = authenticated_client.get('/gantt/mapare')
    assert r.status_code == 200
    assert b'Mapeaza coloanele' in r.data
    assert b'rand_antet' in r.data  # exista selectorul de antet


def test_wizard_post_lipsa_denumire_respins(authenticated_client):
    authenticated_client.post('/gantt/genereaza', data=_fisier(),
                              content_type='multipart/form-data')
    # mapare invalida (fara denumire) -> redirect inapoi la wizard cu mesaj
    r = authenticated_client.post('/gantt/mapare', data={
        'nr_coloane': '3', 'col_0': 'ignora', 'col_1': 'um', 'col_2': 'cantitate',
        'rand_antet': '0',
    })
    assert r.status_code == 302
    assert '/gantt/mapare' in r.headers['Location']


def test_wizard_mapeaza_invata_si_reaplica(authenticated_client, app):
    # 1) upload esueaza -> wizard
    authenticated_client.post('/gantt/genereaza', data=_fisier(),
                              content_type='multipart/form-data')
    # 2) mapare manuala corecta (col0=denumire, col1=um, col2=cantitate, antet pe rand 0)
    r = authenticated_client.post('/gantt/mapare', data={
        'nr_coloane': '3', 'col_0': 'denumire', 'col_1': 'um', 'col_2': 'cantitate',
        'rand_antet': '0', 'salveaza_profil': '1', 'nume_profil': 'Profil test',
    })
    assert r.status_code == 200  # rezultat.html (nu redirect)

    # 3) profilul a fost salvat
    from models import GanttProfilMapare
    with app.app_context():
        profiluri = GanttProfilMapare.query.all()
        assert len(profiluri) == 1
        assert profiluri[0].nume == 'Profil test'

    # 4) re-upload acelasi fisier -> profilul se aplica AUTOMAT (200, nu redirect la wizard)
    r2 = authenticated_client.post('/gantt/genereaza', data=_fisier(),
                                   content_type='multipart/form-data')
    assert r2.status_code == 200
    assert b'/gantt/mapare' not in r2.data  # nu mai cere mapare manuala

    # 5) utilizarea profilului a fost contorizata
    with app.app_context():
        prof = GanttProfilMapare.query.first()
        assert prof.nr_utilizari >= 1
