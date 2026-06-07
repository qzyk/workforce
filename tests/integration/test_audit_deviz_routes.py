"""
Teste de integrare pentru modulul Audit Deviz (rute).

Verific:
  - gating pe feature flag 'audit-deviz' (404 cand e OFF)
  - lista accesibila cand flag-ul e ON
  - upload ZIP -> creeaza audit -> dashboard cu reconciliere + structura cost
"""
import io
import zipfile

from tests.unit.test_audit_deviz import _set_ok


def _zip(files) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for nm, data in files:
            z.writestr(nm, data)
    buf.seek(0)
    return buf


def test_404_cand_flag_off(authenticated_client):
    r = authenticated_client.get('/audit-deviz/')
    assert r.status_code == 404


def test_lista_cu_flag_on(app, authenticated_client):
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('audit-deviz', True)
    r = authenticated_client.get('/audit-deviz/')
    assert r.status_code == 200


def test_upload_creeaza_audit(app, authenticated_client):
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('audit-deviz', True)
    z = _zip(_set_ok())
    r = authenticated_client.post('/audit-deviz/nou', data={
        'nume': 'Test Arhitectura',
        'proiect_id': '0',
        'fisiere': (z, 'set.zip'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Test Arhitectura' in body
    assert 'Structura de cost' in body
