"""
Mapbox Geocoding API wrapper (server-side, foloseste secret token).

Doc: https://docs.mapbox.com/api/search/geocoding/

Strategie:
  - Citeste MAPBOX_SECRET_TOKEN din env (sau MAPBOX_PUBLIC_TOKEN ca fallback,
    pentru endpoint-uri publice gratuite).
  - geocodeaza_adresa() returneaza dict {lat, lng, normalized_address,
    judet, localitate} sau None.
  - Graceful: nu arunca exceptii, doar log + None pe orice eroare.
  - Bias RO (country=ro) pentru rezultate locale relevante.

NU este apelat din template-uri. Doar din routes/locatii.py.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional


_logger = logging.getLogger(__name__)

MAPBOX_GEOCODING_URL = 'https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json'
REQUEST_TIMEOUT_SEC = 5


def _get_token() -> Optional[str]:
    """Returneaza tokenul Mapbox (preferential secret pentru geocoding)."""
    secret = os.environ.get('MAPBOX_SECRET_TOKEN', '').strip()
    if secret:
        return secret
    # Fallback la public token - functioneaza pentru geocoding public free tier
    public = os.environ.get('MAPBOX_PUBLIC_TOKEN', '').strip()
    if public:
        _logger.info('MAPBOX_SECRET_TOKEN nu e setat - folosesc MAPBOX_PUBLIC_TOKEN')
        return public
    return None


def is_configured() -> bool:
    """True daca cel putin un token Mapbox e setat."""
    return _get_token() is not None


def geocodeaza_adresa(
    adresa: str,
    judet: Optional[str] = None,
    localitate: Optional[str] = None,
    country: str = 'ro',
) -> Optional[dict]:
    """
    Geocodeaza o adresa text -> dict cu coordonate + componente.

    Args:
        adresa: text liber, ex: "Strada Stefan cel Mare 15"
        judet: optional, pentru bias geografic
        localitate: optional, pentru bias geografic
        country: country code ISO 3166-1 alpha-2 (default 'ro')

    Returns:
        dict {
            'lat': float, 'lng': float,
            'normalized_address': str,
            'judet': str | None,
            'localitate': str | None,
            'place_name': str,
        }
        sau None daca:
        - tokenul nu e configurat
        - request-ul esueaza (network, rate limit, etc.)
        - niciun rezultat
    """
    token = _get_token()
    if not token:
        _logger.warning('Mapbox token nu e configurat - geocoding skip')
        return None
    if not adresa or not adresa.strip():
        return None

    # Construim query string combinand adresa cu localitate + judet pentru bias
    parts = [adresa.strip()]
    if localitate:
        parts.append(localitate.strip())
    if judet:
        parts.append(judet.strip())
    query = ', '.join(parts)

    url = MAPBOX_GEOCODING_URL.format(query=urllib.parse.quote(query))
    params = {
        'access_token': token,
        'country': country,
        'limit': '1',
        'language': 'ro',
    }
    full_url = f'{url}?{urllib.parse.urlencode(params)}'

    try:
        req = urllib.request.Request(full_url, headers={'User-Agent': 'Edifico/1.0'})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
            if resp.status != 200:
                _logger.warning('Geocoding HTTP %s', resp.status)
                return None
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.URLError as e:
        _logger.warning('Geocoding request a esuat: %s', e)
        return None
    except (ValueError, KeyError) as e:
        _logger.warning('Geocoding response invalid: %s', e)
        return None

    features = data.get('features') or []
    if not features:
        return None

    f = features[0]
    geom = f.get('geometry') or {}
    coords = geom.get('coordinates') or []
    if len(coords) < 2:
        return None

    lng = float(coords[0])
    lat = float(coords[1])

    # Extragere componente din context (judet = "region", localitate = "place")
    judet_extras = None
    localitate_extras = None
    for ctx in f.get('context') or []:
        ctx_id = ctx.get('id', '')
        if ctx_id.startswith('region.'):
            judet_extras = ctx.get('text')
        elif ctx_id.startswith('place.'):
            localitate_extras = ctx.get('text')

    return {
        'lat': lat,
        'lng': lng,
        'normalized_address': f.get('place_name') or '',
        'place_name': f.get('place_name') or '',
        'judet': judet_extras,
        'localitate': localitate_extras,
    }
