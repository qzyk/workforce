"""
Test pentru endpoint-ul /healthz (Faza 3): public, confirma app + DB.
"""


class TestHealthz:
    def test_healthz_ok_public(self, client):
        """Fara login, /healthz raspunde 200 cu status ok + db ok."""
        r = client.get('/healthz')
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'ok'
        assert j['db'] == 'ok'
