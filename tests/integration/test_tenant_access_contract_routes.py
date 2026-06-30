"""Teste tenant access pentru rutele principale de contracte."""

from datetime import date
from decimal import Decimal

import pytest


COD_A = 'TA-CONTRACT-PRJ-A'
COD_B = 'TA-CONTRACT-PRJ-B'
NR_CREATE = 'TA-CONTRACT-NEW'


@pytest.fixture(autouse=True)
def curata_contract_tenant_access(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_lista_mode_off_arata_toate_contractele(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get('/contracte/')

    assert raspuns.status_code == 200
    assert b'TA-CONTRACT-A' in raspuns.data
    assert b'TA-CONTRACT-B' in raspuns.data
    assert ids['contract_a'] != ids['contract_b']


def test_detalii_mode_off_functioneaza(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get(f'/contracte/{ids["contract_b"]}')

    assert raspuns.status_code == 200
    assert b'TA-CONTRACT-B' in raspuns.data


def test_strict_lista_arata_doar_contractele_tenantului(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get('/contracte/')

    assert raspuns.status_code == 200
    assert b'TA-CONTRACT-A' in raspuns.data
    assert b'TA-CONTRACT-B' not in raspuns.data


def test_optional_cu_tenant_scopeaza_lista(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'optional'

    raspuns = authenticated_client.get('/contracte/')

    assert raspuns.status_code == 200
    assert b'TA-CONTRACT-A' in raspuns.data
    assert b'TA-CONTRACT-B' not in raspuns.data


def test_optional_fara_tenant_ramane_permisiv(authenticated_client, app):
    _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'optional'

    raspuns = authenticated_client.get('/contracte/')

    assert raspuns.status_code == 200
    assert b'TA-CONTRACT-A' in raspuns.data
    assert b'TA-CONTRACT-B' in raspuns.data


def test_strict_lista_numara_doar_acte_aditionale_same_tenant(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _creeaza_copii_contract_corupti(app, ids)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get('/contracte/')
    body = raspuns.get_data(as_text=True)

    assert raspuns.status_code == 200
    assert 'TA-CONTRACT-A' in body
    assert '+1 acte aditionale' in body
    assert '+2 acte aditionale' not in body
    assert 'TA-CONTRACT-ADD-FOREIGN' not in body


def test_strict_detalii_ascunde_acte_aditionale_straine(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _creeaza_copii_contract_corupti(app, ids)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/contracte/{ids["contract_a"]}')
    body = raspuns.get_data(as_text=True)

    assert raspuns.status_code == 200
    assert 'TA-CONTRACT-ADD-A' in body
    assert 'TA-CONTRACT-ADD-FOREIGN' not in body


def test_strict_detalii_ascunde_program_oferta_si_pozitii_straine(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _creeaza_copii_contract_corupti(app, ids)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/contracte/{ids["contract_a"]}')
    body = raspuns.get_data(as_text=True)

    assert raspuns.status_code == 200
    assert 'TA-PROG-A' in body
    assert 'TA-PROG-FOREIGN-LINK' not in body
    assert '777777.00 RON' not in body
    assert '<td>1</td>' in body
    assert '<td>2</td>' not in body


def test_optional_cu_tenant_detalii_ascunde_copii_contract_straini(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _creeaza_copii_contract_corupti(app, ids)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'optional'

    raspuns = authenticated_client.get(f'/contracte/{ids["contract_a"]}')
    body = raspuns.get_data(as_text=True)

    assert raspuns.status_code == 200
    assert 'TA-CONTRACT-ADD-A' in body
    assert 'TA-CONTRACT-ADD-FOREIGN' not in body
    assert 'TA-PROG-FOREIGN-LINK' not in body
    assert '777777.00 RON' not in body


def test_mode_off_detalii_pastreaza_copiii_legacy_nefiltrati(
    authenticated_client, app
):
    ids = _creeaza_date(app)
    _creeaza_copii_contract_corupti(app, ids)
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get(f'/contracte/{ids["contract_a"]}')
    body = raspuns.get_data(as_text=True)

    assert raspuns.status_code == 200
    assert 'TA-CONTRACT-ADD-FOREIGN' in body
    assert 'TA-PROG-FOREIGN-LINK' in body
    assert '777777.00 RON' in body
    assert '<td>2</td>' in body


def test_strict_blocheaza_contract_strain_detalii_edit_delete(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    detalii = authenticated_client.get(f'/contracte/{ids["contract_b"]}')
    edit = authenticated_client.get(f'/contracte/{ids["contract_b"]}/editeaza')
    sterge = authenticated_client.post(f'/contracte/{ids["contract_b"]}/sterge')

    assert detalii.status_code == 404
    assert edit.status_code == 404
    assert sterge.status_code == 404


def test_strict_creare_contract_asigneaza_tenantul_curent(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/contracte/nou', data=_form_contract(
        ids['proiect_a'],
        NR_CREATE,
    ))

    assert raspuns.status_code in (302, 303)
    with app.app_context():
        from models import Contract

        contract = Contract.query.filter_by(nr_contract=NR_CREATE).one()
        assert contract.tenant_id == ids['tenant_a']
        assert contract.proiect_id == ids['proiect_a']


def test_strict_user_normal_fara_tenant_nu_creeaza_sau_acceseaza(
    operator_client, app
):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    lista = operator_client.get('/contracte/')
    detalii = operator_client.get(f'/contracte/{ids["contract_a"]}')
    creare = operator_client.post('/contracte/nou', data=_form_contract(
        ids['proiect_a'],
        NR_CREATE,
    ))

    assert lista.status_code == 200
    assert b'TA-CONTRACT-A' not in lista.data
    assert detalii.status_code == 404
    assert creare.status_code == 403


def test_strict_super_admin_are_acces_explicit_nefiltrat(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    lista = authenticated_client.get('/contracte/')
    detalii_b = authenticated_client.get(f'/contracte/{ids["contract_b"]}')

    assert lista.status_code == 200
    assert b'TA-CONTRACT-A' in lista.data
    assert b'TA-CONTRACT-B' in lista.data
    assert detalii_b.status_code == 200


def test_strict_blocheaza_program_si_oferta_straine(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    program_import = authenticated_client.get(
        f'/contracte/{ids["contract_b"]}/program/import'
    )
    program_detalii = authenticated_client.get(
        f'/contracte/program/{ids["program_b"]}'
    )
    oferta_import = authenticated_client.get(
        f'/contracte/{ids["contract_b"]}/oferta/import'
    )
    oferta_detalii = authenticated_client.get(
        f'/contracte/oferta/{ids["oferta_b"]}'
    )
    oferta_cantitati = authenticated_client.get(
        f'/contracte/oferta/{ids["oferta_b"]}/cantitati'
    )

    assert program_import.status_code == 404
    assert program_detalii.status_code == 404
    assert oferta_import.status_code == 404
    assert oferta_detalii.status_code == 404
    assert oferta_cantitati.status_code == 404


def test_strict_blocheaza_situatie_straina_si_exportul(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    detalii = authenticated_client.get(f'/contracte/situatie/{ids["situatie_b"]}')
    export = authenticated_client.get(
        f'/contracte/situatie/{ids["situatie_b"]}/export/xlsx'
    )
    export_pdf = authenticated_client.get(
        f'/contracte/situatie/{ids["situatie_b"]}/export/pdf'
    )
    status = authenticated_client.post(
        f'/contracte/situatie/{ids["situatie_b"]}/status',
        data={'nou_status': 'emisa'},
    )

    assert detalii.status_code == 404
    assert export.status_code == 404
    assert export_pdf.status_code == 404
    assert status.status_code == 404


def test_strict_revendicari_lista_si_detalii_sunt_tenant_scoped(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    lista = authenticated_client.get('/contracte/revendicari')
    detalii_b = authenticated_client.get(
        f'/contracte/revendicare/{ids["revendicare_b"]}'
    )
    edit_b = authenticated_client.get(
        f'/contracte/revendicare/{ids["revendicare_b"]}/editeaza'
    )

    assert lista.status_code == 200
    assert b'TA-REV-A' in lista.data
    assert b'TA-REV-B' not in lista.data
    assert detalii_b.status_code == 404
    assert edit_b.status_code == 404


def test_strict_blocheaza_link_revendicare_catre_term_task_cantitate_straine(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    link_termen = authenticated_client.post(
        f'/contracte/revendicare/{ids["revendicare_a"]}/link/termen',
        data={'termen_contract_id': str(ids['termen_b']), 'tip_legatura': 'cauza'},
    )
    link_task = authenticated_client.post(
        f'/contracte/revendicare/{ids["revendicare_a"]}/link/task',
        data={'task_program_id': str(ids['task_b']), 'tip_legatura': 'consecinta'},
    )
    link_cantitate = authenticated_client.post(
        f'/contracte/revendicare/{ids["revendicare_a"]}/link/cantitate',
        data={'cantitate_lunara_id': str(ids['cantitate_b'])},
    )

    assert link_termen.status_code == 404
    assert link_task.status_code == 404
    assert link_cantitate.status_code == 404


def test_strict_blocheaza_stergere_link_revendicare_strain(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    sterge_termen = authenticated_client.post(
        f'/contracte/revendicare/{ids["revendicare_a"]}/link/termen/'
        f'{ids["link_termen_b"]}/sterge'
    )
    sterge_task = authenticated_client.post(
        f'/contracte/revendicare/{ids["revendicare_a"]}/link/task/'
        f'{ids["link_task_b"]}/sterge'
    )
    sterge_cantitate = authenticated_client.post(
        f'/contracte/revendicare/{ids["revendicare_a"]}/link/cantitate/'
        f'{ids["link_cantitate_b"]}/sterge'
    )

    assert sterge_termen.status_code == 404
    assert sterge_task.status_code == 404
    assert sterge_cantitate.status_code == 404

    with app.app_context():
        from models import RevendicareCantitate, RevendicareTask, RevendicareTermen, db

        assert db.session.get(RevendicareTermen, ids['link_termen_b']) is not None
        assert db.session.get(RevendicareTask, ids['link_task_b']) is not None
        assert db.session.get(RevendicareCantitate, ids['link_cantitate_b']) is not None


def test_strict_blocheaza_pv_si_centralizator_straine(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    pv_edit = authenticated_client.get(f'/contracte/pv/{ids["pv_b"]}/editeaza')
    pv_docx = authenticated_client.get(f'/contracte/pv/{ids["pv_b"]}/export/docx')
    pv_pdf = authenticated_client.get(f'/contracte/pv/{ids["pv_b"]}/export/pdf')
    centralizator = authenticated_client.get(
        f'/contracte/proiect/{ids["proiect_b"]}/centralizator'
    )
    centralizator_export = authenticated_client.get(
        f'/contracte/proiect/{ids["proiect_b"]}/centralizator/export'
    )
    deviz_general = authenticated_client.get(
        f'/contracte/proiect/{ids["proiect_b"]}/deviz-general'
    )
    deviz_export = authenticated_client.get(
        f'/contracte/proiect/{ids["proiect_b"]}/deviz-general/export'
    )

    assert pv_edit.status_code == 404
    assert pv_docx.status_code == 404
    assert pv_pdf.status_code == 404
    assert centralizator.status_code == 404
    assert centralizator_export.status_code == 404
    assert deviz_general.status_code == 404
    assert deviz_export.status_code == 404


def test_strict_blocheaza_mutatii_boq_si_cantitati_straine(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    cantitate_valideaza = authenticated_client.post(
        f'/contracte/cantitate/{ids["cantitate_b"]}/valideaza'
    )
    cantitate_sterge = authenticated_client.post(
        f'/contracte/cantitate/{ids["cantitate_b"]}/sterge'
    )
    cantitate_bulk = authenticated_client.post(
        f'/contracte/oferta/{ids["oferta_a"]}/cantitati',
        data={f'cantitate_{ids["pozitie_b"]}': '5'},
    )
    clasificare = authenticated_client.post(
        f'/contracte/oferta/{ids["oferta_a"]}/clasificare-manuala',
        data={f'categorie_{ids["pozitie_b"]}': 'ta-route-hijack'},
    )

    assert cantitate_valideaza.status_code == 404
    assert cantitate_sterge.status_code == 404
    assert cantitate_bulk.status_code == 404
    assert clasificare.status_code == 404


def test_strict_tarife_nu_expune_tariful_altui_tenant_si_salvare_scopeaza(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    lista = authenticated_client.get(
        f'/contracte/proiect/{ids["proiect_a"]}/tarife'
    )
    salvare_straina = authenticated_client.post(
        f'/contracte/proiect/{ids["proiect_b"]}/tarife/salveaza',
        data={'tarif_general__ta-route-a': '222'},
    )
    salvare = authenticated_client.post(
        f'/contracte/proiect/{ids["proiect_a"]}/tarife/salveaza',
        data={'tarif_general__ta-route-a': '222'},
    )

    assert lista.status_code == 200
    assert b'ta-route-global' in lista.data
    assert b'ta-route-a' in lista.data
    assert b'ta-route-b' not in lista.data
    assert salvare_straina.status_code == 404
    assert salvare.status_code in (302, 303)

    with app.app_context():
        from models import TarifCategorie

        tarif = TarifCategorie.query.filter_by(
            proiect_id=ids['proiect_a'],
            disciplina='general',
            categorie_lucrare='ta-route-a',
        ).one()
        assert tarif.tenant_id == ids['tenant_a']


def test_strict_termen_form_responsabili_scopeaza_dropdown(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    useri = _creeaza_responsabili(app, ids['tenant_a'], ids['tenant_b'])
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(
        f'/contracte/{ids["contract_a"]}/termen/nou'
    )

    assert raspuns.status_code == 200
    assert b'RespA Vizibil' in raspuns.data
    assert b'-- Niciun responsabil --' in raspuns.data
    assert b'RespB Strain' not in raspuns.data
    assert b'RespA Inactiv' not in raspuns.data
    assert useri['resp_a'] != useri['resp_b']


def test_mode_off_termen_form_pastreaza_responsabilii_legacy(
    authenticated_client, app
):
    ids = _creeaza_date(app)
    _creeaza_responsabili(app, ids['tenant_a'], ids['tenant_b'])
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get(
        f'/contracte/{ids["contract_a"]}/termen/nou'
    )

    assert raspuns.status_code == 200
    assert b'RespA Vizibil' in raspuns.data
    assert b'RespB Strain' in raspuns.data
    assert b'RespA Inactiv' not in raspuns.data


def test_strict_termen_nou_resp_valid_si_fara_responsabil(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    useri = _creeaza_responsabili(app, ids['tenant_a'], ids['tenant_b'])
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    valid = authenticated_client.post(
        f'/contracte/{ids["contract_a"]}/termen/nou',
        data=_form_termen('TA-TERM-RESP-VALID', useri['resp_a']),
        follow_redirects=False,
    )
    fara_responsabil = authenticated_client.post(
        f'/contracte/{ids["contract_a"]}/termen/nou',
        data=_form_termen('TA-TERM-RESP-NONE', 0),
        follow_redirects=False,
    )

    assert valid.status_code in (302, 303)
    assert fara_responsabil.status_code in (302, 303)
    with app.app_context():
        from models import TermenContract

        termen_valid = TermenContract.query.filter_by(
            denumire='TA-TERM-RESP-VALID'
        ).one()
        termen_none = TermenContract.query.filter_by(
            denumire='TA-TERM-RESP-NONE'
        ).one()
        assert termen_valid.tenant_id == ids['tenant_a']
        assert termen_valid.responsabil_id == useri['resp_a']
        assert termen_none.tenant_id == ids['tenant_a']
        assert termen_none.responsabil_id is None


def test_strict_termen_nou_resp_strain_nu_creeaza(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    useri = _creeaza_responsabili(app, ids['tenant_a'], ids['tenant_b'])
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post(
        f'/contracte/{ids["contract_a"]}/termen/nou',
        data=_form_termen('TA-TERM-RESP-STRAIN', useri['resp_b']),
        follow_redirects=False,
    )

    assert raspuns.status_code == 200
    with app.app_context():
        from models import TermenContract

        assert TermenContract.query.filter_by(
            denumire='TA-TERM-RESP-STRAIN'
        ).first() is None


def test_strict_termen_editeaza_resp_strain_nu_actualizeaza(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    useri = _creeaza_responsabili(app, ids['tenant_a'], ids['tenant_b'])
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    with app.app_context():
        from models import TermenContract, db

        termen = db.session.get(TermenContract, ids['termen_a'])
        termen.responsabil_id = useri['resp_a']
        db.session.commit()

    raspuns = authenticated_client.post(
        f'/contracte/termen/{ids["termen_a"]}/editeaza',
        data=_form_termen('TA-TERM-A-EDIT-STRAIN', useri['resp_b']),
        follow_redirects=False,
    )

    assert raspuns.status_code == 200
    with app.app_context():
        from models import TermenContract, db

        termen = db.session.get(TermenContract, ids['termen_a'])
        assert termen.responsabil_id == useri['resp_a']
        assert termen.denumire == 'TA-TERM-A'


def _creeaza_date(app):
    from models import (
        db, Tenant, Proiect, Contract, TermenContract, ProgramReferinta,
        TaskProgram, OfertaContract, PozitieBoQ, CantitateExecutataLunara,
        SituatieLunara, Revendicare, RevendicareTermen, RevendicareTask,
        RevendicareCantitate, ProcesVerbal, TarifCategorie,
    )
    from services.feature_flags import set_flag

    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        set_flag('controale-contract-import-msproject', True, commit=True)

        tenant_a = Tenant(cod='test-ta-contract-a', nume='Tenant Contract A')
        tenant_b = Tenant(cod='test-ta-contract-b', nume='Tenant Contract B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect=COD_A,
            nume='Tenant Contract Project A',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect=COD_B,
            nume='Tenant Contract Project B',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        contract_a = _contract(tenant_a.id, proiect_a.id, 'TA-CONTRACT-A')
        contract_b = _contract(tenant_b.id, proiect_b.id, 'TA-CONTRACT-B')
        db.session.add_all([contract_a, contract_b])
        db.session.commit()

        termen_a = _termen(tenant_a.id, contract_a.id, proiect_a.id, 'TA-TERM-A')
        termen_b = _termen(tenant_b.id, contract_b.id, proiect_b.id, 'TA-TERM-B')
        db.session.add_all([termen_a, termen_b])

        program_a = _program(tenant_a.id, proiect_a.id, contract_a.id, 'TA-PROG-A')
        program_b = _program(tenant_b.id, proiect_b.id, contract_b.id, 'TA-PROG-B')
        db.session.add_all([program_a, program_b])
        db.session.commit()

        task_a = _task(tenant_a.id, program_a.id, proiect_a.id, 'TA-TASK-A')
        task_b = _task(tenant_b.id, program_b.id, proiect_b.id, 'TA-TASK-B')
        db.session.add_all([task_a, task_b])

        oferta_a = _oferta(tenant_a.id, contract_a.id, proiect_a.id)
        oferta_b = _oferta(tenant_b.id, contract_b.id, proiect_b.id)
        db.session.add_all([oferta_a, oferta_b])
        db.session.commit()

        poz_a = _pozitie(tenant_a.id, oferta_a.id, proiect_a.id, 'TA-BOQ-A')
        poz_b = _pozitie(tenant_b.id, oferta_b.id, proiect_b.id, 'TA-BOQ-B')
        db.session.add_all([poz_a, poz_b])
        db.session.commit()

        cant_a = _cantitate(tenant_a.id, poz_a.id, proiect_a.id)
        cant_b = _cantitate(tenant_b.id, poz_b.id, proiect_b.id)
        situatie_a = _situatie(tenant_a.id, proiect_a.id, contract_a.id, 'TA-SIT-A')
        situatie_b = _situatie(tenant_b.id, proiect_b.id, contract_b.id, 'TA-SIT-B')
        rev_a = _revendicare(tenant_a.id, proiect_a.id, contract_a.id, 'TA-REV-A')
        rev_b = _revendicare(tenant_b.id, proiect_b.id, contract_b.id, 'TA-REV-B')
        pv_a = _pv(tenant_a.id, proiect_a.id, contract_a.id, 'TA-PV-A')
        pv_b = _pv(tenant_b.id, proiect_b.id, contract_b.id, 'TA-PV-B')
        db.session.add_all([
            cant_a, cant_b, situatie_a, situatie_b, rev_a, rev_b, pv_a, pv_b,
        ])
        db.session.commit()

        link_termen_b = RevendicareTermen(
            tenant_id=tenant_b.id,
            revendicare_id=rev_b.id,
            termen_contract_id=termen_b.id,
            tip_legatura='cauza',
        )
        link_task_b = RevendicareTask(
            tenant_id=tenant_b.id,
            revendicare_id=rev_b.id,
            task_program_id=task_b.id,
            tip_legatura='consecinta',
        )
        link_cantitate_b = RevendicareCantitate(
            tenant_id=tenant_b.id,
            revendicare_id=rev_b.id,
            cantitate_lunara_id=cant_b.id,
        )
        tarif_global = TarifCategorie(
            tenant_id=None,
            proiect_id=None,
            disciplina='general',
            categorie_lucrare='ta-route-global',
            tarif_baza=Decimal('100'),
        )
        tarif_a = TarifCategorie(
            tenant_id=tenant_a.id,
            proiect_id=None,
            disciplina='general',
            categorie_lucrare='ta-route-a',
            tarif_baza=Decimal('200'),
        )
        tarif_b = TarifCategorie(
            tenant_id=tenant_b.id,
            proiect_id=None,
            disciplina='general',
            categorie_lucrare='ta-route-b',
            tarif_baza=Decimal('300'),
        )
        db.session.add_all([
            link_termen_b, link_task_b, link_cantitate_b,
            tarif_global, tarif_a, tarif_b,
        ])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'contract_a': contract_a.id,
            'contract_b': contract_b.id,
            'termen_a': termen_a.id,
            'termen_b': termen_b.id,
            'program_b': program_b.id,
            'task_b': task_b.id,
            'oferta_a': oferta_a.id,
            'oferta_b': oferta_b.id,
            'pozitie_b': poz_b.id,
            'cantitate_b': cant_b.id,
            'situatie_b': situatie_b.id,
            'revendicare_a': rev_a.id,
            'revendicare_b': rev_b.id,
            'pv_b': pv_b.id,
            'link_termen_b': link_termen_b.id,
            'link_task_b': link_task_b.id,
            'link_cantitate_b': link_cantitate_b.id,
        }


def _creeaza_copii_contract_corupti(app, ids):
    from models import db

    with app.app_context():
        act_aditional_a = _contract(
            ids['tenant_a'], ids['proiect_a'], 'TA-CONTRACT-ADD-A'
        )
        act_aditional_a.parinte_contract_id = ids['contract_a']

        act_aditional_strain = _contract(
            ids['tenant_b'], ids['proiect_b'], 'TA-CONTRACT-ADD-FOREIGN'
        )
        act_aditional_strain.parinte_contract_id = ids['contract_a']

        program_strain = _program(
            ids['tenant_b'],
            ids['proiect_b'],
            ids['contract_a'],
            'TA-PROG-FOREIGN-LINK',
        )
        program_strain.versiune = 2

        oferta_straina = _oferta(
            ids['tenant_b'], ids['contract_a'], ids['proiect_b']
        )
        oferta_straina.versiune = 2
        oferta_straina.valoare_totala = Decimal('777777')

        pozitie_straina = _pozitie(
            ids['tenant_b'], ids['oferta_a'], ids['proiect_b'], 'TA-BOQ-FOREIGN-IN-A'
        )

        db.session.add_all([
            act_aditional_a,
            act_aditional_strain,
            program_strain,
            oferta_straina,
            pozitie_straina,
        ])
        db.session.commit()


def _contract(tenant_id, proiect_id, nr):
    from models import Contract

    return Contract(
        tenant_id=tenant_id,
        proiect_id=proiect_id,
        nr_contract=nr,
        data_semnare=date(2026, 1, 15),
        status='activ',
        valoare_totala=Decimal('100000'),
        moneda='RON',
    )


def _termen(tenant_id, contract_id, proiect_id, denumire):
    from models import TermenContract

    return TermenContract(
        tenant_id=tenant_id,
        contract_id=contract_id,
        proiect_id=proiect_id,
        denumire=denumire,
        tip='executie',
        data_scadenta=date(2026, 5, 1),
        status='planificat',
    )


def _program(tenant_id, proiect_id, contract_id, denumire):
    from models import ProgramReferinta

    return ProgramReferinta(
        tenant_id=tenant_id,
        proiect_id=proiect_id,
        contract_id=contract_id,
        versiune=1,
        denumire=denumire,
        data_emitere=date(2026, 1, 1),
        sursa_import='manual',
    )


def _task(tenant_id, program_id, proiect_id, denumire):
    from models import TaskProgram

    return TaskProgram(
        tenant_id=tenant_id,
        program_id=program_id,
        proiect_id=proiect_id,
        cod_extern=denumire,
        denumire=denumire,
        data_start_planificat=date(2026, 4, 1),
        data_sfarsit_planificat=date(2026, 4, 30),
    )


def _oferta(tenant_id, contract_id, proiect_id):
    from models import OfertaContract

    return OfertaContract(
        tenant_id=tenant_id,
        contract_id=contract_id,
        proiect_id=proiect_id,
        versiune=1,
        data_emitere=date(2026, 1, 20),
        valoare_totala=Decimal('100000'),
        sursa_import='manual',
        aprobata=True,
    )


def _pozitie(tenant_id, oferta_id, proiect_id, cod):
    from models import PozitieBoQ

    return PozitieBoQ(
        tenant_id=tenant_id,
        oferta_id=oferta_id,
        proiect_id=proiect_id,
        cod_articol=cod,
        denumire=cod,
        um='mc',
        cantitate_oferta=Decimal('100'),
        pret_unitar=Decimal('500'),
        categorie='mixt',
        ordine=1,
    )


def _cantitate(tenant_id, pozitie_id, proiect_id):
    from models import CantitateExecutataLunara

    return CantitateExecutataLunara(
        tenant_id=tenant_id,
        pozitie_boq_id=pozitie_id,
        proiect_id=proiect_id,
        an=2026,
        luna=4,
        cantitate_executata=Decimal('10'),
        valoare_calculata=Decimal('5000'),
        validat=True,
    )


def _situatie(tenant_id, proiect_id, contract_id, numar):
    from models import SituatieLunara

    return SituatieLunara(
        tenant_id=tenant_id,
        proiect_id=proiect_id,
        contract_id=contract_id,
        an=2026,
        luna=4,
        status='draft',
        valoare_totala_luna=Decimal('5000'),
        numar_situatie=numar,
    )


def _revendicare(tenant_id, proiect_id, contract_id, numar):
    from models import Revendicare

    return Revendicare(
        tenant_id=tenant_id,
        proiect_id=proiect_id,
        contract_id=contract_id,
        numar_revendicare=numar,
        data_emitere=date(2026, 4, 15),
        tip='intarziere',
        status='draft',
    )


def _pv(tenant_id, proiect_id, contract_id, numar):
    from models import ProcesVerbal

    return ProcesVerbal(
        tenant_id=tenant_id,
        proiect_id=proiect_id,
        contract_id=contract_id,
        tip='predare_amplasament',
        numar=numar,
        data_emitere=date(2026, 2, 1),
    )


def _form_contract(proiect_id, nr_contract):
    return {
        'proiect_id': str(proiect_id),
        'parinte_contract_id': '0',
        'nr_contract': nr_contract,
        'data_semnare': '2026-01-15',
        'data_inceput_referinta': '',
        'data_inceput_executie': '',
        'data_finalizare_planificata': '',
        'valoare_totala': '100000',
        'moneda': 'RON',
        'beneficiar': 'Beneficiar Test',
        'antreprenor': 'Antreprenor Test',
        'obiect_contract': 'Test',
        'observatii': '',
        'status': 'activ',
    }


def _form_termen(denumire, responsabil_id):
    return {
        'denumire': denumire,
        'tip': 'executie',
        'descriere': '',
        'data_scadenta': '2026-05-01',
        'data_realizare': '',
        'zile_alerta_inainte': '7',
        'status': 'planificat',
        'responsabil_id': str(responsabil_id),
    }


def _creeaza_responsabili(app, tenant_a, tenant_b):
    from models import db, Utilizator

    with app.app_context():
        resp_a = Utilizator(
            tenant_id=tenant_a,
            nume='RespA',
            prenume='Vizibil',
            email='ta-contract-resp-a@test.local',
            rol='manager',
            activ=True,
        )
        resp_a.set_password('test_pass_123')
        resp_b = Utilizator(
            tenant_id=tenant_b,
            nume='RespB',
            prenume='Strain',
            email='ta-contract-resp-b@test.local',
            rol='manager',
            activ=True,
        )
        resp_b.set_password('test_pass_123')
        resp_inactiv = Utilizator(
            tenant_id=tenant_a,
            nume='RespA',
            prenume='Inactiv',
            email='ta-contract-resp-inactiv@test.local',
            rol='manager',
            activ=False,
        )
        resp_inactiv.set_password('test_pass_123')
        db.session.add_all([resp_a, resp_b, resp_inactiv])
        db.session.commit()
        return {
            'resp_a': resp_a.id,
            'resp_b': resp_b.id,
            'resp_inactiv': resp_inactiv.id,
        }


def _seteaza_tenant_user(app, user_id, tenant_id):
    from models import db, Utilizator

    with app.app_context():
        user = db.session.get(Utilizator, user_id)
        user.tenant_id = tenant_id
        db.session.commit()


def _curata_date(app):
    from models import (
        db, Tenant, Proiect, Contract, TermenContract, ProgramReferinta,
        TaskProgram, OfertaContract, PozitieBoQ, CantitateExecutataLunara,
        SituatieLunara, Revendicare, RevendicareTermen, RevendicareTask,
        RevendicareCantitate, ProcesVerbal, TarifCategorie, Utilizator,
    )
    from services.feature_flags import set_flag

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'

        for user in Utilizator.query.filter(Utilizator.email.in_([
            'admin_test@test.local',
            'operator_test@test.local',
        ])).all():
            user.tenant_id = None

        RevendicareTermen.query.delete()
        RevendicareTask.query.delete()
        RevendicareCantitate.query.delete()
        TarifCategorie.query.filter(
            TarifCategorie.categorie_lucrare.like('ta-route-%')
        ).delete(synchronize_session=False)
        Revendicare.query.filter(
            Revendicare.numar_revendicare.like('TA-REV-%')
        ).delete()
        SituatieLunara.query.filter(
            SituatieLunara.numar_situatie.like('TA-SIT-%')
        ).delete()
        ProcesVerbal.query.filter(ProcesVerbal.numar.like('TA-PV-%')).delete()
        pozitie_ids = [
            p.id for p in PozitieBoQ.query.filter(
                PozitieBoQ.cod_articol.like('TA-BOQ-%')
            ).all()
        ]
        if pozitie_ids:
            CantitateExecutataLunara.query.filter(
                CantitateExecutataLunara.pozitie_boq_id.in_(pozitie_ids)
            ).delete(synchronize_session=False)
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('TA-BOQ-%')).delete()
        contract_ids = [
            c.id for c in Contract.query.filter(
                Contract.nr_contract.like('TA-CONTRACT%')
            ).all()
        ]
        if contract_ids:
            OfertaContract.query.filter(
                OfertaContract.contract_id.in_(contract_ids)
            ).delete(synchronize_session=False)
        TaskProgram.query.filter(TaskProgram.cod_extern.like('TA-TASK-%')).delete()
        ProgramReferinta.query.filter(ProgramReferinta.denumire.like('TA-PROG-%')).delete()
        TermenContract.query.filter(TermenContract.denumire.like('TA-TERM-%')).delete()
        Utilizator.query.filter(
            Utilizator.email.like('ta-contract-resp-%@test.local')
        ).delete(synchronize_session=False)
        Contract.query.filter(Contract.nr_contract.like('TA-CONTRACT%')).delete()
        Proiect.query.filter(Proiect.cod_proiect.like('TA-CONTRACT-PRJ-%')).delete()
        Tenant.query.filter(Tenant.cod.like('test-ta-contract-%')).delete()

        set_flag('controale-contract-import-msproject', False, commit=False)
        set_flag('controale-contract', False, commit=True)
