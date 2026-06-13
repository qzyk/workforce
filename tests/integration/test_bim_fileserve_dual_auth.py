"""
Integration tests pentru securitatea file-serve a versiunilor BIM (Faza bim-1).

Ruta `/bim/api/model-version/<id>/file` foloseste autentificare DUALA:
- sesiune Flask-Login valida (viewer federat, front-end logat), SAU
- token API valid cu scope 'bim:read' (consum programatic).

Verificam:
- anonim (fara sesiune, fara token) -> 401
- token valid cu scope citire -> 200 (+ continut fisier)
- token fara scope -> 403
- token invalid -> 401
- sesiune valida -> 200 (regresie viewer federat)
"""

import os
import pytest

from models import db, BIMModelVersion, ModelBIM, ApiToken, Utilizator
from services import api_tokens as tokens_svc


@pytest.fixture
def versiune_cu_fisier(app):
    """
    Creeaza un ModelBIM + BIMModelVersion 'shared' cu un fisier IFC real pe disc
    (sub app.root_path). Returneaza dict cu id-uri + path absolut pentru cleanup.
    """
    with app.app_context():
        m = ModelBIM(nume='M-FILESERVE', tip='ifc')
        db.session.add(m)
        db.session.commit()

        rel_path = os.path.join('uploads', 'test_fileserve_model.ifc')
        abs_path = os.path.join(app.root_path, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as fh:
            fh.write('ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n')

        v = BIMModelVersion(model_id=m.id, versiune='v1.0', disciplina='ARH',
                            status='shared', fisier_path=rel_path)
        db.session.add(v)
        db.session.commit()
        ids = {'version_id': v.id, 'model_id': m.id, 'abs_path': abs_path}

    yield ids

    # Cleanup fisier
    try:
        os.unlink(ids['abs_path'])
    except OSError:
        pass


@pytest.fixture
def bim_read_token(app):
    """Token API valid cu scope 'bim:read'. Returneaza string-ul plain."""
    with app.app_context():
        owner = Utilizator.query.filter_by(email='admin_test@test.local').first()
        if not owner:
            owner = Utilizator(nume='Admin', prenume='Test',
                               email='admin_test@test.local', rol='admin', activ=True)
            owner.set_password('test_pass_123'); db.session.add(owner); db.session.commit()
        t = tokens_svc.create_token('fileserve-read', owner.id, ['bim:read'])
        return t.token


@pytest.fixture
def no_scope_token(app):
    """Token API valid dar FARA scope de citire BIM (doar iot:read)."""
    with app.app_context():
        owner = Utilizator.query.filter_by(email='admin_test@test.local').first()
        if not owner:
            owner = Utilizator(nume='Admin', prenume='Test',
                               email='admin_test@test.local', rol='admin', activ=True)
            owner.set_password('test_pass_123'); db.session.add(owner); db.session.commit()
        t = tokens_svc.create_token('fileserve-noscope', owner.id, ['iot:read'])
        return t.token


def _url(version_id):
    return f'/bim/api/model-version/{version_id}/file'


def test_anonim_fara_sesiune_fara_token_401(app, versiune_cu_fisier):
    """Cerere anonima (client nelogat, fara token) -> 401."""
    client = app.test_client()
    resp = client.get(_url(versiune_cu_fisier['version_id']))
    assert resp.status_code == 401


def test_token_valid_scope_citire_200(app, versiune_cu_fisier, bim_read_token):
    """Token valid cu scope bim:read -> 200 + continut fisier."""
    client = app.test_client()
    resp = client.get(_url(versiune_cu_fisier['version_id']),
                       headers={'Authorization': f'Bearer {bim_read_token}'})
    assert resp.status_code == 200
    assert b'ISO-10303-21' in resp.data


def test_token_alt_header_x_api_token_200(app, versiune_cu_fisier, bim_read_token):
    """Acelasi token, prin header X-Api-Token -> 200."""
    client = app.test_client()
    resp = client.get(_url(versiune_cu_fisier['version_id']),
                       headers={'X-Api-Token': bim_read_token})
    assert resp.status_code == 200


def test_token_fara_scope_403(app, versiune_cu_fisier, no_scope_token):
    """Token valid dar fara scope bim:read -> 403."""
    client = app.test_client()
    resp = client.get(_url(versiune_cu_fisier['version_id']),
                       headers={'Authorization': f'Bearer {no_scope_token}'})
    assert resp.status_code == 403


def test_token_invalid_401(app, versiune_cu_fisier):
    """Token inexistent -> 401."""
    client = app.test_client()
    resp = client.get(_url(versiune_cu_fisier['version_id']),
                       headers={'Authorization': 'Bearer ' + 'f' * 64})
    assert resp.status_code == 401


def test_sesiune_valida_200_regresie_federat(authenticated_client, versiune_cu_fisier):
    """Regresie: utilizator logat prin sesiune (viewer federat) -> 200."""
    resp = authenticated_client.get(_url(versiune_cu_fisier['version_id']))
    assert resp.status_code == 200
    assert b'ISO-10303-21' in resp.data


def test_versiune_wip_nepartajata_403_pentru_alt_user(app):
    """
    Versiune in stare 'wip' (nepartajata), creata de alt user: un token al
    unui owner diferit (operator, non-admin) NU primeste fisierul.
    Verificam regula de status pastrata (status + rol + creator).
    """
    from models import Utilizator
    with app.app_context():
        # Creator versiune: un user 'manager' separat de owner-ul tokenului
        creator = Utilizator.query.filter_by(email='fs_creator@test.local').first()
        if not creator:
            creator = Utilizator(nume='FS', prenume='Creator', email='fs_creator@test.local',
                                 rol='manager', activ=True)
            creator.set_password('x'); db.session.add(creator); db.session.commit()
        # Owner operator (non-admin) pentru token
        op = Utilizator.query.filter_by(email='fs_op@test.local').first()
        if not op:
            op = Utilizator(nume='FS', prenume='Op', email='fs_op@test.local',
                            rol='operator', activ=True)
            op.set_password('x'); db.session.add(op); db.session.commit()

        m = ModelBIM(nume='M-WIP', tip='ifc')
        db.session.add(m); db.session.commit()
        rel_path = os.path.join('uploads', 'test_wip_model.ifc')
        abs_path = os.path.join(app.root_path, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as fh:
            fh.write('ISO-10303-21;\n')
        # Versiune wip creata de 'creator' (alt user decat operatorul tokenului)
        v = BIMModelVersion(model_id=m.id, versiune='v1.0', status='wip',
                            fisier_path=rel_path, creat_de_id=creator.id)
        db.session.add(v); db.session.commit()
        tok = tokens_svc.create_token('wip-op', op.id, ['bim:read']).token
        vid = v.id

    client = app.test_client()
    resp = client.get(_url(vid), headers={'Authorization': f'Bearer {tok}'})
    assert resp.status_code == 403

    try:
        os.unlink(abs_path)
    except OSError:
        pass
