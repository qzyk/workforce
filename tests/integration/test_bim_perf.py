"""Teste Tema C (performanta): paginare lista elemente + QTO geometric (plumbing)."""


def test_elemente_paginare(authenticated_client, app):
    """Lista de elemente pagineaza (nu mai taie la limit(200))."""
    from models import db, ElementBIM
    with app.app_context():
        db.session.add_all([
            ElementBIM(cod=f'P{i:03d}', tip_element='slab', ifc_global_id=f'GP{i}')
            for i in range(105)
        ])
        db.session.commit()
    # pagina 1: pager prezent (link spre page=2)
    r = authenticated_client.get('/bim/elemente')
    assert r.status_code == 200
    assert b'105 elemente' in r.data           # totalul afisat
    assert b'page=2' in r.data                 # exista pagina urmatoare
    # pagina 2 se incarca
    r2 = authenticated_client.get('/bim/elemente?page=2')
    assert r2.status_code == 200
    # filtrele se pastreaza in linkurile de paginare
    r3 = authenticated_client.get('/bim/elemente?tip=slab')
    assert r3.status_code == 200 and b'tip=slab' in r3.data


def test_qto_geometric_plumbing(app):
    """qto_din_ifc accepta geometric=True si nu crapa pe cale invalida."""
    from services.ifc_qto import qto_din_ifc, VOLUMETRIC_TIPURI
    assert qto_din_ifc('/nu/exista.ifc', geometric=True) == []
    # tipurile volumetrice (mc) includ betonul, NU armatura/echipamentele
    assert 'slab' in VOLUMETRIC_TIPURI and 'beam' in VOLUMETRIC_TIPURI
    assert 'rebar' not in VOLUMETRIC_TIPURI and 'duct' not in VOLUMETRIC_TIPURI


def test_ruta_qto_geometric(authenticated_client, app):
    """Ruta QTO accepta ?geometric=1 (fallback la count cand modelul n-are fisier)."""
    from models import db, ModelBIM, ElementBIM
    with app.app_context():
        m = ModelBIM(nume='M-GEOM')
        db.session.add(m); db.session.flush()
        db.session.add(ElementBIM(cod='SG1', tip_element='slab',
                                  model_bim_id=m.id, ifc_global_id='GG1'))
        db.session.commit()
        mid = m.id
    r = authenticated_client.get(f'/bim/model/{mid}/qto?geometric=1')
    assert r.status_code == 200 and b'Antemasuratoare' in r.data
    rc = authenticated_client.get(f'/bim/model/{mid}/qto.csv?geometric=1')
    assert rc.status_code == 200 and b'cod_articol' in rc.data
