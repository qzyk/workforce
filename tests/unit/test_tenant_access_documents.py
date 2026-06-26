"""Teste pentru helper-ele tenant-safe din domeniul documente."""

from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


@pytest.fixture(autouse=True)
def curata_tenant_access_documents(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_project_documents_strict_returneaza_doar_tenantul(app):
    from services.security.tenant_access import query_project_documents_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        docs = query_project_documents_for_tenant().all()

    assert {d.id for d in docs} == {ids['doc_proiect_a']}


def test_get_project_document_or_404_blocheaza_document_strain(app):
    from services.security.tenant_access import get_project_document_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_project_document_or_404(ids['doc_proiect_b'])

    assert exc.value.code == 404


def test_get_project_document_revision_or_404_blocheaza_revizie_straina(app):
    from services.security.tenant_access import get_project_document_revision_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_project_document_revision_or_404(ids['revizie_b'])

    assert exc.value.code == 404


def test_query_legacy_documents_strict_returneaza_doar_owner_sigur(app):
    from services.security.tenant_access import query_legacy_documents_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        docs = query_legacy_documents_for_tenant().all()

    assert {d.id for d in docs} == {ids['doc_legacy_a']}


def test_get_legacy_document_or_404_blocheaza_document_strain(app):
    from services.security.tenant_access import get_legacy_document_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_legacy_document_or_404(ids['doc_legacy_b'])

    assert exc.value.code == 404


def _creeaza_date(app):
    from models import (
        db, Angajat, Document, DocumentProiect, Proiect, RevizieDocument,
        Tenant, TipInstalatie,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-doc-helper-a', nume='Tenant Doc Helper A')
        tenant_b = Tenant(cod='test-ta-doc-helper-b', nume='Tenant Doc Helper B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = _proiect(tenant_a.id, 'TA-DOC-HELPER-PRJ-A')
        proiect_b = _proiect(tenant_b.id, 'TA-DOC-HELPER-PRJ-B')
        angajat_a = _angajat(tenant_a.id, '1990101010101', 'DocA')
        angajat_b = _angajat(tenant_b.id, '2990101010101', 'DocB')
        inst = TipInstalatie(
            cod='TA-DOC-HELPER-INST',
            denumire='TA Document Helper Instalatie',
            activ=True,
        )
        db.session.add_all([proiect_a, proiect_b, angajat_a, angajat_b, inst])
        db.session.commit()

        doc_proiect_a = _doc_proiect(proiect_a.id, inst.id, 'TA-DOC-HELPER-PROJ-A')
        doc_proiect_b = _doc_proiect(proiect_b.id, inst.id, 'TA-DOC-HELPER-PROJ-B')
        doc_legacy_a = _doc_legacy(angajat_a.id, None, 'TA-DOC-HELPER-LEG-A')
        doc_legacy_b = _doc_legacy(angajat_b.id, None, 'TA-DOC-HELPER-LEG-B')
        doc_ownerless = _doc_legacy(None, None, 'TA-DOC-HELPER-OWNERLESS')
        db.session.add_all([
            doc_proiect_a, doc_proiect_b,
            doc_legacy_a, doc_legacy_b, doc_ownerless,
        ])
        db.session.commit()

        revizie_a = RevizieDocument(
            document_proiect_id=doc_proiect_a.id,
            nr_revizie=1,
            fisier_path='ta_doc_helper_a.pdf',
        )
        revizie_b = RevizieDocument(
            document_proiect_id=doc_proiect_b.id,
            nr_revizie=1,
            fisier_path='ta_doc_helper_b.pdf',
        )
        db.session.add_all([revizie_a, revizie_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'doc_proiect_a': doc_proiect_a.id,
            'doc_proiect_b': doc_proiect_b.id,
            'revizie_a': revizie_a.id,
            'revizie_b': revizie_b.id,
            'doc_legacy_a': doc_legacy_a.id,
            'doc_legacy_b': doc_legacy_b.id,
        }


def _proiect(tenant_id, cod):
    from models import Proiect

    return Proiect(
        tenant_id=tenant_id,
        cod_proiect=cod,
        nume=cod,
        data_start=date(2026, 1, 1),
        status='activ',
    )


def _angajat(tenant_id, cnp, nume):
    from models import Angajat

    return Angajat(
        tenant_id=tenant_id,
        nume=nume,
        prenume='Test',
        cnp=cnp,
        functie='Muncitor',
        data_angajare=date(2026, 1, 1),
        status='activ',
    )


def _doc_proiect(proiect_id, instalatie_id, denumire):
    from models import DocumentProiect

    return DocumentProiect(
        proiect_id=proiect_id,
        tip_instalatie_id=instalatie_id,
        denumire_document=denumire,
        status='draft',
        versiune_curenta=True,
    )


def _doc_legacy(angajat_id, proiect_id, denumire):
    from models import Document

    return Document(
        angajat_id=angajat_id,
        proiect_id=proiect_id,
        tip='alte',
        nume_document=denumire,
        status='valabil',
    )


def _curata_date(app):
    from models import (
        db, Angajat, Document, DocumentProiect, Proiect, RevizieDocument,
        Tenant, TipInstalatie,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'

        Document.query.filter(
            Document.nume_document.like('TA-DOC-HELPER-%')
        ).delete(synchronize_session=False)
        doc_ids = [
            d.id for d in DocumentProiect.query.filter(
                DocumentProiect.denumire_document.like('TA-DOC-HELPER-%')
            ).all()
        ]
        if doc_ids:
            RevizieDocument.query.filter(
                RevizieDocument.document_proiect_id.in_(doc_ids)
            ).delete(synchronize_session=False)
        DocumentProiect.query.filter(
            DocumentProiect.denumire_document.like('TA-DOC-HELPER-%')
        ).delete(synchronize_session=False)
        TipInstalatie.query.filter_by(cod='TA-DOC-HELPER-INST').delete()
        Angajat.query.filter(Angajat.cnp.in_([
            '1990101010101', '2990101010101',
        ])).delete(synchronize_session=False)
        Proiect.query.filter(
            Proiect.cod_proiect.like('TA-DOC-HELPER-PRJ-%')
        ).delete(synchronize_session=False)
        Tenant.query.filter(
            Tenant.cod.like('test-ta-doc-helper-%')
        ).delete(synchronize_session=False)
        db.session.commit()
