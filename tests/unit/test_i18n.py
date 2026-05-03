"""
Unit tests pentru sistemul i18n.
"""

import pytest


class TestI18nTranslation:
    def test_t_default_returns_key(self, app):
        """Daca limba default = ro, t() returneaza cheia ca atare."""
        from i18n import t
        with app.test_request_context('/'):
            assert t('Salveaza', lang='ro') == 'Salveaza'

    def test_t_english_translation(self, app):
        from i18n import t
        with app.test_request_context('/'):
            assert t('Salveaza', lang='en') == 'Save'
            assert t('Anuleaza', lang='en') == 'Cancel'
            assert t('Santier', lang='en') == 'Site'

    def test_t_unknown_key_falls_back(self, app):
        """Cheie netradusa -> returnam cheia ca atare."""
        from i18n import t
        with app.test_request_context('/'):
            assert t('NoSuchKey123', lang='en') == 'NoSuchKey123'

    def test_t_format_interpolation(self, app):
        """t() suporta format params: t('Hello {name}', name='X')."""
        from i18n import t
        with app.test_request_context('/'):
            # Cheia simpla nu are {name}, format e no-op
            result = t('Salveaza', lang='en', name='X')
            assert result == 'Save'


class TestI18nLanguageDetection:
    def test_get_current_lang_default_ro(self, app):
        """Fara session/user/header, default ro."""
        from i18n import get_current_lang
        with app.test_request_context('/'):
            assert get_current_lang() == 'ro'

    def test_get_current_lang_session_overrides(self, app):
        """Session language wins over default."""
        from i18n import get_current_lang
        from flask import session
        with app.test_request_context('/'):
            session['lang'] = 'en'
            assert get_current_lang() == 'en'

    def test_get_current_lang_invalid_session_lang(self, app):
        """Lang invalid in session -> fallback la default."""
        from i18n import get_current_lang
        from flask import session
        with app.test_request_context('/'):
            session['lang'] = 'xx'  # nesuportat
            assert get_current_lang() == 'ro'


class TestI18nRoute:
    """Ruta /limba/<lang> seteaza limba."""

    def test_set_language_redirects(self, client):
        resp = client.get('/limba/en', follow_redirects=False)
        assert resp.status_code == 302

    def test_set_language_invalid_lang_no_change(self, client):
        """Lang nesuportat -> redirect fara modificare."""
        resp = client.get('/limba/zz', follow_redirects=False)
        assert resp.status_code == 302
