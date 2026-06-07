"""
Serviciu Audit Deviz - verificare pachet de deviz EXTERN (Faza Audit Deviz).

Ingestia unui set complet de deviz romanesc pe obiect:
  - F2  centralizator pe obiect (valori declarate per obiect + total + TVA)
  - F3  lista de cantitati per obiect (total fara TVA)
  - C6/C7/C8/C9  extrase de resurse: materiale / manopera / utilaje / transport

Produce:
  - Reconciliere L1: Sigma F3 (fara TVA) vs F2 (per obiect + total general)
  - Reconciliere L2: F3 == C6 + C7 + C8 + C9 (per obiect)
  - Structura de cost (material / manopera / utilaj / transport, %)
  - Agregare resurse (top materiale dupa valoare, top meserii dupa ore)
  - Detectie anomalii (transport 0, tarif uniform, utilaje 0, delte reconciliere)

PUR: nu face DB writes; intoarce un dict. Call-site-ul (routes) creeaza entitatile.
Suporta .xls (xlrd) si .xlsx (openpyxl) via import_engine._citeste_sheeturi.
Distinct de:
  - services/centralizator.py  (GENEREAZA centralizatorul din datele proprii)
  - services/deviz_extras.reconciliere()  (reconciliere intra-proiect plan vs extrase)
Aici se VERIFICA un pachet primit din exterior, ca unitate.
"""
from __future__ import annotations

import re
from collections import defaultdict

from services.gantt.normalizare import normalizeaza
from services.gantt.modele import _to_float
from services.gantt.import_engine import _citeste_sheeturi
from services.deviz_extras import parse_extras


_RX_TIP = re.compile(r'(?<![A-Za-z0-9])(F2|F3|C6|C7|C8|C9)(?![A-Za-z0-9])', re.IGNORECASE)
# Numarul de obiect = numarul DE DINAINTEA numelui (sare peste prefixul de
# disciplina, ex "004_"): 004_01_LUCRARI..._F3 -> obiect "01", nume "Lucrari...".
_RX_OBIECT = re.compile(
    r'(?:\d{1,3}[_\- ]+)?(\d{1,3})[_\- ]+(.+?)[_\- ]+(?:F2|F3|C6|C7|C8|C9)(?![A-Za-z0-9])',
    re.IGNORECASE)
_RX_OBIECT_F2 = re.compile(r'(?<!\d)(\d{1,2})\s+lucrari\b')


def ext_din_nume(nume: str) -> str:
    return nume.rsplit('.', 1)[-1].lower() if '.' in nume else 'xls'


def clasifica_fisier(nume: str) -> str | None:
    """Tipul de formular din numele fisierului: F2/F3/C6/C7/C8/C9 sau None."""
    m = _RX_TIP.search(nume)
    return m.group(1).upper() if m else None


def cheie_obiect(nume: str) -> tuple[str, str]:
    """(numar, nume_obiect) extras din numele fisierului."""
    m = _RX_OBIECT.search(nume)
    if m:
        return m.group(1).zfill(2), m.group(2).replace('_', ' ').strip().title()
    return '', nume


# ------------------------------------------------------------------ utilitare

def _randuri(continut: bytes, ext: str) -> list:
    """Randurile foii cu cele mai multe celule ne-goale (sare title-page)."""
    try:
        sheets = _citeste_sheeturi(continut, ext)
    except Exception:
        return []
    if not sheets:
        return []

    def scor(s):
        return sum(1 for r in s[1] if any(c not in (None, '') for c in (r or [])))

    return max(sheets, key=scor)[1] or []


def _numere(rand) -> list[float]:
    out = []
    for c in (rand or []):
        v = _to_float(c)
        if v:
            out.append(float(v))
    return out


def _total_label(randuri, include, exclude=()) -> float | None:
    """De jos in sus: primul rand care contine TOATE keyword-urile `include` si
    NICIUNUL din `exclude` (normalizat) -> max numeric din rand."""
    inc = [normalizeaza(k) for k in include]
    exc = [normalizeaza(k) for k in exclude]
    for r in reversed(randuri):
        blob = ' '.join(normalizeaza(str(c)) for c in (r or []) if c not in (None, ''))
        if blob and all(k in blob for k in inc) and not any(k in blob for k in exc):
            nums = _numere(r)
            if nums:
                return max(nums)
    return None


# ------------------------------------------------------------------ parsere

def parse_f2(randuri) -> dict:
    """Centralizatorul F2 -> {obiecte:{num:{nume,valoare}}, total_fara_tva, tva, total_cu_tva}."""
    obiecte: dict[str, dict] = {}
    for r in randuri:
        celule = [str(c) for c in (r or []) if c not in (None, '')]
        blob = ' '.join(normalizeaza(c) for c in celule)
        m = _RX_OBIECT_F2.search(blob)
        nums = _numere(r)
        if m and nums:
            num = m.group(1).zfill(2)
            # numele = celula text cea mai lunga din rand
            nume = max((c for c in celule), key=len, default=f'Obiect {num}')
            obiecte[num] = {'nume': nume.strip().title(), 'valoare': max(nums)}
    return {
        'obiecte': obiecte,
        'total_fara_tva': _total_label(randuri, ['total', 'fara tva'], exclude=['capitol']),
        'tva': _total_label(randuri, ['tva'], exclude=['total', 'capitol']),
        'total_cu_tva': _total_label(randuri, ['total', 'cu tva'], exclude=['capitol']),
    }


def total_f3(randuri) -> float | None:
    """TOTAL GENERAL (fara TVA) dintr-o lista F3."""
    return _total_label(randuri, ['total general'], exclude=['inclusiv'])


def total_extras(continut: bytes, ext: str, randuri, tip_fisier: str):
    """(total, [resurse]) pentru un extras C6/C7/C8/C9.
    C6/C7/C8 via parse_extras (sum valoare); C9 (transport) via label scan."""
    if tip_fisier in ('C6', 'C7', 'C8'):
        _tip, resurse = parse_extras(continut, ext)
        if resurse:
            total = round(sum(float(x.get('valoare') or 0) for x in resurse), 2)
            return total, resurse
    # C9 transport (sau fallback): scan dupa label TOTAL
    t = _total_label(randuri, ['total', 'transport']) or _total_label(randuri, ['total'])
    return (float(t) if t else 0.0), []


# ------------------------------------------------------------------ analiza

def _status_delta(delta: float, baza: float) -> str:
    if baza <= 0:
        return 'ok'
    pct = abs(delta) / baza * 100.0
    if pct <= 0.5:
        return 'ok'
    if pct <= 5:
        return 'atentie'
    return 'critic'


def analizeaza_set(fisiere: list[tuple[str, bytes]]) -> dict:
    """fisiere = [(nume, continut_bytes)]. Intoarce dict-ul de audit (vezi modulul)."""
    # 1. Grupare pe obiect + reperare F2
    grupe: dict[str, dict] = defaultdict(dict)  # num -> {tip: (nume, continut)}
    f2_file = None
    avertismente: list[str] = []
    for nume, continut in fisiere:
        tip = clasifica_fisier(nume)
        if tip is None:
            avertismente.append(f'Ignorat (tip necunoscut): {nume}')
            continue
        if tip == 'F2':
            f2_file = (nume, continut)
            continue
        num, _ob = cheie_obiect(nume)
        if not num:
            avertismente.append(f'Fara numar de obiect: {nume}')
            continue
        grupe[num][tip] = (nume, continut)

    # 2. F2 declarat
    f2 = {'obiecte': {}, 'total_fara_tva': None, 'tva': None, 'total_cu_tva': None}
    if f2_file:
        f2 = parse_f2(_randuri(f2_file[1], ext_din_nume(f2_file[0])))

    # 3. Per obiect: F3 + C6/C7/C8/C9
    mat_agg: dict[str, list] = {}     # cod -> [valoare, cantitate, um, denumire]
    trade_agg: dict[str, list] = {}   # meserie -> [ore, valoare]
    tarife_man: set = set()
    obiecte_out = []
    sum_f3 = sum_c6 = sum_c7 = sum_c8 = sum_c9 = 0.0

    for num in sorted(grupe):
        g = grupe[num]
        nume_ob = (cheie_obiect(g.get('F3', g.get('C6', ('', b'')))[0])[1]
                   or f2['obiecte'].get(num, {}).get('nume') or f'Obiect {num}')
        # F3
        f3v = 0.0
        if 'F3' in g:
            nm, ct = g['F3']
            f3v = total_f3(_randuri(ct, ext_din_nume(nm))) or 0.0
        else:
            avertismente.append(f'Obiect {num}: lipseste F3')
        # extrase
        vals = {'C6': 0.0, 'C7': 0.0, 'C8': 0.0, 'C9': 0.0}
        for tip in ('C6', 'C7', 'C8', 'C9'):
            if tip not in g:
                continue
            nm, ct = g[tip]
            rnd = _randuri(ct, ext_din_nume(nm))
            tot, resurse = total_extras(ct, ext_din_nume(nm), rnd, tip)
            vals[tip] = tot
            # agregare resurse
            if tip == 'C6':
                for x in resurse:
                    k = x.get('cod') or x.get('denumire', '')[:60]
                    a = mat_agg.setdefault(k, [0.0, 0.0, x.get('um') or '', x.get('denumire', '')])
                    a[0] += float(x.get('valoare') or 0)
                    a[1] += float(x.get('cantitate') or 0)
            elif tip == 'C7':
                for x in resurse:
                    k = x.get('denumire', '')[:80]
                    a = trade_agg.setdefault(k, [0.0, 0.0])
                    a[0] += float(x.get('cantitate') or 0)
                    a[1] += float(x.get('valoare') or 0)
                    if x.get('tarif_unitar'):
                        tarife_man.add(round(float(x['tarif_unitar']), 2))

        c6, c7, c8, c9 = vals['C6'], vals['C7'], vals['C8'], vals['C9']
        sum_f3 += f3v; sum_c6 += c6; sum_c7 += c7; sum_c8 += c8; sum_c9 += c9

        f2v = f2['obiecte'].get(num, {}).get('valoare')
        delta_l1 = (f3v - float(f2v)) if f2v is not None else None
        delta_l2 = f3v - (c6 + c7 + c8 + c9)
        status = _status_delta(delta_l2, f3v)
        if delta_l1 is not None and _status_delta(delta_l1, f3v) == 'critic':
            status = 'critic'

        obiecte_out.append({
            'numar': num, 'nume': nume_ob,
            'f3': round(f3v, 2), 'f2': (round(float(f2v), 2) if f2v is not None else None),
            'c6': round(c6, 2), 'c7': round(c7, 2), 'c8': round(c8, 2), 'c9': round(c9, 2),
            'delta_l1': (round(delta_l1, 2) if delta_l1 is not None else None),
            'delta_l2': round(delta_l2, 2), 'status': status,
        })

    # 4. Structura de cost
    baza = sum_c6 + sum_c7 + sum_c8 + sum_c9
    def pct(x):
        return round(x / baza * 100.0, 2) if baza else 0.0

    # 5. Top resurse
    top_materiale = [
        {'cod': k, 'denumire': v[3][:90], 'um': v[2], 'consum': round(v[1], 2),
         'valoare': round(v[0], 2)}
        for k, v in sorted(mat_agg.items(), key=lambda x: -x[1][0])[:15]
    ]
    top_meserii = [
        {'denumire': k, 'ore': round(v[0], 1), 'valoare': round(v[1], 2)}
        for k, v in sorted(trade_agg.items(), key=lambda x: -x[1][0])[:12]
    ]

    # 6. Anomalii
    anomalii = []

    def anom(tip, sev, mesaj, obiect=None, valoare=None):
        anomalii.append({'tip': tip, 'severitate': sev, 'mesaj': mesaj,
                         'obiect': obiect, 'valoare': valoare})

    if sum_c6 > 0 and sum_c9 <= 0:
        anom('transport_zero', 'critic',
             'Transport (C9) = 0 pe tot setul, desi exista material. Probabil nebugetat.',
             valoare=0)
    if len(tarife_man) == 1 and next(iter(tarife_man)) > 0:
        anom('tarif_uniform', 'atentie',
             f'Tarif manopera uniform ({next(iter(tarife_man))} lei/ora) pe toate meseriile.')
    for o in obiecte_out:
        if o['delta_l2'] is not None and _status_delta(o['delta_l2'], o['f3']) == 'critic':
            anom('reconciliere_l2', 'critic',
                 f'{o["nume"]}: F3 ({o["f3"]:,.0f}) != C6+C7+C8+C9 (delta {o["delta_l2"]:,.0f}).',
                 obiect=o['nume'], valoare=o['delta_l2'])
        if o['delta_l1'] is not None and _status_delta(o['delta_l1'], o['f3']) == 'critic':
            anom('reconciliere_l1', 'critic',
                 f'{o["nume"]}: F3 difera de valoarea din F2 (delta {o["delta_l1"]:,.0f}).',
                 obiect=o['nume'], valoare=o['delta_l1'])
        if o['c8'] <= 0 and o['f3'] > baza * 0.02 if baza else False:
            anom('utilaje_zero', 'info',
                 f'{o["nume"]}: utilaje (C8) = 0 la o valoare semnificativa.',
                 obiect=o['nume'], valoare=0)

    total_f2v = f2.get('total_fara_tva')
    delta_total = (sum_f3 - float(total_f2v)) if total_f2v else None
    if delta_total is not None and _status_delta(delta_total, sum_f3) == 'critic':
        anom('reconciliere_total', 'critic',
             f'Sigma F3 ({sum_f3:,.0f}) != Total F2 ({float(total_f2v):,.0f}).',
             valoare=round(delta_total, 2))

    tva = f2.get('tva')
    total_cu = f2.get('total_cu_tva')
    if total_cu is None and total_f2v:
        total_cu = round(float(total_f2v) * 1.21, 2)
    if tva is None and total_f2v:
        tva = round(float(total_f2v) * 0.21, 2)

    return {
        'total_f2': (round(float(total_f2v), 2) if total_f2v else None),
        'total_f3': round(sum_f3, 2),
        'tva': (round(float(tva), 2) if tva else None),
        'total_cu_tva': (round(float(total_cu), 2) if total_cu else None),
        'delta_reconciliere': (round(delta_total, 2) if delta_total is not None else None),
        'val_material': round(sum_c6, 2), 'val_manopera': round(sum_c7, 2),
        'val_utilaj': round(sum_c8, 2), 'val_transport': round(sum_c9, 2),
        'pct_material': pct(sum_c6), 'pct_manopera': pct(sum_c7),
        'pct_utilaj': pct(sum_c8), 'pct_transport': pct(sum_c9),
        'nr_obiecte': len(obiecte_out),
        'obiecte': obiecte_out,
        'top_materiale': top_materiale,
        'top_meserii': top_meserii,
        'anomalii': anomalii,
        'nr_anomalii': len(anomalii),
        'avertismente': avertismente,
    }
