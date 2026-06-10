"""
Banca de preturi de resurse - referinta din extrase REALE.

Importa preturi unitare pe cod-resursa din extrasele unui deviz
(C6 materiale / C7 manopera / C8 utilaje / C9 transport / F4 echipamente)
si le pune in tabelul PretResursa, cu sursa (proiect/oferta) + data, ca sa
putem face benchmark intre proiecte (P25/P50/P75 pe acelasi cod).

Distinct de:
  - deviz_pricing (tarife pe CATEGORIE de lucrare, pt distribuit un total global)
  - ExtrasResursa (consum PLANIFICAT pe un proiect anume)

Functii publice:
  - parse_extras_xls(path) -> list[dict]            (citeste un .xls C6/C7/C8/C9/F4)
  - importa_din_extrase(fisiere, sursa, ...) -> dict (parse + upsert din .xls)
  - importa_din_catalog(catalog, sursa, ...) -> dict (upsert dintr-un catalog deja extras)
  - pret_referinta(cod, tip=None) -> Decimal | None (mediana pe cod)
  - rezumat(tenant_id=None) -> dict                 (counts + interval pret pe tip)
  - cauta(q=None, tip=None, limit=50) -> list[PretResursa]

Idempotent: un rand per (tenant_id, tip, cod, sursa). Re-import pe aceeasi
sursa actualizeaza pretul, nu dubleaza.
"""

from __future__ import annotations

import os
import re
import statistics
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from typing import Optional, Iterable

from models import db, PretResursa


# ============================================================
# Parsing .xls (Excel 97-2003) - foloseste xlrd (in requirements)
# ============================================================

# Detectie tip dupa numele fisierului
_TIP_DUPA_NUME = [
    ('material',   ['c6', 'materiale', 'material']),
    ('manopera',   ['c7', 'manopera']),
    ('utilaj',     ['c8', 'utilaje', 'utilaj']),
    ('transport',  ['c9', 'transport']),
    ('echipament', ['f4', 'echipamente', 'echipament']),
]

# Index coloana pret unitar + UM implicit, pe tip
_LAYOUT = {
    #          col_pret  um_default  col_um   col_furnizor
    'material':   dict(pret=4, um=None, col_um=2, furnizor=6),
    'manopera':   dict(pret=3, um='ora', col_um=None, furnizor=None),
    'utilaj':     dict(pret=3, um='ora', col_um=None, furnizor=None),
    'transport':  dict(pret=5, um='to*km', col_um=None, furnizor=None),
    'echipament': dict(pret=4, um=None, col_um=2, furnizor=None),
}


def _tip_din_nume(nume: str) -> Optional[str]:
    low = nume.lower()
    for tip, kws in _TIP_DUPA_NUME:
        for kw in kws:
            if kw in low:
                return tip
    return None


def _num(v) -> Optional[Decimal]:
    try:
        if v is None or v == '':
            return None
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _is_nr(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _split_cod(s: str) -> tuple[str, str]:
    """'CG01A-15# - Strat suport' -> ('CG01A-15#', 'Strat suport')."""
    s = str(s).strip()
    m = re.match(r'^([0-9A-Za-z\[\]\.%#\-/]+?)\s*[-–]\s*(.+)$', s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return '', s


def parse_extras_xls(path: str, tip: Optional[str] = None) -> list[dict]:
    """Citeste un fisier extras .xls si intoarce lista de dict-uri normalizate:
    {tip, cod, denumire, um, pret_unitar, furnizor}. Sare peste randuri TOTAL /
    fara cod numeric. Tipul se deduce din numele fisierului daca nu e dat."""
    import xlrd  # local import - nu blocheaza app daca lipseste in alt context

    if tip is None:
        tip = _tip_din_nume(os.path.basename(path))
    if tip is None:
        return []
    lay = _LAYOUT[tip]

    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)
    out: list[dict] = []
    obiect = ''
    for r in range(sh.nrows):
        c0 = sh.cell_value(r, 0)
        c1 = str(sh.cell_value(r, 1)).strip() if sh.ncols > 1 else ''
        # Header de obiect in F4 (ex "003 Instalatii") - retinem dar nu importam
        if tip == 'echipament' and not _is_nr(c0) and re.match(r'^\d{3}\s', c1):
            obiect = c1
            continue
        if not _is_nr(c0) or not c1:
            continue
        cod, den = _split_cod(c1)
        pret = _num(sh.cell_value(r, lay['pret'])) if sh.ncols > lay['pret'] else None
        if pret is None:
            continue
        um = lay['um']
        if lay['col_um'] is not None and sh.ncols > lay['col_um']:
            um = str(sh.cell_value(r, lay['col_um'])).strip() or lay['um']
        furnizor = None
        if lay['furnizor'] is not None and sh.ncols > lay['furnizor']:
            furnizor = str(sh.cell_value(r, lay['furnizor'])).strip() or None
        out.append(dict(tip=tip, cod=cod, denumire=den, um=um,
                        pret_unitar=pret, furnizor=furnizor))
    return out


# ============================================================
# Clasificare pe categorie de lucrare
# ============================================================

def clasifica_resursa(tip: str, denumire: str, cod: Optional[str] = None,
                      um: Optional[str] = None) -> str:
    """Categorie de lucrare pentru o resursa din banca.

    Materialele si echipamentele trec prin clasificatorul de devize existent
    (beton, cabluri, conducte_sanitare...); manopera/utilajele/transportul au
    categoria = tipul lor (meseriile/utilajele sunt deja granulare in denumire)."""
    if tip in ('manopera', 'utilaj', 'transport'):
        return tip
    from services.deviz_pricing import clasifica_pozitie
    return clasifica_pozitie(denumire or '', cod, 'general', um)


def reclasifica(doar_lipsa: bool = True, tenant_id: Optional[int] = None,
                commit: bool = True) -> dict:
    """Backfill: clasifica inregistrarile existente. `doar_lipsa=True` nu atinge
    categoriile setate deja (protejeaza editarile manuale)."""
    q = PretResursa.query
    if tenant_id is not None:
        q = q.filter(PretResursa.tenant_id == tenant_id)
    if doar_lipsa:
        q = q.filter(db.or_(PretResursa.categorie.is_(None), PretResursa.categorie == ''))
    n = 0
    for p in q.all():
        p.categorie = clasifica_resursa(p.tip, p.denumire, p.cod, p.um)
        n += 1
    if commit:
        db.session.commit()
    return {'clasificate': n}


# ============================================================
# Import in DB (upsert idempotent)
# ============================================================

def _upsert(rows: Iterable[dict], sursa: str, *, proiect_id=None, tenant_id=None,
            data_pret: Optional[date] = None, introdus_de=None) -> dict:
    creat = actualizat = sarit = 0
    per_tip: dict[str, int] = {}
    for row in rows:
        cod = (row.get('cod') or '').strip()
        if not cod:
            sarit += 1
            continue
        tip = row['tip']
        existing = PretResursa.query.filter_by(
            tenant_id=tenant_id, tip=tip, cod=cod, sursa=sursa
        ).first()
        if existing:
            existing.pret_unitar = row['pret_unitar']
            existing.denumire = row.get('denumire') or existing.denumire
            existing.um = row.get('um') or existing.um
            existing.furnizor = row.get('furnizor') or existing.furnizor
            existing.proiect_id = proiect_id or existing.proiect_id
            existing.data_pret = data_pret or existing.data_pret
            if not existing.categorie:   # nu suprascrie editarile manuale
                existing.categorie = clasifica_resursa(tip, existing.denumire,
                                                       cod, existing.um)
            actualizat += 1
        else:
            db.session.add(PretResursa(
                tenant_id=tenant_id, tip=tip, cod=cod,
                denumire=row.get('denumire') or cod, um=row.get('um'),
                categorie=clasifica_resursa(tip, row.get('denumire') or cod,
                                            cod, row.get('um')),
                pret_unitar=row['pret_unitar'], moneda='RON', sursa=sursa,
                proiect_id=proiect_id, data_pret=data_pret,
                furnizor=row.get('furnizor'), introdus_de=introdus_de,
            ))
            creat += 1
        per_tip[tip] = per_tip.get(tip, 0) + 1
    return dict(creat=creat, actualizat=actualizat, sarit=sarit, per_tip=per_tip)


def importa_din_extrase(fisiere, sursa: str, *, proiect_id=None, tenant_id=None,
                        data_pret: Optional[date] = None, introdus_de=None,
                        commit: bool = True) -> dict:
    """Importa preturi din .xls reale. `fisiere` = lista de cai SAU un folder
    (se cauta C6/C7/C8/C9/F4 in el). Intoarce stats {creat, actualizat, per_tip}."""
    paths: list[str] = []
    if isinstance(fisiere, str) and os.path.isdir(fisiere):
        for root, _dirs, files in os.walk(fisiere):
            for f in files:
                if f.lower().endswith('.xls') and _tip_din_nume(f):
                    paths.append(os.path.join(root, f))
    else:
        paths = list(fisiere)

    all_rows: list[dict] = []
    fisiere_citite = 0
    for p in paths:
        rows = parse_extras_xls(p)
        if rows:
            fisiere_citite += 1
            all_rows.extend(rows)
    stats = _upsert(all_rows, sursa, proiect_id=proiect_id, tenant_id=tenant_id,
                    data_pret=data_pret, introdus_de=introdus_de)
    stats['fisiere'] = fisiere_citite
    if commit:
        db.session.commit()
    return stats


# Mapare chei catalog (din extragerea de pe Desktop) -> (tip, camp_pret, camp_denumire, camp_um, camp_furnizor)
_CATALOG_MAP = {
    'C6_materiale':   ('material',   'pret_unitar',   'denumire',      'um',  'furnizor'),
    'C7_manopera':    ('manopera',   'tarif_lei_ora', 'meserie',       None,  None),
    'C8_utilaje':     ('utilaj',     'tarif_unitar',  'utilaj',        None,  None),
    'C9_transport':   ('transport',  'tarif_unitar',  'tip_transport', None,  None),
    'F4_echipamente': ('echipament', 'pret_unitar',   'denumire',      'um',  None),
}
_UM_DEFAULT = {'manopera': 'ora', 'utilaj': 'ora', 'transport': 'to*km'}


def importa_din_catalog(catalog: dict, sursa: str, *, proiect_id=None, tenant_id=None,
                        data_pret: Optional[date] = None, introdus_de=None,
                        commit: bool = True) -> dict:
    """Importa dintr-un catalog deja extras (dict cu chei C6_materiale, ... ca in
    catalog.json). Util cand parsarea s-a facut deja offline."""
    rows: list[dict] = []
    for key, (tip, f_pret, f_den, f_um, f_furn) in _CATALOG_MAP.items():
        for x in catalog.get(key, []) or []:
            pret = _num(x.get(f_pret))
            if pret is None:
                continue
            um = x.get(f_um) if f_um else _UM_DEFAULT.get(tip)
            rows.append(dict(tip=tip, cod=(x.get('cod') or '').strip(),
                             denumire=x.get(f_den) or '', um=um, pret_unitar=pret,
                             furnizor=x.get(f_furn) if f_furn else None))
    stats = _upsert(rows, sursa, proiect_id=proiect_id, tenant_id=tenant_id,
                    data_pret=data_pret, introdus_de=introdus_de)
    if commit:
        db.session.commit()
    return stats


# ============================================================
# Query / benchmark
# ============================================================

def pret_referinta(cod: str, tip: Optional[str] = None,
                   tenant_id: Optional[int] = None) -> Optional[Decimal]:
    """Mediana preturilor pentru un cod (peste toate sursele). None daca nu exista."""
    q = PretResursa.query.filter(PretResursa.cod == cod)
    if tip:
        q = q.filter(PretResursa.tip == tip)
    if tenant_id is not None:
        q = q.filter(PretResursa.tenant_id == tenant_id)
    preturi = [p.pret_unitar for p in q.all() if p.pret_unitar is not None]
    if not preturi:
        return None
    return Decimal(str(statistics.median(preturi)))


def rezumat(tenant_id: Optional[int] = None) -> dict:
    """Sumar pe tip: nr inregistrari, nr coduri distincte, interval pret (min/median/max)."""
    q = PretResursa.query
    if tenant_id is not None:
        q = q.filter(PretResursa.tenant_id == tenant_id)
    out: dict[str, dict] = {}
    by_tip: dict[str, list] = {}
    coduri_tip: dict[str, set] = {}
    for p in q.all():
        by_tip.setdefault(p.tip, []).append(p.pret_unitar)
        coduri_tip.setdefault(p.tip, set()).add(p.cod)
    for tip, preturi in by_tip.items():
        vals = [v for v in preturi if v is not None]
        out[tip] = dict(
            n=len(preturi),
            n_coduri=len(coduri_tip.get(tip, set())),
            pret_min=min(vals) if vals else None,
            pret_median=Decimal(str(statistics.median(vals))) if vals else None,
            pret_max=max(vals) if vals else None,
        )
    return out


def cauta(q: Optional[str] = None, tip: Optional[str] = None,
          categorie: Optional[str] = None,
          tenant_id: Optional[int] = None, limit: int = 50) -> list:
    """Cauta in banca dupa cod/denumire (LIKE). Filtre optionale tip/categorie."""
    query = PretResursa.query
    if tenant_id is not None:
        query = query.filter(PretResursa.tenant_id == tenant_id)
    if tip:
        query = query.filter(PretResursa.tip == tip)
    if categorie:
        query = query.filter(PretResursa.categorie == categorie)
    if q:
        like = f'%{q.strip()}%'
        query = query.filter(db.or_(PretResursa.cod.ilike(like),
                                    PretResursa.denumire.ilike(like)))
    return query.order_by(PretResursa.tip, PretResursa.cod).limit(limit).all()


def categorii_existente(tenant_id: Optional[int] = None) -> list:
    """Categoriile distincte din banca (pt dropdown filtru)."""
    q = db.session.query(PretResursa.categorie).distinct()
    if tenant_id is not None:
        q = q.filter(PretResursa.tenant_id == tenant_id)
    return sorted(c[0] for c in q.all() if c[0])
