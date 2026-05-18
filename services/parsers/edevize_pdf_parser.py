"""
Parser PDF eDevize / ALDOC (Formular F3 standard romanesc HG907/2016).

Folosit pentru import devize generate de programul eDevize.ro cand nu avem
XML/Excel disponibil. Testat pe layout-ul curent al eDevize (2026).

Strategie:
  - Citeste TOATE paginile PDF cu pypdf.
  - Filtreaza paginile F3 (header "Formular F3" + "SECTIUNEA TEHNICA").
  - State machine peste liniile concatenate, cu 3 stari:
      WAITING_ARTICLE -> READING_ARTICLE -> READING_SUBLINES -> WAITING_ARTICLE
  - Per articol, extrage:
      * nr ordine (din PDF)
      * cod_articol (alfanumeric, cu sufixe %, #, >, ^, * preserved)
      * denumire (single sau multi-line)
      * UM, cantitate, pret unitar
      * 4 sub-rânduri: material/manopera/utilaj/transport (valori unitare)
  - cod_capitol = ultimul "Stadiul fizic: ..." vazut.

NU parseaza paginile CENTRALIZATOR (sunt summary, valori derivate din F3).
NU parseaza Recapitulatia (Coeficienti T1->T4, TVA). Daca user vrea, se poate
extinde in viitor.

Format numerice eDevize PDF:
  - virgula = thousands separator ("2,260.000" = 2260.000)
  - punct   = decimal separator ("13.97" = 13.97)

Aceasta convenție difera de XML eDevize (care era RO-style "650,00").
Parser-ul PDF foloseste US-style, vazut in toate exemplele reale.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from .base import Parser, ParseResult, ParseError


# Pagini F3: contin acest header
F3_MARKERS = ('Formular F3', 'SECTIUNEA TEHNICA')

# Header articol: "<nr> <cod>[suffix] - <rest>"
ARTICOL_HEADER_RE = re.compile(
    r'^(?P<nr>\d+)\s+'
    r'(?P<cod>[A-Z][A-Z0-9\-_.]+[%#>^*]?)'
    r'\s+-\s+'
    r'(?P<rest>.+)$'
)

# Sub-linie: "material: 0.00 0.00" sau "manopera:" etc.
SUBLINIE_RE = re.compile(
    r'^(?P<tip>material|manopera|utilaj|transport):\s+'
    r'(?P<unitar>[\d.,]+)\s+'
    r'(?P<total>[\d.,]+)$'
)

# Linia cu UM + 3 valori (pentru cazul denumire multi-linie)
# UM e ultimul cuvant non-numeric inainte de 3 numere.
UM_LINE_RE = re.compile(
    r'^(?P<prefix>(?:\S+\s+)*?)'              # Optional prefix words
    r'(?P<um>\S+?)\s+'                         # UM
    r'(?P<cant>[\d.,]+)\s+'                    # Cantitate
    r'(?P<pret>[\d.,]+)\s+'                    # Pret unitar
    r'(?P<total>[\d.,]+)\s*$'                  # Total
)

# UM-uri recunoscute (extensibil). Validare ca un token e intr-adevar UM.
UM_VALIDE = {
    'mc', 'mp', 'kg', 'ml', 'm', 'buc', 'ans', 'to', 't', 'l', 'h',
    'ora', 'cmp', 'gl', 'set', 'ce', 'kgcorp', 'cm', 'ha', 'lit',
    'tona', 'mii', 'mp2', 'm2', 'm3', 'kw', 'kwh', 'mwh',
}

# Stadiul fizic: extrage cod_capitol
STADIU_RE = re.compile(r'Stadiul fizic:\s*(.+)$')

# Linii de TOTAL / Recapitulatie / header repetat - skip
SKIP_LINE_PATTERNS = (
    re.compile(r'^TOTAL\s+[A-Z]'),
    re.compile(r'^TOTAL\s+\d'),
    re.compile(r'^Antet stanga'),
    re.compile(r'^Formular generat'),
    re.compile(r'^Deviz\s+"\d+"\s+-\s+Formular'),
    re.compile(r'^SECTIUNEA TEHNICA'),
    re.compile(r'^Nr\.\s+Capitol'),
    re.compile(r'^0\s+1\s+2\s+3'),
)


class EDevizePDFParser(Parser):
    """Parser PDF eDevize Formular F3."""

    SURSA_COD = 'edevize_pdf'

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(sursa=self.SURSA_COD)

        try:
            import pypdf
        except ImportError:
            raise ParseError(
                "Lib 'pypdf' nu e instalat. Ruleaza: pip install pypdf>=6.0.0"
            )

        try:
            reader = pypdf.PdfReader(file_path)
        except Exception as e:
            raise ParseError(f'Nu pot deschide PDF: {e}') from e

        # Concatenez doar paginile F3
        f3_text_parts: list[str] = []
        f3_pages_count = 0
        for page in reader.pages:
            try:
                text = page.extract_text() or ''
            except Exception:
                continue
            if all(m in text for m in F3_MARKERS):
                f3_text_parts.append(text)
                f3_pages_count += 1

        result.stats['total_pages'] = len(reader.pages)
        result.stats['f3_pages'] = f3_pages_count

        if f3_pages_count == 0:
            result.add_error(
                'Nu am gasit pagini Formular F3 in PDF. '
                'Verifica ca PDF-ul e un export eDevize standard (cu F3).'
            )
            return result

        all_text = '\n'.join(f3_text_parts)
        result.stats['extracted_chars'] = len(all_text)

        # State machine
        entities = self._parse_text(all_text, result)
        result.entities = entities

        # Atribui ordine globala
        for i, e in enumerate(entities, start=1):
            e['ordine'] = i

        result.stats['entities_count'] = len(entities)
        result.stats['warnings_count'] = len(result.warnings)
        return result

    # ------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------

    def _parse_text(self, text: str, result: ParseResult) -> list[dict]:
        entities: list[dict] = []
        current: Optional[dict] = None
        denumire_buf: list[str] = []
        cod_capitol: Optional[str] = None

        def finalize(art: dict):
            """Adauga articol-ul curent la rezultate daca e complet."""
            if not art.get('um') or not art.get('cantitate_oferta'):
                result.add_warning(
                    f"Articol nr={art.get('nr', '?')} cod={art.get('cod_articol', '?')}: "
                    'UM sau cantitate lipsa - articol incomplet skipped.'
                )
                return
            denumire = art.get('denumire', '').strip()
            if not denumire:
                denumire = f'(Articol {art.get("cod_articol", "?")})'
            art['denumire'] = denumire
            # Deduc categorie principala din valorile unitare (cea mai mare)
            art['categorie'] = self._infer_categorie(art)
            # Lipsesc valori unitare detaliate? Default None ok in model.
            entities.append(art)

        for raw_line in text.split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            if self._should_skip(line):
                continue

            # Stadiul fizic - cod_capitol
            m = STADIU_RE.match(line)
            if m:
                cod_capitol = m.group(1).strip()
                continue

            # Sub-linie material/manopera/utilaj/transport
            m = SUBLINIE_RE.match(line)
            if m and current:
                tip = m.group('tip')
                unitar = self._parse_decimal(m.group('unitar'))
                # Mapare PDF (singular) -> camp model (plural pentru materiale)
                # PDF: material/manopera/utilaj/transport
                # Model: valoare_materiale_unitar / valoare_manopera_unitar /
                #        valoare_utilaj_unitar / valoare_transport_unitar
                field_map = {
                    'material': 'valoare_materiale_unitar',
                    'manopera': 'valoare_manopera_unitar',
                    'utilaj': 'valoare_utilaj_unitar',
                    'transport': 'valoare_transport_unitar',
                }
                current[field_map[tip]] = unitar
                if tip == 'transport':
                    # Ultima sub-linie - finalizam articol
                    if denumire_buf:
                        existing = current.get('denumire', '').strip()
                        adds = ' '.join(denumire_buf).strip()
                        current['denumire'] = (existing + ' ' + adds).strip() if existing else adds
                        denumire_buf = []
                    finalize(current)
                    current = None
                continue

            # Header articol
            m = ARTICOL_HEADER_RE.match(line)
            if m:
                # Daca era unul incomplet, il finalizam best-effort
                if current:
                    if denumire_buf and not current.get('denumire'):
                        current['denumire'] = ' '.join(denumire_buf).strip()
                    if current.get('um'):
                        finalize(current)
                # Init articol nou
                current = {
                    'nr': m.group('nr'),
                    'cod_articol': m.group('cod').strip(),
                    'cod_capitol': cod_capitol,
                }
                denumire_buf = []
                rest = m.group('rest').strip()
                # Verific daca rest contine UM + 3 numere (one-liner).
                # Daca NU, rest e parte din denumire (caz multi-linie).
                if not self._try_extract_um_values(rest, current, denumire_buf):
                    denumire_buf.append(rest)
                continue

            # Linia cu UM + valori (caz denumire multi-linie)
            if current and not current.get('um'):
                if self._try_extract_um_values(line, current, denumire_buf, allow_only_um=True):
                    continue
                # Altfel, continua denumirea
                denumire_buf.append(line)
                continue

            # Linie izolata fara articol curent - skip

        # Finalizam ultimul articol daca exista
        if current:
            if denumire_buf and not current.get('denumire'):
                current['denumire'] = ' '.join(denumire_buf).strip()
            if current.get('um'):
                finalize(current)

        return entities

    def _try_extract_um_values(self, text: str, current: dict,
                                denumire_buf: list[str],
                                allow_only_um: bool = False) -> bool:
        """
        Incearca sa extraga UM + cantitate + pret + total din `text`.

        Daca match si UM e valid:
          - allow_only_um=True: presupunem ca toata `text` inainte de UM e
            parte din denumire (cazul liniei separate)
          - allow_only_um=False: presupunem ca toata `text` inainte de UM e
            denumire (cazul one-liner; rest inainte de UM = denumire)
        """
        m = UM_LINE_RE.match(text)
        if not m:
            return False
        um_token = m.group('um').lower()
        if um_token not in UM_VALIDE:
            return False
        cant = self._parse_decimal(m.group('cant'))
        pret = self._parse_decimal(m.group('pret'))
        if cant is None or pret is None:
            return False
        current['um'] = um_token
        current['cantitate_oferta'] = cant
        current['pret_unitar'] = pret
        prefix = (m.group('prefix') or '').strip()
        if prefix:
            existing = current.get('denumire', '').strip()
            current['denumire'] = (existing + ' ' + prefix).strip() if existing else prefix
        return True

    @staticmethod
    def _should_skip(line: str) -> bool:
        for pat in SKIP_LINE_PATTERNS:
            if pat.match(line):
                return True
        return False

    @staticmethod
    def _parse_decimal(s: str) -> Optional[Decimal]:
        """Parse numar PDF eDevize: US-style (comma=thousands, dot=decimal)."""
        if not s:
            return None
        try:
            return Decimal(s.replace(',', ''))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _infer_categorie(art: dict) -> str:
        """Deduc categoria principala din valorile unitare (cea mai mare)."""
        vals = {
            'materiale': art.get('valoare_materiale_unitar') or Decimal('0'),
            'manopera': art.get('valoare_manopera_unitar') or Decimal('0'),
            'utilaje': art.get('valoare_utilaj_unitar') or Decimal('0'),
            'transport': art.get('valoare_transport_unitar') or Decimal('0'),
        }
        # Daca toate sunt 0, default 'mixt'
        nonzero = {k: v for k, v in vals.items() if v > 0}
        if not nonzero:
            return 'mixt'
        # Daca mai mult de 1 categorie are valoare -> 'mixt'
        if len(nonzero) > 1:
            return 'mixt'
        return next(iter(nonzero.keys()))
