"""
Integration tests pentru pagina publica de prezentare /home + redirect root.
"""


class TestMarketingHome:
    def test_home_public_200(self, client):
        """/home e public (fara login) si randeaza pagina."""
        r = client.get('/home')
        assert r.status_code == 200
        # Hero h1 (prefix ASCII-safe din "O platforma, toate santierele tale")
        assert b'O platform' in r.data
        assert b'Edifico' in r.data

    def test_home_are_sectiunile_cheie(self, client):
        r = client.get('/home')
        body = r.data
        assert b'hero-video.mp4' in body          # hero video
        assert b'marketing/marketing.css' in body  # CSS din static
        assert b'navbar__logo' in body             # navbar
        assert b'faq__item' in body                # FAQ
        assert b'footer__columns' in body          # footer

    def test_home_link_login_wired(self, client):
        """Butoanele Conectare/Incercare duc la /auth/login."""
        r = client.get('/home')
        assert b'/auth/login' in r.data

    def test_home_static_css_served(self, client):
        r = client.get('/static/marketing/marketing.css')
        assert r.status_code == 200

    def test_home_static_image_served(self, client):
        r = client.get('/static/marketing/assets/photo-team-review.jpg')
        assert r.status_code == 200
        assert r.data[:3] == b'\xff\xd8\xff'  # semnatura JPEG


class TestRootRedirect:
    def test_anonim_root_redirect_la_home(self, client):
        r = client.get('/', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert r.headers['Location'].endswith('/home')

    def test_anonim_dashboard_redirect_la_home(self, client):
        r = client.get('/dashboard', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert r.headers['Location'].endswith('/home')

    def test_autentificat_root_vede_dashboard(self, authenticated_client):
        """Utilizatorul logat NU e redirectionat la /home - vede dashboard-ul."""
        r = authenticated_client.get('/', follow_redirects=False)
        assert r.status_code == 200
        # nu e redirect catre /home
        assert b'O platform' not in r.data
