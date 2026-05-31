"""
Overlay de configurare pentru motorul Gantt: DB suprascrie JSON.

Principiu (zero regresie):
- daca exista randuri active in DB (pe tenant sau global) -> se folosesc;
- daca tabelul e gol, lipseste, sau nu suntem in context de aplicatie -> se cade
  pe config/gantt/*.json (config_loader). Orice eroare de DB -> fallback la JSON.

Astfel codul poate fi deployat INAINTE de rularea migratiei 0012 fara sa crape
(tabelele inca inexistente -> exceptie prinsa -> JSON).
"""
from __future__ import annotations

from typing import Optional

from . import config_loader as cfg
from .normalizare import normalizeaza


# ---------------------------------------------------------------------------
# Acces DB defensiv (fallback la None daca nu e disponibil).
# ---------------------------------------------------------------------------
def _randuri_active(model, tenant_id: Optional[int]):
    """Randuri active pentru tenant_id + globale (tenant_id NULL). None la orice esec."""
    try:
        from flask import has_app_context
        if not has_app_context():
            return None
        from sqlalchemy import or_
        q = model.query.filter_by(activ=True)
        if tenant_id is not None:
            q = q.filter(or_(model.tenant_id == tenant_id, model.tenant_id.is_(None)))
        else:
            q = q.filter(model.tenant_id.is_(None))
        return q.all()
    except Exception:
        return None  # tabel inexistent / fara context / orice eroare -> JSON


# ---------------------------------------------------------------------------
# Domenii de configurare (fiecare: DB daca exista, altfel JSON).
# ---------------------------------------------------------------------------
def coloane(tenant_id: Optional[int] = None) -> dict:
    """{camp_logic: [sinonime]} pentru maparea coloanelor de antet."""
    from models import GanttSinonimColoana
    rows = _randuri_active(GanttSinonimColoana, tenant_id)
    if rows:
        d: dict = {}
        for r in rows:
            d.setdefault(r.camp, []).append(r.sinonim)
        return d
    return cfg.incarca('setari', cfg.SETARI_IMPLICITE).get(
        'coloane', cfg.SETARI_IMPLICITE['coloane'])


def clasificare(tenant_id: Optional[int] = None) -> dict:
    """{CATEGORIE: [cuvinte-cheie]} pentru clasificare (doar regulile 'cuvant')."""
    from models import GanttClasificareRegula
    rows = _randuri_active(GanttClasificareRegula, tenant_id)
    cuvinte = [r for r in rows if r.tip_regula == 'cuvant'] if rows else None
    if cuvinte:
        d: dict = {}
        for r in sorted(cuvinte, key=lambda x: (x.prioritate, x.id)):
            d.setdefault(r.categorie, []).append(r.valoare)
        return d
    return cfg.incarca('clasificare', cfg.CLASIFICARE_IMPLICITA)


def reguli_prefix_cod(tenant_id: Optional[int] = None) -> list:
    """[(prefix, CATEGORIE, prioritate)] pentru clasificare pe prefix de cod (Faza 3)."""
    from models import GanttClasificareRegula
    rows = _randuri_active(GanttClasificareRegula, tenant_id)
    if not rows:
        return []
    pref = [r for r in rows if r.tip_regula == 'prefix_cod']
    return [(r.valoare, r.categorie, r.prioritate)
            for r in sorted(pref, key=lambda x: (x.prioritate, -len(x.valoare or '')))]


def dependinte(tenant_id: Optional[int] = None) -> dict:
    """{'ordine_categorii', 'intra_categorie', 'relatii'} pentru dependente."""
    from models import GanttRelatieTemplate
    rows = _randuri_active(GanttRelatieTemplate, tenant_id)
    json_dep = cfg.incarca('dependinte', cfg.DEPENDINTE_IMPLICITE)
    if not rows:
        return json_dep

    relatii = [{'from': r.categorie_din, 'to': r.categorie_in,
                'tip': r.tip, 'decalaj': r.decalaj} for r in rows]
    # reconstruieste ordine_categorii: rangul lui 'din' intai, apoi 'in' = rang_din + 1
    rang: dict = {}
    for r in rows:
        if r.rang_din is not None:
            rang.setdefault(r.categorie_din, r.rang_din)
    for r in rows:
        baza = rang.get(r.categorie_din, r.rang_din if r.rang_din is not None else 0)
        rang.setdefault(r.categorie_in, baza + 1)
    ordine = sorted(rang, key=lambda c: (rang[c], c))
    return {
        'ordine_categorii': ordine,
        'intra_categorie': json_dep.get('intra_categorie', 'secvential'),
        'relatii': relatii,
    }


def setari(tenant_id: Optional[int] = None) -> dict:
    """setari.json cu `coloane` suprascris din DB (daca exista)."""
    base = dict(cfg.incarca('setari', cfg.SETARI_IMPLICITE))
    base['coloane'] = coloane(tenant_id)
    return base


# ---------------------------------------------------------------------------
# Profiluri de mapare (invatate din wizard) - amprenta antetului.
# ---------------------------------------------------------------------------
def semnatura_antet(rand_antet) -> str:
    """Amprenta stabila a unui rand de antet (celule normalizate, sortate, unite cu '|')."""
    celule = sorted({normalizeaza(c) for c in (rand_antet or []) if c is not None
                     and str(c).strip()})
    return '|'.join(celule)[:255]


def gaseste_profil(semnatura: str, tenant_id: Optional[int] = None):
    """Profilul de mapare activ pentru o semnatura de antet (sau None)."""
    if not semnatura:
        return None
    try:
        from flask import has_app_context
        if not has_app_context():
            return None
        from sqlalchemy import or_
        from models import GanttProfilMapare
        q = GanttProfilMapare.query.filter_by(activ=True, semnatura=semnatura)
        if tenant_id is not None:
            q = q.filter(or_(GanttProfilMapare.tenant_id == tenant_id,
                             GanttProfilMapare.tenant_id.is_(None)))
        else:
            q = q.filter(GanttProfilMapare.tenant_id.is_(None))
        return q.order_by(GanttProfilMapare.nr_utilizari.desc()).first()
    except Exception:
        return None


def profil_mapare(profil) -> tuple:
    """Despacheteaza un profil -> ({camp: index_coloana}, rand_antet:int|None)."""
    import json
    try:
        d = json.loads(profil.mapare_json) if (profil and profil.mapare_json) else {}
        col = {k: int(v) for k, v in (d.get('coloane') or {}).items()}
        ra = d.get('rand_antet')
        return col, (int(ra) if ra is not None else None)
    except Exception:
        return {}, None


def salveaza_profil(nume: str, semnatura: str, coloane_map: dict,
                    rand_antet: Optional[int] = None, sursa: str = 'wizard',
                    tenant_id: Optional[int] = None, user_id: Optional[int] = None):
    """Upsert profil de mapare pe (tenant_id, semnatura). Audit-logat. None la esec."""
    if not semnatura:
        return None
    try:
        from flask import has_app_context
        if not has_app_context():
            return None
        import json
        from datetime import datetime
        from models import db, GanttProfilMapare
        from services import audit

        payload = json.dumps({
            'coloane': {k: int(v) for k, v in (coloane_map or {}).items()},
            'rand_antet': (int(rand_antet) if rand_antet is not None else None),
        })
        prof = GanttProfilMapare.query.filter_by(semnatura=semnatura,
                                                 tenant_id=tenant_id).first()
        nou = prof is None
        if nou:
            prof = GanttProfilMapare(
                nume=(nume or f'Profil {semnatura[:12]}'), semnatura=semnatura,
                mapare_json=payload, sursa=sursa, tenant_id=tenant_id, creat_de_id=user_id)
            db.session.add(prof)
        else:
            prof.mapare_json = payload
            prof.sursa = sursa
            prof.activ = True
            if nume:
                prof.nume = nume
            prof.data_actualizare = datetime.utcnow()
        db.session.flush()
        audit.log('create' if nou else 'update', 'gantt_profil_mapare', prof.id,
                  new_values={'nume': prof.nume, 'semnatura': semnatura, 'sursa': sursa})
        db.session.commit()
        return prof
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return None


def marcheaza_utilizare(profil) -> None:
    """Incrementeaza nr_utilizari pe un profil aplicat (best-effort)."""
    try:
        from flask import has_app_context
        if not has_app_context() or profil is None:
            return
        from models import db
        profil.nr_utilizari = (profil.nr_utilizari or 0) + 1
        db.session.commit()
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
