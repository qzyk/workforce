"""
Parser XML eDevize / generic deviz romanesc.

NOTA IMPORTANTA: formatul exact al fisierelor exportate de eDevize/ALDOC
nu e public-documentat. Acest parser implementeaza un schema generica
tolerant la variante uzuale:

    <Oferta>                          (sau <Deviz>)
        <Antet>                       (optional)
            <Numar>...</Numar>
            <DataEmitere>2025-01-15</DataEmitere>
            <ValoareTotala>1250000.00</ValoareTotala>
            <Moneda>RON</Moneda>
        </Antet>
        <Capitole>
            <Capitol cod="CA01" denumire="Terasamente">
                <Articole>
                    <Articol cod="CA01A1" denumire="Sapatura manuala" um="mc"
                             cantitate="150.0000" pret_unitar="45.50"
                             categorie="manopera">
                        <Detalii>
                            <ValoareManopera>30.00</ValoareManopera>
                            <ValoareMateriale>10.00</ValoareMateriale>
                            <ValoareUtilaj>5.50</ValoareUtilaj>
                            <ValoareTransport>0</ValoareTransport>
                        </Detalii>
                    </Articol>
                </Articole>
            </Capitol>
        </Capitole>
    </Oferta>

Cand vom avea sample real eDevize, doar `_field_aliases` si XPath-urile
trebuie ajustate - structura entitatii ramane identica.

Mapare XML -> dict pentru `PozitieBoQ`:
    Capitol cod/denumire -> cod_capitol + (capitol = ordine_grup)
    Articol cod          -> cod_articol
    Articol denumire     -> denumire
    Articol um           -> um (unitate de masura)
    Articol cantitate    -> cantitate_oferta (Decimal 14,4)
    Articol pret_unitar  -> pret_unitar (Decimal 14,4)
    Articol categorie    -> categorie (materiale/manopera/utilaje/transport/mixt)
    Detalii Valoare*     -> valoare_*_unitar (Decimal 14,4)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .base import Parser, ParseResult, ParseError


# Aliasuri tag-uri pentru tolerance la variante (camelCase, PascalCase, snake)
_ALIAS_OFERTA = {'Oferta', 'Deviz', 'OFERTA', 'DEVIZ'}
_ALIAS_CAPITOL = {'Capitol', 'capitol', 'CAPITOL'}
_ALIAS_ARTICOL = {'Articol', 'articol', 'ARTICOL', 'Pozitie', 'pozitie'}
_ALIAS_CATEGORIE_DEFAULT = 'mixt'
_VALID_CATEGORII = {'materiale', 'manopera', 'utilaje', 'transport', 'mixt'}


class EDevizeXMLParser(Parser):
    """Parser XML eDevize / generic deviz romanesc."""

    SURSA_COD = 'edevize_xml'

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(sursa=self.SURSA_COD)

        try:
            tree = ET.parse(file_path)
        except ET.ParseError as e:
            raise ParseError(f'XML invalid: {e}') from e
        except OSError as e:
            raise ParseError(f'Nu pot citi fisierul: {e}') from e

        root = tree.getroot()
        # Acceptam Oferta / Deviz ca root sau imbricat la primul nivel
        if self._localname(root.tag) not in _ALIAS_OFERTA:
            # Cautam un copil care e Oferta/Deviz
            inner = self._find_alias(root, _ALIAS_OFERTA)
            if inner is None:
                result.add_error(
                    'Root XML nu e <Oferta> sau <Deviz> (sau echivalent).'
                )
                return result
            root = inner

        # Metadata din <Antet> (optional)
        antet = self._find_any(root, ['Antet', 'antet', 'ANTET',
                                      'Header', 'header'])
        if antet is not None:
            result.stats['numar'] = self._text_any(
                antet, ['Numar', 'numar', 'Number']
            )
            result.stats['data_emitere'] = self._text_any(
                antet, ['DataEmitere', 'data_emitere', 'IssueDate']
            )
            result.stats['valoare_totala'] = self._text_any(
                antet, ['ValoareTotala', 'valoare_totala', 'TotalValue']
            )
            result.stats['moneda'] = self._text_any(
                antet, ['Moneda', 'moneda', 'Currency']
            ) or 'RON'

        # Capitole + articole. Suportam si <Articole> direct sub <Oferta>
        # (fara capitole) ca format simplificat.
        capitole = self._collect_capitole(root)
        if capitole:
            ordine_global = 0
            for cap_data in capitole:
                # Inregistrez "capitol" ca prima pozitie din grup (cod=cod_capitol)
                # Daca utilizatorul vrea separat capitol vs articole, putem in viitor
                # crea o entitate "tip=capitol". Pentru simplitate, doar marcam
                # cod_capitol pe articole.
                for art_el in cap_data['articole']:
                    ordine_global += 1
                    art = self._parse_articol(
                        art_el, cap_data['cod'], ordine_global, result
                    )
                    if art:
                        result.entities.append(art)
        else:
            # Cautam articole direct (fara capitole)
            articole_container = self._find_any(
                root, ['Articole', 'articole', 'Pozitii', 'pozitii']
            )
            if articole_container is not None:
                ordine_global = 0
                for art_el in articole_container:
                    if self._localname(art_el.tag) in _ALIAS_ARTICOL:
                        ordine_global += 1
                        art = self._parse_articol(
                            art_el, None, ordine_global, result
                        )
                        if art:
                            result.entities.append(art)

        if not result.entities and not result.errors:
            result.add_error(
                'Nu am gasit niciun articol/pozitie in XML. '
                'Verifica structura fisierului (<Capitol>/<Articol> sau '
                '<Articole>/<Articol>).'
            )

        result.stats['entities_count'] = len(result.entities)
        result.stats['warnings_count'] = len(result.warnings)
        return result

    # ------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------

    @staticmethod
    def _localname(tag: str) -> str:
        """Strip namespace prefix daca exista."""
        if tag.startswith('{'):
            return tag.split('}', 1)[1]
        return tag

    def _find_alias(self, parent: ET.Element, aliases: set[str]):
        for child in parent:
            if self._localname(child.tag) in aliases:
                return child
        return None

    def _find_any(self, parent: ET.Element, names: list[str]):
        for n in names:
            for child in parent:
                if self._localname(child.tag) == n:
                    return child
        return None

    def _text_any(self, parent: ET.Element, names: list[str],
                  default: str = '') -> str:
        for n in names:
            for child in parent:
                if self._localname(child.tag) == n and child.text:
                    return child.text.strip()
        return default

    def _collect_capitole(self, root: ET.Element) -> list[dict]:
        """Cauta <Capitole>/<Capitol> si returneaza lista de {'cod', 'articole'}."""
        rezultat = []
        capitole_container = self._find_any(
            root, ['Capitole', 'capitole', 'CAPITOLE', 'Chapters']
        )
        if capitole_container is None:
            return rezultat

        for cap_el in capitole_container:
            if self._localname(cap_el.tag) not in _ALIAS_CAPITOL:
                continue
            cod = cap_el.get('cod') or cap_el.get('Cod') or \
                  self._text_any(cap_el, ['Cod', 'cod']) or None
            # Articole sub Capitol pot fi sub <Articole>/<Articol>
            articole_container = self._find_any(
                cap_el, ['Articole', 'articole', 'Pozitii', 'pozitii']
            )
            articole = []
            if articole_container is not None:
                for art_el in articole_container:
                    if self._localname(art_el.tag) in _ALIAS_ARTICOL:
                        articole.append(art_el)
            else:
                # Articole direct copii ai capitolului
                for art_el in cap_el:
                    if self._localname(art_el.tag) in _ALIAS_ARTICOL:
                        articole.append(art_el)
            rezultat.append({'cod': cod, 'articole': articole})
        return rezultat

    def _parse_articol(self, art_el: ET.Element, cod_capitol: Optional[str],
                       ordine: int, result: ParseResult) -> Optional[dict]:
        """Parse o singura entitate <Articol>."""
        # Atribute pe tag sau elemente copil - acoperim ambele.
        cod_articol = (
            art_el.get('cod') or art_el.get('Cod')
            or self._text_any(art_el, ['Cod', 'cod', 'CodArticol'])
        )
        denumire = (
            art_el.get('denumire') or art_el.get('Denumire')
            or self._text_any(art_el, ['Denumire', 'denumire', 'Nume', 'Name'])
        )
        um = (
            art_el.get('um') or art_el.get('UM') or art_el.get('Um')
            or self._text_any(art_el, ['UM', 'um', 'UnitateMasura'])
        )

        if not cod_articol or not denumire or not um:
            result.add_warning(
                f'Articol incomplet skip-at (cod="{cod_articol}", '
                f'denumire="{denumire}", um="{um}").'
            )
            return None

        cantitate = self._decimal(
            art_el.get('cantitate') or art_el.get('Cantitate')
            or self._text_any(art_el, ['Cantitate', 'cantitate', 'Qty']),
            result, f'cantitate articol {cod_articol}', default=Decimal('0')
        )
        pret_unitar = self._decimal(
            art_el.get('pret_unitar') or art_el.get('PretUnitar')
            or self._text_any(art_el, ['PretUnitar', 'pret_unitar', 'UnitPrice']),
            result, f'pret articol {cod_articol}', default=Decimal('0')
        )

        categorie = (
            art_el.get('categorie') or art_el.get('Categorie')
            or self._text_any(art_el, ['Categorie', 'categorie', 'Category'])
        )
        if categorie:
            categorie = categorie.strip().lower()
        if categorie not in _VALID_CATEGORII:
            if categorie:
                result.add_warning(
                    f'Articol {cod_articol}: categorie "{categorie}" '
                    f'necunoscuta, default "{_ALIAS_CATEGORIE_DEFAULT}".'
                )
            categorie = _ALIAS_CATEGORIE_DEFAULT

        # Detalii valori unitare (optional, sub <Detalii>)
        det = self._find_any(art_el, ['Detalii', 'detalii', 'Details'])
        valori_unitar = {
            'valoare_materiale_unitar': None,
            'valoare_manopera_unitar': None,
            'valoare_utilaj_unitar': None,
            'valoare_transport_unitar': None,
        }
        if det is not None:
            valori_unitar['valoare_materiale_unitar'] = self._decimal(
                self._text_any(det, ['ValoareMateriale', 'valoare_materiale']),
                result, f'val_materiale {cod_articol}', default=None
            )
            valori_unitar['valoare_manopera_unitar'] = self._decimal(
                self._text_any(det, ['ValoareManopera', 'valoare_manopera']),
                result, f'val_manopera {cod_articol}', default=None
            )
            valori_unitar['valoare_utilaj_unitar'] = self._decimal(
                self._text_any(det, ['ValoareUtilaj', 'valoare_utilaj']),
                result, f'val_utilaj {cod_articol}', default=None
            )
            valori_unitar['valoare_transport_unitar'] = self._decimal(
                self._text_any(det, ['ValoareTransport', 'valoare_transport']),
                result, f'val_transport {cod_articol}', default=None
            )

        return {
            'cod_articol': cod_articol.strip(),
            'cod_capitol': cod_capitol,
            'denumire': denumire.strip(),
            'um': um.strip(),
            'cantitate_oferta': cantitate,
            'pret_unitar': pret_unitar,
            'categorie': categorie,
            'ordine': ordine,
            **valori_unitar,
        }

    @staticmethod
    def _decimal(value: Any, result: ParseResult, context: str = '',
                 default: Optional[Decimal] = None) -> Optional[Decimal]:
        if value is None or value == '':
            return default
        try:
            # Toleram virgula ca separator decimal (uzual in RO)
            if isinstance(value, str):
                value = value.strip().replace(',', '.')
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            if context:
                result.add_warning(
                    f'Valoare invalida "{value}" ({context}), default aplicat.'
                )
            return default
