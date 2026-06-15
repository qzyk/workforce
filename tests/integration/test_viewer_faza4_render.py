"""
Smoke test render pentru viewer-ul xeokit (Faza 4): paginile randeaza 200 si
contin referintele la plugin-uri (SectionPlanesPlugin, DistanceMeasurementsPlugin)
+ butoanele noi (Sectiune, Masoara, Reset). Fara WebGL real - doar HTML.

Plus: banner-ul de deprecare pe viewer-ul legacy.
"""
import os

import pytest

from models import db, ModelBIM
from services import feature_flags as ff


@pytest.fixture
def model_ifc(app):
    with app.app_context():
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'ifc')
        os.makedirs(upload_dir, exist_ok=True)
        path = os.path.join(upload_dir, 'test_faza4_render.ifc')
        with open(path, 'w') as f:
            f.write('ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n')
        m = ModelBIM(nume='Model Faza4', tip='ifc',
                     fisier_path=os.path.relpath(path, app.root_path),
                     fisier_marime=os.path.getsize(path))
        db.session.add(m); db.session.commit()
        yield {'id': m.id, 'path': path}
        try:
            os.unlink(path)
        except OSError:
            pass


def test_viewer_xeokit_contine_pluginuri_clipping_masuratori(app, authenticated_client, model_ifc):
    with app.app_context():
        ff.set_flag('bim-viewer-3d', True)
    try:
        r = authenticated_client.get(f'/bim/viewer/{model_ifc["id"]}')
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        # Referinte la plugin-uri in import + cod
        assert 'SectionPlanesPlugin' in body
        assert 'DistanceMeasurementsPlugin' in body
        # Butoane noi
        assert 'xvSectionBtn' in body
        assert 'xvMeasureBtn' in body
        assert 'xvResetToolsBtn' in body
        assert 'xvSaveViewBtn' in body
        # Save view-state foloseste ruta corecta
        assert 'view-state' in body
    finally:
        with app.app_context():
            ff.set_flag('bim-viewer-3d', False)


def test_viewer_legacy_are_banner_deprecare(authenticated_client, model_ifc):
    # Fara flag -> legacy; ?legacy=1 forteaza oricum legacy
    r = authenticated_client.get(f'/bim/viewer/{model_ifc["id"]}?legacy=1')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'web-ifc-viewer' in body
    assert 'depreciat' in body.lower()
