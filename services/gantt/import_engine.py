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


# ----------------------------------------------------------------------------
# Detectie format dupa CONTINUT (magic bytes), nu doar dupa extensie.
# Rezolva eroarea "File is not a zip file": un .xls binar vechi sau un export
# HTML/XML de la softuri de devize (eDevize, WinDev, Devize2000) ajunge adesea
# cu extensia .xlsx, dar openpyxl citeste DOAR .xlsx real (arhiva zip).
# ----------------------------------------------------------------------------
_MAGIC_OLE2 = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'  # .xls binar (OLE2/BIFF)


def _decode_best(continut: bytes) -> str:
    """Decodeaza bytes incercand mai multe codari (utf-8, Windows-1250 RO, latin-1)."""
    if continut[:3] == b'\xef\xbb\xbf':
        continut = continut[3:]
    for enc in ('utf-8', 'cp1250', 'iso-8859-2', 'latin-1'):
        try:
            return continut.decode(enc)
        except UnicodeDecodeError:
            continue
    return continut.decode('utf-8', errors='replace')


def _randuri_xls_binar(continut: bytes) -> Iterable[list]:
    """Citeste un .xls binar (OLE2/BIFF) via xlrd. Primul sheet ne-gol."""
    try:
        import xlrd
    except ImportError:
        raise EroareImport(
            'Fisierul e un Excel binar vechi (.xls). Instaleaza "xlrd" '
            '(pe PythonAnywhere: ~/.virtualenvs/workforce-env/bin/pip install xlrd) '
            'sau re-salveaza fisierul ca .xlsx (Salvare ca -> Registru Excel) ori .csv.'
        )
    wb = xlrd.open_workbook(file_contents=continut)
    for sh in wb.sheets():
        if sh.nrows == 0:
            continue
        for r in range(sh.nrows):
            yield [sh.cell_value(r, c) for c in range(sh.ncols)]
        return  # doar primul sheet cu continut (parity cu openpyxl .active)


def _randuri_html(continut: bytes) -> Iterable[list]:
    """Parseaza un 'Excel' care e de fapt HTML (<table>) - export tipic de devize."""
    from html.parser import HTMLParser

    class _Tabel(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.randuri: list = []
            self._rand = None
            self._cel: list = []
            self._in_cel = False

        def handle_starttag(self, tag, attrs):
            t = tag.lower()
            if t == 'tr':
                self._rand = []
            elif t in ('td', 'th'):
                self._cel = []
                self._in_cel = True
            elif t == 'br' and self._in_cel:
                self._cel.append(' ')

        def handle_endtag(self, tag):
            t = tag.lower()
            if t in ('td', 'th') and self._rand is not None:
                self._rand.append(''.join(self._cel).strip())
                self._in_cel = False
            elif t == 'tr' and self._rand is not None:
                self.randuri.append(self._rand)
                self._rand = None

        def handle_data(self, data):
            if self._in_cel:
                self._cel.append(data)

    p = _Tabel()
    p.feed(_decode_best(continut))
    for r in p.randuri:
        yield r


def _randuri_spreadsheetml(continut: bytes) -> Iterable[list]:
    """Parseaza 'XML Spreadsheet 2003' (SpreadsheetML): Workbook/Worksheet/Row/Cell/Data."""
    import xml.etree.ElementTree as ET
    ns = '{urn:schemas-microsoft-com:office:spreadsheet}'
    root = ET.fromstring(_decode_best(continut))
    for ws in root.iter(f'{ns}Worksheet'):
        table = ws.find(f'{ns}Table')
        if table is None:
            continue
        randuri = []
        for row in table.findall(f'{ns}Row'):
            celule: list = []
            col = 0
            for cell in row.findall(f'{ns}Cell'):
                idx = cell.get(f'{ns}Index')  # poate sari peste coloane goale (1-based)
                if idx:
                    target = int(idx) - 1
                    while col < target:
                        celule.append('')
                        col += 1
                data = cell.find(f'{ns}Data')
                celule.append(data.text if (data is not None and data.text) else '')
                col += 1
            randuri.append(celule)
        if randuri:
            yield from randuri
            return


def _detecteaza_si_citeste(continut: bytes, ext: str) -> Iterable[list]:
    """Alege parserul potrivit dupa CONTINUT (magic bytes), apoi dupa extensie."""
    if not continut:
        raise EroareImport('Fisier gol.')
    cap = continut[:8]
    raw = continut[3:] if continut[:3] == b'\xef\xbb\xbf' else continut
    proba = raw[:8192].lstrip().lower()

    if cap[:2] == b'PK':                                     # zip -> .xlsx/.xlsm real
        return _randuri_xlsx(continut)
    if cap == _MAGIC_OLE2:                                   # OLE2 -> .xls binar vechi
        return _randuri_xls_binar(continut)
    if proba[:5] == b'<?xml' and b'spreadsheet' in proba:    # SpreadsheetML 2003
        return _randuri_spreadsheetml(continut)
    if proba[:1] == b'<' and (b'<table' in proba or b'<html' in proba
                              or b'<!doctype html' in proba):  # HTML <table> deghizat
        return _randuri_html(continut)

    # Fara semnatura clara -> dupa extensie
    if ext == 'csv':
        return _randuri_csv(continut)
    if ext in ('xlsx', 'xlsm'):
        return _randuri_xlsx(continut)
    if ext == 'xls':
        return _randuri_xls_binar(continut)
    return _randuri_csv(continut)  # ultim fallback: text delimitat


def _mesaj_format(continut: bytes, e: Exception) -> str:
    """Mesaj prietenos in functie de formatul real detectat (pentru flash UI)."""
    cap = continut[:8] if continut else b''
    proba = (continut[3:] if continut[:3] == b'\xef\xbb\xbf' else continut)[:64].lstrip().lower()
    if cap == _MAGIC_OLE2:
        return ('Fisierul e un Excel binar vechi (.xls), nu .xlsx. Deschide-l in Excel '
                'si foloseste "Salvare ca -> Registru Excel (.xlsx)" sau salveaza ca .csv. '
                f'(detaliu tehnic: {e})')
    if proba[:1] == b'<':
        return ('Fisierul pare HTML/XML, nu un Excel real (export tipic de la softuri de '
                'devize). Deschide-l in Excel si "Salveaza ca -> .xlsx" sau .csv. '
                f'(detaliu tehnic: {e})')
    if cap[:2] != b'PK':
        return ('Formatul fisierului nu e un Excel valid (.xlsx trebuie sa fie arhiva zip). '
                f'Re-salveaza ca .xlsx (Registru Excel) sau .csv. (detaliu tehnic: {e})')
    return f'Nu pot citi fisierul Excel: {e}. Re-salveaza ca .xlsx sau .csv.'


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

    # Detectie dupa CONTINUT (magic bytes) -> robust la .xls binar / HTML deghizat in .xlsx
    try:
        randuri = list(_detecteaza_si_citeste(continut, ext))
    except EroareImport:
        raise
    except Exception as e:  # BadZipFile, XML parse, xlrd etc. -> mesaj prietenos
        raise EroareImport(_mesaj_format(continut, e)) from e
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
