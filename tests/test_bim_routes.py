"""
Smoke tests pentru rutele BIM.
"""

import pytest


def test_bim_dashboard_protected(client):
    """BIM dashboard cere autentificare."""
    resp = client.get('/bim/', follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_bim_dashboard_admin(authenticated_client):
    """Admin accesează dashboard BIM."""
    resp = authenticated_client.get('/bim/')
    assert resp.status_code == 200
    assert b'BIM' in resp.data


def test_bim_santiere_lista(authenticated_client):
    """Lista șantiere se încarcă."""
    resp = authenticated_client.get('/bim/santiere')
    assert resp.status_code == 200


def test_bim_elemente_lista(authenticated_client):
    """Lista elemente se încarcă."""
    resp = authenticated_client.get('/bim/elemente')
    assert resp.status_code == 200


def test_bim_issues_lista(authenticated_client):
    """Lista issues se încarcă."""
    resp = authenticated_client.get('/bim/issues')
    assert resp.status_code == 200


def test_bim_api_tree_returns_json(authenticated_client):
    """API tree întoarce JSON valid."""
    resp = authenticated_client.get('/bim/api/tree')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_bim_api_elemente_returns_json(authenticated_client):
    """API elemente întoarce JSON valid."""
    resp = authenticated_client.get('/bim/api/elemente')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_bim_santier_nou_form_admin(authenticated_client):
    """Admin poate accesa formularul de șantier nou."""
    resp = authenticated_client.get('/bim/santier/nou')
    assert resp.status_code == 200


def test_bim_santier_create_via_post(app, authenticated_client):
    """POST către /bim/santier/nou creează entitatea în DB."""
    from models import db, Santier
    with app.app_context():
        Santier.query.filter_by(cod='SMOKE-001').delete()
        db.session.commit()

    resp = authenticated_client.post('/bim/santier/nou', data={
        'cod': 'SMOKE-001',
        'nume': 'Smoke Test Santier',
        'oras': 'Bucuresti',
    }, follow_redirects=False)
    assert resp.status_code in (302, 200)

    with app.app_context():
        s = Santier.query.filter_by(cod='SMOKE-001').first()
        assert s is not None
        assert s.nume == 'Smoke Test Santier'
        # Cleanup
        db.session.delete(s)
        db.session.commit()


def test_bim_import_ifc_form(authenticated_client):
    """Pagina de import IFC se incarca."""
    resp = authenticated_client.get('/bim/import/ifc')
    assert resp.status_code == 200
    assert b'IFC' in resp.data


def test_bim_export_bcf_no_issues_redirects(authenticated_client):
    """Export BCF cand nu sunt issues -> redirect cu warning."""
    resp = authenticated_client.get('/bim/export/bcf', follow_redirects=False)
    assert resp.status_code in (200, 302)


def test_bim_export_bcf_with_issue(app, authenticated_client):
    """Export BCF cand exista cel putin un issue -> primim ZIP BCF."""
    from models import db, IssueBIM
    with app.app_context():
        IssueBIM.query.filter_by(titlu='__SMOKE_BCF__').delete()
        i = IssueBIM(titlu='__SMOKE_BCF__', tip='defect', severitate='medie', status='deschis')
        db.session.add(i)
        db.session.commit()
        iid = i.id

    resp = authenticated_client.get('/bim/export/bcf', follow_redirects=False)
    assert resp.status_code == 200
    assert resp.data[:2] == b'PK'  # ZIP magic bytes

    with app.app_context():
        IssueBIM.query.filter_by(id=iid).delete()
        db.session.commit()


def test_ifc_service_is_available_returns_bool():
    """ifc_service.is_available() returneaza bool fara exceptie."""
    from services.ifc_import import is_available
    assert isinstance(is_available(), bool)


def test_ifc_service_dry_run_without_lib():
    """import_ifc returneaza eroare gracefully daca ifcopenshell lipseste."""
    from services.ifc_import import import_ifc, is_available
    if is_available():
        # Lib-ul e instalat, sarim peste test (sau il facem cu un IFC fake)
        return
    rez = import_ifc('/tmp/nonexistent.ifc')
    assert rez['status'] == 'eroare'
    assert 'ifcopenshell' in rez['mesaj'].lower()


def test_export_bcf_service_genereaza_zip(app):
    """export_bcf creeaza un ZIP valid cu bcf.version + topic markup."""
    from services.ifc_import import export_bcf
    from models import db, IssueBIM

    class FakeIssue:
        bcf_topic_guid = '12345678-1234-1234-1234-123456789abc'
        tip = 'defect'
        status = 'deschis'
        severitate = 'mare'
        titlu = 'Test issue'
        descriere = 'Descr'
        data_creare = None
        raportor = None

    bcf_zip = export_bcf([FakeIssue()])
    bcf_zip.seek(0)
    # Verific via zipfile (datele in ZIP sunt comprimate)
    from zipfile import ZipFile
    with ZipFile(bcf_zip, 'r') as zf:
        names = zf.namelist()
        assert 'bcf.version' in names
        markup_files = [n for n in names if n.endswith('markup.bcf')]
        assert len(markup_files) == 1
        markup = zf.read(markup_files[0]).decode('utf-8')
        assert 'Test issue' in markup
        assert '12345678-1234-1234-1234-123456789abc' in markup
