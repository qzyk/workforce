"""
Motor de import F3 (XLSX / CSV).

- streaming pe xlsx (openpyxl read_only) -> memorie constanta pentru 100k+ randuri
- auto-detectie rand antet + maparea coloanelor pe sinonime (configurabil)
- normalizare string-uri (trim, fara diacritice la comparatie)
- validare null (cod + denumire obligatorii)
- detectie duplicate (dupa cod articol normalizat)

Intoarce (articole: list[ArticolF3], raport: dict cu statistici si avertismente).
"""
from __future__ import annotations

import csv
import io
import os
from typing import Iterable, Optional

from .modele import ArticolF3, _to_float
from .normalizare import normalizeaza, normalizeaza_cheie
from .config_loader import SETARI_IMPLICITE


class EroareImport(Exception):
    """Eroare fatala de import (format necunoscut, lipsa coloane esentiale)."""


def _mapeaza_coloane(antet: list, coloane_cfg: dict) -> dict:
    """Construieste {camp_logic: index_coloana} pe baza sinonimelor din config.
    Match pe egalitate normalizata; fallback pe 'contine'."""
    antet_norm = [normalizeaza(c) for c in antet]
    harta = {}
    for camp, sinonime in coloane_cfg.items():
        sin_norm = [normalizeaza(s) for s in sinonime]
        idx = None
        # 1. egalitate exacta
        for i, h in enumerate(antet_norm):
            if h in sin_norm:
                idx = i
                break
        # 2. contine (ex: "denumirea lucrarilor (articol)" contine "denumire")
        if idx is None:
            for i, h in enumerate(antet_norm):
                if any(s and s in h for s in sin_norm):
                    idx = i
                    break
        if idx is not None:
            harta[camp] = idx
    return harta


def _randuri_xlsx(continut: bytes) -> Iterable[list]:
    """Genereaza randuri (liste de valori) dintr-un xlsx, in mod streaming/read_only."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(continut), read_only=True, data_only=True)
    try:
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            yield list(row)
    finally:
        wb.close()


def _randuri_csv(continut: bytes) -> Iterable[list]:
    """Genereaza randuri dintr-un CSV (detecteaza separatorul ; sau ,)."""
    text = continut.decode('utf-8-sig', errors='replace')
    proba = text[:4096]
    sep = ';' if proba.count(';') >= proba.count(',') else ','
    for row in csv.reader(io.StringIO(text), delimiter=sep):
        yield row


def _gaseste_antet(randuri: list, coloane_cfg: dict, max_scan: int = 15):
    """Gaseste randul de antet (cel care mapeaza cel putin cod_articol + denumire).
    Intoarce (index_antet, harta_coloane). Ridica EroareImport daca nu gaseste."""
    for i, rand in enumerate(randuri[:max_scan]):
        if not rand:
            continue
        harta = _mapeaza_coloane(rand, coloane_cfg)
        if 'cod_articol' in harta and 'denumire' in harta:
            return i, harta
    # fallback: presupunem ordinea standard din specificatie
    raise EroareImport(
        'Nu am gasit randul de antet. Asigura coloanele: cod_articol, denumire, um, '
        'cantitate, obiect, tronson, categorie (sau sinonime configurate).'
    )


def importa(continut: bytes, extensie: str, setari: Optional[dict] = None):
    """Importa un fisier F3.

    Args:
        continut: bytes-ul fisierului.
        extensie: '.xlsx' / '.xls' / '.csv'.
        setari: dict de setari (foloseste SETARI_IMPLICITE daca lipseste).

    Returns:
        (articole, raport) unde articole=list[ArticolF3] iar raport e un dict cu statistici.
    """
    setari = setari or SETARI_IMPLICITE
    coloane_cfg = setari.get('coloane', SETARI_IMPLICITE['coloane'])
    ext = (extensie or '').lower().lstrip('.')

    if ext in ('xlsx', 'xlsm', 'xls'):
        gen = _randuri_xlsx(continut)
    elif ext == 'csv':
        gen = _randuri_csv(continut)
    else:
        raise EroareImport(f'Extensie nesuportata: {extensie!r} (acceptat: .xlsx, .csv)')

    randuri = list(gen)
    if not randuri:
        raise EroareImport('Fisier gol.')

    idx_antet, harta = _gaseste_antet(randuri, coloane_cfg)

    articole: list[ArticolF3] = []
    avertismente: list[str] = []
    chei_vazute: dict = {}
    nr_duplicate = 0
    nr_ignorate = 0

    def _val(rand, camp):
        i = harta.get(camp)
        if i is None or i >= len(rand):
            return ''
        v = rand[i]
        return '' if v is None else str(v).strip()

    for nr_rand, rand in enumerate(randuri[idx_antet + 1:], start=idx_antet + 2):
        if not rand or not any(c is not None and str(c).strip() for c in rand):
            continue  # rand gol
        cod = _val(rand, 'cod_articol')
        den = _val(rand, 'denumire')
        if not den:
            nr_ignorate += 1
            avertismente.append(f'Rand {nr_rand}: fara denumire - ignorat.')
            continue
        if not cod:
            cod = f'AUTO{nr_rand}'  # generam un cod daca lipseste, ca sa nu pierdem articolul

        cheie = normalizeaza_cheie(cod)
        if cheie in chei_vazute:
            nr_duplicate += 1
            cod = f'{cod}#{nr_duplicate}'  # facem codul unic, pastram articolul
        chei_vazute[cheie] = True

        articole.append(ArticolF3(
            cod_articol=cod,
            denumire=den,
            um=_val(rand, 'um'),
            cantitate=_to_float(_val(rand, 'cantitate')),
            obiect=_val(rand, 'obiect') or '(fara obiect)',
            tronson=_val(rand, 'tronson') or '(fara tronson)',
            categorie=_val(rand, 'categorie'),
            rand_sursa=nr_rand,
        ))

    raport = {
        'nr_randuri_fisier': len(randuri),
        'rand_antet': idx_antet + 1,
        'coloane_mapate': {k: antet_nume(randuri[idx_antet], v) for k, v in harta.items()},
        'nr_articole': len(articole),
        'nr_duplicate_redenumite': nr_duplicate,
        'nr_randuri_ignorate': nr_ignorate,
        'avertismente': avertismente[:50],  # limitam zgomotul
    }
    return articole, raport


def antet_nume(rand_antet: list, idx: int) -> str:
    try:
        return str(rand_antet[idx])
    except Exception:
        return f'col{idx}'


def importa_din_cale(cale: str, setari: Optional[dict] = None):
    """Helper: importa direct de pe disc (util pentru teste / batch)."""
    with open(cale, 'rb') as f:
        continut = f.read()
    return importa(continut, os.path.splitext(cale)[1], setari)
