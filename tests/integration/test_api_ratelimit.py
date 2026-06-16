"""
Teste integrare rate-limit API in-memory (ARIA 4, Faza 5b).

Verifica pe ruta reala token-protejata /bim/api/v1/issues (api_token_required):
- flag OFF (default) -> nicio limitare, identic cu azi (zero regresie).
- flag ON + prag mic -> sub prag 200, peste prag 429 cu header Retry-After.
- starea se reseteaza intre teste (reset_rate_limit) ca sa nu polueze restul suite-ului.
"""

import pytest

from models import db, ApiToken, Utilizator
from services import feature_flags as ff
from services import api_tokens as svc_tokens


def _admin_id(admin_user):
    """ID-ul adminului re-interogat in contextul curent (evita DetachedInstance)."""
    u = Utilizator.query.filter_by(email='admin_test@test.local').first()
    return u.id if u else admin_user.id


@pytest.fixture
def token_str(app, admin_user):
    with app.app_context():
        ApiToken.query.delete(); db.session.commit()
        tok = svc_tokens.create_token('rl-test', _admin_id(admin_user), ['bim:read'])
        yield tok.token


@pytest.fixture(autouse=True)
def _curata_rate_limit(app):
    """Reseteaza starea + config-ul rate-limit dupa fiecare test."""
    svc_tokens.reset_rate_limit()
    yield
    svc_tokens.reset_rate_limit()
    with app.app_context():
        ff.set_flag('bim-api-rate-limit', False)
    app.config.pop('API_RATE_LIMIT', None)
    app.config.pop('API_RATE_LIMIT_WINDOW', None)


def _get(client, token_str):
    return client.get('/bim/api/v1/issues',
                      headers={'Authorization': f'Bearer {token_str}'})


# ====================================================
# FLAG OFF -> nicio limitare (zero regresie)
# ====================================================

def test_flag_off_nu_limiteaza(client, app, token_str):
    with app.app_context():
        ff.set_flag('bim-api-rate-limit', False)
    app.config['API_RATE_LIMIT'] = 3
    app.config['API_RATE_LIMIT_WINDOW'] = 60
    # 10 cereri, toate trebuie sa treaca (flag OFF -> check e no-op)
    for _ in range(10):
        resp = _get(client, token_str)
        assert resp.status_code == 200


# ====================================================
# FLAG ON -> limitare la prag
# ====================================================

def test_flag_on_sub_prag_ok_peste_prag_429(client, app, token_str):
    with app.app_context():
        ff.set_flag('bim-api-rate-limit', True)
    app.config['API_RATE_LIMIT'] = 3
    app.config['API_RATE_LIMIT_WINDOW'] = 60

    # Primele 3 cereri sub prag -> 200
    for i in range(3):
        resp = _get(client, token_str)
        assert resp.status_code == 200, f'cererea {i} ar trebui sa treaca'

    # A 4-a depaseste pragul -> 429 cu Retry-After
    resp = _get(client, token_str)
    assert resp.status_code == 429
    assert 'Retry-After' in resp.headers
    retry = int(resp.headers['Retry-After'])
    assert retry >= 1
    body = resp.get_json()
    assert body['error'] == 'rate limit exceeded'
    assert body['retry_after'] == retry


def test_reset_state_redeschide_accesul(client, app, token_str):
    with app.app_context():
        ff.set_flag('bim-api-rate-limit', True)
    app.config['API_RATE_LIMIT'] = 2
    app.config['API_RATE_LIMIT_WINDOW'] = 60

    assert _get(client, token_str).status_code == 200
    assert _get(client, token_str).status_code == 200
    assert _get(client, token_str).status_code == 429
    # Dupa reset (echivalent fereastra noua) -> iar permis
    svc_tokens.reset_rate_limit()
    assert _get(client, token_str).status_code == 200


def test_limita_e_per_token(client, app, admin_user):
    """Doua tokenuri distincte au contoare separate."""
    with app.app_context():
        ff.set_flag('bim-api-rate-limit', True)
        ApiToken.query.delete(); db.session.commit()
        aid = _admin_id(admin_user)
        t1 = svc_tokens.create_token('rl-a', aid, ['bim:read']).token
        t2 = svc_tokens.create_token('rl-b', aid, ['bim:read']).token
    app.config['API_RATE_LIMIT'] = 1
    app.config['API_RATE_LIMIT_WINDOW'] = 60

    # token 1: prima ok, a doua 429
    assert _get(client, t1).status_code == 200
    assert _get(client, t1).status_code == 429
    # token 2: contor propriu -> prima ok
    assert _get(client, t2).status_code == 200


# ====================================================
# Unit pe functia de check (fara HTTP)
# ====================================================

def test_check_rate_limit_no_op_cu_flag_off(app):
    with app.app_context():
        ff.set_flag('bim-api-rate-limit', False)
        for _ in range(1000):
            permis, retry = svc_tokens.check_rate_limit(999)
            assert permis is True
            assert retry == 0


def test_check_rate_limit_contor_cu_flag_on(app):
    with app.app_context():
        ff.set_flag('bim-api-rate-limit', True)
        app.config['API_RATE_LIMIT'] = 2
        app.config['API_RATE_LIMIT_WINDOW'] = 60
        svc_tokens.reset_rate_limit()
        try:
            assert svc_tokens.check_rate_limit(7)[0] is True
            assert svc_tokens.check_rate_limit(7)[0] is True
            permis, retry = svc_tokens.check_rate_limit(7)
            assert permis is False
            assert retry >= 1
        finally:
            ff.set_flag('bim-api-rate-limit', False)
            app.config.pop('API_RATE_LIMIT', None)
            app.config.pop('API_RATE_LIMIT_WINDOW', None)
            svc_tokens.reset_rate_limit()
