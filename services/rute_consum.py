"""
Calculator consum combustibil pe ruta (Mapbox Directions API, server-side).

Flux:
  - Primesc punctele A -> B -> (C, D) ca lista de (lng, lat).
  - calculeaza_distanta() -> distanta reala pe sosea (km) via Mapbox Directions.
  - calcul_consum(consum_mediu, km) -> litri = consum_mediu x km / 100.

Token: refoloseste aceeasi strategie ca geocoding (secret -> public -> None).
Graceful: nu arunca exceptii pe erori de retea, doar log + None.

NU este apelat din template-uri. Doar din routes/masini.py.
Doc: https://docs.mapbox.com/api/navigation/directions/
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence

_logger = logging.getLogger(__name__)

# {coords} = "lng,lat;lng,lat[;lng,lat...]" (max 25 puncte la Directions; noi 2..4)
MAPBOX_DIRECTIONS_URL = 'https://api.mapbox.com/directions/v5/mapbox/driving/{coords}'
REQUEST_TIMEOUT_SEC = 8
MAX_WAYPOINTS = 4


def _get_token() -> Optional[str]:
    """Token Mapbox (secret preferential, public ca fallback - merge la Directions)."""
    secret = os.environ.get('MAPBOX_SECRET_TOKEN', '').strip()
    if secret:
        return secret
    public = os.environ.get('MAPBOX_PUBLIC_TOKEN', '').strip()
    if public:
        return public
    return None


def is_configured() -> bool:
    """True daca cel putin un token Mapbox e setat."""
    return _get_token() is not None


def calculeaza_distanta(
    waypoints: Sequence[Sequence[float]],
) -> Optional[dict]:
    """
    Calculeaza distanta reala pe sosea pentru o ruta A -> B -> (C, D).

    Args:
        waypoints: lista de (lng, lat), 2..4 puncte, in ordinea parcurgerii.

    Returns:
        dict {'distanta_km': float, 'durata_min': float, 'legs': int}
        sau None daca: token lipsa, < 2 puncte, request esuat, fara ruta.
    """
    token = _get_token()
    if not token:
        _logger.warning('Mapbox token nu e configurat - calcul ruta skip')
        return None

    pts = []
    for w in waypoints:
        try:
            lng = float(w[0])
            lat = float(w[1])
        except (TypeError, ValueError, IndexError):
            continue
        pts.append((lng, lat))
    if len(pts) < 2:
        return None
    pts = pts[:MAX_WAYPOINTS]

    coords = ';'.join(f'{lng},{lat}' for lng, lat in pts)
    url = MAPBOX_DIRECTIONS_URL.format(coords=urllib.parse.quote(coords, safe=';,'))
    params = {
        'access_token': token,
        'overview': 'false',     # nu avem nevoie de geometria detaliata server-side
        'alternatives': 'false',
        'steps': 'false',
    }
    full_url = f'{url}?{urllib.parse.urlencode(params)}'

    try:
        req = urllib.request.Request(full_url, headers={'User-Agent': 'Edifico/1.0'})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
            if resp.status != 200:
                _logger.warning('Directions HTTP %s', resp.status)
                return None
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.URLError as e:
        _logger.warning('Directions request a esuat: %s', e)
        return None
    except (ValueError, KeyError) as e:
        _logger.warning('Directions response invalid: %s', e)
        return None

    if data.get('code') != 'Ok':
        _logger.warning('Directions code != Ok: %s', data.get('code'))
        return None
    routes = data.get('routes') or []
    if not routes:
        return None

    route = routes[0]
    distanta_m = float(route.get('distance') or 0.0)
    durata_s = float(route.get('duration') or 0.0)
    return {
        'distanta_km': round(distanta_m / 1000.0, 2),
        'durata_min': round(durata_s / 60.0, 1),
        'legs': len(route.get('legs') or []),
    }


def calcul_consum(consum_mediu, distanta_km) -> Optional[Decimal]:
    """
    litri = consum_mediu (L/100km) x distanta_km / 100.

    Returneaza Decimal cu 2 zecimale sau None daca date invalide.
    """
    if consum_mediu is None or distanta_km is None:
        return None
    try:
        cm = Decimal(str(consum_mediu))
        km = Decimal(str(distanta_km))
    except (TypeError, ValueError, ArithmeticError):
        return None
    if cm <= 0 or km < 0:
        return None
    litri = (cm * km / Decimal('100'))
    return litri.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
