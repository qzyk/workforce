"""Teste pentru QTO (antemasuratoare din model BIM)."""


def test_qto_din_elemente(app):
    from models import db, ElementBIM
    from services.ifc_qto import qto_din_elemente
    with app.app_context():
        els = [
            ElementBIM(cod='S1', tip_element='slab', cantitate=10, unitate_masura='mc'),
            ElementBIM(cod='S2', tip_element='slab', cantitate=5, unitate_masura='mc'),
            ElementBIM(cod='B1', tip_element='beam'),   # fara cantitate -> count
        ]
        db.session.add_all(els)
        db.session.commit()
        by = {r['tip']: r for r in qto_din_elemente(els)}
        assert by['slab']['cantitate'] == 15.0 and by['slab']['um'] == 'mc' and by['slab']['nr'] == 2
        assert by['beam']['cantitate'] == 1 and by['beam']['um'] == 'buc' and by['beam']['nr'] == 1


def test_ruta_qto_si_csv(authenticated_client, app):
    from models import db, ModelBIM, ElementBIM
    with app.app_context():
        m = ModelBIM(nume='M-QTO')
        db.session.add(m); db.session.flush()
        db.session.add_all([
            ElementBIM(cod='S1', tip_element='slab', model_bim_id=m.id, ifc_global_id='G1'),
            ElementBIM(cod='C1', tip_element='column', model_bim_id=m.id, ifc_global_id='G2'),
        ])
        db.session.commit()
        mid = m.id
    r = authenticated_client.get(f'/bim/model/{mid}/qto')
    assert r.status_code == 200 and b'Antemasuratoare' in r.data
    rc = authenticated_client.get(f'/bim/model/{mid}/qto.csv')
    assert rc.status_code == 200 and b'cod_articol' in rc.data
