"""
Teste unit pentru services/rute_consum.py (calculator consum combustibil).
Reteaua Mapbox e mock-uita (monkeypatch urlopen) - nu se face request real.
"""

import json
from decimal import Decimal

import pytest

from services import rute_consum


class TestCalculConsum:
    def test_basic(self):
        # 7.5 L/100km x 42.31 km / 100 = 3.17325 -> 3.17
        assert rute_consum.calcul_consum(7.5, 42.31) == Decimal('3.17')

    def test_round_half_up(self):
        # 6 x 12.75 / 100 = 0.765 -> half-up -> 0.77
        assert rute_consum.calcul_consum(6, 12.75) == Decimal('0.77')

    def test_decimal_inputs(self):
        assert rute_consum.calcul_consum(Decimal('6.00'), Decimal('100')) == Decimal('6.00')

    def test_none_inputs(self):
        assert rute_consum.calcul_consum(None, 50) is None
        assert rute_consum.calcul_consum(7.5, None) is None

    def test_zero_or_negative(self):
        assert rute_consum.calcul_consum(0, 50) is None
        assert rute_consum.calcul_consum(-5, 50) is None
        assert rute_consum.calcul_consum(7.5, -10) is None


class TestIsConfigured:
    def test_no_token(self, monkeypatch):
        monkeypatch.delenv('MAPBOX_SECRET_TOKEN', raising=False)
        monkeypatch.delenv('MAPBOX_PUBLIC_TOKEN', raising=False)
        assert rute_consum.is_configured() is False

    def test_public_token(self, monkeypatch):
        monkeypatch.delenv('MAPBOX_SECRET_TOKEN', raising=False)
        monkeypatch.setenv('MAPBOX_PUBLIC_TOKEN', 'pk.test')
        assert rute_consum.is_configured() is True

    def test_secret_preferred(self, monkeypatch):
        monkeypatch.setenv('MAPBOX_SECRET_TOKEN', 'sk.secret')
        monkeypatch.setenv('MAPBOX_PUBLIC_TOKEN', 'pk.public')
        assert rute_consum._get_token() == 'sk.secret'


def _fake_urlopen(payload, status=200):
    class FakeResp:
        def __init__(self):
            self.status = status
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return json.dumps(payload).encode('utf-8')
    def _open(req, timeout=None):
        return FakeResp()
    return _open


class TestCalculeazaDistanta:
    def test_no_token(self, monkeypatch):
        monkeypatch.delenv('MAPBOX_SECRET_TOKEN', raising=False)
        monkeypatch.delenv('MAPBOX_PUBLIC_TOKEN', raising=False)
        assert rute_consum.calculeaza_distanta([(23.6, 46.77), (23.79, 46.57)]) is None

    def test_under_two_points(self, monkeypatch):
        monkeypatch.setenv('MAPBOX_PUBLIC_TOKEN', 'pk.test')
        assert rute_consum.calculeaza_distanta([(23.6, 46.77)]) is None

    def test_ok(self, monkeypatch):
        monkeypatch.setenv('MAPBOX_PUBLIC_TOKEN', 'pk.test')
        payload = {'code': 'Ok', 'routes': [{'distance': 42310.0, 'duration': 3660.0, 'legs': [{}, {}]}]}
        monkeypatch.setattr(rute_consum.urllib.request, 'urlopen', _fake_urlopen(payload))
        r = rute_consum.calculeaza_distanta([(23.59, 46.77), (23.79, 46.57), (23.88, 46.54)])
        assert r['distanta_km'] == 42.31
        assert r['durata_min'] == 61.0
        assert r['legs'] == 2

    def test_code_not_ok(self, monkeypatch):
        monkeypatch.setenv('MAPBOX_PUBLIC_TOKEN', 'pk.test')
        monkeypatch.setattr(rute_consum.urllib.request, 'urlopen',
                            _fake_urlopen({'code': 'NoRoute', 'routes': []}))
        assert rute_consum.calculeaza_distanta([(23.6, 46.77), (23.79, 46.57)]) is None

    def test_max_4_waypoints(self, monkeypatch):
        """Trimite 5 puncte; functia trunchiaza la 4 (nu crapa)."""
        monkeypatch.setenv('MAPBOX_PUBLIC_TOKEN', 'pk.test')
        payload = {'code': 'Ok', 'routes': [{'distance': 1000.0, 'duration': 120.0, 'legs': [{}, {}, {}]}]}
        monkeypatch.setattr(rute_consum.urllib.request, 'urlopen', _fake_urlopen(payload))
        r = rute_consum.calculeaza_distanta([(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)])
        assert r is not None
        assert r['distanta_km'] == 1.0
