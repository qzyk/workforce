"""
Integration tests pentru workflow-ul activitatilor:
- create draft -> edit -> trimite -> aproba/respinge
- multi-proiect, detalii pe zi
"""

from datetime import date
import pytest


@pytest.fixture
def admin_with_data(app, admin_user, workforce_basic):
    """Admin + proiect + angajat (returneaza ID-uri)."""
    return {
        'admin_id': admin_user.id,
        'proiect_id': workforce_basic['proiect_id'],
        'angajat_id': workforce_basic['angajat_id'],
    }


class TestActivitatiCrud:
    def test_panou_se_incarca_pentru_admin(self, authenticated_client):
        resp = authenticated_client.get('/activitati/')
        assert resp.status_code == 200

    def test_form_adauga_se_incarca(self, authenticated_client):
        resp = authenticated_client.get('/activitati/adauga')
        assert resp.status_code == 200
        assert b'Tip Activitate' in resp.data or b'tip_activitate' in resp.data

    def test_create_activitate_zilnica_via_post(self, app, authenticated_client, admin_with_data):
        from models import db, RaportActivitate

        resp = authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            'proiect_ids[]': [admin_with_data['proiect_id']],
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_CRUD_ZILNIC',
            'status_executie': 'planificata',
            'actiune': 'draft',
        }, follow_redirects=False)
        assert resp.status_code in (200, 302)

        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_CRUD_ZILNIC'
            ).first()
            assert a is not None
            assert a.tip_activitate == 'zilnica'
            assert a.status == 'draft'
            db.session.delete(a)
            db.session.commit()

    def test_create_activitate_saptamanala_calculeaza_iso_week(
            self, app, authenticated_client, admin_with_data):
        from models import db, RaportActivitate

        resp = authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            'proiect_ids[]': [admin_with_data['proiect_id']],
            'data': '2025-09-01',  # luni, ISO week 36
            'data_sfarsit': '2025-09-05',
            'tip_activitate': 'saptamanala',
            'activitate_principala': 'TEST_CRUD_SAPT',
            'status_executie': 'planificata',
            'actiune': 'draft',
        }, follow_redirects=False)
        assert resp.status_code in (200, 302)

        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_CRUD_SAPT'
            ).first()
            assert a is not None
            assert a.tip_activitate == 'saptamanala'
            assert a.numar_saptamana == 36
            db.session.delete(a)
            db.session.commit()

    def test_create_activitate_lunara_calculeaza_luna_an(
            self, app, authenticated_client, admin_with_data):
        from models import db, RaportActivitate

        resp = authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            'proiect_ids[]': [admin_with_data['proiect_id']],
            'data': '2025-09-01',
            'tip_activitate': 'lunara',
            'activitate_principala': 'TEST_CRUD_LUNAR',
            'status_executie': 'planificata',
            'actiune': 'draft',
        }, follow_redirects=False)
        assert resp.status_code in (200, 302)

        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_CRUD_LUNAR'
            ).first()
            assert a is not None
            assert a.luna_an == '2025-09'
            db.session.delete(a)
            db.session.commit()

    def test_create_activitate_validare_proiect_obligatoriu(
            self, app, authenticated_client, admin_with_data):
        """Fara proiect, nu salveaza."""
        from models import db, RaportActivitate

        resp = authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            # proiect_ids[] missing
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_NO_PROJ',
            'actiune': 'draft',
        }, follow_redirects=False)
        # Asteapta redirect cu flash error sau 200 cu mesaj
        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_NO_PROJ'
            ).first()
            assert a is None  # NU s-a salvat

    def test_create_multi_proiect(self, app, authenticated_client, admin_with_data):
        from models import db, Proiect, RaportActivitate
        from tests.fixtures.data import make_proiect

        with app.app_context():
            p2 = make_proiect(db, Proiect, cod='PRJ-WB-002')
            p2_id = p2.id

        resp = authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            'proiect_ids[]': [admin_with_data['proiect_id'], p2_id],
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_MULTI_PROJ',
            'status_executie': 'planificata',
            'actiune': 'draft',
        }, follow_redirects=False)

        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_MULTI_PROJ'
            ).first()
            assert a is not None
            assert sorted(a.proiecte_lista) == sorted([admin_with_data['proiect_id'], p2_id])
            db.session.delete(a)
            Proiect.query.filter_by(cod_proiect='PRJ-WB-002').delete()
            db.session.commit()


class TestActivitatiWorkflow:
    """Test workflow draft -> trimis -> aprobat / respins."""

    def test_workflow_draft_to_trimis(self, app, authenticated_client, admin_with_data):
        from models import db, RaportActivitate

        # 1. Create draft
        authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            'proiect_ids[]': [admin_with_data['proiect_id']],
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_WF_DRAFT',
            'actiune': 'draft',
        })
        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_WF_DRAFT'
            ).first()
            assert a.status == 'draft'
            aid = a.id

        # 2. Trimite
        resp = authenticated_client.post(f'/activitati/{aid}/trimite')
        assert resp.status_code in (200, 302)
        with app.app_context():
            a2 = RaportActivitate.query.get(aid)
            assert a2.status == 'trimis'
            db.session.delete(a2); db.session.commit()

    def test_workflow_aprobare_de_admin(self, app, authenticated_client, admin_with_data):
        from models import db, RaportActivitate

        # 1. Create + trimite
        authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            'proiect_ids[]': [admin_with_data['proiect_id']],
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_WF_APR',
            'actiune': 'trimite',
        })
        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_WF_APR'
            ).first()
            assert a.status == 'trimis'
            aid = a.id

        # 2. Aproba
        resp = authenticated_client.post(f'/activitati/{aid}/aproba')
        assert resp.status_code in (200, 302)
        with app.app_context():
            a2 = RaportActivitate.query.get(aid)
            assert a2.status == 'aprobat'
            assert a2.aprobat_de_id is not None
            assert a2.data_aprobare is not None
            db.session.delete(a2); db.session.commit()

    def test_workflow_respingere(self, app, authenticated_client, admin_with_data):
        from models import db, RaportActivitate

        authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            'proiect_ids[]': [admin_with_data['proiect_id']],
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_WF_REJ',
            'actiune': 'trimite',
        })
        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_WF_REJ'
            ).first()
            aid = a.id

        resp = authenticated_client.post(f'/activitati/{aid}/respinge', data={
            'motiv_respingere': 'Date incomplete',
        })
        assert resp.status_code in (200, 302)
        with app.app_context():
            a2 = RaportActivitate.query.get(aid)
            assert a2.status == 'respins'
            assert 'incomplete' in (a2.motiv_respingere or '').lower()
            db.session.delete(a2); db.session.commit()

    def test_stergere_draft(self, app, authenticated_client, admin_with_data):
        from models import db, RaportActivitate

        authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            'proiect_ids[]': [admin_with_data['proiect_id']],
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_WF_DEL',
            'actiune': 'draft',
        })
        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_WF_DEL'
            ).first()
            aid = a.id

        resp = authenticated_client.post(f'/activitati/{aid}/sterge')
        assert resp.status_code in (200, 302)
        with app.app_context():
            assert RaportActivitate.query.get(aid) is None


class TestActivitatiFiltre:
    """Test filtre pe panou."""

    def test_filtru_tip_zilnica(self, authenticated_client):
        resp = authenticated_client.get('/activitati/?tip=zilnica')
        assert resp.status_code == 200

    def test_filtru_status(self, authenticated_client):
        resp = authenticated_client.get('/activitati/?status=draft')
        assert resp.status_code == 200

    def test_filtru_status_executie(self, authenticated_client):
        resp = authenticated_client.get('/activitati/?status_executie=planificata')
        assert resp.status_code == 200

    def test_filtre_combinate(self, authenticated_client):
        resp = authenticated_client.get(
            '/activitati/?tip=saptamanala&status=draft&status_executie=in_desfasurare'
        )
        assert resp.status_code == 200

    def test_filtru_data_range(self, authenticated_client):
        resp = authenticated_client.get(
            '/activitati/?data_start=2025-09-01&data_end=2025-09-30'
        )
        assert resp.status_code == 200


class TestActivitatiDetalii:
    """Test pagina detaliu activitate."""

    def test_detaliu_activitate_se_incarca(self, app, authenticated_client, admin_with_data):
        from models import db, RaportActivitate

        # Create
        authenticated_client.post('/activitati/adauga', data={
            'angajat_id': admin_with_data['angajat_id'],
            'proiect_ids[]': [admin_with_data['proiect_id']],
            'data': '2025-09-01',
            'tip_activitate': 'zilnica',
            'activitate_principala': 'TEST_DETALIU',
            'actiune': 'draft',
        })
        with app.app_context():
            a = RaportActivitate.query.filter_by(
                activitate_principala='TEST_DETALIU'
            ).first()
            aid = a.id

        resp = authenticated_client.get(f'/activitati/{aid}')
        assert resp.status_code == 200
        assert b'TEST_DETALIU' in resp.data

        with app.app_context():
            db.session.delete(RaportActivitate.query.get(aid))
            db.session.commit()

    def test_detaliu_404_pentru_id_inexistent(self, authenticated_client):
        resp = authenticated_client.get('/activitati/999999')
        assert resp.status_code == 404
