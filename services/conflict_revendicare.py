"""
Detectare conflicte pentru Revendicari (Faza 13).

Functia publica `detecta_conflicte(revendicare_id) -> list[dict]` ruleaza
regulile aplicabile in functie de tipul revendicarii si returneaza o lista
de dict-uri cu structura:
    {
        'severitate': 'info' | 'warning' | 'critical',
        'entitate': 'TermenContract' | 'TaskProgram' | 'CantitateLunara' | ...,
        'id': <id-ul entitatii>,
        'titlu': str,
        'descriere': str,
        'url': str (optional, link catre entitate),
    }

Rezultatul e calculat la cerere (read-only), NU stocat. Folosit in
revendicare_detalii.html pentru badge "⚠ N conflicte" si tabel detaliat.

Reguli implementate:
  - intarziere / prelungire_termen:
    * Conflict cu TermenContract.data_scadenta in intervalul
      [data_emitere - zile_prelungire, data_emitere + zile_prelungire].
    * Conflict cu TaskProgram.data_sfarsit_planificat in interval similar.
  - schimbare_scop:
    * Conflict cu PozitieBoQ via legaturile M:N (CantitateExecutataLunara).
      Severitate 'critical' daca cantitatea e validata.
  - perturbare / costuri_suplimentare:
    * Conflict cu SituatieLunara aprobata care include luna revendicarii.
  - General (orice tip):
    * Conflict cross-revendicari: alta Revendicare linkata la acelasi
      Termen/Task -> severitate 'warning'.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from models import (
    db, Revendicare, TermenContract, TaskProgram, CantitateExecutataLunara,
    PozitieBoQ, SituatieLunara,
    RevendicareTermen, RevendicareTask, RevendicareCantitate,
)


def detecta_conflicte(revendicare_id: int) -> list[dict[str, Any]]:
    """Punctul de intrare principal. Returneaza lista combinata de conflicte."""
    rev = Revendicare.query.get(revendicare_id)
    if rev is None:
        return []
    conflicte: list[dict] = []

    tip = (rev.tip or '').lower()

    if tip in ('intarziere', 'prelungire_termen'):
        conflicte.extend(_conflicte_intarziere(rev))
    if tip == 'schimbare_scop':
        conflicte.extend(_conflicte_schimbare_scop(rev))
    if tip in ('perturbare', 'costuri_suplimentare'):
        conflicte.extend(_conflicte_perturbare(rev))

    # General: cross-revendicari pe legaturile existente
    conflicte.extend(_conflicte_cross_revendicari(rev))

    # Sortare: critical first, apoi warning, apoi info
    sev_order = {'critical': 0, 'warning': 1, 'info': 2}
    conflicte.sort(key=lambda c: sev_order.get(c.get('severitate', 'info'), 3))
    return conflicte


# ============================================================
# Reguli per tip revendicare
# ============================================================

def _conflicte_intarziere(rev: Revendicare) -> list[dict]:
    """Termene si Taskuri afectate de prelungirea solicitata."""
    out: list[dict] = []
    if not rev.data_emitere:
        return out
    zile = rev.zile_prelungire_solicitate or 30  # default 30 zile interval
    start = rev.data_emitere - timedelta(days=zile)
    end = rev.data_emitere + timedelta(days=zile)

    # TermenContract pe acelasi contract, in interval
    termene = TermenContract.query.filter(
        TermenContract.contract_id == rev.contract_id,
        TermenContract.data_scadenta >= start,
        TermenContract.data_scadenta <= end,
    ).all()
    for t in termene:
        # Severitate: realizat -> info; intarziat -> critical; altfel warning
        if t.status == 'realizat':
            sev = 'info'
            extra = ' (deja realizat)'
        elif t.status == 'intarziat':
            sev = 'critical'
            extra = ' (deja intarziat - amplifica problema)'
        else:
            sev = 'warning'
            extra = ''
        out.append({
            'severitate': sev,
            'entitate': 'TermenContract',
            'id': t.id,
            'titlu': f'Termen "{t.denumire}" (scadenta {t.data_scadenta})',
            'descriere': (f'Termen contractual ({t.tip}) cu scadenta in '
                          f'intervalul prelungirii solicitate{extra}.'),
        })

    # TaskProgram pe acelasi proiect, data_sfarsit in interval
    taskuri = TaskProgram.query.filter(
        TaskProgram.proiect_id == rev.proiect_id,
        TaskProgram.data_sfarsit_planificat >= start,
        TaskProgram.data_sfarsit_planificat <= end,
    ).limit(50).all()
    for t in taskuri:
        # Severitate dupa procent realizare
        pr = float(t.procent_realizare or 0)
        if pr >= 100:
            sev = 'info'
            extra = ' (deja realizat 100%)'
        elif pr >= 50:
            sev = 'warning'
            extra = f' (in lucru: {pr:.0f}% realizat)'
        else:
            sev = 'critical'
            extra = f' (slab realizat: {pr:.0f}%)'
        out.append({
            'severitate': sev,
            'entitate': 'TaskProgram',
            'id': t.id,
            'titlu': f'Task "{t.denumire[:50]}" (finish {t.data_sfarsit_planificat})',
            'descriere': (f'Task din program cu data finish in interval'
                          f'{extra}.'),
        })
    return out


def _conflicte_schimbare_scop(rev: Revendicare) -> list[dict]:
    """Pozitii BoQ afectate de schimbarea scopului (via M:N cantitati)."""
    out: list[dict] = []
    legaturi = RevendicareCantitate.query.filter_by(
        revendicare_id=rev.id
    ).all()
    for lc in legaturi:
        c = lc.cantitate
        if not c:
            continue
        pz = c.pozitie_boq
        if not pz:
            continue
        if c.validat:
            sev = 'critical'
            extra = ' VALIDATA - schimbarea scopului afecteaza cantitati confirmate.'
        else:
            sev = 'warning'
            extra = ' (nevalidata - schimbare posibila fara impact major).'
        out.append({
            'severitate': sev,
            'entitate': 'CantitateLunara',
            'id': c.id,
            'titlu': (f'Pozitie {pz.cod_articol} - '
                      f'{c.an}-{c.luna:02d} cant={c.cantitate_executata}'),
            'descriere': f'Cantitate executata afectata de schimbarea scopului{extra}',
        })

    # Daca revendicarea NU are link-uri M:N cantitati, sugereaza utilizare
    if not legaturi:
        out.append({
            'severitate': 'info',
            'entitate': 'Revendicare',
            'id': rev.id,
            'titlu': 'Nicio legatura M:N cantitati',
            'descriere': ('Pentru schimbare_scop, leaga revendicarea de '
                          'cantitatile/pozitiile afectate ca sa vezi impactul.'),
        })
    return out


def _conflicte_perturbare(rev: Revendicare) -> list[dict]:
    """Situatii lunare APROBATE care cuprind cantitatile afectate."""
    out: list[dict] = []
    if not rev.data_emitere:
        return out
    an = rev.data_emitere.year
    luna = rev.data_emitere.month
    # Situatii aprobate pentru contract care includ luna revendicarii
    situatii = SituatieLunara.query.filter(
        SituatieLunara.contract_id == rev.contract_id,
        SituatieLunara.status.in_(['aprobata_beneficiar', 'platita']),
        db.or_(
            SituatieLunara.an < an,
            db.and_(SituatieLunara.an == an, SituatieLunara.luna <= luna),
        ),
    ).all()
    for s in situatii:
        sev = 'critical' if s.status == 'platita' else 'warning'
        extra = ' (PLATITA - costuri suplimentare greu de recuperat)' if s.status == 'platita' else ''
        out.append({
            'severitate': sev,
            'entitate': 'SituatieLunara',
            'id': s.id,
            'titlu': (f'Situatie {s.an}-{s.luna:02d} {s.status} '
                      f'(valoare luna {s.valoare_totala_luna or 0:.2f})'),
            'descriere': (f'Situatie lunara aprobata anterior care include '
                          f'perioada revendicarii{extra}.'),
        })
    return out


def _conflicte_cross_revendicari(rev: Revendicare) -> list[dict]:
    """Alte revendicari linkate la aceleasi termene/taskuri/cantitati."""
    out: list[dict] = []

    # Termene partajate cu alte revendicari
    termene_ids = [lt.termen_contract_id for lt in
                   RevendicareTermen.query.filter_by(revendicare_id=rev.id).all()]
    if termene_ids:
        alte_linkuri_termen = RevendicareTermen.query.filter(
            RevendicareTermen.termen_contract_id.in_(termene_ids),
            RevendicareTermen.revendicare_id != rev.id,
        ).all()
        seen_rev_ids: set[int] = set()
        for lt in alte_linkuri_termen:
            if lt.revendicare_id in seen_rev_ids:
                continue
            seen_rev_ids.add(lt.revendicare_id)
            alta = Revendicare.query.get(lt.revendicare_id)
            if alta is None:
                continue
            out.append({
                'severitate': 'warning',
                'entitate': 'Revendicare',
                'id': alta.id,
                'titlu': f'Revendicare {alta.numar_revendicare} ({alta.tip})',
                'descriere': (f'Alta revendicare (status {alta.status}) '
                              f'foloseste acelasi/aceleasi termene contractuale.'),
            })

    # Taskuri partajate
    task_ids = [lt.task_program_id for lt in
                RevendicareTask.query.filter_by(revendicare_id=rev.id).all()]
    if task_ids:
        alte_linkuri_task = RevendicareTask.query.filter(
            RevendicareTask.task_program_id.in_(task_ids),
            RevendicareTask.revendicare_id != rev.id,
        ).all()
        seen_rev_ids: set[int] = set()
        for lt in alte_linkuri_task:
            if lt.revendicare_id in seen_rev_ids:
                continue
            seen_rev_ids.add(lt.revendicare_id)
            alta = Revendicare.query.get(lt.revendicare_id)
            if alta is None:
                continue
            out.append({
                'severitate': 'warning',
                'entitate': 'Revendicare',
                'id': alta.id,
                'titlu': f'Revendicare {alta.numar_revendicare} ({alta.tip})',
                'descriere': (f'Alta revendicare foloseste acelasi/aceleasi '
                              f'taskuri din program.'),
            })

    return out


def numara_conflicte(revendicare_id: int) -> dict[str, int]:
    """Returneaza dict cu numarul de conflicte per severitate (pentru badge UI)."""
    conf = detecta_conflicte(revendicare_id)
    counts = {'critical': 0, 'warning': 0, 'info': 0, 'total': len(conf)}
    for c in conf:
        sev = c.get('severitate', 'info')
        counts[sev] = counts.get(sev, 0) + 1
    return counts
