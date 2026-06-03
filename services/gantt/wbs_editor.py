"""
Editor WBS pentru planuri salvate: arbore editabil (GanttWbsNod) seedat din
WBS-ul auto, apoi randat/exportat cu prioritate fata de auto.

  - asigura_arbore(plan, noduri_auto): seedeaza arborele din auto daca nu exista
  - noduri_plan(plan_id): nodurile salvate
  - wbs_din_arbore(activitati, noduri_db): reconstruieste lista NodWBS + leaga
    activitatile (dupa activitate_ref); activitatile fara nod -> grup 'Neincadrate'
  - operatii editor: redenumeste, muta_sus/jos, muta_in_grup, adauga_grup,
    sterge_nod, reset (sterge arborele -> revine la auto)
"""
from __future__ import annotations

from typing import Optional

from .modele import NodWBS


def arbore_exista(plan_id: int) -> bool:
    from models import GanttWbsNod
    return GanttWbsNod.query.filter_by(plan_id=plan_id).first() is not None


def noduri_plan(plan_id: int):
    from models import GanttWbsNod
    return (GanttWbsNod.query.filter_by(plan_id=plan_id)
            .order_by(GanttWbsNod.parinte_id, GanttWbsNod.ordine, GanttWbsNod.id).all())


def seed_arbore(plan, noduri_auto) -> int:
    """Persista WBS-ul auto ca GanttWbsNod. Intoarce nr. noduri create."""
    from models import db, GanttWbsNod
    id_dupa_wbs = {}                 # wbs_id auto (str) -> GanttWbsNod.id
    ordine_per_parinte: dict = {}
    n_create = 0
    for n in noduri_auto:            # preorder: parintele apare inaintea copiilor
        parinte_db = id_dupa_wbs.get(n.parinte_id) if n.parinte_id else None
        o = ordine_per_parinte.get(parinte_db, 0)
        ordine_per_parinte[parinte_db] = o + 1
        nod = GanttWbsNod(
            plan_id=plan.id, tenant_id=getattr(plan, 'tenant_id', None),
            parinte_id=parinte_db,
            tip='activitate' if n.tip == 'activitate' else 'grup',
            nume=(n.nume or '(fara nume)')[:300], ordine=o,
            activitate_ref=(n.activitate_id if n.tip == 'activitate' else None))
        db.session.add(nod)
        db.session.flush()
        id_dupa_wbs[n.wbs_id] = nod.id
        n_create += 1
    db.session.commit()
    return n_create


def asigura_arbore(plan, noduri_auto) -> bool:
    """Seedeaza arborele daca nu exista. True daca a seedat acum."""
    if arbore_exista(plan.id):
        return False
    seed_arbore(plan, noduri_auto)
    return True


def wbs_din_arbore(activitati, noduri_db) -> list:
    """Reconstruieste lista NodWBS (preorder) din arborele salvat si seteaza
    wbs_id/nivel pe activitati. Activitatile fara nod -> grup 'Neincadrate'."""
    copii: dict = {}
    for n in noduri_db:
        copii.setdefault(n.parinte_id, []).append(n)
    for k in copii:
        copii[k].sort(key=lambda x: (x.ordine, x.id))
    act_by_id = {a.id: a for a in activitati}
    folosite = set()
    out: list = []

    def walk(parent_db_id, parent_wbs, nivel):
        for i, n in enumerate(copii.get(parent_db_id, []), start=1):
            wbs = f'{parent_wbs}.{i}' if parent_wbs else str(i)
            if n.tip == 'activitate':
                a = act_by_id.get(n.activitate_ref)
                if not a:
                    continue                      # activitate disparuta (fisier schimbat)
                folosite.add(a.id)
                a.wbs_id, a.nivel = wbs, nivel
                out.append(NodWBS(wbs, a.nume, nivel, parent_wbs or None, 'activitate', a.id))
            else:
                out.append(NodWBS(wbs, n.nume, nivel, parent_wbs or None, 'grup'))
                walk(n.id, wbs, nivel + 1)

    walk(None, '', 1)

    orfane = [a for a in activitati if a.id not in folosite]
    if orfane:
        gi = len(copii.get(None, [])) + 1
        gw = str(gi)
        out.append(NodWBS(gw, 'Neincadrate', 1, None, 'grup'))
        for j, a in enumerate(orfane, start=1):
            a.wbs_id, a.nivel = f'{gw}.{j}', 2
            out.append(NodWBS(a.wbs_id, a.nume, 2, gw, 'activitate', a.id))
    return out


# ----------------------------------------------------------------- operatii editor
def _nod(plan_id, nod_id):
    from models import GanttWbsNod
    n = GanttWbsNod.query.filter_by(id=nod_id, plan_id=plan_id).first()
    return n


def redenumeste(plan_id, nod_id, nume) -> bool:
    from models import db
    n = _nod(plan_id, nod_id)
    if not n or not (nume or '').strip():
        return False
    n.nume = nume.strip()[:300]
    db.session.commit()
    return True


def muta(plan_id, nod_id, directie) -> bool:
    """Reordoneaza nodul in cadrul parintelui (directie='sus'|'jos')."""
    from models import db, GanttWbsNod
    n = _nod(plan_id, nod_id)
    if not n:
        return False
    frati = (GanttWbsNod.query.filter_by(plan_id=plan_id, parinte_id=n.parinte_id)
             .order_by(GanttWbsNod.ordine, GanttWbsNod.id).all())
    idx = next((i for i, x in enumerate(frati) if x.id == n.id), None)
    if idx is None:
        return False
    j = idx - 1 if directie == 'sus' else idx + 1
    if j < 0 or j >= len(frati):
        return False
    frati[idx].ordine, frati[j].ordine = frati[j].ordine, frati[idx].ordine
    db.session.commit()
    return True


def muta_in_grup(plan_id, nod_id, grup_id) -> bool:
    """Muta un nod sub alt grup (sau la radacina daca grup_id=None)."""
    from models import db, GanttWbsNod
    n = _nod(plan_id, nod_id)
    if not n:
        return False
    if grup_id:
        g = _nod(plan_id, grup_id)
        if not g or g.tip != 'grup' or g.id == n.id:
            return False
    maxo = (db.session.query(db.func.max(GanttWbsNod.ordine))
            .filter_by(plan_id=plan_id, parinte_id=grup_id).scalar()) or 0
    n.parinte_id = grup_id or None
    n.ordine = maxo + 1
    db.session.commit()
    return True


def adauga_grup(plan, nume, parinte_id=None):
    from models import db, GanttWbsNod
    nume = (nume or '').strip()
    if not nume:
        return None
    maxo = (db.session.query(db.func.max(GanttWbsNod.ordine))
            .filter_by(plan_id=plan.id, parinte_id=parinte_id).scalar()) or 0
    g = GanttWbsNod(plan_id=plan.id, tenant_id=getattr(plan, 'tenant_id', None),
                    parinte_id=parinte_id, tip='grup', nume=nume[:300], ordine=maxo + 1)
    db.session.add(g)
    db.session.commit()
    return g


def sterge_nod(plan_id, nod_id) -> bool:
    """Sterge un nod. Activitatile de sub el devin orfane (-> 'Neincadrate' la randare),
    deci nu se pierd. Grupurile cu copii: copiii urca la parintele nodului sters."""
    from models import db, GanttWbsNod
    n = _nod(plan_id, nod_id)
    if not n:
        return False
    for c in GanttWbsNod.query.filter_by(plan_id=plan_id, parinte_id=n.id).all():
        c.parinte_id = n.parinte_id
    db.session.delete(n)
    db.session.commit()
    return True


def reset(plan_id) -> int:
    """Sterge arborele salvat -> randarea revine la WBS-ul auto. Nr. sterse."""
    from models import db, GanttWbsNod
    n = GanttWbsNod.query.filter_by(plan_id=plan_id).delete()
    db.session.commit()
    return n
