"""
Integration test pentru ruta POST /bim/issue/<id>/view-state (Faza 4 BIM).

Salveaza view-state-ul (camera + visibility + clipping) pe issue.viewpoint_json
si verifica reflectarea lui in DB. CSRF e dezactivat in conftest (testing).
"""
import json

import pytest

from models import db, IssueBIM


@pytest.fixture
def issue(app):
    with app.app_context():
        i = IssueBIM(titlu='Issue view-state', tip='neconformitate',
                     severitate='medie', status='deschis')
        db.session.add(i); db.session.commit()
        return i.id


def test_view_state_salveaza_si_reflecta(app, authenticated_client, issue):
    payload = {
        'camera': {'eye': [10, 20, 30], 'look': [1, 2, 3], 'up': [0, 0, 1], 'fov': 50},
        'visible_guids': ['GUID-1', 'GUID-2'],
        'clipping': [{'pos': [0, 0, 1], 'dir': [0, 0, -1]}],
    }
    r = authenticated_client.post(f'/bim/issue/{issue}/view-state',
                                  data=json.dumps(payload),
                                  content_type='application/json')
    assert r.status_code == 200
    assert r.get_json()['ok'] is True

    with app.app_context():
        i = IssueBIM.query.get(issue)
        assert i.viewpoint_json is not None
        vp = json.loads(i.viewpoint_json)
        assert vp['camera']['eye'] == [10, 20, 30]
        assert vp['camera']['look'] == [1, 2, 3]
        assert vp['visible_guids'] == ['GUID-1', 'GUID-2']
        assert vp['clipping'][0]['dir'] == [0, 0, -1]


def test_view_state_respinge_fara_camera(app, authenticated_client, issue):
    r = authenticated_client.post(f'/bim/issue/{issue}/view-state',
                                  data=json.dumps({'camera': {'eye': [1, 2, 3]}}),
                                  content_type='application/json')
    assert r.status_code == 400


def test_view_state_necesita_login(client, issue):
    r = client.post(f'/bim/issue/{issue}/view-state',
                    data=json.dumps({'camera': {'eye': [1, 1, 1], 'look': [0, 0, 0]}}),
                    content_type='application/json',
                    follow_redirects=False)
    assert r.status_code == 302
    assert '/auth/login' in r.location


def test_view_state_404_issue_inexistent(authenticated_client):
    r = authenticated_client.post('/bim/issue/999999/view-state',
                                  data=json.dumps({'camera': {'eye': [1, 1, 1], 'look': [0, 0, 0]}}),
                                  content_type='application/json')
    assert r.status_code == 404
