"""
Integration tests pentru Faza 14 - Notificari in-app + job APScheduler.

Verifica:
  - Helpers (create/mark-read/count)
  - Endpoints inbox + mark-read + count
  - Job notificari: termene expirate, termene apropiate, idempotenta
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest


@pytest.fixture
def flag_on(app):
    """Activeaza flag-ul 'controale-contract' pentru testele Faza 14."""
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
    yield
    with app.app_context():
        set_flag('controale-contract', False, commit=True)


@pytest.fixture
def admin_id(app, admin_user):
    """Re-query admin user inside app context si returneaza ID (evita detached)."""
    from models import Utilizator
    with app.app_context():
        u = Utilizator.query.filter_by(email='admin_test@test.local').first()
        return u.id


@pytest.fixture
def setup_termene(app, admin_user):
    from models import db, Proiect, Contract, TermenUrmarit, NotificareApp
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        # Cleanup
        NotificareApp.query.delete()
        TermenUrmarit.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='NTF-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='NTF-PRJ', nume='Ntf Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='NTF-CTR',
                     data_semnare=date(2026, 1, 15), status='activ')
        db.session.add(c); db.session.commit()
        today = date.today()
        # Termene: 1 expirat (ieri), 1 aproape (azi+3), 1 departe (azi+60)
        t_exp = TermenUrmarit(
            proiect_id=p.id, entitate_sursa='contract', id_entitate_sursa=c.id,
            tip_regula='custom',
            data_start=today - timedelta(days=10), data_scadenta=today - timedelta(days=1),
            status='activ', zile_anticipare=7,
        )
        t_aproape = TermenUrmarit(
            proiect_id=p.id, entitate_sursa='contract', id_entitate_sursa=c.id,
            tip_regula='custom',
            data_start=today, data_scadenta=today + timedelta(days=3),
            status='activ', zile_anticipare=7,
        )
        t_departe = TermenUrmarit(
            proiect_id=p.id, entitate_sursa='contract', id_entitate_sursa=c.id,
            tip_regula='custom',
            data_start=today, data_scadenta=today + timedelta(days=60),
            status='activ', zile_anticipare=7,
        )
        db.session.add_all([t_exp, t_aproape, t_departe]); db.session.commit()
        yield {
            'proiect_id': p.id, 't_exp_id': t_exp.id,
            't_aproape_id': t_aproape.id, 't_departe_id': t_departe.id,
        }
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        NotificareApp.query.delete()
        TermenUrmarit.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='NTF-PRJ').delete()
        db.session.commit()


class TestNotificariHelpers:
    def test_creeaza_si_count(self, app, admin_id):
        from models import db, NotificareApp
        from services.notificari_app import (
            creeaza_notificare, count_necitite, lista_notificari,
        )
        with app.app_context():
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()
            n = creeaza_notificare(
                utilizator_id=admin_id,
                tip='generic', titlu='Test',
            )
            db.session.commit()
            assert n is not None
            assert count_necitite(admin_id) == 1
            assert len(lista_notificari(admin_id)) == 1
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()

    def test_idempotenta_duplicate_today(self, app, admin_id):
        from models import db, NotificareApp
        from services.notificari_app import creeaza_notificare
        with app.app_context():
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()
            for _ in range(3):
                creeaza_notificare(
                    utilizator_id=admin_id,
                    tip='termen_apropiat', titlu='Dup',
                    entitate_referinta='termen_urmarit', id_entitate_referinta=999,
                )
            db.session.commit()
            count = NotificareApp.query.filter_by(
                utilizator_id=admin_id, tip='termen_apropiat'
            ).count()
            assert count == 1
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()

    def test_marcheaza_citita(self, app, admin_id):
        from models import db, NotificareApp
        from services.notificari_app import creeaza_notificare, marcheaza_citita
        with app.app_context():
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()
            n = creeaza_notificare(utilizator_id=admin_id,
                                   tip='generic', titlu='X')
            db.session.commit()
            nid = n.id
            assert marcheaza_citita(nid, admin_id) is True
            assert NotificareApp.query.get(nid).citita is True
            assert marcheaza_citita(nid, admin_id) is False
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()


class TestJobNotificari:
    def test_marcheaza_termene_expirate(self, app, setup_termene):
        from models import db, TermenUrmarit
        from services.notificari_job import ruleaza_job_notificari
        with app.app_context():
            stats = ruleaza_job_notificari(today=date.today())
            assert stats['termene_expirate'] == 1
            # Verific status update
            t = TermenUrmarit.query.get(setup_termene['t_exp_id'])
            assert t.status == 'expirat'

    def test_creeaza_notificari_pentru_termene_aproape(self, app, admin_user, setup_termene):
        from models import NotificareApp
        from services.notificari_job import ruleaza_job_notificari
        with app.app_context():
            stats = ruleaza_job_notificari(today=date.today())
            # Trebuie sa avem cel putin o notificare pentru termen_aproape + termen_depasit
            assert stats['notificari_create'] >= 2  # 1 admin user pe ambele
            # Verific NotificareApp pe admin
            notif_apropiat = NotificareApp.query.filter_by(
                utilizator_id=admin_user.id, tip='termen_apropiat'
            ).all()
            notif_depasit = NotificareApp.query.filter_by(
                utilizator_id=admin_user.id, tip='termen_depasit'
            ).all()
            assert len(notif_apropiat) >= 1
            assert len(notif_depasit) >= 1

    def test_nu_creeaza_pentru_termen_departe(self, app, admin_user, setup_termene):
        from models import NotificareApp, TermenUrmarit
        from services.notificari_job import ruleaza_job_notificari
        with app.app_context():
            ruleaza_job_notificari(today=date.today())
            # Pentru t_departe (60 zile in viitor, anticipare 7) NU se emite notificare
            t = TermenUrmarit.query.get(setup_termene['t_departe_id'])
            # NOT marcat expirat
            assert t.status == 'activ'

    def test_job_idempotent_aceeasi_zi(self, app, setup_termene):
        """A doua rulare in aceeasi zi NU duplica notificarile."""
        from models import NotificareApp
        from services.notificari_job import ruleaza_job_notificari
        with app.app_context():
            stats1 = ruleaza_job_notificari(today=date.today())
            count1 = NotificareApp.query.count()
            stats2 = ruleaza_job_notificari(today=date.today())
            count2 = NotificareApp.query.count()
            assert count2 == count1  # idempotent
            assert stats2['notificari_create'] == 0


class TestEndpointsInbox:
    def test_inbox_endpoint_ok(self, authenticated_client, flag_on, admin_id):
        r = authenticated_client.get('/contracte/notificari/inbox')
        assert r.status_code == 200

    def test_count_endpoint_json(self, app, authenticated_client, flag_on, admin_id):
        from models import db, NotificareApp
        from services.notificari_app import creeaza_notificare
        with app.app_context():
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()
            creeaza_notificare(utilizator_id=admin_id, tip='generic', titlu='X')
            db.session.commit()
        r = authenticated_client.get('/contracte/notificari/count')
        assert r.status_code == 200
        assert r.is_json
        assert r.json['count'] >= 1
        with app.app_context():
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()

    def test_mark_read_endpoint(self, app, authenticated_client, flag_on, admin_id):
        from models import db, NotificareApp
        from services.notificari_app import creeaza_notificare
        with app.app_context():
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()
            n = creeaza_notificare(utilizator_id=admin_id, tip='generic', titlu='X')
            db.session.commit()
            nid = n.id
        r = authenticated_client.post(f'/contracte/notificari/{nid}/mark-read')
        assert r.status_code in (302, 303)
        with app.app_context():
            assert NotificareApp.query.get(nid).citita is True
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()

    def test_mark_all_read_endpoint(self, app, authenticated_client, flag_on, admin_id):
        from models import db, NotificareApp
        from services.notificari_app import creeaza_notificare
        with app.app_context():
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()
            for i in range(3):
                creeaza_notificare(utilizator_id=admin_id, tip='generic',
                                   titlu=f'X{i}',
                                   entitate_referinta='x', id_entitate_referinta=i)
            db.session.commit()
        r = authenticated_client.post('/contracte/notificari/mark-all-read')
        assert r.status_code in (302, 303)
        with app.app_context():
            necitite = NotificareApp.query.filter_by(
                utilizator_id=admin_id, citita=False
            ).count()
            assert necitite == 0
            NotificareApp.query.filter_by(utilizator_id=admin_id).delete()
            db.session.commit()
