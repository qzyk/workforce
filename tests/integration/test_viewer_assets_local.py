"""
Integration tests pentru asset-urile viewer vendorizate local (Faza bim-1).

Self-host xeokit-sdk@2.6.78 + web-ifc@0.0.50 in static/lib/. Verificam ca
fisierele exista pe disc si ca Flask le serveste prin /static/lib/*.

Daca vendorizarea NU s-a facut (download blocat la deploy), aceste teste se
SKIP elegant - pinul CDN ramane castigul sigur, iar viewerii fac fallback.
"""

import os
import pytest


LIB_FILES = [
    'lib/xeokit-sdk@2.6.78/xeokit-sdk.es.min.js',
    'lib/web-ifc@0.0.50/web-ifc-api.js',
    'lib/web-ifc@0.0.50/web-ifc.wasm',
    'lib/web-ifc@0.0.50/web-ifc-mt.wasm',
]


def _static_dir(app):
    return os.path.join(app.root_path, 'static')


def _lib_present(app):
    base = _static_dir(app)
    return all(os.path.exists(os.path.join(base, f)) for f in LIB_FILES)


def test_fisiere_lib_exista_pe_disc(app):
    if not _lib_present(app):
        pytest.skip('static/lib nevendorizat (download CDN indisponibil la build)')
    base = _static_dir(app)
    for f in LIB_FILES:
        path = os.path.join(base, f)
        assert os.path.exists(path), f'lipseste {f}'
        # Sanity: fisierele cheie sunt binare mari (>1MB), nu pagini HTML de eroare 404.
        size = os.path.getsize(path)
        assert size > 1_000_000, f'{f} prea mic ({size} bytes) - download probabil esuat'


def test_flask_serveste_xeokit_sdk(client, app):
    if not _lib_present(app):
        pytest.skip('static/lib nevendorizat')
    resp = client.get('/static/lib/xeokit-sdk@2.6.78/xeokit-sdk.es.min.js')
    assert resp.status_code == 200
    body = resp.get_data()
    assert b'export' in body  # ESM bundle real


def test_flask_serveste_web_ifc_wasm(client, app):
    if not _lib_present(app):
        pytest.skip('static/lib nevendorizat')
    resp = client.get('/static/lib/web-ifc@0.0.50/web-ifc.wasm')
    assert resp.status_code == 200
    # Magic bytes WASM: \0asm
    assert resp.get_data()[:4] == b'\x00asm'
