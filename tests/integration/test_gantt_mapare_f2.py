"""Teste Faza 2 (F2): taxonomie unica - mapare categorie Gantt -> categorie_lucrare deviz."""


def _curata_mapari(app):
    from models import db, GanttClasificareRegula
    with app.app_context():
        GanttClasificareRegula.query.filter_by(tip_regula='mapare_categorie').delete()
        db.session.commit()


def test_mapare_si_fallback(app):
    """JSON: SAPATURA->terasamente; fara echivalent -> lowercase; None->None."""
    from services.gantt import store
    with app.app_context():
        m = store.mapare_categorii()
        assert m['SAPATURA'] == 'terasamente' and m['ARMATURI'] == 'armatura'
        assert store.la_categorie_lucrare('SAPATURA', m) == 'terasamente'
        assert store.la_categorie_lucrare('DEMONTARI', m) == 'demontari'   # fallback
        assert store.la_categorie_lucrare(None, m) is None


def test_pipeline_seteaza_categorie_lucrare(app):
    """Activitatea poarta categorie_lucrare canonica + rollup F2 in statistici."""
    from services.gantt.pipeline import MotorPlanificare
    from services.gantt.modele import ArticolF3
    with app.app_context():
        arts = [ArticolF3('TS01', 'Sapatura mecanizata pamant', um='mc', cantitate=100)]
        rez = MotorPlanificare().proceseaza(arts, clasifica=True)
    a = rez.activitati[0]
    assert a.categorie_tehnologica == 'SAPATURA' and a.categorie_lucrare == 'terasamente'
    assert 'terasamente' in rez.statistici['cost_per_categorie_lucrare']


def test_centralizator_f2_in_statistici(app):
    """Centralizatorul F2: cost pe categorie de lucrare, descompus pe resurse."""
    from services.gantt.pipeline import MotorPlanificare
    from services.gantt.modele import ArticolF3
    with app.app_context():
        arts = [ArticolF3('TS01', 'Sapatura mecanizata pamant', um='mc', cantitate=100),
                ArticolF3('AR01', 'Montaj armatura BST500', um='kg', cantitate=200)]
        rez = MotorPlanificare().proceseaza(arts, clasifica=True)
    cf2 = rez.statistici['centralizator_f2']
    assert isinstance(cf2, list) and cf2
    for r in cf2:
        assert {'categorie', 'nr', 'material', 'manopera', 'utilaj', 'total'} <= set(r)
        # estimat -> material+manopera+utilaj insumeaza totalul (split exact)
        assert abs((r['material'] + r['manopera'] + r['utilaj']) - r['total']) < 1.0


def test_export_f2_csv(authenticated_client):
    """Upload F3 -> descarca centralizatorul F2 (CSV) pe token-ul din sesiune."""
    from io import BytesIO
    csv = (b"cod_articol;denumire;um;cantitate;obiect;tronson\n"
           b"TS01;Sapatura mecanizata;mc;100;O;T\n")
    authenticated_client.post('/gantt/genereaza',
                              data={'fisier': (BytesIO(csv), 'f.csv')},
                              content_type='multipart/form-data', follow_redirects=True)
    with authenticated_client.session_transaction() as sess:
        token = sess.get('gantt_token')
    assert token
    r = authenticated_client.get(f'/gantt/export-f2/{token}')
    assert r.status_code == 200
    assert b'Categorie lucrare' in r.data and b'TOTAL' in r.data


def test_mapare_db_suprascrie_json(app):
    """O regula in DB (tip mapare_categorie) suprascrie maparea din JSON."""
    from services.gantt import store
    try:
        with app.app_context():
            assert store.mapare_categorii()['SAPATURA'] == 'terasamente'   # implicit JSON
            row, err = store.adauga_regula('terasamente_drum', 'mapare_categorie', 'SAPATURA')
            assert err is None and row is not None
            assert store.mapare_categorii()['SAPATURA'] == 'terasamente_drum'  # DB castiga
    finally:
        _curata_mapari(app)


def test_config_mapare_ui(authenticated_client, app):
    """Pagina config arata sectiunea F2; POST adauga override; stergerea il scoate."""
    from models import GanttClasificareRegula
    try:
        r = authenticated_client.get('/gantt/config')
        assert r.status_code == 200
        assert b'Mapare categorii' in r.data and b'terasamente' in r.data

        authenticated_client.post('/gantt/config/mapare', data={
            'categorie_gantt': 'SAPATURA', 'categorie_lucrare': 'terasamente_drum',
        }, follow_redirects=True)
        with app.app_context():
            row = GanttClasificareRegula.query.filter_by(
                tip_regula='mapare_categorie', valoare='SAPATURA').first()
            assert row is not None and row.categorie == 'terasamente_drum'
            rid = row.id

        authenticated_client.post(f'/gantt/config/regula/{rid}/sterge', follow_redirects=True)
        with app.app_context():
            assert GanttClasificareRegula.query.filter_by(id=rid).first() is None
    finally:
        _curata_mapari(app)
