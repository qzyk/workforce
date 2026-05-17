"""
Parser MS Project XML (format standard mspdi_pj12.xsd, Project 2007+).

Documentatie de referinta:
  https://learn.microsoft.com/en-us/office-project/xml-data-interchange/

Namespace: http://schemas.microsoft.com/project (uneori absent in fisiere
non-Microsoft - parser tolereaza ambele variante).

Mapare task XML -> dict pentru `TaskProgram`:
    UID                 -> cod_extern
    WBS                 -> cod_wbs
    Name                -> denumire
    OutlineLevel        -> nivel_ierarhie (int)
    Start               -> data_start_planificat (date)
    Finish              -> data_sfarsit_planificat (date)
    Duration (PT...H)   -> durata_zile (round to days; H/8)
    PercentComplete     -> procent_realizare (Decimal)
    Summary=true/Milestone=true -> tip_task ('summary'/'milestone'/'task')
    PredecessorLink[]   -> predecesori_json: [{'uid_extern','tip','lag_zile'}, ...]

Predecesor types (din schema MS Project):
  0 = FF (Finish-to-Finish)
  1 = FS (Finish-to-Start)   <-- default in MS Project
  2 = SF (Start-to-Finish)
  3 = SS (Start-to-Start)
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from .base import Parser, ParseResult, ParseError


# Namespace standard MS Project. Fisierele exportate au-l pe el explicit;
# Project Online uneori il omite, iar tools terte la fel - acoperim ambele.
NS_MS = 'http://schemas.microsoft.com/project'

# Mapare type-uri PredecessorLink (cf. MS Project XML schema) -> codurile
# folosite in `TaskProgram.predecesori_json`.
PREDECESOR_TYPE_MAP = {
    '0': 'FF',
    '1': 'FS',
    '2': 'SF',
    '3': 'SS',
}


class MSProjectXMLParser(Parser):
    """Parser XML MS Project standard (Project 2007/2010/2013/2016)."""

    SURSA_COD = 'msproject_xml'

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(sursa=self.SURSA_COD)

        try:
            tree = ET.parse(file_path)
        except ET.ParseError as e:
            raise ParseError(f'XML invalid: {e}') from e
        except OSError as e:
            raise ParseError(f'Nu pot citi fisierul: {e}') from e

        root = tree.getroot()
        # Detectam daca avem namespace sau nu (auto-strip pentru lookup)
        ns = self._detect_namespace(root)
        result.stats['namespace'] = ns or '(none)'

        # Metadata project (Name, StartDate, FinishDate)
        result.stats['project_name'] = self._text(root, 'Name', ns)
        result.stats['project_start'] = self._text(root, 'StartDate', ns)
        result.stats['project_finish'] = self._text(root, 'FinishDate', ns)

        tasks_el = self._find(root, 'Tasks', ns)
        if tasks_el is None:
            result.add_error('Element <Tasks> nu a fost gasit in XML.')
            return result

        for task_el in self._findall(tasks_el, 'Task', ns):
            task_data = self._parse_task(task_el, ns, result)
            if task_data:
                result.entities.append(task_data)

        result.stats['entities_count'] = len(result.entities)
        result.stats['warnings_count'] = len(result.warnings)
        return result

    # ------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------

    def _detect_namespace(self, root: ET.Element) -> Optional[str]:
        """Detecteaza namespace-ul daca exista in root tag."""
        if root.tag.startswith('{'):
            return root.tag[1:].split('}')[0]
        return None

    def _qname(self, name: str, ns: Optional[str]) -> str:
        return f'{{{ns}}}{name}' if ns else name

    def _find(self, parent: ET.Element, name: str, ns: Optional[str]):
        return parent.find(self._qname(name, ns))

    def _findall(self, parent: ET.Element, name: str, ns: Optional[str]):
        return parent.findall(self._qname(name, ns))

    def _text(self, parent: ET.Element, name: str, ns: Optional[str],
              default: str = '') -> str:
        el = self._find(parent, name, ns)
        if el is None or el.text is None:
            return default
        return el.text.strip()

    def _parse_task(self, task_el: ET.Element, ns: Optional[str],
                    result: ParseResult) -> Optional[dict]:
        """Parse o singura entitate <Task>."""
        uid = self._text(task_el, 'UID', ns)
        if not uid:
            result.add_warning('Task fara UID skip-at.')
            return None

        # MS Project pune un task "fantoma" cu UID=0 (root). Sarim peste el.
        if uid == '0':
            return None

        # Verific IsNull (=true inseamna placeholder gol)
        is_null = self._text(task_el, 'IsNull', ns).lower() == 'true'
        if is_null:
            return None

        denumire = self._text(task_el, 'Name', ns) or f'(Task UID {uid})'
        wbs = self._text(task_el, 'WBS', ns) or None
        outline_level = self._int(self._text(task_el, 'OutlineLevel', ns), default=1)

        # Date start/finish
        start = self._parse_datetime_to_date(
            self._text(task_el, 'Start', ns), result, f'Start UID {uid}'
        )
        finish = self._parse_datetime_to_date(
            self._text(task_el, 'Finish', ns), result, f'Finish UID {uid}'
        )
        if not start or not finish:
            result.add_warning(
                f'Task UID {uid}: data_start sau data_sfarsit lipsa, '
                'task skip-at.'
            )
            return None

        # Durata
        duration_str = self._text(task_el, 'Duration', ns)
        durata_zile = self._parse_duration_to_days(duration_str)

        # Procent realizare
        procent_str = self._text(task_el, 'PercentComplete', ns) or '0'
        try:
            procent_realizare = Decimal(procent_str)
        except (InvalidOperation, ValueError):
            procent_realizare = Decimal('0')
            result.add_warning(
                f'Task UID {uid}: PercentComplete invalid "{procent_str}", default 0.'
            )

        # Tip task
        is_summary = self._text(task_el, 'Summary', ns).lower() == 'true'
        is_milestone = self._text(task_el, 'Milestone', ns).lower() == 'true'
        if is_milestone:
            tip_task = 'milestone'
        elif is_summary:
            tip_task = 'summary'
        else:
            tip_task = 'task'

        # Predecesori (lista pe XML)
        predecesori = []
        for pred_el in self._findall(task_el, 'PredecessorLink', ns):
            pred_uid = self._text(pred_el, 'PredecessorUID', ns)
            if not pred_uid or pred_uid == '0':
                continue
            type_raw = self._text(pred_el, 'Type', ns) or '1'  # default FS
            type_str = PREDECESOR_TYPE_MAP.get(type_raw, 'FS')
            lag_raw = self._text(pred_el, 'LinkLag', ns) or '0'
            # LinkLag in MS Project: in "tenths of a minute" sau ca duration
            # In majoritatea fisierelor e integer minute*10. Convertim la zile
            # asumand 8h/zi (480 minute).
            try:
                lag_tenths_min = int(lag_raw)
                lag_zile = round(lag_tenths_min / 10 / 480)
            except ValueError:
                lag_zile = 0
            predecesori.append({
                'uid_extern': pred_uid,
                'tip': type_str,
                'lag_zile': lag_zile,
            })

        return {
            'cod_extern': uid,
            'cod_wbs': wbs,
            'denumire': denumire,
            'nivel_ierarhie': outline_level,
            'data_start_planificat': start,
            'data_sfarsit_planificat': finish,
            'durata_zile': durata_zile,
            'procent_realizare': procent_realizare,
            'tip_task': tip_task,
            'predecesori': predecesori,  # va fi setat via property setter
        }

    @staticmethod
    def _int(value: str, default: int = 0) -> int:
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _parse_datetime_to_date(value: str, result: ParseResult,
                                context: str = '') -> Optional[date]:
        """Parse '2025-01-15T08:00:00' -> date(2025, 1, 15)."""
        if not value:
            return None
        try:
            # MS Project: ISO 8601 cu timezone optional
            # Format tipic: 2025-01-15T08:00:00
            if 'T' in value:
                value = value.split('T')[0]
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            if context:
                result.add_warning(f'Data invalida "{value}" ({context}).')
            return None

    @staticmethod
    def _parse_duration_to_days(value: str) -> Optional[int]:
        """
        Parse durata ISO 8601 (ex: 'PT80H0M0S') -> zile.

        Conventie: 1 zi lucratoare = 8h. PT0H = 0 zile.
        Returneaza None daca format necunoscut.
        """
        if not value:
            return None
        # Format ISO 8601 Duration: PT<H>H<M>M<S>S sau PdaysDT...
        m = re.match(r'P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', value)
        if not m:
            return None
        days_raw = int(m.group(1) or 0)
        hours = int(m.group(2) or 0)
        minutes = int(m.group(3) or 0)
        # 8h zi lucratoare
        total_hours = hours + minutes / 60
        zile_din_ore = total_hours / 8
        zile = days_raw + zile_din_ore
        return int(round(zile)) if zile > 0 else 0
