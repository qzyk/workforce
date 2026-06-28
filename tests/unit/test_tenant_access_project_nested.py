"""Teste pentru helper-ele T1.12 project nested tenant access."""

from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


@pytest.fixture(autouse=True)
def curata_project_nested_tenant_access(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_project_assignments_strict_exclude_asignari_conflict(app):
    from models import AngajatProiect
    from services.security.tenant_access import query_project_assignments_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        angajati = {
            ap.angajat_id for ap in query_project_assignments_for_tenant(
                project_id=ids['proiect_a'],
            ).filter(AngajatProiect.id.in_([
                ids['asignare_a'],
                ids['asignare_conflict'],
            ])).all()
        }

    assert angajati == {ids['angajat_a']}


def test_get_project_assignment_or_404_blocheaza_asignare_straina(app):
    from services.security.tenant_access import get_project_assignment_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_project_assignment_or_404(ids['asignare_b'])

    assert exc.value.code == 404


def test_require_project_nested_inputs_same_tenant_blocheaza_mixuri(app):
    from services.security.tenant_access import require_project_nested_inputs_same_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        for kwargs in (
            {'project_id': ids['proiect_a'], 'employee_id': ids['angajat_b']},
            {'project_id': ids['proiect_a'], 'machine_id': ids['masina_b']},
            {'project_id': ids['proiect_a'], 'site_id': ids['site_b']},
            {'project_id': ids['proiect_a'], 'plan_id': ids['plan_b']},
            {'project_id': ids['proiect_a'], 'contract_id': ids['contract_b']},
        ):
            with pytest.raises(HTTPException) as exc:
                require_project_nested_inputs_same_tenant(**kwargs)
            assert exc.value.code == 404


def test_query_project_consum_utilaj_filtreaza_masina_si_tenant(app):
    from models import ConsumUtilaj
    from services.security.tenant_access import query_project_consum_utilaj_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        denumiri = {
            c.denumire for c in query_project_consum_utilaj_for_tenant(
                project_id=ids['proiect_a'],
            ).filter(ConsumUtilaj.denumire.like('TPN%')).all()
        }

    assert denumiri == {'TPN Consum A'}


def test_query_project_nested_resources_filtreaza_tenant_direct_conflict(app):
    from models import ExtrasResursa
    from services.security.tenant_access import query_project_nested_resources_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        resurse = {
            r.denumire for r in query_project_nested_resources_for_tenant(
                project_id=ids['proiect_a'],
            ).filter(ExtrasResursa.denumire.like('TPN%')).all()
        }

    assert resurse == {'TPN Material A'}


def test_mode_off_pastreaza_query_nefiltrat(app):
    from models import AngajatProiect, ExtrasResursa
    from services.security.tenant_access import (
        query_project_assignments_for_tenant,
        query_project_nested_resources_for_tenant,
    )

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'off'
        g.tenant_override = ids['tenant_a']

        asignari = query_project_assignments_for_tenant(
            project_id=ids['proiect_a'],
        ).filter(AngajatProiect.id.in_([
            ids['asignare_a'],
            ids['asignare_conflict'],
        ])).count()
        resurse = query_project_nested_resources_for_tenant(
            project_id=ids['proiect_a'],
        ).filter(ExtrasResursa.denumire.like('TPN%')).count()

    assert asignari == 2
    assert resurse == 2


def _creeaza_date(app):
    from models import (
        Angajat, AngajatProiect, Cladire, ConsumUtilaj, Contract, Document,
        ExtrasResursa, GanttPlan, Masina, ModelBIM, Pontaj, Proiect, Santier,
        Tenant, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-tpn-a', nume='TPN Tenant A')
        tenant_b = Tenant(cod='test-tpn-b', nume='TPN Tenant B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = _proiect(tenant_a.id, 'TPN-PA', 'TPN Proiect A')
        proiect_b = _proiect(tenant_b.id, 'TPN-PB', 'TPN Proiect B')
        angajat_a = _angajat(tenant_a.id, 'TPN Angajat A', '1901201010101')
        angajat_b = _angajat(tenant_b.id, 'TPN Angajat B', '1901201010102')
        db.session.add_all([proiect_a, proiect_b, angajat_a, angajat_b])
        db.session.commit()

        masina_a = _masina('TPN-A', proiect_a.id, angajat_a.id)
        masina_b = _masina('TPN-B', proiect_b.id, angajat_b.id)
        db.session.add_all([masina_a, masina_b])
        db.session.commit()

        site_a = Santier(tenant_id=tenant_a.id, proiect_id=proiect_a.id, cod='TPN-SITE-A', nume='TPN Site A')
        site_b = Santier(tenant_id=tenant_b.id, proiect_id=proiect_b.id, cod='TPN-SITE-B', nume='TPN Site B')
        db.session.add_all([site_a, site_b])
        db.session.commit()
        cladire_a = Cladire(santier_id=site_a.id, cod='TPN-BLD-A', nume='TPN Cladire A')
        cladire_b = Cladire(santier_id=site_b.id, cod='TPN-BLD-B', nume='TPN Cladire B')
        db.session.add_all([cladire_a, cladire_b])
        db.session.commit()
        db.session.add_all([
            ModelBIM(tenant_id=tenant_a.id, santier_id=site_a.id, cladire_id=cladire_a.id, nume='TPN Model A'),
            ModelBIM(tenant_id=tenant_b.id, santier_id=site_b.id, cladire_id=cladire_b.id, nume='TPN Model B'),
        ])

        plan_a = _plan(tenant_a.id, proiect_a.id, 'TPN Plan A')
        plan_b = _plan(tenant_b.id, proiect_b.id, 'TPN Plan B')
        contract_a = _contract(tenant_a.id, proiect_a.id, 'TPN Contract A')
        contract_b = _contract(tenant_b.id, proiect_b.id, 'TPN Contract B')
        asignare_a = AngajatProiect(angajat_id=angajat_a.id, proiect_id=proiect_a.id, tarif_negociat=50)
        asignare_b = AngajatProiect(angajat_id=angajat_b.id, proiect_id=proiect_b.id, tarif_negociat=60)
        asignare_conflict = AngajatProiect(angajat_id=angajat_b.id, proiect_id=proiect_a.id, tarif_negociat=99)
        db.session.add_all([plan_a, plan_b, contract_a, contract_b, asignare_a, asignare_b, asignare_conflict])
        db.session.add_all([
            Pontaj(angajat_id=angajat_a.id, proiect_id=proiect_a.id, data=date(2026, 1, 5), ore_lucrate=8),
            Pontaj(angajat_id=angajat_b.id, proiect_id=proiect_a.id, data=date(2026, 1, 6), ore_lucrate=7),
            Document(proiect_id=proiect_a.id, tip='alte', nume_document='TPN Doc A'),
            Document(proiect_id=proiect_b.id, tip='alte', nume_document='TPN Doc B'),
            Document(proiect_id=proiect_a.id, angajat_id=angajat_b.id, tip='alte', nume_document='TPN Doc Conflict'),
            ConsumUtilaj(tenant_id=tenant_a.id, proiect_id=proiect_a.id, masina_id=masina_a.id, denumire='TPN Consum A', data=date(2026, 1, 5), ore=2, tarif_ora=100),
            ConsumUtilaj(tenant_id=tenant_b.id, proiect_id=proiect_a.id, masina_id=masina_b.id, denumire='TPN Consum Conflict', data=date(2026, 1, 6), ore=3, tarif_ora=100),
            ExtrasResursa(tenant_id=tenant_a.id, proiect_id=proiect_a.id, tip='material', denumire='TPN Material A', cantitate=1, tarif_unitar=10, valoare=10),
            ExtrasResursa(tenant_id=tenant_b.id, proiect_id=proiect_a.id, tip='material', denumire='TPN Material Conflict', cantitate=1, tarif_unitar=20, valoare=20),
        ])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'angajat_a': angajat_a.id,
            'angajat_b': angajat_b.id,
            'masina_b': masina_b.id,
            'site_b': site_b.id,
            'plan_b': plan_b.id,
            'contract_b': contract_b.id,
            'asignare_a': asignare_a.id,
            'asignare_b': asignare_b.id,
            'asignare_conflict': asignare_conflict.id,
        }


def _proiect(tenant_id, cod, nume):
    from models import Proiect

    return Proiect(tenant_id=tenant_id, cod_proiect=cod, nume=nume, data_start=date(2026, 1, 1), status='activ')


def _angajat(tenant_id, nume, cnp):
    from models import Angajat

    return Angajat(tenant_id=tenant_id, nume=nume, prenume='Test', cnp=cnp, functie='Muncitor', data_angajare=date(2026, 1, 1), status='activ')


def _masina(numar, proiect_id, angajat_id):
    from models import Masina

    return Masina(numar_inmatriculare=numar, marca='Dacia', model='TPN', proiect_id=proiect_id, angajat_responsabil_id=angajat_id)


def _plan(tenant_id, proiect_id, nume):
    from models import GanttPlan

    return GanttPlan(tenant_id=tenant_id, proiect_id=proiect_id, nume=nume, continut=b'cod;denumire\n1;Test', ext='csv')


def _contract(tenant_id, proiect_id, nr):
    from models import Contract

    return Contract(tenant_id=tenant_id, proiect_id=proiect_id, nr_contract=nr, data_semnare=date(2026, 1, 1), status='activ')


def _curata_date(app):
    from models import (
        Angajat, AngajatProiect, Cladire, ConsumUtilaj, Contract, Document,
        ExtrasResursa, GanttPlan, Masina, ModelBIM, Pontaj, Proiect,
        ProiectSantier, Santier, Tenant, Utilizator, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        for cls in (
            Pontaj, AngajatProiect, ConsumUtilaj, ExtrasResursa, Document,
            Contract, GanttPlan, ProiectSantier, ModelBIM, Cladire, Santier,
            Masina, Angajat, Proiect,
        ):
            for obj in cls.query.filter(_filtru_tpn(cls)).all():
                db.session.delete(obj)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-tpn-%')).all():
            db.session.delete(tenant)
        for user in Utilizator.query.filter(Utilizator.email.in_([
            'admin_test@test.local',
            'operator_test@test.local',
        ])).all():
            user.tenant_id = None
        db.session.commit()


def _filtru_tpn(cls):
    from models import (
        Angajat, AngajatProiect, Cladire, ConsumUtilaj, Contract, Document,
        ExtrasResursa, GanttPlan, Masina, ModelBIM, Pontaj, Proiect,
        ProiectSantier, Santier,
    )

    if cls in (Pontaj, AngajatProiect, ProiectSantier):
        return cls.proiect.has(Proiect.cod_proiect.like('TPN-%'))
    if cls is Proiect:
        return Proiect.cod_proiect.like('TPN-%')
    if cls is Angajat:
        return Angajat.nume.like('TPN%')
    if cls is Masina:
        return Masina.numar_inmatriculare.like('TPN-%')
    if cls is Santier:
        return Santier.cod.like('TPN-%')
    if cls is Cladire:
        return Cladire.cod.like('TPN-%')
    if cls is ModelBIM:
        return ModelBIM.nume.like('TPN%')
    if cls is Contract:
        return Contract.nr_contract.like('TPN%')
    if cls is GanttPlan:
        return GanttPlan.nume.like('TPN%')
    if cls is ConsumUtilaj:
        return ConsumUtilaj.denumire.like('TPN%')
    if cls is ExtrasResursa:
        return ExtrasResursa.denumire.like('TPN%')
    if cls is Document:
        return Document.nume_document.like('TPN%')
    return cls.id.isnot(None)
