"""
Teste pentru harvest-ul QTO IFC -> ElementBIM (Etapa 1: punte IFC -> F3).

Construiesc un IFC mic cu ifcopenshell.api (perete cu Qto + layer set multistrat,
placa cu Qto, stalp fara Qto, usa) si verific:
  - cantitatea citita din BaseQuantities (fara geometrie)
  - flag 'necesita_verificare' pe element multistrat (double-count) si pe gol
  - count (buc) pe tipuri non-volumetrice
  - maparea pe categorie deviz + pastrarea GlobalId
  - degradare gratioasa cand fisierul lipseste
"""
import os
import tempfile

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")
from ifcopenshell.api import run as ifc_run  # noqa: E402


def _build_ifc():
    f = ifcopenshell.file(schema="IFC4")
    ifc_run("root.create_entity", f, ifc_class="IfcProject", name="P")

    wall = ifc_run("root.create_entity", f, ifc_class="IfcWall", name="W1")
    q = ifc_run("pset.add_qto", f, product=wall, name="Qto_WallBaseQuantities")
    ifc_run("pset.edit_qto", f, qto=q, properties={"NetVolume": 2.5})
    ls = ifc_run("material.add_material_set", f, name="LS", set_type="IfcMaterialLayerSet")
    for nm, th in (("Beton", 0.2), ("Vata", 0.1)):
        m = ifc_run("material.add_material", f, name=nm)
        lay = ifc_run("material.add_layer", f, layer_set=ls, material=m)
        ifc_run("material.edit_layer", f, layer=lay, attributes={"LayerThickness": th})
    ifc_run("material.assign_material", f, products=[wall], material=ls)

    slab = ifc_run("root.create_entity", f, ifc_class="IfcSlab", name="S1")
    qs = ifc_run("pset.add_qto", f, product=slab, name="Qto_SlabBaseQuantities")
    ifc_run("pset.edit_qto", f, qto=qs, properties={"NetVolume": 5.0})

    col = ifc_run("root.create_entity", f, ifc_class="IfcColumn", name="C1")
    door = ifc_run("root.create_entity", f, ifc_class="IfcDoor", name="D1")

    path = tempfile.mktemp(suffix=".ifc")
    f.write(path)
    gids = {"wall": wall.GlobalId, "slab": slab.GlobalId,
            "column": col.GlobalId, "door": door.GlobalId}
    return path, gids


def test_harvest_model_complet(app):
    from models import db, ElementBIM, ModelBIM
    from services.ifc_qto_harvest import harvest_model, ciorna_review

    path, gids = _build_ifc()
    try:
        with app.app_context():
            model = ModelBIM(nume="Test IFC", tip="ifc", fisier_path=path)
            db.session.add(model)
            db.session.flush()
            for tip, gid in gids.items():
                db.session.add(ElementBIM(cod=tip.upper() + "-1", tip_element=tip,
                                          ifc_global_id=gid, source_system='ifc'))
            db.session.commit()

            r = harvest_model(model, root_path='')
            assert r['ok'], r
            assert r['stat']['elemente'] == 4

            els = {e.tip_element: e for e in ElementBIM.query
                   .filter(ElementBIM.ifc_global_id.in_(list(gids.values()))).all()}

            # perete: cantitate din Qto + flag multistrat (double-count)
            w = els['wall']
            assert float(w.cantitate) == 2.5 and w.unitate_masura == 'mc'
            assert w.qto_sursa == 'ifc_basequantity' and w.qto_set == 'Qto_WallBaseQuantities'
            assert w.necesita_verificare and 'multistrat' in (w.motiv_verificare or '')
            assert w.cod_deviz == 'zidarie'
            assert w.ifc_global_id == gids['wall']    # GlobalId = trasabilitate

            # placa: cantitate, fara flag
            sl = els['slab']
            assert float(sl.cantitate) == 5.0 and sl.qto_sursa == 'ifc_basequantity'
            assert not sl.necesita_verificare and sl.cod_deviz == 'beton'

            # stalp: fara Qto -> lipsa + flag, NU recalcul geometric
            co = els['column']
            assert co.qto_sursa == 'lipsa' and co.necesita_verificare
            assert co.cod_deviz == 'beton'

            # usa: count (buc), fara flag
            do = els['door']
            assert do.qto_sursa == 'count' and do.unitate_masura == 'buc'
            assert not do.necesita_verificare and do.cod_deviz == 'tamplarie'

            # ciorna review
            rev = ciorna_review(model.id)
            assert rev['nr_elemente'] == 4
            assert rev['stat']['de_verificat'] >= 2   # wall + column
            assert any(d['global_id'] == gids['column'] for d in rev['de_verificat'])
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_harvest_fisier_lipsa(app):
    from models import db, ModelBIM
    from services.ifc_qto_harvest import harvest_model
    with app.app_context():
        m = ModelBIM(nume="X", tip="ifc", fisier_path="/nu/exista.ifc")
        db.session.add(m)
        db.session.flush()
        r = harvest_model(m, root_path='')
        assert r['ok'] is False and 'inexistent' in r['motiv']
