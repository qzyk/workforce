"""
Teste unit pentru validatorul IDS (services.bim_ids).

Verifica CONTINUTUL violarilor (mesaj, element, status), nu doar numarul.
Lectie din fazele anterioare: element fara proprietati_json -> violare ONESTA
'lipsa date', NU pass fals.
"""

import json
import pytest

from models import (db, BIMIDSSpec, BIMIDSViolation, ElementBIM,
                    Cladire, Santier, Utilizator)
from services import bim_ids


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='ids_admin@test.local').first()
        if not u:
            u = Utilizator(nume='IA', prenume='X', email='ids_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


def _make_element(cladire_id, cod, tip='wall', proprietati='__NIMIC__', nume=None):
    """proprietati='__NIMIC__' (sentinel) -> proprietati_json ramane NULL (lipsa date).
    Altfel se serializeaza nested {pset: {prop: val}}."""
    kwargs = dict(cladire_id=cladire_id, cod=cod, tip_element=tip,
                  status='proiectat', nume=nume or cod)
    if proprietati != '__NIMIC__':
        kwargs['proprietati_json'] = json.dumps(proprietati or {})
    el = ElementBIM(**kwargs)
    db.session.add(el)
    db.session.flush()
    return el


def _spec(admin, definition, faza='executie', nume='IDS test'):
    return bim_ids.create_spec(nume=nume, definition=definition, faza=faza, user=admin)


# ====================================================
# create_spec
# ====================================================

def test_create_spec_writes_audit(app, admin):
    with app.app_context():
        spec = bim_ids.create_spec(
            nume='Pereti FR la executie',
            definition={'clase_ifc': ['wall'],
                        'proprietati_cerute': [{'pset': 'Pset_WallCommon', 'nume': 'FireRating'}]},
            faza='executie', user=admin,
        )
        assert spec.id is not None
        assert spec.faza == 'executie'
        from models import AuditLog
        rows = AuditLog.query.filter_by(entity_type='bim_ids_spec', action='create').count()
        assert rows >= 1


def test_create_spec_empty_name_raises(app, admin):
    with app.app_context():
        with pytest.raises(ValueError):
            bim_ids.create_spec(nume='   ', definition={}, user=admin)


# ====================================================
# Validare: prezenta proprietate (Faza 2 nested pset)
# ====================================================

def test_element_cu_proprietatea_ceruta_trece(app, admin):
    with app.app_context():
        s = Santier(cod='S-IDS1', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Element care ARE FireRating in Pset_WallCommon (structura Faza 2)
        _make_element(c.id, 'W-OK', tip='wall',
                      proprietati={'Pset_WallCommon': {'FireRating': 'REI 120'}})
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [
                                 {'pset': 'Pset_WallCommon', 'nume': 'FireRating'}]})
        res = bim_ids.valideaza_spec(spec, user=admin)
        assert res['total_elemente'] == 1
        assert res['total_violations'] == 0
        assert BIMIDSViolation.query.filter_by(spec_id=spec.id).count() == 0


def test_element_fara_proprietatea_ceruta_genereaza_violare(app, admin):
    with app.app_context():
        s = Santier(cod='S-IDS2', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Are PSet, dar fara FireRating
        el = _make_element(c.id, 'W-MISS', tip='wall',
                           proprietati={'Pset_WallCommon': {'IsExternal': True}})
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [
                                 {'pset': 'Pset_WallCommon', 'nume': 'FireRating'}]})
        res = bim_ids.valideaza_spec(spec, user=admin)
        assert res['total_violations'] == 1
        v = BIMIDSViolation.query.filter_by(spec_id=spec.id).first()
        # CONTINUT: mesaj mentioneaza proprietatea, element corect, status corect
        assert 'FireRating' in v.mesaj
        assert v.element_bim_id == el.id
        det = json.loads(v.detalii_json)
        assert det['status'] == 'lipsa_proprietate'
        assert det['proprietate'] == 'FireRating'


def test_revalidare_nu_acumuleaza_violarile(app, admin):
    """Re-rularea aceleiasi spec (flux normal ISO 19650 dupa corectii) NU trebuie
    sa dubleze violarile: o validare reflecta starea curenta, nu istoricul."""
    with app.app_context():
        s = Santier(cod='S-IDS-RE', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _make_element(c.id, 'W-RE', tip='wall',
                      proprietati={'Pset_WallCommon': {'IsExternal': True}})
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [
                                 {'pset': 'Pset_WallCommon', 'nume': 'FireRating'}]})
        # 3 rulari succesive pe acelasi element neconform
        for _ in range(3):
            res = bim_ids.valideaza_spec(spec, user=admin)
            assert res['total_violations'] == 1
        # Totalul din DB ramane 1 (o singura neconformitate reala), NU 3 cumulat
        assert BIMIDSViolation.query.filter_by(spec_id=spec.id).count() == 1


def test_element_fara_proprietati_json_e_lipsa_date_nu_pass_fals(app, admin):
    with app.app_context():
        s = Santier(cod='S-IDS3', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Element FARA proprietati_json (model neimportat cu Faza 2 / flag OFF)
        el = _make_element(c.id, 'W-NODATA', tip='wall')  # proprietati_json = NULL
        assert ElementBIM.query.get(el.id).proprietati_json is None
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [
                                 {'pset': 'Pset_WallCommon', 'nume': 'FireRating'}]})
        res = bim_ids.valideaza_spec(spec, user=admin)
        # NU pass fals: o violare 'lipsa date'
        assert res['total_violations'] == 1
        v = BIMIDSViolation.query.filter_by(spec_id=spec.id).first()
        assert v.element_bim_id == el.id
        det = json.loads(v.detalii_json)
        assert det['status'] == 'lipsa_date'
        assert 'lipsa date' in v.mesaj.lower()
        # by_status reflecta onestitatea
        assert res['by_status'].get('lipsa_date') == 1


# ====================================================
# Validare: valoare exacta + tipar
# ====================================================

def test_valoare_gresita_genereaza_violare(app, admin):
    with app.app_context():
        s = Santier(cod='S-IDS4', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _make_element(c.id, 'W-VAL', tip='wall',
                      proprietati={'Pset_WallCommon': {'FireRating': 'REI 60'}})
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [
                                 {'pset': 'Pset_WallCommon', 'nume': 'FireRating',
                                  'valoare': 'REI 120'}]})
        res = bim_ids.valideaza_spec(spec, user=admin)
        assert res['total_violations'] == 1
        v = BIMIDSViolation.query.filter_by(spec_id=spec.id).first()
        det = json.loads(v.detalii_json)
        assert det['status'] == 'valoare_gresita'
        assert det['valoare'] == 'REI 60'
        assert det['valoare_ceruta'] == 'REI 120'


def test_valoare_corecta_case_insensitive_trece(app, admin):
    with app.app_context():
        s = Santier(cod='S-IDS5', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _make_element(c.id, 'W-CI', tip='wall',
                      proprietati={'Pset_WallCommon': {'FireRating': 'rei 120'}})
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [
                                 {'pset': 'Pset_WallCommon', 'nume': 'FireRating',
                                  'valoare': 'REI 120'}]})
        res = bim_ids.valideaza_spec(spec, user=admin)
        assert res['total_violations'] == 0


def test_tipar_regex_nepotrivit(app, admin):
    with app.app_context():
        s = Santier(cod='S-IDS6', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _make_element(c.id, 'W-RX', tip='wall',
                      proprietati={'Pset_WallCommon': {'FireRating': 'necunoscut'}})
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [
                                 {'pset': 'Pset_WallCommon', 'nume': 'FireRating',
                                  'tipar': r'^REI \d+$'}]})
        res = bim_ids.valideaza_spec(spec, user=admin)
        assert res['total_violations'] == 1
        v = BIMIDSViolation.query.filter_by(spec_id=spec.id).first()
        det = json.loads(v.detalii_json)
        assert det['status'] == 'tipar_nepotrivit'


# ====================================================
# Selectie pe clasa IFC + proprietate optionala + pset implicit
# ====================================================

def test_clasa_ifc_filtreaza_elementele(app, admin):
    with app.app_context():
        s = Santier(cod='S-IDS7', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _make_element(c.id, 'W1', tip='wall',
                      proprietati={'Pset_WallCommon': {'IsExternal': True}})  # lipsa FireRating
        _make_element(c.id, 'D1', tip='door',
                      proprietati={'Pset_DoorCommon': {'Nume': 'usa'}})  # nu e vizat
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [
                                 {'pset': 'Pset_WallCommon', 'nume': 'FireRating'}]})
        res = bim_ids.valideaza_spec(spec, user=admin)
        # Doar peretele e verificat -> 1 violare; usa ignorata
        assert res['total_elemente'] == 1
        assert res['total_violations'] == 1


def test_proprietate_neobligatorie_lipsa_nu_violeaza(app, admin):
    with app.app_context():
        s = Santier(cod='S-IDS8', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _make_element(c.id, 'W-OPT', tip='wall',
                      proprietati={'Pset_WallCommon': {'IsExternal': True}})
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [
                                 {'pset': 'Pset_WallCommon', 'nume': 'FireRating',
                                  'obligatoriu': False}]})
        res = bim_ids.valideaza_spec(spec, user=admin)
        assert res['total_violations'] == 0


def test_pset_implicit_cauta_in_orice_pset(app, admin):
    with app.app_context():
        s = Santier(cod='S-IDS9', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Proprietatea LoadBearing exista intr-un pset custom; cerinta fara 'pset'
        _make_element(c.id, 'W-ANY', tip='wall',
                      proprietati={'Pset_Custom': {'LoadBearing': 'true'}})
        spec = _spec(admin, {'clase_ifc': ['wall'],
                             'proprietati_cerute': [{'nume': 'LoadBearing'}]})
        res = bim_ids.valideaza_spec(spec, user=admin)
        assert res['total_violations'] == 0
