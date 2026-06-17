"""
Serviciu pentru feature flags.

Permite activarea progresiva a feature-urilor BIM (Fazele 2-8) per tenant
sau global, fara redeploy. Default: orice flag necunoscut e DEZACTIVAT.

Reguli de evaluare (in ordine):
1. Daca exista un flag cu key=K si tenant_id=current_tenant -> foloseste valoarea lui.
2. Altfel, daca exista un flag cu key=K si tenant_id=NULL (global) -> foloseste-o.
3. Altfel: False (default explicit).

Cache pe request (g.feature_flags_cache) pentru a evita query-uri multiple.

Folosire:
    from services.feature_flags import is_enabled

    if is_enabled('bim-viewer-3d'):
        ...

Pentru context Jinja: 'feature_enabled' e disponibil ca filter/global
(setat in app.py via init_app daca dorim).
"""

from __future__ import annotations

import logging
from typing import Optional

from models import db, FeatureFlag


_logger = logging.getLogger(__name__)


# Catalog cu flag-urile cunoscute - util pentru documentare si UI admin.
# Cheile NU se valideaza la apelarea is_enabled(); orice cheie noua merge.
KNOWN_FLAGS: dict[str, str] = {
    # Faza 2
    'bim-viewer-3d': 'Activeaza viewer-ul 3D (xeokit) pentru elemente BIM',
    'bim-ifc-async-conversion': 'Conversie IFC->XKT asincrona (worker)',
    'bim-aps-adapter': 'Adapter Autodesk Platform Services (necesita credentiale)',
    # Faza 3
    'bim-model-versioning': 'Activeaza versioning + workflow CDE pentru modele',
    'bim-federation': 'Vizualizare federata multi-disciplina',
    # Faza 4
    'bim-clash-detection': 'Detectie automata clash-uri',
    'bim-rule-engine': 'Rule-based model checking',
    # Faza 5
    'bim-4d-schedule': '4D scheduling (link element -> task)',
    'bim-5d-cost': '5D cost (link element -> cost item)',
    # Faza 5a - governance livrare informationala
    'bim-ids': 'Validator IDS (Information Delivery Specification, ISO 19650): '
               'verifica Property Sets-urile cerute pe faza de livrare. Default OFF.',
    # Faza 6
    'bim-iot-sensors': 'Digital Twin: ingest sensor data + live overlay',
    # Faza 7
    'bim-realtime-collab': 'Colaborare real-time via SSE (presence + comments)',
    'bim-issue-kanban': 'Kanban board pentru issue management',
    # Faza 8
    'bim-rbac-fine': 'RBAC fin pe disciplina/cladire/faza',
    'bim-cobie-export': 'Export COBie',
    'bim-bcf-full': 'Import/Export BCF 2.1/3.0 complet',
    'bim-public-api': 'API publica versionata cu tokens',
    'bim-api-rate-limit': 'Rate-limit in-memory pe token API (429 + Retry-After la '
                          'depasirea pragului). Single-worker PA, fara Redis. Default OFF.',
    # Faza 9 - Contract & Project Controls
    'controale-contract': 'Modul Contract Controls (contracte, termene, oferte, situatii, revendicari, PV)',
    'controale-contract-import-msproject': 'Activeaza import MS Project XML in programe referinta',
    'controale-contract-notificari-email': 'Activeaza trimitere email pentru alertele de termen (in plus de in-app)',
    # Planificare Gantt din F3
    'planificare-gantt': 'Modul Planificare Gantt din F3 (WBS + dependente tehnologice + export P6/MS Project)',
    # Banca de preturi de resurse
    'banca-preturi': 'Banca de preturi de resurse (referinta din extrase reale C6/C7/C8/C9/F4)',
    'gantt-calendar': 'Calendar de lucru real pentru Gantt (sarbatori legale RO, exceptii pe date, date Start/Finish in exporturi)',
    # Extragere proprietati BIM la import IFC
    'bim-pset-extraction': 'Extrage Property Sets (IfcPropertySet) + bounding box geometric la importul IFC '
                           '(populeaza proprietati_json + bbox_json). Mareste efortul de import; default OFF.',
    # Workforce Faza 1 - gestiune concedii / absente
    'concedii': 'Modul Concedii (gestiune absente): lista + creare cereri, workflow '
                'aprobare/respingere, calendar vizual de absente. Default OFF.',
    # Deviz Faza 1 - indicatori prognoza EVM
    'evm-prognoza': 'Afiseaza indicatorii de prognoza EVM (forecast la finalizare): '
                    'EAC (cost estimat final), ETC (cost ramas), VAC (abatere buget), '
                    'TCPI (eficienta necesara). Calcul derivat, fara schema noua. Default OFF.',
}


def _get_cache() -> Optional[dict]:
    """Returneaza cache-ul pe request (Flask g) sau None daca nu in request."""
    try:
        from flask import g, has_request_context
        if not has_request_context():
            return None
        if not hasattr(g, '_feature_flags_cache'):
            g._feature_flags_cache = {}
        return g._feature_flags_cache
    except Exception:
        return None


def is_enabled(key: str, tenant_id: Optional[int] = None) -> bool:
    """
    Verifica daca flag-ul `key` e activ pentru tenant-ul dat (sau global).

    Daca tenant_id nu e specificat, foloseste tenant-ul curent (din tenant.py).
    Default: False (flag inexistent => disabled).
    """
    if tenant_id is None:
        try:
            import tenant as _tenant
            tenant_id = _tenant.get_current_tenant_id()
        except Exception:
            tenant_id = None

    cache = _get_cache()
    cache_key = (key, tenant_id)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    enabled = _evaluate(key, tenant_id)

    if cache is not None:
        cache[cache_key] = enabled
    return enabled


def _evaluate(key: str, tenant_id: Optional[int]) -> bool:
    try:
        if tenant_id is not None:
            ff = FeatureFlag.query.filter_by(key=key, tenant_id=tenant_id).first()
            if ff is not None:
                return bool(ff.enabled)
        ff = FeatureFlag.query.filter_by(key=key, tenant_id=None).first()
        if ff is not None:
            return bool(ff.enabled)
    except Exception as e:
        _logger.warning('feature_flags._evaluate(%s) a esuat: %s', key, e)
    return False


def set_flag(
    key: str,
    enabled: bool,
    *,
    tenant_id: Optional[int] = None,
    descriere: Optional[str] = None,
    commit: bool = True,
) -> FeatureFlag:
    """Creeaza sau actualizeaza un flag (UPSERT). Folosit din admin UI / scripturi."""
    ff = FeatureFlag.query.filter_by(key=key, tenant_id=tenant_id).first()
    if ff is None:
        ff = FeatureFlag(key=key, tenant_id=tenant_id, enabled=enabled,
                         descriere=descriere or KNOWN_FLAGS.get(key))
        db.session.add(ff)
    else:
        ff.enabled = enabled
        if descriere:
            ff.descriere = descriere
    if commit:
        db.session.commit()
    return ff


def list_flags(tenant_id: Optional[int] = None) -> list[FeatureFlag]:
    """
    Returneaza toate flag-urile relevante pentru tenant-ul dat:
    - flag-urile globale
    - + flag-urile specifice tenant-ului (override-uri)
    """
    q = FeatureFlag.query
    if tenant_id is None:
        q = q.filter(FeatureFlag.tenant_id.is_(None))
    else:
        q = q.filter(
            (FeatureFlag.tenant_id == tenant_id) | (FeatureFlag.tenant_id.is_(None))
        )
    return q.order_by(FeatureFlag.key, FeatureFlag.tenant_id).all()


def init_app(app):
    """
    Inregistreaza helper Jinja `feature_enabled('key')` pentru template-uri.

    Usage in template:
        {% if feature_enabled('bim-viewer-3d') %} ... {% endif %}
    """
    @app.context_processor
    def _inject_feature_helpers():
        return {'feature_enabled': is_enabled}
