"""
Smoke tests pentru Faza 10 - Contract Controls CRUD.

Verifica:
  - Flag OFF -> toate endpoint-urile dau 404 (modul invizibil default)
  - Flag ON  -> GET lista / formular / detalii functioneaza (200)
  - POST nou Contract -> creeaza in DB + audit log entry
  - POST editeaza -> actualizeaza + audit update entry
  - POST sterge -> sterge + audit delete entry
  - Endpoint-uri TermenContract si ProcesVerbal raspund
"""

from datetime import date
import pytest


# ============================================================
# Helpers
# ============================================================

@pytest.fixture
def flag_on(app):
    """Activeaza flag-ul 'controale-contract' pentru toata durata testului."""
    from models import db
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
    yield
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        # Cleanup contracte create in test
        from models import Contract, TermenContract, ProcesVerbal, Proiect
        TermenContract.query.delete()
        ProcesVerbal.query.delete()
        # NU stergem direct Contract pentru ca exista FK self -> trebuie order
        # Stergem mai intai acte aditionale, apoi principale
        Contract.query.filter(Contract.parinte_contract_id.isnot(None)).delete()
        Contract.query.delete()
        Proiect.query.filter(Proiect.cod_proiect.like('F10-PRJ-%')).delete()
        db.session.commit()


@pytest.fixture
def proiect_f10(app):
    """Proiect minimal pentru testele Faza 10."""
    from models import db, Proiect
    with app.app_context():
        p = Proiect.query.filter_by(cod_proiect='F10-PRJ-001').first()
        if not p:
            p = Proiect(
                cod_proiect='F10-PRJ-001', nume='F10 Test',
                data_start=date(2025, 1, 1), status='activ',
            )
            db.session.add(p)
            db.session.commit()
        yield p.id


# ============================================================
# FLAG OFF: tot modulul e invizibil
# ============================================================

class TestFlagOff:
    """Cu flag-ul off, toate endpoint-urile contracte trebuie sa dea 404."""

    def test_lista_404(self, authenticated_client):
        r = authenticated_client.get('/contracte/')
        assert r.status_code == 404

    def test_formular_nou_404(self, authenticated_client):
        r = authenticated_client.get('/contracte/nou')
        assert r.status_code == 404

    def test_pv_lista_404(self, authenticated_client):
        r = authenticated_client.get('/contracte/pv')
        assert r.status_code == 404

    def test_post_create_404(self, authenticated_client):
        """Cu flag off, chiar si POST blocat -> 404 (nu se creeaza nimic)."""
        r = authenticated_client.post('/contracte/nou', data={
            'nr_contract': 'EVIL-001', 'data_semnare': '2025-01-01',
        })
        assert r.status_code == 404


# ============================================================
# FLAG ON: CRUD Contract
# ============================================================

class TestContractCRUD:
    def test_lista_ok(self, authenticated_client, flag_on):
        r = authenticated_client.get('/contracte/')
        assert r.status_code == 200
        assert b'Contracte' in r.data or b'contracte' in r.data

    def test_formular_nou_get(self, authenticated_client, flag_on):
        r = authenticated_client.get('/contracte/nou')
        assert r.status_code == 200
        # Form fields prezente
        assert b'nr_contract' in r.data
        assert b'data_semnare' in r.data

    def test_create_contract_post(self, app, authenticated_client, flag_on, proiect_f10):
        from models import Contract, AuditLog
        r = authenticated_client.post('/contracte/nou', data={
            'proiect_id': str(proiect_f10),
            'parinte_contract_id': '0',
            'nr_contract': 'F10-CTR-CRUD-001',
            'data_semnare': '2025-03-15',
            'data_finalizare_planificata': '2026-06-30',
            'valoare_totala': '1250000.00',
            'moneda': 'RON',
            'beneficiar': 'Beneficiar SRL',
            'antreprenor': 'Antreprenor SA',
            'obiect_contract': 'Constructie cladire birouri',
            'status': 'activ',
        }, follow_redirects=False)
        # Trebuie redirect catre detalii dupa create
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            c = Contract.query.filter_by(nr_contract='F10-CTR-CRUD-001').first()
            assert c is not None
            assert c.proiect_id == proiect_f10
            assert c.status == 'activ'
            assert str(c.valoare_totala) == '1250000.00'
            # Audit entry pentru create
            audits = AuditLog.query.filter_by(
                entity_type='contract', entity_id=c.id, action='create'
            ).all()
            assert len(audits) >= 1

    def test_detalii_ok(self, app, authenticated_client, flag_on, proiect_f10):
        from models import db, Contract
        with app.app_context():
            c = Contract(proiect_id=proiect_f10, nr_contract='F10-CTR-DET',
                         data_semnare=date(2025, 1, 1), status='activ')
            db.session.add(c); db.session.commit()
            cid = c.id
        r = authenticated_client.get(f'/contracte/{cid}')
        assert r.status_code == 200
        assert b'F10-CTR-DET' in r.data

    def test_detalii_404_on_missing(self, authenticated_client, flag_on):
        r = authenticated_client.get('/contracte/999999')
        assert r.status_code == 404

    def test_edit_post(self, app, authenticated_client, flag_on, proiect_f10):
        from models import db, Contract, AuditLog
        with app.app_context():
            c = Contract(proiect_id=proiect_f10, nr_contract='F10-CTR-EDIT',
                         data_semnare=date(2025, 1, 1), status='activ')
            db.session.add(c); db.session.commit()
            cid = c.id
        r = authenticated_client.post(f'/contracte/{cid}/editeaza', data={
            'contract_id': str(cid),
            'proiect_id': str(proiect_f10),
            'parinte_contract_id': '0',
            'nr_contract': 'F10-CTR-EDIT',
            'data_semnare': '2025-01-01',
            'status': 'suspendat',
            'moneda': 'RON',
        }, follow_redirects=False)
        assert r.status_code in (302, 303)
        with app.app_context():
            c = Contract.query.get(cid)
            assert c.status == 'suspendat'
            audits = AuditLog.query.filter_by(
                entity_type='contract', entity_id=cid, action='update'
            ).all()
            assert len(audits) >= 1

    def test_delete_post(self, app, authenticated_client, flag_on, proiect_f10):
        from models import db, Contract, AuditLog
        with app.app_context():
            c = Contract(proiect_id=proiect_f10, nr_contract='F10-CTR-DEL',
                         data_semnare=date(2025, 1, 1), status='activ')
            db.session.add(c); db.session.commit()
            cid = c.id
        r = authenticated_client.post(f'/contracte/{cid}/sterge', follow_redirects=False)
        assert r.status_code in (302, 303)
        with app.app_context():
            assert Contract.query.get(cid) is None
            audits = AuditLog.query.filter_by(
                entity_type='contract', entity_id=cid, action='delete'
            ).all()
            assert len(audits) >= 1


# ============================================================
# TermenContract CRUD
# ============================================================

class TestTermenCRUD:
    def test_termen_nou_get(self, app, authenticated_client, flag_on, proiect_f10):
        from models import db, Contract
        with app.app_context():
            c = Contract(proiect_id=proiect_f10, nr_contract='F10-CTR-TRMN',
                         data_semnare=date(2025, 1, 1), status='activ')
            db.session.add(c); db.session.commit()
            cid = c.id
        r = authenticated_client.get(f'/contracte/{cid}/termen/nou')
        assert r.status_code == 200

    def test_termen_create_post(self, app, authenticated_client, flag_on, proiect_f10):
        from models import db, Contract, TermenContract
        with app.app_context():
            c = Contract(proiect_id=proiect_f10, nr_contract='F10-CTR-TPOST',
                         data_semnare=date(2025, 1, 1), status='activ')
            db.session.add(c); db.session.commit()
            cid = c.id
        r = authenticated_client.post(f'/contracte/{cid}/termen/nou', data={
            'denumire': 'Predare amplasament F10',
            'tip': 'predare_amplasament',
            'data_scadenta': '2025-03-01',
            'zile_alerta_inainte': '7',
            'status': 'planificat',
            'responsabil_id': '0',
        }, follow_redirects=False)
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            t = TermenContract.query.filter_by(
                contract_id=cid, denumire='Predare amplasament F10'
            ).first()
            assert t is not None
            assert t.tip == 'predare_amplasament'


# ============================================================
# ProcesVerbal CRUD
# ============================================================

class TestProcesVerbalCRUD:
    def test_pv_lista_ok(self, authenticated_client, flag_on):
        r = authenticated_client.get('/contracte/pv')
        assert r.status_code == 200

    def test_pv_create_post(self, app, authenticated_client, flag_on, proiect_f10):
        from models import ProcesVerbal
        r = authenticated_client.post('/contracte/pv/nou', data={
            'proiect_id': str(proiect_f10),
            'contract_id': '0',
            'tip': 'predare_amplasament',
            'numar': 'F10-PV-001',
            'data_emitere': '2025-02-15',
            'obiect': 'Predare amplasament test',
            'concluzii': 'OK',
            'participanti_text': 'Ion Test | Diriginte | Beneficiar SRL\nMaria Test | PM | Antreprenor SA',
            'semnat': 'y',
        }, follow_redirects=False)
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            pv = ProcesVerbal.query.filter_by(numar='F10-PV-001').first()
            assert pv is not None
            assert pv.tip == 'predare_amplasament'
            assert pv.semnat is True
            # Verific parser participanti
            assert len(pv.participanti) == 2
            assert pv.participanti[0]['nume'] == 'Ion Test'


# ============================================================
# Sanity: app-ul porneste cu blueprint inregistrat
# ============================================================

def test_blueprint_registered(app):
    """Sanity: contracte_bp e in app.blueprints."""
    assert 'contracte' in app.blueprints


def test_sidebar_link_invisible_with_flag_off(authenticated_client):
    """Cu flag-ul off, link-ul 'Contracte' nu apare in sidebar."""
    r = authenticated_client.get('/')
    assert r.status_code in (200, 302)
    if r.status_code == 200:
        # Daca redirected, urmarim 1 nivel
        body = r.data.decode('utf-8', errors='ignore')
        # In sidebar nu trebuie sa apara '/contracte/' ca href
        # (poate apare in URL-uri unrelated, dar in sidebar specific NU)
        assert 'href="/contracte/"' not in body, (
            'Link Contracte aparut in sidebar cu flag off!'
        )


def test_sidebar_link_visible_with_flag_on(authenticated_client, flag_on):
    """Cu flag-ul on, link-ul 'Contracte' apare in sidebar."""
    r = authenticated_client.get('/')
    if r.status_code == 200:
        body = r.data.decode('utf-8', errors='ignore')
        assert '/contracte/' in body, 'Link Contracte lipsa cu flag on'
