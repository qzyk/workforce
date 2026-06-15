"""
Integration tests pentru rutele Faza 5a transmittals ISO 19650.

Gate pe flag 'bim-model-versioning' (extind workflow-ul de versionare).
"""

import json
import pytest

from models import (db, BIMTransmittal, BIMModelVersion, ModelBIM)
from services import feature_flags as ff


def _make_version(app):
    with app.app_context():
        ff.set_flag('bim-model-versioning', True)
        m = ModelBIM(nume='Model TR-RT', tip='ifc'); db.session.add(m); db.session.flush()
        v = BIMModelVersion(model_id=m.id, versiune='v1.0', status='shared')
        db.session.add(v); db.session.commit()
        return v.id


def test_transmittals_lista_redirects_when_flag_off(authenticated_client, app):
    vid = _make_version(app)
    with app.app_context():
        ff.set_flag('bim-model-versioning', False)
    resp = authenticated_client.get(f'/bim/model-version/{vid}/transmittals',
                                    follow_redirects=False)
    assert resp.status_code == 302


def test_transmittals_lista_renders_when_flag_on(authenticated_client, app):
    vid = _make_version(app)
    resp = authenticated_client.get(f'/bim/model-version/{vid}/transmittals')
    assert resp.status_code == 200
    assert b'Transmittals' in resp.data


def test_creare_transmittal_via_route_apare_in_lista(authenticated_client, app):
    vid = _make_version(app)
    resp = authenticated_client.post(
        f'/bim/model-version/{vid}/transmittal-nou',
        data={'cod': 'TR-RT-001', 'nume': 'Predare',
              'destinatari': 'Beneficiar SRL\nVerificator MLPAT'},
        follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        tr = BIMTransmittal.query.filter_by(cod='TR-RT-001').first()
        assert tr is not None
        assert tr.model_version_id == vid
        assert tr.status == 'pregatit'
        assert tr.get_destinatari() == ['Beneficiar SRL', 'Verificator MLPAT']


def test_tranzitie_status_via_route_cu_audit(authenticated_client, app):
    vid = _make_version(app)
    with app.app_context():
        from models import AuditLog
        AuditLog.query.delete(); db.session.commit()
        tr = BIMTransmittal(model_version_id=vid, cod='TR-RT-002',
                            status='pregatit')
        db.session.add(tr); db.session.commit()
        tr_id = tr.id

    resp = authenticated_client.post(f'/bim/transmittal/{tr_id}/status',
                                     data={'status': 'trimis'},
                                     follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        from models import AuditLog
        tr = BIMTransmittal.query.get(tr_id)
        assert tr.status == 'trimis'
        assert tr.data_trimitere is not None
        # Audit logat
        assert AuditLog.query.filter_by(entity_type='bim_transmittal',
                                        action='transmittal_trimis').count() >= 1


def test_tranzitie_invalida_via_route_nu_schimba_status(authenticated_client, app):
    vid = _make_version(app)
    with app.app_context():
        tr = BIMTransmittal(model_version_id=vid, cod='TR-RT-003',
                            status='pregatit')
        db.session.add(tr); db.session.commit()
        tr_id = tr.id
    # pregatit -> primit invalid
    resp = authenticated_client.post(f'/bim/transmittal/{tr_id}/status',
                                     data={'status': 'primit'},
                                     follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert BIMTransmittal.query.get(tr_id).status == 'pregatit'
