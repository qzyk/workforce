"""
Teste pentru BIM Data Quality + ExternalMapping + validation.
"""

import pytest
from datetime import datetime


def test_external_mapping_creation(app):
    """ExternalMapping se creeaza si add_or_update e idempotent."""
    from models import db, ExternalMapping
    with app.app_context():
        ExternalMapping.query.filter_by(extern_id='TEST-EXT-001').delete()
        db.session.commit()

        m1 = ExternalMapping.add_or_update(
            entity_type='element_bim', entity_id=999,
            source_system='ifc', extern_id='TEST-EXT-001',
            metadata={'source_file': 'test.ifc'},
        )
        db.session.commit()
        assert m1.id is not None
        assert m1.metadata_json is not None

        # Re-add cu acelasi key -> update, nu insert nou
        m2 = ExternalMapping.add_or_update(
            entity_type='element_bim', entity_id=999,
            source_system='ifc', extern_id='TEST-EXT-001',
            metadata={'source_file': 'test_v2.ifc'},
        )
        db.session.commit()
        assert m2.id == m1.id  # acelasi rand
        assert ExternalMapping.query.filter_by(extern_id='TEST-EXT-001').count() == 1

        # Cleanup
        ExternalMapping.query.filter_by(extern_id='TEST-EXT-001').delete()
        db.session.commit()


def test_external_mapping_unicity_constraint(app):
    """Constraint UNIQUE pe (entity_type, entity_id, source_system, extern_id)."""
    from models import db, ExternalMapping
    with app.app_context():
        ExternalMapping.query.filter_by(extern_id='TEST-DUPL').delete()
        db.session.commit()

        m1 = ExternalMapping(entity_type='element_bim', entity_id=1,
                             source_system='ifc', extern_id='TEST-DUPL')
        db.session.add(m1)
        db.session.commit()

        m2 = ExternalMapping(entity_type='element_bim', entity_id=1,
                             source_system='ifc', extern_id='TEST-DUPL')
        db.session.add(m2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

        ExternalMapping.query.filter_by(extern_id='TEST-DUPL').delete()
        db.session.commit()


def test_external_mapping_find_entity(app):
    """ExternalMapping.find_entity face lookup invers."""
    from models import db, ExternalMapping
    with app.app_context():
        ExternalMapping.query.filter_by(extern_id='LOOKUP-TEST').delete()
        db.session.commit()

        m = ExternalMapping(entity_type='spatiu', entity_id=42,
                            source_system='revit', extern_id='LOOKUP-TEST')
        db.session.add(m)
        db.session.commit()

        et, eid = ExternalMapping.find_entity('revit', 'LOOKUP-TEST')
        assert et == 'spatiu'
        assert eid == 42

        et2, eid2 = ExternalMapping.find_entity('revit', 'NOT-EXISTS')
        assert et2 is None and eid2 is None

        ExternalMapping.query.filter_by(extern_id='LOOKUP-TEST').delete()
        db.session.commit()


def test_element_validation_warnings(app):
    """ElementBIM.validation_warnings detecteaza inconsistente."""
    from models import db, Santier, Cladire, Nivel, Spatiu, ElementBIM
    with app.app_context():
        # Setup curat
        Santier.query.filter_by(cod='WARN-S').delete()
        db.session.commit()

        s = Santier(cod='WARN-S', nume='S')
        db.session.add(s); db.session.commit()
        c1 = Cladire(santier_id=s.id, cod='C1', nume='C1')
        c2 = Cladire(santier_id=s.id, cod='C2', nume='C2')
        db.session.add(c1); db.session.add(c2); db.session.commit()
        n1 = Nivel(cladire_id=c1.id, cod='N0', nume='Parter', ordine=0)
        n2 = Nivel(cladire_id=c2.id, cod='N0', nume='Parter', ordine=0)
        db.session.add(n1); db.session.add(n2); db.session.commit()
        sp_c1 = Spatiu(nivel_id=n1.id, cod='SP1', nume='Spatiu C1')
        sp_c2 = Spatiu(nivel_id=n2.id, cod='SP1', nume='Spatiu C2')
        db.session.add(sp_c1); db.session.add(sp_c2); db.session.commit()

        # Element OK: spatiu in c1, cladire = c1, nivel = n1
        e_ok = ElementBIM(cladire_id=c1.id, nivel_id=n1.id, spatiu_id=sp_c1.id,
                          cod='OK', tip_element='wall')
        db.session.add(e_ok); db.session.commit()
        assert e_ok.validation_warnings == []

        # Element BAD: spatiu in c2 dar cladire = c1
        e_bad = ElementBIM(cladire_id=c1.id, nivel_id=n1.id, spatiu_id=sp_c2.id,
                           cod='BAD', tip_element='wall')
        db.session.add(e_bad); db.session.commit()
        warnings = e_bad.validation_warnings
        assert len(warnings) > 0  # Ar trebui sa raporteze mismatch

        # Element IFC fara GUID
        e_ifc = ElementBIM(cod='IFC-NO-GUID', tip_element='wall',
                           source_system='ifc', ifc_global_id=None)
        db.session.add(e_ifc); db.session.commit()
        assert any('GlobalId' in w for w in e_ifc.validation_warnings)

        # Cleanup
        ElementBIM.query.filter(ElementBIM.cod.in_(['OK', 'BAD', 'IFC-NO-GUID'])).delete()
        Santier.query.filter_by(cod='WARN-S').delete()
        db.session.commit()


def test_quality_report_runs_without_error(app):
    """Service-ul de quality ruleaza si returneaza dict valid."""
    from models import (
        db, RaportActivitate, ElementBIM, Spatiu, ExternalMapping,
        Santier, Cladire, Nivel, Zona, Asset, IssueBIM, ModelBIM,
    )
    from services import bim_quality
    with app.app_context():
        raport = bim_quality.run_all_reports(
            db, RaportActivitate, ElementBIM, Spatiu, ExternalMapping,
            Santier, Cladire, Nivel, Zona, Asset, IssueBIM, ModelBIM,
        )
        assert 'total' in raport
        assert 'by_severitate' in raport
        assert 'entries' in raport
        assert isinstance(raport['entries'], list)


def test_quality_report_endpoint(authenticated_client):
    """Pagina /bim/quality se incarca pentru admin."""
    resp = authenticated_client.get('/bim/quality')
    assert resp.status_code == 200
    assert b'Quality' in resp.data or b'quality' in resp.data


def test_api_quality_returns_json(authenticated_client):
    """API quality returneaza JSON."""
    resp = authenticated_client.get('/bim/api/quality')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'total' in data
    assert 'entries' in data


def test_api_external_mapping_get(app, authenticated_client):
    """GET /bim/api/external-mapping face lookup."""
    from models import db, ExternalMapping
    with app.app_context():
        ExternalMapping.query.filter_by(extern_id='API-LOOKUP').delete()
        db.session.commit()
        m = ExternalMapping(entity_type='santier', entity_id=1,
                            source_system='revit', extern_id='API-LOOKUP')
        db.session.add(m); db.session.commit()

    r = authenticated_client.get('/bim/api/external-mapping?source_system=revit&extern_id=API-LOOKUP')
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) >= 1
    assert items[0]['entity_type'] == 'santier'

    # Cleanup
    with app.app_context():
        ExternalMapping.query.filter_by(extern_id='API-LOOKUP').delete()
        db.session.commit()


def test_api_external_mapping_post(app, authenticated_client):
    """POST creeaza mapping."""
    from models import db, ExternalMapping
    with app.app_context():
        ExternalMapping.query.filter_by(extern_id='API-POST').delete()
        db.session.commit()

    r = authenticated_client.post('/bim/api/external-mapping', json={
        'entity_type': 'cladire',
        'entity_id': 1,
        'source_system': 'trimble_connect',
        'extern_id': 'API-POST',
        'metadata': {'project_id': 'PR-123'},
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('id') is not None

    # Cleanup
    with app.app_context():
        ExternalMapping.query.filter_by(extern_id='API-POST').delete()
        db.session.commit()


def test_api_elemente_catalog(authenticated_client):
    """Catalog elemente returneaza JSON cu mapping-uri externe."""
    resp = authenticated_client.get('/bim/api/elemente/catalog')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'total' in data
    assert 'elements' in data
    assert isinstance(data['elements'], list)
    if data['elements']:
        e = data['elements'][0]
        assert 'id' in e
        assert 'external_mappings' in e
        assert isinstance(e['external_mappings'], list)
