"""
Parser Excel BoQ (XLSX + XLS) robust, cu auto-detectie.

Citeste liste de cantitati (devize) din Excel in forme VARIATE:
  - .xlsx (openpyxl) si .xls binar OLE2 (xlrd) - auto-detect engine via pandas
  - Header pe ORICE rand (auto-detectie prin keyword scan, nu pozitie fixa)
  - Coloane mapate dupa NUMELE din header (nu pozitie fixa) - tolerant la ordine
  - MULTIPLE sheet-uri (parcurge toate; sare peste TITLE PAGE / sheet-uri goale)
  - Randuri de GRUP/CAPITOL (cod + denumire fara UM) -> devin cod_capitol
  - Coloana MATERIAL separata (ex C25/30, S500C) -> prefixeaza denumirea

Testat pe:
  - eDevize export (header simplu, 1 sheet)
  - "Liste de cantitati" PT/DE (multi-sheet, header pe rand 4, coloane RO,
    grupe Infrastructura/Suprastructura, preturi goale)

Mapare coloane (keyword matching, normalizat fara diacritice):
    capitol      <- "capitol", "cod_capitol", "grupa"
    categorie    <- "categorie"
    denumire     <- "denumire", "descriere", "lucrare", "specificatie",
                    "capitol de lucrari"
    um           <- "u.m.", "um", "u/m", "unitate"
    cantitate    <- "cantitate", "cant"
    pret_unitar  <- "pret unitar", "p.u.", "pret/um", "pu"
    pret_material<- "pret material"
    pret_manopera<- "pret manopera"
    material     <- "material" (tip material, nu pret)
    cod_articol  <- "nr", "cod", "articol", "simbol", "pozitie", "poz"
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .base import Parser, ParseResult, ParseError


_VALID_CATEGORII = {'materiale', 'manopera', 'utilaje', 'transport', 'mixt'}

# UM-uri recunoscute (pentru a distinge articol vs rand de grup)
_UM_VALIDE = {
    'mc', 'm3', 'mp', 'm2', 'm²', 'm³', 'kg', 'ml', 'm', 'buc', 'ans',
    'to', 't', 'l', 'h', 'ora', 'cmp', 'gl', 'set', 'ce', 'kgcorp',
    'cm', 'ha', 'lit', 'tona', 'mii', 'km', 'mc.', 'mp.', 'buc.',
}


def _norm(value: Any) -> str:
    """Normalizeaza text: fara diacritice, lowercase, strip, fara punctuatie redundanta."""
    if value is None:
        return ''
    s = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode()
    return s.lower().strip()


def _clasifica_coloana(header_text: str) -> Optional[str]:
    """Decide ce camp reprezinta o coloana de header. Ordine specific->generic."""
    h = _norm(header_text)
    if not h:
        return None
    # SPECIFIC inainte de generic
    if 'capitol' in h and 'lucrari' not in h:
        return 'cod_capitol'
    if 'categorie' in h or 'categ' in h:
        return 'categorie'
    if 'pret' in h and ('unitar' in h or 'unit' in h or 'p.u' in h or '/um' in h):
        return 'pret_unitar'
    if 'pret' in h and 'material' in h:
        return 'pret_material'
    if 'pret' in h and ('manoper' in h or 'manop' in h):
        return 'pret_manopera'
    if 'pret' in h and ('total' in h):
        return 'pret_total'
    if 'denumire' in h or 'descriere' in h or 'specificat' in h \
            or 'capitol de lucrari' in h or 'lucrare' in h or 'lucrari' in h:
        return 'denumire'
    if h in ('um', 'u.m.', 'u/m', 'u.m', 'u m') or 'unitate' in h \
            or h.startswith('um') or 'u.m' in h:
        return 'um'
    if 'cantitate' in h or h == 'cant' or 'cantit' in h:
        return 'cantitate'
    if 'material' in h:  # dupa pret_material -> aici e tip material
        return 'material'
    if h in ('nr', 'nr.', 'nr crt', 'crt') or 'cod' in h or 'articol' in h \
            or 'simbol' in h or 'pozitie' in h or h == 'poz':
        return 'cod_articol'
    if 'mentiun' in h or 'obs' in h or 'observ' in h:
        return 'ignore'
    return None


# Keyword-uri care indica un rand de header (minim denumire + (um sau cantitate))
def _este_rand_header(cells: list) -> Optional[dict]:
    """
    Daca randul arata ca un header de tabel, returneaza maparea
    {camp: col_index}. Altfel None.
    """
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(cells):
        camp = _clasifica_coloana(cell)
        if camp and camp not in ('ignore',) and camp not in mapping:
            mapping[camp] = idx
    # Header valid daca avem denumire SI (um SAU cantitate)
    if 'denumire' in mapping and ('um' in mapping or 'cantitate' in mapping):
        return mapping
    return None


class ExcelBoQParser(Parser):
    """Parser Excel BoQ robust (.xlsx + .xls), auto-detect header + coloane + multi-sheet."""

    SURSA_COD = 'excel_xlsx'  # pastrat pentru compat (acopera si .xls)

    # Cate randuri scanam la inceputul fiecarui sheet ca sa gasim header-ul
    HEADER_SCAN_ROWS = 20

    def __init__(self, header_row: Optional[int] = None,
                 sheet_name: Optional[str] = None):
        """
        Args:
          header_row: optional override (1-based). Daca None -> auto-detect.
          sheet_name: optional - doar acest sheet. Daca None -> toate sheet-urile.
        """
        self.header_row = header_row
        self.sheet_name = sheet_name

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(sursa=self.SURSA_COD)

        try:
            import pandas as pd
        except ImportError:
            raise ParseError("Lib 'pandas' nu e instalat.")

        # pandas alege engine automat: .xlsx->openpyxl, .xls->xlrd
        try:
            ext = file_path.rsplit('.', 1)[-1].lower()
            engine = 'xlrd' if ext == 'xls' else 'openpyxl'
            sheets = pd.read_excel(file_path, sheet_name=None, header=None,
                                   dtype=str, engine=engine)
        except ImportError as e:
            raise ParseError(
                f'Lipseste lib pentru {ext}: {e}. '
                f'Pentru .xls instaleaza xlrd; pentru .xlsx openpyxl.'
            )
        except Exception as e:
            raise ParseError(f'Nu pot deschide Excel: {e}') from e

        result.stats['sheets_total'] = len(sheets)
        result.stats['sheets_procesate'] = []

        ordine_global = 0
        for sheet_nume, df in sheets.items():
            if self.sheet_name and sheet_nume != self.sheet_name:
                continue
            ent_sheet, ordine_global = self._parse_sheet(
                sheet_nume, df, result, ordine_global
            )
            if ent_sheet > 0:
                result.stats['sheets_procesate'].append(
                    {'sheet': sheet_nume, 'articole': ent_sheet}
                )

        if not result.entities and not result.errors:
            result.add_error(
                'Niciun articol gasit. Verifica daca fisierul contine un tabel '
                'cu coloane Denumire + U.M. + Cantitate (header pe orice rand).'
            )

        result.stats['entities_count'] = len(result.entities)
        result.stats['warnings_count'] = len(result.warnings)
        return result

    # ------------------------------------------------------------
    # Per sheet
    # ------------------------------------------------------------

    def _parse_sheet(self, sheet_nume, df, result: ParseResult,
                     ordine_global: int) -> tuple[int, int]:
        """Parse un sheet. Returneaza (numar_articole, ordine_global_actualizat)."""
        import pandas as pd

        if df is None or df.empty:
            return 0, ordine_global

        rows = df.values.tolist()
        n = len(rows)

        # 1. Detectez header-ul
        header_map = None
        header_idx = None
        if self.header_row:
            hr = self.header_row - 1
            if 0 <= hr < n:
                header_map = _este_rand_header(rows[hr])
                header_idx = hr
        if header_map is None:
            for i in range(min(self.HEADER_SCAN_ROWS, n)):
                m = _este_rand_header(rows[i])
                if m:
                    header_map = m
                    header_idx = i
                    break

        if header_map is None:
            # Sheet fara tabel valid (ex TITLE PAGE) - skip silent
            return 0, ordine_global

        # 2. Parcurg randurile de date (dupa header)
        articole = 0
        cod_capitol_curent = None
        col_den = header_map['denumire']
        col_um = header_map.get('um')
        col_cant = header_map.get('cantitate')
        col_cod = header_map.get('cod_articol')
        col_cap = header_map.get('cod_capitol')
        col_pret = header_map.get('pret_unitar')
        col_pret_mat = header_map.get('pret_material')
        col_pret_man = header_map.get('pret_manopera')
        col_material = header_map.get('material')
        col_categ = header_map.get('categorie')

        def _cell(row, idx):
            if idx is None or idx >= len(row):
                return None
            v = row[idx]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            s = str(v).strip()
            return s if s and s.lower() != 'nan' else None

        for i in range(header_idx + 1, n):
            row = rows[i]
            denumire = _cell(row, col_den)
            um = _cell(row, col_um) if col_um is not None else None
            cod = _cell(row, col_cod) if col_cod is not None else None
            cant_raw = _cell(row, col_cant) if col_cant is not None else None

            if not denumire and not cod:
                continue  # rand gol

            um_norm = _norm(um) if um else ''
            este_um_valid = um_norm in _UM_VALIDE or (
                um and len(um) <= 6 and any(c.isalpha() for c in um))
            den_norm = _norm(denumire)

            # Rand FARA UM si FARA cantitate: grup/capitol, nota, total sau zgomot
            if not este_um_valid and not cant_raw:
                # zgomot pur (cod orfan fara denumire) -> skip
                if not denumire:
                    continue
                # note / totaluri -> skip
                if den_norm in ('note', 'notes', 'nota', 'note /notes',
                                'note/notes', 'observatii') \
                        or den_norm.startswith('total') \
                        or den_norm.startswith('subtotal'):
                    continue
                # altfel = grup/capitol (mosteneste de articolele urmatoare)
                cod_capitol_curent = denumire.strip()
                continue

            # ARTICOL
            cantitate = self._decimal(cant_raw, result,
                                      f'{sheet_nume} cantitate "{denumire[:30] if denumire else cod}"',
                                      default=Decimal('0'))
            pret_unitar = self._decimal(
                _cell(row, col_pret) if col_pret is not None else None,
                result, 'pret', default=Decimal('0'))
            pret_mat = self._decimal(
                _cell(row, col_pret_mat) if col_pret_mat is not None else None,
                result, 'pret_mat', default=None)
            pret_man = self._decimal(
                _cell(row, col_pret_man) if col_pret_man is not None else None,
                result, 'pret_man', default=None)

            material = _cell(row, col_material) if col_material is not None else None
            # Prefixez denumirea cu materialul (ex "Beton egalizare [C12/15]")
            denumire_final = denumire or f'(articol {cod})'
            if material and material.lower() not in denumire_final.lower():
                denumire_final = f'{denumire_final} ({material})'

            # Warning daca UM lipseste pe un articol cu cantitate (default aplicat)
            if not este_um_valid:
                result.add_warning(
                    f'{sheet_nume}: articol "{denumire_final[:40]}" fara U.M. - '
                    'aplicat default "buc".'
                )

            categorie_raw = _cell(row, col_categ) if col_categ is not None else None
            categorie = (_norm(categorie_raw) if categorie_raw else 'mixt')
            if categorie_raw and categorie not in _VALID_CATEGORII:
                result.add_warning(
                    f'{sheet_nume}: categorie "{categorie_raw}" necunoscuta '
                    f'pentru "{denumire_final[:40]}" - default "mixt".'
                )
                categorie = 'mixt'
            elif categorie not in _VALID_CATEGORII:
                categorie = 'mixt'

            ordine_global += 1
            articole += 1
            result.entities.append({
                'cod_articol': (cod or f'{sheet_nume}-{ordine_global}').strip()[:50],
                'cod_capitol': cod_capitol_curent,
                'denumire': denumire_final,
                'um': (um or 'buc').strip()[:20],
                'cantitate_oferta': cantitate,
                'pret_unitar': pret_unitar,
                'categorie': categorie,
                'ordine': ordine_global,
                'valoare_materiale_unitar': pret_mat,
                'valoare_manopera_unitar': pret_man,
                'valoare_utilaj_unitar': None,
                'valoare_transport_unitar': None,
            })

        return articole, ordine_global

    @staticmethod
    def _decimal(value: Any, result: ParseResult, context: str = '',
                 default: Optional[Decimal] = None) -> Optional[Decimal]:
        if value is None or value == '':
            return default
        try:
            s = str(value).strip()
            # Toleranta: separatori mii (spatiu/punct), virgula decimala RO
            s = s.replace(' ', '')
            # Daca are si '.' si ',' -> '.' e mii, ',' e decimal (format RO)
            if '.' in s and ',' in s:
                s = s.replace('.', '').replace(',', '.')
            elif ',' in s:
                s = s.replace(',', '.')
            return Decimal(s)
        except (InvalidOperation, ValueError):
            if context:
                result.add_warning(f'Valoare numerica invalida "{value}" ({context}).')
            return default
