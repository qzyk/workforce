"""
Integration tests pentru Faza 13 - Corespondenta:
  - CRUD endpoints
  - Hook auto-creare TermenUrmarit la genereaza_termen=True
  - Hook stergere TermenUrmarit la unset genereaza_termen
  - Lista cu filtre
"""

from datetime import date, timedelta

import pytest


@pytest.fixture
def setup_proiect_coresp(app, admin_user):
    from models import db, Proiect, Contract, Corespondenta, TermenUrmarit
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        TermenUrmarit.query.delete()
        Corespondenta.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='COR-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='COR-PRJ', nume='Cor Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='COR-CTR-001',
                     data_semnare=date(2026, 1, 15), status='activ')
        db.session.add(c); db.session.commit()
        yield {'proiect_id': p.id, 'contract_id': c.id}
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        TermenUrmarit.query.delete()
        Corespondenta.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='COR-PRJ').delete()
        db.session.commit()


class TestCorespondentaCRUD:
    def test_lista_ok(self, authenticated_client, setup_proiect_coresp):
        r = authenticated_client.get('/contracte/corespondenta')
        assert r.status_code == 200

    def test_create_post(self, app, authenticated_client, setup_proiect_coresp):
        from models import Corespondenta
        r = authenticated_client.post('/contracte/corespondenta/nou', data={
            'proiect_id': str(setup_proiect_coresp['proiect_id']),
            'contract_id': str(setup_proiect_coresp['contract_id']),
            'numar_inregistrare': 'COR-TEST-001',
            'data_inregistrare': '2026-03-15',
            'tip': 'scrisoare',
            'subtip': '',
            'directie': 'primita',
            'expeditor': 'Beneficiar SRL',
            'subiect': 'Test subject',
            'raspuns_la_id': '0',
        }, follow_redirects=False)
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            c = Corespondenta.query.filter_by(numar_inregistrare='COR-TEST-001').first()
            assert c is not None
            assert c.tip == 'scrisoare'
            assert c.expeditor == 'Beneficiar SRL'

    def test_detalii_404_invalid(self, authenticated_client, setup_proiect_coresp):
        r = authenticated_client.get('/contracte/corespondenta/999999')
        assert r.status_code == 404


class TestHookAutoTermen:
    """Hook: genereaza_termen=True + notificare -> creeaza TermenUrmarit 30z."""

    def test_creeaza_termen_la_save(
        self, app, authenticated_client, setup_proiect_coresp
    ):
        from models import Corespondenta, TermenUrmarit
        r = authenticated_client.post('/contracte/corespondenta/nou', data={
            'proiect_id': str(setup_proiect_coresp['proiect_id']),
            'contract_id': str(setup_proiect_coresp['contract_id']),
            'numar_inregistrare': 'COR-NOTIF-001',
            'data_inregistrare': '2026-03-01',
            'tip': 'notificare',
            'subtip': 'notificare_cerinte_beneficiar',
            'directie': 'primita',
            'expeditor': 'Beneficiar',
            'genereaza_termen': 'y',
            'raspuns_la_id': '0',
        }, follow_redirects=False)
        assert r.status_code in (302, 303)
        with app.app_context():
            c = Corespondenta.query.filter_by(numar_inregistrare='COR-NOTIF-001').first()
            assert c is not None
            t = TermenUrmarit.query.filter_by(
                entitate_sursa='corespondenta', id_entitate_sursa=c.id
            ).first()
            assert t is not None
            assert t.tip_regula == 'raspuns_30_zile'
            assert t.zile_grace == 30
            assert t.data_scadenta == date(2026, 3, 1) + timedelta(days=30)

    def test_nu_creeaza_termen_fara_flag(
        self, app, authenticated_client, setup_proiect_coresp
    ):
        """Corespondenta fara genereaza_termen -> NU se creeaza TermenUrmarit."""
        from models import Corespondenta, TermenUrmarit
        authenticated_client.post('/contracte/corespondenta/nou', data={
            'proiect_id': str(setup_proiect_coresp['proiect_id']),
            'numar_inregistrare': 'COR-NOFLAG-001',
            'data_inregistrare': '2026-03-01',
            'tip': 'scrisoare',
            'directie': 'primita',
            'raspuns_la_id': '0',
        })
        with app.app_context():
            c = Corespondenta.query.filter_by(numar_inregistrare='COR-NOFLAG-001').first()
            t_count = TermenUrmarit.query.filter_by(
                entitate_sursa='corespondenta', id_entitate_sursa=c.id
            ).count()
            assert t_count == 0

    def test_sterge_termen_la_unset_flag(
        self, app, authenticated_client, setup_proiect_coresp
    ):
        """Edit cu genereaza_termen=False -> sterge TermenUrmarit asociat."""
        from models import db, Corespondenta, TermenUrmarit
        # Create cu genereaza_termen=True
        authenticated_client.post('/contracte/corespondenta/nou', data={
            'proiect_id': str(setup_proiect_coresp['proiect_id']),
            'numar_inregistrare': 'COR-UNSET-001',
            'data_inregistrare': '2026-04-01',
            'tip': 'notificare',
            'subtip': 'notificare_cerinte_beneficiar',
            'directie': 'primita',
            'genereaza_termen': 'y',
            'raspuns_la_id': '0',
        })
        with app.app_context():
            c = Corespondenta.query.filter_by(numar_inregistrare='COR-UNSET-001').first()
            cid = c.id
            assert TermenUrmarit.query.filter_by(
                entitate_sursa='corespondenta', id_entitate_sursa=cid
            ).count() == 1
        # Edit: unset genereaza_termen
        authenticated_client.post(f'/contracte/corespondenta/{cid}/editeaza', data={
            'corespondenta_id': str(cid),
            'proiect_id': str(setup_proiect_coresp['proiect_id']),
            'numar_inregistrare': 'COR-UNSET-001',
            'data_inregistrare': '2026-04-01',
            'tip': 'notificare',
            'subtip': 'notificare_cerinte_beneficiar',
            'directie': 'primita',
            # NU includ genereaza_termen → False
            'raspuns_la_id': '0',
        })
        with app.app_context():
            assert TermenUrmarit.query.filter_by(
                entitate_sursa='corespondenta', id_entitate_sursa=cid
            ).count() == 0

    def test_sterge_corespondenta_sterge_termen(
        self, app, authenticated_client, setup_proiect_coresp
    ):
        """Stergerea corespondentei sterge TermenUrmarit asociat."""
        from models import Corespondenta, TermenUrmarit
        authenticated_client.post('/contracte/corespondenta/nou', data={
            'proiect_id': str(setup_proiect_coresp['proiect_id']),
            'numar_inregistrare': 'COR-DEL-001',
            'data_inregistrare': '2026-05-01',
            'tip': 'notificare',
            'subtip': 'notificare_cerinte_beneficiar',
            'directie': 'primita',
            'genereaza_termen': 'y',
            'raspuns_la_id': '0',
        })
        with app.app_context():
            c = Corespondenta.query.filter_by(numar_inregistrare='COR-DEL-001').first()
            cid = c.id
        authenticated_client.post(f'/contracte/corespondenta/{cid}/sterge')
        with app.app_context():
            assert TermenUrmarit.query.filter_by(
                entitate_sursa='corespondenta', id_entitate_sursa=cid
            ).count() == 0
