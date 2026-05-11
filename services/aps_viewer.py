"""
Adapter pentru Autodesk Platform Services (APS, fost Forge).

Faza 2 BIM: stub minimal cu interfata + detectie config. Implementarea reala
(upload bucket, translation job, viewer URL) vine cand activam flag-ul
'bim-aps-adapter' si avem credentiale APS.

Setup pentru activare:
    Variabile de mediu (sau in WSGI config pe PythonAnywhere):
      APS_CLIENT_ID=<your_client_id>
      APS_CLIENT_SECRET=<your_client_secret>
      APS_BUCKET_KEY=<bucket_name_unique>   # optional, default = edifico-bim-bucket

API:
    is_configured() -> bool        # avem credentiale + flag activ
    get_viewer_url(model) -> str?  # URL Forge Viewer pentru un ModelBIM (None = fallback xeokit)
    get_translation_status(...) -> ...  # in viitor

Toate functiile care fac retea sunt RATE-LIMITED si CACHED (token APS dureaza 1h).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from services import feature_flags

_logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

def _client_id() -> Optional[str]:
    return os.environ.get('APS_CLIENT_ID') or None


def _client_secret() -> Optional[str]:
    return os.environ.get('APS_CLIENT_SECRET') or None


def _bucket_key() -> str:
    return os.environ.get('APS_BUCKET_KEY', 'edifico-bim-bucket')


def has_credentials() -> bool:
    """True daca env vars APS_CLIENT_ID + APS_CLIENT_SECRET sunt setate."""
    return bool(_client_id() and _client_secret())


def is_configured() -> bool:
    """
    True daca:
    - feature flag 'bim-aps-adapter' e activ (per tenant sau global), SI
    - credentialele APS sunt setate.
    """
    return feature_flags.is_enabled('bim-aps-adapter') and has_credentials()


# ============================================================
# VIEWER URL (high-level API folosit de routes/bim.py)
# ============================================================

def get_viewer_url(model) -> Optional[str]:
    """
    Returneaza URL-ul Autodesk Forge Viewer pentru modelul dat.

    Pentru moment STUB: returneaza None daca:
    - APS nu e configurat
    - Modelul nu are URN APS asociat (camp 'extern_id' cu source_system='autodesk')

    Cand implementarea reala e gata, va:
    1. verifica daca exista deja URN tradus pentru model in ExternalMapping
    2. daca da, returneaza URL-ul Forge Viewer
    3. daca nu, intoarce None (caller-ul fallback la xeokit)
    """
    if not is_configured():
        return None

    # Modelul are URN APS deja inregistrat?
    urn = _get_aps_urn_for_model(model)
    if not urn:
        return None

    # URL-ul standard Autodesk Viewer (publicat pe viewer.autodesk.com)
    # Necesita ca utilizatorul sa fie autentificat APS in browser sau ca
    # modelul sa fie public. Pentru flow privat, viitorul cod va emite
    # un signed URL via APS Data API.
    return f'https://viewer.autodesk.com/?urn={urn}'


def _get_aps_urn_for_model(model) -> Optional[str]:
    """
    Cauta URN APS pentru un ModelBIM in ExternalMapping (source_system='autodesk').
    Sau direct in model.extern_id daca model.source_system='autodesk'.
    """
    if not model:
        return None

    # Caz 1: extern_id direct pe model
    if getattr(model, 'source_system', None) == 'autodesk' and getattr(model, 'extern_id', None):
        return model.extern_id

    # Caz 2: cautare in ExternalMapping
    try:
        from models import ExternalMapping
        mapping = ExternalMapping.query.filter_by(
            entity_type='model_bim',
            entity_id=model.id,
            source_system='autodesk',
        ).first()
        if mapping and mapping.extern_id:
            return mapping.extern_id
    except Exception as e:
        _logger.debug('aps_viewer: lookup ExternalMapping a esuat: %s', e)

    return None


# ============================================================
# DIAGNOSTIC (pentru pagina /setari sau debug)
# ============================================================

def status_summary() -> dict:
    """
    Snapshot al statusului APS. Folosit in UI admin pentru a arata
    daca integrarea e gata sau ce lipseste.
    """
    return {
        'has_credentials': has_credentials(),
        'flag_enabled': feature_flags.is_enabled('bim-aps-adapter'),
        'is_configured': is_configured(),
        'bucket_key': _bucket_key() if has_credentials() else None,
        'client_id_preview': (_client_id()[:6] + '...') if _client_id() else None,
    }
