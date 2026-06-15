"""Teste pentru Faza 2 BIM: extragere Property Sets + bounding box la import IFC.

Acopera:
- parsing PUR al Psets (duck-typed, FARA ifcopenshell) -> ruleaza mereu;
- import cu IFC REAL generat programatic (importorskip) -> proprietati_json + bbox_json;
- regresie flag OFF: import IDENTIC cu azi (proprietati_json + bbox_json raman None);
- CLI migrate-bim adauga bbox_json/bbox_sursa pe o schema veche (fara coloane).
"""
import json

import pytest


# ---------------------------------------------------------------------------
# (A) Parsing PUR - fara ifcopenshell. Construim un element fals (duck-typed)
#     cu .IsDefinedBy ce mimeaza un IfcPropertySet + un IfcElementQuantity.
# ---------------------------------------------------------------------------

class _FakeEntity:
    """Mimeaza o entitate IFC: .is_a(tip) + atribute arbitrare."""
    def __init__(self, _tip, **attrs):
        self._tip = _tip
        for k, v in attrs.items():
            setattr(self, k, v)

    def is_a(self, tip):
        return self._tip == tip


def _fake_nominal(val):
    """Mimeaza un IFC value cu .wrappedValue."""
    return _FakeEntity('IfcValue', wrappedValue=val)


def _fake_element_cu_pset():
    """Element fals cu Pset_WallCommon (IsExternal, FireRating) + BaseQuantities."""
    p1 = _FakeEntity('IfcPropertySingleValue', Name='IsExternal',
                     NominalValue=_fake_nominal(True))
    p2 = _FakeEntity('IfcPropertySingleValue', Name='FireRating',
                     NominalValue=_fake_nominal('REI 120'))
    # proprietate fara nume -> ignorata
    p3 = _FakeEntity('IfcPropertySingleValue', Name=None,
                     NominalValue=_fake_nominal('x'))
    pset = _FakeEntity('IfcPropertySet', Name='Pset_WallCommon',
                       HasProperties=[p1, p2, p3])
    rel_pset = _FakeEntity('IfcRelDefinesByProperties',
                           RelatingPropertyDefinition=pset)

    q_vol = _FakeEntity('IfcQuantityVolume', Name='GrossVolume', VolumeValue=2.5)
    q_len = _FakeEntity('IfcQuantityLength', Name='Length', LengthValue=5.0)
    qto = _FakeEntity('IfcElementQuantity', Name='BaseQuantities',
                      Quantities=[q_vol, q_len])
    rel_qto = _FakeEntity('IfcRelDefinesByProperties',
                          RelatingPropertyDefinition=qto)

    return _FakeEntity('IfcWall', IsDefinedBy=[rel_pset, rel_qto])


def test_pset_parsing_pur():
    """extrage_psets pe element duck-typed -> dict-ul asteptat (fara ifcopenshell)."""
    from services.ifc_import import extrage_psets
    el = _fake_element_cu_pset()
    rez = extrage_psets(el)

    assert 'Pset_WallCommon' in rez
    assert rez['Pset_WallCommon']['IsExternal'] is True
    assert rez['Pset_WallCommon']['FireRating'] == 'REI 120'
    # proprietatea fara nume nu apare
    assert None not in rez['Pset_WallCommon']

    assert 'BaseQuantities' in rez
    assert rez['BaseQuantities']['GrossVolume'] == 2.5
    assert rez['BaseQuantities']['Length'] == 5.0

    # serializabil JSON (valorile non-simple devin str)
    json.dumps(rez)


def test_pset_parsing_robust_la_lipsa():
    """Element fara IsDefinedBy / cu relatii goale -> dict gol, fara exceptie."""
    from services.ifc_import import extrage_psets
    assert extrage_psets(_FakeEntity('IfcWall')) == {}
    assert extrage_psets(_FakeEntity('IfcWall', IsDefinedBy=None)) == {}
    assert extrage_psets(_FakeEntity('IfcWall', IsDefinedBy=[])) == {}
    # relatie de alt tip -> ignorata
    alt = _FakeEntity('IfcRelAssociatesMaterial')
    assert extrage_psets(_FakeEntity('IfcWall', IsDefinedBy=[alt])) == {}


def test_extrage_bbox_fara_motor_geom_intoarce_none():
    """extrage_bbox cu geom/settings None -> None (degradare gratioasa)."""
    from services.ifc_import import extrage_bbox
    assert extrage_bbox(object(), None, None) is None


# ---------------------------------------------------------------------------
# Helper: genereaza un IFC mic (1 IfcWall cu Pset + geometrie) in memorie.
# Folosit de testele cu IFC real (importorskip ifcopenshell).
# ---------------------------------------------------------------------------

def _scrie_ifc_mic(tmp_path):
    """Creeaza un .ifc minimal cu IfcSite/IfcBuilding/IfcWallStandardCase,
    un Pset_WallCommon.IsExternal=True si geometrie (extruded box). Returneaza
    calea fisierului."""
    import ifcopenshell
    from ifcopenshell.api import run

    f = ifcopenshell.file(schema='IFC4')
    proj = run('root.create_entity', f, ifc_class='IfcProject', name='ProiectTest')
    run('unit.assign_unit', f)
    ctx = run('context.add_context', f, context_type='Model')
    body = run('context.add_context', f, context_type='Model',
               context_identifier='Body', target_view='MODEL_VIEW', parent=ctx)

    site = run('root.create_entity', f, ifc_class='IfcSite', name='SantierTest')
    building = run('root.create_entity', f, ifc_class='IfcBuilding', name='CladireTest')
    storey = run('root.create_entity', f, ifc_class='IfcBuildingStorey', name='Parter')
    run('aggregate.assign_object', f, products=[site], relating_object=proj)
    run('aggregate.assign_object', f, products=[building], relating_object=site)
    run('aggregate.assign_object', f, products=[storey], relating_object=building)

    wall = run('root.create_entity', f, ifc_class='IfcWallStandardCase', name='Perete-01')
    run('spatial.assign_container', f, products=[wall], relating_structure=storey)

    # Geometrie: un box prin reprezentare extrudata simpla
    repr_ = run('geometry.add_wall_representation', f, context=body,
                length=4.0, height=3.0, thickness=0.2)
    run('geometry.assign_representation', f, product=wall, representation=repr_)

    # Pset cu o proprietate
    pset = run('pset.add_pset', f, product=wall, name='Pset_WallCommon')
    run('pset.edit_pset', f, pset=pset, properties={'IsExternal': True})

    cale = str(tmp_path / 'mic.ifc')
    f.write(cale)
    return cale


@pytest.fixture()
def _flag_pset_on(app):
    """Activeaza 'bim-pset-extraction' pe durata testului, apoi il reseteaza."""
    from services.feature_flags import set_flag
    from models import db, FeatureFlag
    with app.app_context():
        set_flag('bim-pset-extraction', True)
    yield
    with app.app_context():
        ff = FeatureFlag.query.filter_by(key='bim-pset-extraction', tenant_id=None).first()
        if ff is not None:
            db.session.delete(ff)
            db.session.commit()


def test_ifc_import_pset_cu_ifc_real(app, tmp_path, _flag_pset_on):
    """Import cu flag ON pe un IFC real -> proprietati_json contine Pset-ul."""
    pytest.importorskip('ifcopenshell')
    from services.ifc_import import import_ifc
    from models import ElementBIM
    cale = _scrie_ifc_mic(tmp_path)
    with app.app_context():
        rez = import_ifc(cale)
        assert rez['status'] == 'ok', rez
        el = ElementBIM.query.filter_by(tip_element='wall').first()
        assert el is not None
        assert el.proprietati_json is not None
        props = json.loads(el.proprietati_json)
        assert 'Pset_WallCommon' in props
        assert props['Pset_WallCommon'].get('IsExternal') is True


def test_bbox_extraction_cu_ifc_real(app, tmp_path, _flag_pset_on):
    """Import cu flag ON -> bbox_json cu min/max plauzibile + bbox_sursa='ifc_geom'."""
    pytest.importorskip('ifcopenshell')
    from services.ifc_import import import_ifc
    from models import ElementBIM
    cale = _scrie_ifc_mic(tmp_path)
    with app.app_context():
        rez = import_ifc(cale)
        assert rez['status'] == 'ok', rez
        el = ElementBIM.query.filter_by(tip_element='wall').first()
        assert el is not None and el.bbox_json is not None
        assert el.bbox_sursa == 'ifc_geom'
        bbox = json.loads(el.bbox_json)
        assert set(bbox) == {'min', 'max'}
        assert len(bbox['min']) == 3 and len(bbox['max']) == 3
        # max >= min pe fiecare axa; volumul nu e degenerat
        for i in range(3):
            assert bbox['max'][i] >= bbox['min'][i]
        dims = [bbox['max'][i] - bbox['min'][i] for i in range(3)]
        assert max(dims) > 0.0


def _scrie_ifc_doua_ziduri_deplasate(tmp_path):
    """Creeaza un .ifc cu DOUA ziduri identice ca geometrie (length=4, height=3,
    thickness=0.2), dar deplasate diferit in model: W1 la origine, W2 la (100,50,10) m
    via ObjectPlacement. Returneaza (cale, offset_w2).

    Scop: regresie pentru bug-ul de coordonate LOCALE - daca bbox-ul ignora
    ObjectPlacement, ambele ziduri primesc bbox IDENTIC (inutilizabil pentru clash).
    """
    import numpy as np
    import ifcopenshell
    from ifcopenshell.api import run

    f = ifcopenshell.file(schema='IFC4')
    proj = run('root.create_entity', f, ifc_class='IfcProject', name='ProiectTest')
    run('unit.assign_unit', f)
    ctx = run('context.add_context', f, context_type='Model')
    body = run('context.add_context', f, context_type='Model',
               context_identifier='Body', target_view='MODEL_VIEW', parent=ctx)
    site = run('root.create_entity', f, ifc_class='IfcSite', name='SantierTest')
    building = run('root.create_entity', f, ifc_class='IfcBuilding', name='CladireTest')
    storey = run('root.create_entity', f, ifc_class='IfcBuildingStorey', name='Parter')
    run('aggregate.assign_object', f, products=[site], relating_object=proj)
    run('aggregate.assign_object', f, products=[building], relating_object=site)
    run('aggregate.assign_object', f, products=[storey], relating_object=building)

    offset = (100.0, 50.0, 10.0)

    def _zid(nume, dx_dy_dz):
        w = run('root.create_entity', f, ifc_class='IfcWallStandardCase', name=nume)
        run('spatial.assign_container', f, products=[w], relating_structure=storey)
        repr_ = run('geometry.add_wall_representation', f, context=body,
                    length=4.0, height=3.0, thickness=0.2)
        run('geometry.assign_representation', f, product=w, representation=repr_)
        m = np.eye(4)
        m[0, 3], m[1, 3], m[2, 3] = dx_dy_dz
        run('geometry.edit_object_placement', f, product=w, matrix=m)
        return w

    _zid('Perete-W1', (0.0, 0.0, 0.0))
    _zid('Perete-W2', offset)

    cale = str(tmp_path / 'doua_ziduri.ifc')
    f.write(cale)
    return cale, offset


def test_bbox_world_coords_ziduri_deplasate_distincte(app, tmp_path, _flag_pset_on):
    """REGRESIE: doua ziduri identice deplasate in model TREBUIE sa primeasca
    bbox-uri DISTINCTE (coordonate world, NU locale).

    Cu bug-ul (settings QTO default, use-world-coords=False) ambele primeau acelasi
    bbox {min:[0,0,0], max:[4,0.2,3]} -> inutilizabil pentru clash/min_clearance.
    Aici verificam ca W2 e deplasat fata de W1 cu exact offset-ul din model.
    """
    pytest.importorskip('ifcopenshell')
    import numpy as np
    from services.ifc_import import import_ifc
    from models import ElementBIM
    cale, offset = _scrie_ifc_doua_ziduri_deplasate(tmp_path)
    with app.app_context():
        rez = import_ifc(cale)
        assert rez['status'] == 'ok', rez
        ziduri = ElementBIM.query.filter_by(tip_element='wall').order_by(ElementBIM.cod).all()
        assert len(ziduri) == 2
        bboxuri = {z.nume: json.loads(z.bbox_json) for z in ziduri if z.bbox_json}
        assert set(bboxuri) == {'Perete-W1', 'Perete-W2'}, bboxuri

        b1, b2 = bboxuri['Perete-W1'], bboxuri['Perete-W2']
        # bbox-urile NU sunt identice (ar fi fost, cu bug-ul de coordonate locale)
        assert b1 != b2
        # W2 e deplasat fata de W1 cu exact offset-ul model pe fiecare axa
        for i in range(3):
            assert b2['min'][i] - b1['min'][i] == pytest.approx(offset[i], abs=1e-6)
            assert b2['max'][i] - b1['max'][i] == pytest.approx(offset[i], abs=1e-6)
        # dimensiunile (latimi) raman egale: aceeasi geometrie, doar deplasata
        dims1 = [b1['max'][i] - b1['min'][i] for i in range(3)]
        dims2 = [b2['max'][i] - b2['min'][i] for i in range(3)]
        assert dims1 == pytest.approx(dims2, abs=1e-6)
        assert np.max(dims1) == pytest.approx(4.0, abs=1e-6)  # length=4 ajunge in bbox


def test_regresie_flag_off_nu_extrage_nimic(app, tmp_path):
    """Flag OFF (default) -> proprietati_json + bbox_json raman None (identic cu azi)."""
    pytest.importorskip('ifcopenshell')
    from services.ifc_import import import_ifc
    from services.feature_flags import is_enabled
    from models import ElementBIM
    cale = _scrie_ifc_mic(tmp_path)
    with app.app_context():
        assert is_enabled('bim-pset-extraction') is False
        rez = import_ifc(cale)
        assert rez['status'] == 'ok', rez
        el = ElementBIM.query.filter_by(tip_element='wall').first()
        assert el is not None
        assert el.proprietati_json is None
        assert el.bbox_json is None
        assert el.bbox_sursa is None


# ---------------------------------------------------------------------------
# (E) CLI migrate-bim adauga bbox_json/bbox_sursa pe o schema VECHE
#     (bim_elemente fara aceste coloane). Teardown robust: recreem schema
#     din modelele curente via db.create_all() (vezi test_gantt_calendar_db.py).
# ---------------------------------------------------------------------------

# DDL bim_elemente FARA bbox_json/bbox_sursa (schema dinainte de 0022).
_DDL_BIM_ELEMENTE_VECHI = """
CREATE TABLE bim_elemente (
    id INTEGER NOT NULL,
    spatiu_id INTEGER,
    nivel_id INTEGER,
    cladire_id INTEGER,
    cod VARCHAR(100) NOT NULL,
    nume VARCHAR(200),
    tip_element VARCHAR(50) NOT NULL,
    descriere TEXT,
    cantitate NUMERIC(12, 3),
    unitate_masura VARCHAR(20),
    ifc_global_id VARCHAR(100),
    extern_id VARCHAR(100),
    source_system VARCHAR(30),
    model_bim_id INTEGER,
    last_synced_at DATETIME,
    status VARCHAR(30),
    proprietati_json TEXT,
    data_creare DATETIME,
    data_actualizare DATETIME,
    PRIMARY KEY (id)
)
"""


def test_cli_migrate_bim_adauga_bbox_pe_schema_veche(app):
    """Simuleaza prod cu bim_elemente FARA bbox_json/bbox_sursa si verifica ca
    'flask migrate-bim' adauga coloanele cu ALTER idempotent.

    Capcana: db.create_all() NU adauga coloane pe tabele existente - fara ALTER,
    orice query pe ElementBIM (care mapeaza bbox_json) ar crapa cu
    'no such column: bim_elemente.bbox_json' dupa deploy.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import OperationalError
    from models import db, ElementBIM

    with app.app_context():
        # 1. Aduce bim_elemente la schema veche (fara coloanele bbox)
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS bim_elemente'))
            conn.execute(text(_DDL_BIM_ELEMENTE_VECHI))
            conn.execute(text(
                "INSERT INTO bim_elemente (cod, tip_element, status) "
                "VALUES ('W-VECHI', 'wall', 'proiectat')"))
        db.session.remove()

        # 2. Reproducere: modelul mapeaza bbox_json -> query crapa pe schema veche
        with pytest.raises(OperationalError):
            ElementBIM.query.first()
        db.session.rollback()

    # 3. Ruleaza CLI-ul (pasul de deploy) - trebuie sa repare schema
    runner = app.test_cli_runner()
    r1 = runner.invoke(args=['migrate-bim'])
    assert r1.exit_code == 0, r1.output
    assert 'bim_elemente.bbox_json adaugat' in r1.output
    assert 'bim_elemente.bbox_sursa adaugat' in r1.output

    with app.app_context():
        cols = {c['name'] for c in inspect(db.engine).get_columns('bim_elemente')}
        assert 'bbox_json' in cols and 'bbox_sursa' in cols
        el = ElementBIM.query.first()
        assert el is not None and el.cod == 'W-VECHI'
        assert el.bbox_json is None and el.bbox_sursa is None

    # 4. Idempotent: a doua rulare nu mai face ALTER
    r2 = runner.invoke(args=['migrate-bim'])
    assert r2.exit_code == 0
    assert 'bim_elemente.bbox_json exista deja' in r2.output

    # 5. Teardown ROBUST: recreem bim_elemente din modelele curente ca sa NU
    # poluam sesiunea (DB session-scoped, partajat cu restul testelor).
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS bim_elemente'))
        db.session.remove()
        db.create_all()


# ---------------------------------------------------------------------------
# (F) Frontend: properties panel pe element_detaliu - prezent cand exista
#     proprietati, inofensiv (absent) cand proprietati_json e NULL.
# ---------------------------------------------------------------------------

def test_model_proprietati_si_bbox_parse():
    """Proprietatile model ElementBIM.proprietati / .bbox degradeaza gratios."""
    from models import ElementBIM
    e = ElementBIM(cod='X', tip_element='wall')
    assert e.proprietati == {} and e.bbox is None       # NULL -> gol
    e.proprietati_json = '{nu e json'
    assert e.proprietati == {}                          # invalid -> gol
    e.proprietati_json = json.dumps({'Pset_X': {'A': 1}})
    assert e.proprietati == {'Pset_X': {'A': 1}}
    e.bbox_json = json.dumps({'min': [0, 0, 0], 'max': [1, 2, 3]})
    assert e.bbox['max'] == [1, 2, 3]


def test_element_detaliu_arata_proprietati(authenticated_client, app):
    """Pagina element afiseaza Property Sets cand proprietati_json e populat."""
    from models import db, ElementBIM
    with app.app_context():
        e = ElementBIM(cod='W-PROPS', tip_element='wall',
                       proprietati_json=json.dumps({'Pset_WallCommon': {'IsExternal': True}}),
                       bbox_json=json.dumps({'min': [0, 0, 0], 'max': [4.0, 0.2, 3.0]}),
                       bbox_sursa='ifc_geom')
        db.session.add(e)
        db.session.commit()
        eid = e.id
    r = authenticated_client.get(f'/bim/element/{eid}')
    assert r.status_code == 200
    assert b'Proprietati IFC' in r.data
    assert b'Pset_WallCommon' in r.data
    assert b'IsExternal' in r.data
    assert b'Bounding box' in r.data


def test_element_detaliu_fara_proprietati_inofensiv(authenticated_client, app):
    """Element fara proprietati (model vechi / flag OFF) -> pagina OK, fara panou."""
    from models import db, ElementBIM
    with app.app_context():
        e = ElementBIM(cod='W-GOL', tip_element='wall')
        db.session.add(e)
        db.session.commit()
        eid = e.id
    r = authenticated_client.get(f'/bim/element/{eid}')
    assert r.status_code == 200
    assert b'Proprietati IFC' not in r.data
