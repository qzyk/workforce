"""
Teste unit pentru transmittals ISO 19650 (services.bim_transmittals).

Verifica CONTINUTUL: legatura cu versiunea, tranzitii valide/invalide, audit.
"""

import json
import pytest

from models import (db, BIMTransmittal, BIMModelVersion, ModelBIM, Utilizator)
from services import bim_transmittals as tr_svc


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='tr_admin@test.local').first()
        if not u:
            u = Utilizator(nume='TA', prenume='X', email='tr_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


def _make_version(versiune='v1.0'):
    m = ModelBIM(nume='Model TR', tip='ifc'); db.session.add(m); db.session.flush()
    v = BIMModelVersion(model_id=m.id, versiune=versiune, status='shared')
    db.session.add(v); db.session.flush()
    return v


def test_create_transmittal_legat_de_versiune(app, admin):
    with app.app_context():
        v = _make_version()
        tr = tr_svc.create_transmittal(
            v, cod='TR-001', nume='Predare DTAC',
            destinatari=['Beneficiar SRL', 'Verificator'], user=admin)
        assert tr.id is not None
        assert tr.model_version_id == v.id
        assert tr.status == 'pregatit'
        assert tr.get_destinatari() == ['Beneficiar SRL', 'Verificator']
        # Apare in lista versiunii
        lista = BIMTransmittal.query.filter_by(model_version_id=v.id).all()
        assert len(lista) == 1 and lista[0].cod == 'TR-001'
        # Audit
        from models import AuditLog
        assert AuditLog.query.filter_by(entity_type='bim_transmittal',
                                        action='create').count() >= 1


def test_create_transmittal_cod_gol_ridica_eroare(app, admin):
    with app.app_context():
        v = _make_version()
        with pytest.raises(tr_svc.TransmittalError):
            tr_svc.create_transmittal(v, cod='   ', user=admin)


def test_tranzitie_pregatit_la_trimis_seteaza_data(app, admin):
    with app.app_context():
        v = _make_version()
        tr = tr_svc.create_transmittal(v, cod='TR-002', user=admin)
        assert tr.data_trimitere is None
        tr_svc.schimba_status(tr, 'trimis', admin)
        tr_after = BIMTransmittal.query.get(tr.id)
        assert tr_after.status == 'trimis'
        assert tr_after.data_trimitere is not None
        # Audit pe tranzitie
        from models import AuditLog
        assert AuditLog.query.filter_by(entity_type='bim_transmittal',
                                        action='transmittal_trimis').count() >= 1


def test_tranzitie_invalida_ridica_eroare(app, admin):
    with app.app_context():
        v = _make_version()
        tr = tr_svc.create_transmittal(v, cod='TR-003', user=admin)
        # pregatit -> primit NU e permis (trebuie sa treaca prin trimis)
        with pytest.raises(tr_svc.TransmittalError):
            tr_svc.schimba_status(tr, 'primit', admin)
        assert BIMTransmittal.query.get(tr.id).status == 'pregatit'


def test_flux_complet_trimis_primit(app, admin):
    with app.app_context():
        v = _make_version()
        tr = tr_svc.create_transmittal(v, cod='TR-004', user=admin)
        tr_svc.schimba_status(tr, 'trimis', admin)
        tr_svc.schimba_status(tr, 'primit', admin)
        assert BIMTransmittal.query.get(tr.id).status == 'primit'
        # primit e terminal
        with pytest.raises(tr_svc.TransmittalError):
            tr_svc.schimba_status(tr, 'trimis', admin)


def test_respins_se_poate_retrimite(app, admin):
    with app.app_context():
        v = _make_version()
        tr = tr_svc.create_transmittal(v, cod='TR-005', user=admin)
        tr_svc.schimba_status(tr, 'trimis', admin)
        tr_svc.schimba_status(tr, 'respins', admin)
        assert BIMTransmittal.query.get(tr.id).status == 'respins'
        tr_svc.schimba_status(tr, 'trimis', admin)
        assert BIMTransmittal.query.get(tr.id).status == 'trimis'


def test_status_necunoscut_ridica_eroare(app, admin):
    with app.app_context():
        v = _make_version()
        tr = tr_svc.create_transmittal(v, cod='TR-006', user=admin)
        with pytest.raises(tr_svc.TransmittalError):
            tr_svc.schimba_status(tr, 'aiurea', admin)
