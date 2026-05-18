"""
Integration tests pentru Faza 14 - CRUD ReguliNotificareProiect.
"""

from datetime import date

import pytest


@pytest.fixture
def setup_proiect_reg(app, admin_user):
    from models import db, Proiect, ReguliNotificareProiect
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        ReguliNotificareProiect.query.delete()
        Proiect.query.filter_by(cod_proiect='REG-PRJ').delete()
        db.session.commit()
        p = Proiect(cod_proiect='REG-PRJ', nume='Reg Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        yield {'proiect_id': p.id}
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        ReguliNotificareProiect.query.delete()
        Proiect.query.filter_by(cod_proiect='REG-PRJ').delete()
        db.session.commit()


class TestReguliNotificareCRUD:
    def test_lista_ok(self, authenticated_client, setup_proiect_reg):
        r = authenticated_client.get(
            f'/contracte/proiect/{setup_proiect_reg["proiect_id"]}/reguli-notificare'
        )
        assert r.status_code == 200

    def test_create_post(self, app, authenticated_client, setup_proiect_reg):
        from models import ReguliNotificareProiect
        r = authenticated_client.post(
            f'/contracte/proiect/{setup_proiect_reg["proiect_id"]}/reguli-notificare/nou',
            data={
                'tip_eveniment': 'termen_apropiat',
                'zile_anticipare': '7',
                'in_app_activ': 'y',
                'email_activ': 'y',
                'email_destinatari_text': 'manager@firma.ro\nsef@firma.ro\ninvalid_no_at\n',
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            regula = ReguliNotificareProiect.query.filter_by(
                proiect_id=setup_proiect_reg['proiect_id'],
                tip_eveniment='termen_apropiat',
            ).first()
            assert regula is not None
            assert regula.in_app_activ is True
            assert regula.email_activ is True
            # Parser-ul filtreaza linia invalida
            assert regula.email_destinatari == ['manager@firma.ro', 'sef@firma.ro']

    def test_unique_per_proiect_eveniment(self, app, authenticated_client, setup_proiect_reg):
        from models import ReguliNotificareProiect
        # Primul create
        authenticated_client.post(
            f'/contracte/proiect/{setup_proiect_reg["proiect_id"]}/reguli-notificare/nou',
            data={
                'tip_eveniment': 'termen_apropiat',
                'zile_anticipare': '5',
                'in_app_activ': 'y',
            },
        )
        # Al doilea cu acelasi tip_eveniment -> redirect la edit existing
        r = authenticated_client.post(
            f'/contracte/proiect/{setup_proiect_reg["proiect_id"]}/reguli-notificare/nou',
            data={
                'tip_eveniment': 'termen_apropiat',
                'zile_anticipare': '10',
                'in_app_activ': 'y',
            },
            follow_redirects=False,
        )
        # Redirect la edit existing (NU duplicat)
        assert r.status_code in (302, 303)
        with app.app_context():
            count = ReguliNotificareProiect.query.filter_by(
                proiect_id=setup_proiect_reg['proiect_id'],
                tip_eveniment='termen_apropiat',
            ).count()
            assert count == 1

    def test_edit_actualizeaza(self, app, authenticated_client, setup_proiect_reg):
        from models import db, ReguliNotificareProiect
        with app.app_context():
            r = ReguliNotificareProiect(
                proiect_id=setup_proiect_reg['proiect_id'],
                tip_eveniment='termen_depasit',
                zile_anticipare=5,
            )
            db.session.add(r); db.session.commit()
            rid = r.id
        resp = authenticated_client.post(
            f'/contracte/regula-notificare/{rid}/editeaza',
            data={
                'regula_id': str(rid),
                'tip_eveniment': 'termen_depasit',
                'zile_anticipare': '14',
                'in_app_activ': 'y',
                'email_activ': 'y',
                'email_destinatari_text': 'admin@firma.ro',
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        with app.app_context():
            r2 = ReguliNotificareProiect.query.get(rid)
            assert r2.zile_anticipare == 14
            assert r2.email_activ is True
            assert 'admin@firma.ro' in r2.email_destinatari

    def test_sterge(self, app, authenticated_client, setup_proiect_reg):
        from models import db, ReguliNotificareProiect
        with app.app_context():
            r = ReguliNotificareProiect(
                proiect_id=setup_proiect_reg['proiect_id'],
                tip_eveniment='generic',
            )
            db.session.add(r); db.session.commit()
            rid = r.id
        resp = authenticated_client.post(
            f'/contracte/regula-notificare/{rid}/sterge',
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        with app.app_context():
            assert ReguliNotificareProiect.query.get(rid) is None
