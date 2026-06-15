"""
Integration tests pentru rutele Faza 5a IDS (gate flag 'bim-ids' + run).
"""

import json
import pytest

from models import (db, BIMIDSSpec, BIMIDSViolation, ElementBIM,
                    Santier, Cladire)
from services import feature_flags as ff


def test_ids_lista_redirects_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-ids', False)
    resp = authenticated_client.get('/bim/ids', follow_redirects=False)
    assert resp.status_code == 302


def test_ids_lista_renders_when_flag_on(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-ids', True)
    resp = authenticated_client.get('/bim/ids')
    assert resp.status_code == 200
    assert b'IDS' in resp.data


def test_ids_creare_via_route(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-ids', True)
        BIMIDSSpec.query.delete()
        db.session.commit()
    resp = authenticated_client.post('/bim/ids/nou', data={
        'nume': 'Pereti FR executie',
        'faza': 'executie',
        'definitie_json': json.dumps({
            'clase_ifc': ['wall'],
            'proprietati_cerute': [{'pset': 'Pset_WallCommon', 'nume': 'FireRating'}],
        }),
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        spec = BIMIDSSpec.query.filter_by(nume='Pereti FR executie').first()
        assert spec is not None
        assert spec.faza == 'executie'


def test_ids_run_creeaza_violari(authenticated_client, app):
    """Ruleaza validarea pe un element neconform -> violare in DB."""
    with app.app_context():
        ff.set_flag('bim-ids', True)
        s = Santier(cod='S-IDS-RUN', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Element fara FireRating -> trebuie sa genereze o violare
        db.session.add(ElementBIM(cladire_id=c.id, cod='W-RUN', tip_element='wall',
                                  status='proiectat', nume='W-RUN',
                                  proprietati_json=json.dumps(
                                      {'Pset_WallCommon': {'IsExternal': True}})))
        db.session.flush()
        spec = BIMIDSSpec(nume='IDS run', faza='executie',
                          definitie_json=json.dumps({
                              'clase_ifc': ['wall'],
                              'proprietati_cerute': [
                                  {'pset': 'Pset_WallCommon', 'nume': 'FireRating'}]}),
                          activ=True)
        db.session.add(spec); db.session.commit()
        spec_id = spec.id

    resp = authenticated_client.post(f'/bim/ids/{spec_id}/run', follow_redirects=False)
    assert resp.status_code == 302
    assert f'/ids/{spec_id}' in resp.headers.get('Location', '')

    with app.app_context():
        violari = BIMIDSViolation.query.filter_by(spec_id=spec_id).all()
        assert len(violari) == 1
        assert 'FireRating' in violari[0].mesaj


def test_ids_run_flag_off_redirects_la_dashboard(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-ids', True)
        spec = BIMIDSSpec(nume='IDS off', faza='executie',
                          definitie_json=json.dumps({'clase_ifc': ['wall'],
                                                     'proprietati_cerute': []}),
                          activ=True)
        db.session.add(spec); db.session.commit()
        spec_id = spec.id
        ff.set_flag('bim-ids', False)
    resp = authenticated_client.post(f'/bim/ids/{spec_id}/run', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        # Cu flag OFF nu se creeaza violari
        assert BIMIDSViolation.query.filter_by(spec_id=spec_id).count() == 0


def test_ids_detaliu_renders(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-ids', True)
        spec = BIMIDSSpec(nume='IDS det', faza='predare',
                          definitie_json=json.dumps({'clase_ifc': ['door'],
                                                     'proprietati_cerute': [
                                                         {'nume': 'FireRating'}]}),
                          activ=True)
        db.session.add(spec); db.session.commit()
        spec_id = spec.id
    resp = authenticated_client.get(f'/bim/ids/{spec_id}')
    assert resp.status_code == 200
    assert b'IDS det' in resp.data
