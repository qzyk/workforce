"""
Render tests pentru overlay-ul Digital Twin in template-uri (iot-4).

Verifica gating-ul vizual:
- flag OFF -> panoul/JS-ul de overlay NU apare (viewer identic cu azi)
- flag ON  -> panoul + init + URL-urile API/SSE apar
"""

import os
import pytest

from models import db, ModelBIM, Santier, Cladire, ElementBIM
from services import feature_flags as ff


@pytest.fixture
def model_ifc(app):
    with app.app_context():
        s = Santier(cod='S-RNDR', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'ifc')
        os.makedirs(upload_dir, exist_ok=True)
        path = os.path.join(upload_dir, 'twin_render.ifc')
        with open(path, 'w') as f:
            f.write('ISO-10303-21;\n')
        m = ModelBIM(nume='Rndr Model', tip='ifc', santier_id=s.id,
                     fisier_path=os.path.relpath(path, app.root_path), fisier_marime=10)
        db.session.add(m); db.session.commit()
        yield {'model_id': m.id, 'santier_id': s.id, 'path': path}
        try:
            os.unlink(path)
        except OSError:
            pass


def test_viewer_xeokit_fara_overlay_cu_flag_off(authenticated_client, app, model_ifc):
    """bim-viewer-3d ON, iot-twin-overlay OFF -> overlay absent (zero regresie)."""
    with app.app_context():
        ff.set_flag('bim-viewer-3d', True)
        ff.set_flag('bim-iot-sensors', True)
        ff.set_flag('iot-twin-overlay', False)
    resp = authenticated_client.get(f"/bim/viewer/{model_ifc['model_id']}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'xeokit-sdk' in body  # tot viewer-ul xeokit
    assert 'xvTwinPanel' not in body
    assert 'initTwinOverlay(' not in body


def test_viewer_xeokit_cu_overlay_cu_flag_on(authenticated_client, app, model_ifc):
    """Ambele flag-uri ON -> panoul + init + URL-urile API/SSE apar."""
    with app.app_context():
        ff.set_flag('bim-viewer-3d', True)
        ff.set_flag('bim-iot-sensors', True)
        ff.set_flag('iot-twin-overlay', True)
    resp = authenticated_client.get(f"/bim/viewer/{model_ifc['model_id']}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'xvTwinPanel' in body
    assert 'initTwinOverlay(' in body
    assert '/twin-overlay' in body
    assert '/sensors/alerts/stream' in body
