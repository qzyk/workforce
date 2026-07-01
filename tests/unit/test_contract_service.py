"""Teste pentru services/contract_service.py (C1A — lista contracte).

Serviciul este read-only si HTTP-free. Verificam contextul de lista, filtrele,
statisticile, scoping-ul tenant si guard-urile de boundary.
"""

from datetime import date
import inspect

import pytest
from flask import g


@pytest.fixture(autouse=True)
def curata_contract_service(app):
    _curata(app)
    yield
    _curata(app)


def test_contract_list_context_returneaza_cheile_asteptate(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_contract_list_context()

    assert set(ctx.keys()) == {
        'contracte',
        'proiecte',
        'status_filtru',
        'proiect_filtru',
        'cautare',
        'total_activ',
        'total_finalizat',
        'total_suspendat',
        'acte_aditionale_count_by_contract_id',
        'statuses',
    }


def test_contract_list_context_arata_doar_contracte_principale(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_contract_list_context()

    numere = {c.nr_contract for c in ctx['contracte']}
    assert 'C1A-A-OLD' in numere
    assert 'C1A-A-NEW' in numere
    assert 'C1A-A-FIN' in numere
    assert 'C1A-ADD-A' not in numere


def test_contract_list_context_filtreaza_dupa_status(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_contract_list_context(status_filter='suspendat')

    assert [c.nr_contract for c in ctx['contracte']] == ['C1A-A-NEW']
    assert ctx['status_filtru'] == 'suspendat'


def test_contract_list_context_filtreaza_dupa_proiect(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_contract_list_context(project_id=ids['proiect_a2'])

    assert [c.nr_contract for c in ctx['contracte']] == ['C1A-A-NEW']
    assert ctx['proiect_filtru'] == ids['proiect_a2']


def test_contract_list_context_cauta_dupa_numar_beneficiar_antreprenor(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            dupa_numar = _numere(get_contract_list_context(search='A-NEW'))
            dupa_beneficiar = _numere(get_contract_list_context(search='Alpha'))
            dupa_antreprenor = _numere(get_contract_list_context(search='Constructor Two'))

    assert dupa_numar == ['C1A-A-NEW']
    assert dupa_beneficiar == ['C1A-A-OLD']
    assert dupa_antreprenor == ['C1A-A-NEW']


def test_contract_list_context_ordoneaza_dupa_data_semnare_desc(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_contract_list_context()

    assert [c.nr_contract for c in ctx['contracte']] == [
        'C1A-A-NEW',
        'C1A-A-FIN',
        'C1A-A-OLD',
    ]


def test_contract_list_context_statistici_independente_de_filtre(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_contract_list_context(status_filter='suspendat', search='NEW')

    assert [c.nr_contract for c in ctx['contracte']] == ['C1A-A-NEW']
    assert ctx['total_activ'] == 1
    assert ctx['total_finalizat'] == 1
    assert ctx['total_suspendat'] == 1


def test_contract_list_context_proiecte_vizibile_tenant_scoped(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_contract_list_context()

    coduri = {p.cod_proiect for p in ctx['proiecte']}
    assert coduri == {'C1A-PA1', 'C1A-PA2'}


def test_contract_list_context_numara_doar_acte_same_tenant(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_contract_list_context()

    assert ctx['acte_aditionale_count_by_contract_id'][ids['contract_a_old']] == 1


def test_contract_list_context_strict_ascunde_contracte_straine(app):
    from services.contract_service import get_contract_list_context

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_contract_list_context()

    assert 'C1A-B' not in _numere(ctx)


def test_contract_list_context_strict_fara_tenant_fail_closed(app):
    from services.contract_service import get_contract_list_context

    _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            ctx = get_contract_list_context()

    assert ctx['contracte'] == []
    assert ctx['proiecte'] == []
    assert ctx['total_activ'] == 0


def test_contract_list_context_mode_off_pastreaza_legacy_nefiltrat(app):
    from services.contract_service import get_contract_list_context

    _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            ctx = get_contract_list_context()

    assert {'C1A-A-OLD', 'C1A-A-NEW', 'C1A-A-FIN', 'C1A-B'} <= set(_numere(ctx))
    assert {p.cod_proiect for p in ctx['proiecte']} == {'C1A-PA1', 'C1A-PA2', 'C1A-PB'}


def test_contract_list_context_fara_mutatii_si_fara_http_boundary():
    import services.contract_service as svc

    sursa = inspect.getsource(svc)
    for token in (
        'db.session.add',
        'db.session.delete',
        'db.session.commit',
        'db.session.rollback',
        'request',
        'flash(',
        'redirect(',
        'render_template',
        'jsonify',
        'send_file',
        'url_for',
    ):
        assert token not in sursa


def _numere(ctx):
    return [c.nr_contract for c in ctx['contracte']]


def _seed(app):
    from models import Contract, Proiect, Tenant, db

    with app.app_context():
        tenant_a = Tenant(cod='test-c1a-contract-a', nume='Tenant C1A A')
        tenant_b = Tenant(cod='test-c1a-contract-b', nume='Tenant C1A B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a1 = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect='C1A-PA1',
            nume='C1A Proiect A1',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_a2 = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect='C1A-PA2',
            nume='C1A Proiect A2',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect='C1A-PB',
            nume='C1A Proiect B',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        db.session.add_all([proiect_a1, proiect_a2, proiect_b])
        db.session.commit()

        contract_a_old = Contract(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a1.id,
            nr_contract='C1A-A-OLD',
            data_semnare=date(2026, 1, 10),
            status='activ',
            beneficiar='Beneficiar Alpha',
            antreprenor='Constructor One',
        )
        contract_a_new = Contract(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a2.id,
            nr_contract='C1A-A-NEW',
            data_semnare=date(2026, 3, 10),
            status='suspendat',
            beneficiar='Beneficiar Beta',
            antreprenor='Constructor Two',
        )
        contract_a_fin = Contract(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a1.id,
            nr_contract='C1A-A-FIN',
            data_semnare=date(2026, 2, 10),
            status='finalizat',
            beneficiar='Beneficiar Gamma',
            antreprenor='Constructor Three',
        )
        contract_b = Contract(
            tenant_id=tenant_b.id,
            proiect_id=proiect_b.id,
            nr_contract='C1A-B',
            data_semnare=date(2026, 4, 10),
            status='activ',
            beneficiar='Beneficiar Strain',
            antreprenor='Constructor Strain',
        )
        db.session.add_all([contract_a_old, contract_a_new, contract_a_fin, contract_b])
        db.session.commit()

        act_a = Contract(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a1.id,
            parinte_contract_id=contract_a_old.id,
            nr_contract='C1A-ADD-A',
            data_semnare=date(2026, 5, 1),
            status='activ',
        )
        act_strain = Contract(
            tenant_id=tenant_b.id,
            proiect_id=proiect_b.id,
            parinte_contract_id=contract_a_old.id,
            nr_contract='C1A-ADD-FOREIGN',
            data_semnare=date(2026, 5, 2),
            status='activ',
        )
        db.session.add_all([act_a, act_strain])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a1': proiect_a1.id,
            'proiect_a2': proiect_a2.id,
            'proiect_b': proiect_b.id,
            'contract_a_old': contract_a_old.id,
            'contract_a_new': contract_a_new.id,
            'contract_a_fin': contract_a_fin.id,
            'contract_b': contract_b.id,
            'act_a': act_a.id,
            'act_strain': act_strain.id,
        }


def _curata(app):
    from models import Contract, Proiect, Tenant, db

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        Contract.query.filter(
            Contract.nr_contract.like('C1A-ADD-%')
        ).delete(synchronize_session=False)
        Contract.query.filter(
            Contract.nr_contract.like('C1A-%')
        ).delete(synchronize_session=False)
        Proiect.query.filter(
            Proiect.cod_proiect.like('C1A-P%')
        ).delete(synchronize_session=False)
        Tenant.query.filter(
            Tenant.cod.like('test-c1a-contract-%')
        ).delete(synchronize_session=False)
        db.session.commit()
