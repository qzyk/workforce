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


def test_bim_api_search_short_query(authenticated_client):
    """Search cu query <2 caractere returnează listă goală."""
    resp = authenticated_client.get('/bim/api/search?q=a')
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_bim_api_search_returns_json_list(authenticated_client):
    """Search cu query valid returnează listă (poate fi goală)."""
    resp = authenticated_client.get('/bim/api/search?q=test')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_bim_cascade_apis(app, authenticated_client):
    """API-urile de cascada (cladiri/niveluri/spatii) functioneaza."""
    from models import db, Santier, Cladire, Nivel, Spatiu
    with app.app_context():
        # Pregatesc o ierarhie minimala
        Santier.query.filter_by(cod='UX-CASC').delete()
        db.session.commit()
        s = Santier(cod='UX-CASC', nume='Cascade Test')
        db.session.add(s); db.session.commit()
        c = Cladire(santier_id=s.id, cod='C1', nume='C1')
        db.session.add(c); db.session.commit()
        n = Nivel(cladire_id=c.id, cod='N0', nume='Parter', ordine=0)
        db.session.add(n); db.session.commit()
        sp = Spatiu(nivel_id=n.id, cod='SP1', nume='Test')
        db.session.add(sp); db.session.commit()
        sid, cid, nid, spid = s.id, c.id, n.id, sp.id

    r1 = authenticated_client.get(f'/bim/api/santier/{sid}/cladiri')
    assert r1.status_code == 200
    cladiri = r1.get_json()
    assert any(c['cod'] == 'C1' for c in cladiri)

    r2 = authenticated_client.get(f'/bim/api/cladire/{cid}/niveluri')
    assert r2.status_code == 200
    niveluri = r2.get_json()
    assert any(n['cod'] == 'N0' for n in niveluri)

    r3 = authenticated_client.get(f'/bim/api/nivel/{nid}/spatii')
    assert r3.status_code == 200
    spatii = r3.get_json()
    assert any(s['cod'] == 'SP1' for s in spatii)

    # Cleanup
    with app.app_context():
        Santier.query.filter_by(cod='UX-CASC').delete()
        db.session.commit()


def test_activitati_panou_accepts_bim_filters(authenticated_client):
    """Panou activitati accepta filtre BIM (santier_id, cladire_id, tip_element) fara crash."""
    resp = authenticated_client.get('/activitati/?santier_id=1&cladire_id=1&tip_element=AHU')
    assert resp.status_code == 200


def test_model_extern_url_substitution(app):
    """ModelBIM.get_external_url_for_guid substitueaza {guid} corect."""
    from models import ModelBIM
    m1 = ModelBIM(nume='T1', tip='viewer_extern',
                  extern_url='https://example.com/viewer?id=PROJ&select={guid}')
    assert m1.get_external_url_for_guid('ABC-123') == 'https://example.com/viewer?id=PROJ&select=ABC-123'
    assert m1.get_external_url_for_guid(None) == 'https://example.com/viewer?id=PROJ&select={guid}'

    m2 = ModelBIM(nume='T2', tip='viewer_extern',
                  extern_url='https://example.com/static-link')
    assert m2.get_external_url_for_guid('ABC-123') == 'https://example.com/static-link'
    assert m2.get_external_url_for_guid(None) == 'https://example.com/static-link'

    m3 = ModelBIM(nume='T3', tip='ifc')
    assert m3.get_external_url_for_guid('ABC-123') is None


def test_model_intern_extern_flags(app):
    from models import ModelBIM
    m_intern = ModelBIM(nume='I', tip='ifc', fisier_path='/tmp/model.ifc')
    assert m_intern.is_viewer_intern is True
    assert m_intern.is_viewer_extern is False

    m_extern = ModelBIM(nume='E', tip='viewer_extern', extern_url='https://x.com')
    assert m_extern.is_viewer_intern is False
    assert m_extern.is_viewer_extern is True

    m_no_path = ModelBIM(nume='N', tip='ifc')
    assert m_no_path.is_viewer_intern is False


def test_modele_lista_renders(authenticated_client):
    """Lista modele BIM se incarca."""
    resp = authenticated_client.get('/bim/modele')
    assert resp.status_code == 200


def test_model_extern_form_renders(authenticated_client):
    """Formularul de viewer extern se incarca pentru admin."""
    resp = authenticated_client.get('/bim/model/extern/nou')
    assert resp.status_code == 200
    assert b'extern_url' in resp.data
    assert b'Trimble' in resp.data  # preset-ul Trimble Connect


def test_model_extern_create_via_post(app, authenticated_client):
    """POST creeaza model extern in DB."""
    from models import db, ModelBIM
    with app.app_context():
        ModelBIM.query.filter_by(nume='__SMOKE_EXTERN__').delete()
        db.session.commit()

    resp = authenticated_client.post('/bim/model/extern/nou', data={
        'nume': '__SMOKE_EXTERN__',
        'extern_url': 'https://test.example.com/viewer?select={guid}',
    }, follow_redirects=False)
    assert resp.status_code in (200, 302)

    with app.app_context():
        m = ModelBIM.query.filter_by(nume='__SMOKE_EXTERN__').first()
        assert m is not None
        assert m.tip == 'viewer_extern'
        assert m.extern_url == 'https://test.example.com/viewer?select={guid}'
        # Test substitutie
        assert m.get_external_url_for_guid('TEST-GUID-456') == 'https://test.example.com/viewer?select=TEST-GUID-456'
        db.session.delete(m)
        db.session.commit()


def test_api_modele_pentru_element(app, authenticated_client):
    """API-ul returneaza modele asociate cu santierul/cladirea elementului."""
    from models import db, Santier, Cladire, ElementBIM, ModelBIM
    with app.app_context():
        Santier.query.filter_by(cod='UX-VIEW').delete()
        ModelBIM.query.filter_by(nume='__VIEW_TEST__').delete()
        db.session.commit()

        s = Santier(cod='UX-VIEW', nume='V')
        db.session.add(s); db.session.commit()
        c = Cladire(santier_id=s.id, cod='C', nume='C')
        db.session.add(c); db.session.commit()
        e = ElementBIM(cladire_id=c.id, cod='E1', tip_element='wall',
                       ifc_global_id='TEST-GUID-789')
        db.session.add(e); db.session.commit()

        # Adaug 2 modele asociate cu santierul
        m_intern = ModelBIM(nume='__VIEW_TEST__intern', tip='ifc',
                            fisier_path='uploads/ifc/test.ifc',
                            santier_id=s.id)
        m_extern = ModelBIM(nume='__VIEW_TEST__extern', tip='viewer_extern',
                            extern_url='https://ext.example.com/v?g={guid}',
                            santier_id=s.id)
        db.session.add(m_intern); db.session.add(m_extern)
        db.session.commit()
        eid = e.id

    resp = authenticated_client.get(f'/bim/api/modele-pentru-element/{eid}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 2
    # Verific ca url-urile sunt populate corect
    intern_items = [it for it in data if it['is_intern']]
    extern_items = [it for it in data if it['is_extern']]
    assert len(intern_items) >= 1
    assert len(extern_items) >= 1
    # Intern URL trebuie sa contina ?highlight=GUID
    assert 'highlight=TEST-GUID-789' in intern_items[0]['url_intern']
    # Extern URL trebuie sa aiba {guid} substituit
    assert intern_items[0]['url_intern'] is not None
    assert 'TEST-GUID-789' in extern_items[0]['url_extern']

    # Cleanup
    with app.app_context():
        ModelBIM.query.filter(ModelBIM.nume.like('__VIEW_TEST__%')).delete()
        Santier.query.filter_by(cod='UX-VIEW').delete()
        db.session.commit()


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
