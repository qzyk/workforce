"""Teste pentru tenant access HR/flota."""

from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


@pytest.fixture(autouse=True)
def curata_hr_fleet_tenant_access(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_employees_for_tenant_strict_returneaza_doar_tenantul(app):
    from models import Angajat
    from services.security.tenant_access import query_employees_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        nume = {
            a.nume for a in query_employees_for_tenant()
            .filter(Angajat.nume.like('TAHR%')).all()
        }

    assert nume == {'TAHR Angajat A'}


def test_get_employee_or_404_blocheaza_angajat_strain(app):
    from services.security.tenant_access import get_employee_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_employee_or_404(ids['angajat_b'])

    assert exc.value.code == 404


def test_query_leave_requests_for_tenant_urmeaza_angajatul(app):
    from models import Concediu
    from services.security.tenant_access import query_leave_requests_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        concedii = query_leave_requests_for_tenant().filter(
            Concediu.id.in_([ids['concediu_a'], ids['concediu_b']])
        ).all()

    assert [c.id for c in concedii] == [ids['concediu_a']]


def test_query_machines_for_tenant_strict_returneaza_doar_owner_tenant_safe(app):
    from models import Masina
    from services.security.tenant_access import query_machines_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        numere = {
            m.numar_inmatriculare for m in query_machines_for_tenant()
            .filter(Masina.numar_inmatriculare.like('TAHR-%')).all()
        }

    assert numere == {'TAHR-A'}


def test_get_machine_or_404_blocheaza_masina_straina_si_orfana(app):
    from services.security.tenant_access import get_machine_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc_straina:
            get_machine_or_404(ids['masina_b'])
        with pytest.raises(HTTPException) as exc_orfana:
            get_machine_or_404(ids['masina_orfana'])

    assert exc_straina.value.code == 404
    assert exc_orfana.value.code == 404


def test_require_fleet_inputs_same_tenant_blocheaza_inputuri_amestecate(app):
    from services.security.tenant_access import require_fleet_inputs_same_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            require_fleet_inputs_same_tenant(
                machine_id=ids['masina_a'],
                project_id=ids['proiect_a'],
                employee_id=ids['angajat_b'],
            )

    assert exc.value.code == 404


def test_mode_off_pastreaza_comportament_nefiltrat(app):
    from models import Angajat, Masina
    from services.security.tenant_access import query_employees_for_tenant, query_machines_for_tenant

    _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'off'

        angajati = query_employees_for_tenant().filter(Angajat.nume.like('TAHR%')).count()
        masini = query_machines_for_tenant().filter(Masina.numar_inmatriculare.like('TAHR-%')).count()

    assert angajati == 2
    assert masini == 3


def _creeaza_date(app):
    from models import (
        Angajat, AtribuireMasina, Concediu, DefectiuneMasina, DocumentMasina,
        Masina, Proiect, Tenant, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-tahr-a', nume='Tenant HR A')
        tenant_b = Tenant(cod='test-tahr-b', nume='Tenant HR B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect='TAHR-PA',
            nume='TAHR Proiect A',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect='TAHR-PB',
            nume='TAHR Proiect B',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        angajat_a = Angajat(
            tenant_id=tenant_a.id,
            nume='TAHR Angajat A',
            prenume='Test',
            functie='Muncitor',
            data_angajare=date(2026, 1, 1),
            status='activ',
            cnp='1900101010101',
        )
        angajat_b = Angajat(
            tenant_id=tenant_b.id,
            nume='TAHR Angajat B',
            prenume='Test',
            functie='Muncitor',
            data_angajare=date(2026, 1, 1),
            status='activ',
            cnp='1900101010102',
        )
        db.session.add_all([proiect_a, proiect_b, angajat_a, angajat_b])
        db.session.commit()

        masina_a = Masina(
            numar_inmatriculare='TAHR-A',
            marca='Dacia',
            model='A',
            proiect_id=proiect_a.id,
            angajat_responsabil_id=angajat_a.id,
            status='atribuita',
        )
        masina_b = Masina(
            numar_inmatriculare='TAHR-B',
            marca='Dacia',
            model='B',
            proiect_id=proiect_b.id,
            angajat_responsabil_id=angajat_b.id,
            status='atribuita',
        )
        masina_orfana = Masina(
            numar_inmatriculare='TAHR-ORF',
            marca='Dacia',
            model='Orfan',
            status='disponibila',
        )
        db.session.add_all([masina_a, masina_b, masina_orfana])
        db.session.commit()

        concediu_a = Concediu(
            angajat_id=angajat_a.id,
            tip='CO',
            data_start=date(2026, 2, 1),
            data_sfarsit=date(2026, 2, 2),
            nr_zile=2,
        )
        concediu_b = Concediu(
            angajat_id=angajat_b.id,
            tip='CO',
            data_start=date(2026, 2, 1),
            data_sfarsit=date(2026, 2, 2),
            nr_zile=2,
        )
        db.session.add_all([
            concediu_a,
            concediu_b,
            DocumentMasina(masina_id=masina_a.id, tip='itp', nume_document='Doc A'),
            DocumentMasina(masina_id=masina_b.id, tip='itp', nume_document='Doc B'),
            AtribuireMasina(masina_id=masina_a.id, angajat_id=angajat_a.id, proiect_id=proiect_a.id),
            AtribuireMasina(masina_id=masina_b.id, angajat_id=angajat_b.id, proiect_id=proiect_b.id),
            DefectiuneMasina(masina_id=masina_a.id, raportat_de=angajat_a.id, descriere='Def A'),
            DefectiuneMasina(masina_id=masina_b.id, raportat_de=angajat_b.id, descriere='Def B'),
        ])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'angajat_a': angajat_a.id,
            'angajat_b': angajat_b.id,
            'masina_a': masina_a.id,
            'masina_b': masina_b.id,
            'masina_orfana': masina_orfana.id,
            'concediu_a': concediu_a.id,
            'concediu_b': concediu_b.id,
        }


def _curata_date(app):
    from models import (
        Angajat, AtribuireMasina, Concediu, DefectiuneMasina, DocumentMasina,
        Masina, Proiect, Tenant, Utilizator, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'

        for user in Utilizator.query.filter(Utilizator.email.in_([
            'admin_test@test.local',
            'operator_test@test.local',
        ])).all():
            user.tenant_id = None

        for cls in (DocumentMasina, AtribuireMasina, DefectiuneMasina):
            for obj in cls.query.join(Masina).filter(Masina.numar_inmatriculare.like('TAHR-%')).all():
                db.session.delete(obj)

        for concediu in Concediu.query.join(Angajat).filter(Angajat.nume.like('TAHR%')).all():
            db.session.delete(concediu)
        for masina in Masina.query.filter(Masina.numar_inmatriculare.like('TAHR-%')).all():
            db.session.delete(masina)
        for angajat in Angajat.query.filter(Angajat.nume.like('TAHR%')).all():
            db.session.delete(angajat)
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('TAHR-%')).all():
            db.session.delete(proiect)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-tahr-%')).all():
            db.session.delete(tenant)

        db.session.commit()
