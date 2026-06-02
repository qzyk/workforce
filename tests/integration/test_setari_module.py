"""Test pentru pagina de module/functii (feature flags din UI)."""


def test_module_lista_si_toggle(authenticated_client, app):
    r = authenticated_client.get('/setari/module')
    assert r.status_code == 200
    assert b'Module si functii' in r.data
    assert b'planificare-gantt' in r.data and b'bim-viewer-3d' in r.data

    # toggle: planificare-gantt e OFF implicit -> dupa toggle apare rand activ
    rt = authenticated_client.post('/setari/module/toggle', data={'key': 'planificare-gantt'})
    assert rt.status_code == 302
    from models import FeatureFlag
    with app.app_context():
        f = FeatureFlag.query.filter_by(key='planificare-gantt').first()
        assert f is not None and f.enabled is True
