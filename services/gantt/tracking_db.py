"""
Adaptor DB pentru urmarirea executiei Gantt (Faza 2 tracking).

Separat de tracking.py (care e pur, fara DB). Aici legam baseline-ul si progresul
de modelele GanttBaseline / GanttProgres si respectam feature flag-ul 'gantt-tracking':
cu flag OFF, `progrese_active` / `baseline_activ` intorc None -> apelantii pastreaza
comportamentul istoric (progres 0, fara baseline).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from . import tracking


def _flag_on(tenant_id: Optional[int] = None) -> bool:
    """True doar cand flag-ul 'gantt-tracking' e activ (altfel istoric, fara tracking)."""
    try:
        from services.feature_flags import is_enabled
        return bool(is_enabled('gantt-tracking', tenant_id))
    except Exception:
        return False


def progrese_active(plan_id: int, tenant_id: Optional[int] = None) -> Optional[dict]:
    """Progresul curent pe cheie pentru un plan, DOAR cu flag ON (altfel None).

    Intoarce {cheie: procent_float} (forma simpla, pentru diagrama/bare). None cu
    flag OFF sau fara plan -> bare cu progres 0 (comportament istoric)."""
    if not _flag_on(tenant_id):
        return None
    try:
        from models import GanttProgres
        rows = (GanttProgres.query.filter_by(plan_id=plan_id)
                .order_by(GanttProgres.data, GanttProgres.id).all())
        curent = tracking.progres_curent_din_jurnal(rows)
        return {ck: v['procent'] for ck, v in curent.items()}
    except Exception:
        return None


def progrese_detaliat(plan_id: int) -> dict:
    """Progresul curent detaliat ({cheie: {procent, data_start_real, ...}}),
    indiferent de flag (folosit in pagina de tracking, gata gatuita la nivel de ruta)."""
    try:
        from models import GanttProgres
        rows = (GanttProgres.query.filter_by(plan_id=plan_id)
                .order_by(GanttProgres.data, GanttProgres.id).all())
        return tracking.progres_curent_din_jurnal(rows)
    except Exception:
        return {}


def baseline_activ(plan, tenant_id: Optional[int] = None) -> Optional[dict]:
    """Snapshot-ul baseline-ului activ al planului (dict desfacut din JSON), DOAR
    cu flag ON (altfel None -> fara overlay, comportament istoric)."""
    if not _flag_on(tenant_id):
        return None
    bid = getattr(plan, 'baseline_activ_id', None)
    if not bid:
        return None
    try:
        from models import db, GanttBaseline
        bl = db.session.get(GanttBaseline, bid)
        if bl is None or not bl.continut_json:
            return None
        return json.loads(bl.continut_json)
    except Exception:
        return None


def inghetare_baseline(plan, rezultat, nume: str = None,
                       tenant_id: Optional[int] = None, creat_de_id: int = None):
    """Inghetare baseline: creeaza un GanttBaseline din rezultatul programat curent
    si il marcheaza ca activ pe plan. Intoarce randul GanttBaseline."""
    from models import db, GanttBaseline
    snap = tracking.snapshot_baseline(rezultat)
    meta = snap.get('meta', {})
    nume = (nume or f'Baseline {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}')[:120]
    bl = GanttBaseline(
        tenant_id=tenant_id, plan_id=plan.id, nume=nume,
        bac=meta.get('bac', 0) or 0,
        durata_zile=meta.get('durata_zile', 0) or 0,
        data_start=getattr(plan, 'data_start', None),
        continut_json=json.dumps(snap),
        creat_de_id=creat_de_id)
    db.session.add(bl)
    db.session.flush()             # avem nevoie de bl.id pentru baseline_activ_id
    plan.baseline_activ_id = bl.id
    db.session.commit()
    return bl


def adauga_progres_bulk(plan, intrari: list, data_stare: date = None,
                        sursa: str = 'manual', tenant_id: Optional[int] = None,
                        creat_de_id: int = None) -> int:
    """Adauga (append-only) progres pe activitati. `intrari` = list de dict
    {cheie, procent, cantitate_realizata?, data_start_real?, data_finish_real?}.
    Intoarce numarul de randuri adaugate."""
    from models import db, GanttProgres
    if data_stare is None:
        data_stare = date.today()
    adaugate = 0
    for it in (intrari or []):
        ck = (it.get('cheie') or '').strip()
        if not ck:
            continue
        try:
            pct = max(0.0, min(100.0, float(it.get('procent', 0) or 0)))
        except (TypeError, ValueError):
            pct = 0.0
        db.session.add(GanttProgres(
            tenant_id=tenant_id, plan_id=plan.id, cheie_activitate=ck,
            data=_parse_data(it.get('data')) or data_stare,
            procent_fizic=pct,
            cantitate_realizata=_parse_float(it.get('cantitate_realizata')),
            data_start_real=_parse_data(it.get('data_start_real')),
            data_finish_real=_parse_data(it.get('data_finish_real')),
            sursa=(sursa or 'manual')[:20], creat_de_id=creat_de_id))
        adaugate += 1
    if adaugate:
        db.session.commit()
    return adaugate


def _parse_data(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def _parse_float(v):
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
