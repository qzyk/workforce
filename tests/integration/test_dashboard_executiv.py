"""Test pentru dashboard-ul executiv cross-modul."""


def test_dashboard_executiv_se_incarca(authenticated_client):
    r = authenticated_client.get('/dashboard/executiv')
    assert r.status_code == 200
    assert b'Dashboard executiv' in r.data
    assert b'Portofoliu proiecte' in r.data
    assert b'Elemente BIM' in r.data
