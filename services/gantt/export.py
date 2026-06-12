"""
Motor de export catre formate de planificare.

Formate:
  - CSV                : ID | Activity Name | Duration | Predecessors  (predecesori stil MS Project)
  - MS Project 2003 XML: importabil direct in MS Project (Tasks + OutlineLevel + PredecessorLink)
  - Primavera P6 XML   : subset compatibil (Project / WBS / Activity / Relationship)
  - JSON               : structura completa (pentru API / integrari)

Maparea tipurilor de relatie:
  MS Project: 0=FF, 1=FS, 2=SF, 3=SS
  Primavera : 'Finish to Start' / 'Start to Start' / 'Finish to Finish' / 'Start to Finish'
"""
from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from typing import Optional

# Caractere invalide in XML 1.0 (control chars, exceptand TAB/LF/CR).
# MS Project / Primavera resping importul daca un <Name> contine asa ceva.
_INVALID_XML = re.compile(
    '[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]')

from .modele import Activitate, NodWBS

# MS Project: tip relatie -> cod numeric
_MSP_TIP = {'FF': 0, 'FS': 1, 'SF': 2, 'SS': 3}
# Primavera: tip relatie -> eticheta
_P6_TIP = {
    'FS': 'Finish to Start', 'SS': 'Start to Start',
    'FF': 'Finish to Finish', 'SF': 'Start to Finish',
}


def _index_activitati(activitati) -> dict:
    return {a.id: a for a in activitati}


def _functie_date(activitati, data_start, calendar):
    """dz(index_zi) -> date calendaristica, sau None cand nu avem data de start.

    Mapeaza indecsii de zi 0-based (start_zi/finish_zi) pe date reale folosind
    calendarul de lucru dat (CalendarLucru) sau, in lipsa lui, Lu-Vi simplu.
    Cand `data_start` e None, exporturile raman IDENTICE cu istoricul (fara date).
    """
    if data_start is None:
        return None
    from .calendar import CalendarLucru
    cal_lucru = calendar if calendar is not None else CalendarLucru()
    durata = 1
    for a in activitati:
        durata = max(durata, int(getattr(a, 'finish_zi', 0) or 0))
    zile = cal_lucru.lista_zile(data_start, durata)

    def dz(i: int):
        return zile[max(0, min(int(i), len(zile) - 1))]
    return dz


def _interval_activitate(a, dz):
    """(data_start, data_finish) pentru o activitate programata (finish inclusiv)."""
    s_idx = int(getattr(a, 'start_zi', 0) or 0)
    f_idx = max(int(getattr(a, 'finish_zi', 0) or 0) - 1, s_idx)
    return dz(s_idx), dz(f_idx)


def _numerotare(noduri, activitati):
    """Atribuie UID (toate nodurile, preorder) si ID numeric (doar activitatile).
    Intoarce (uid_per_wbs, uid_per_act, idnum_per_act)."""
    uid_per_wbs, uid_per_act, idnum_per_act = {}, {}, {}
    uid = 0
    idnum = 0
    for n in noduri:
        uid += 1
        uid_per_wbs[n.wbs_id] = uid
        if n.tip == 'activitate' and n.activitate_id:
            uid_per_act[n.activitate_id] = uid
            idnum += 1
            idnum_per_act[n.activitate_id] = idnum
    return uid_per_wbs, uid_per_act, idnum_per_act


# --------------------------------------------------------------------------- CSV
def export_csv(activitati, noduri, data_start=None, calendar=None) -> bytes:
    """CSV cu predecesori stil MS Project (ex: '12FS', '12FS+2 days', '12SS-1 day').
    Cu `data_start` (si optional `calendar`): coloane suplimentare Start/Finish.
    Fara ele, output IDENTIC cu istoricul."""
    _, _, idnum = _numerotare(noduri, activitati)
    dz = _functie_date(activitati, data_start, calendar)
    out = io.StringIO()
    w = csv.writer(out, delimiter=',')
    antet = ['ID', 'WBS', 'Activity Name', 'Duration', 'Predecessors', 'Category',
             'Quantity', 'UM', 'Valoare', 'Material', 'Manopera', 'Utilaje']
    if dz is not None:
        antet += ['Start', 'Finish']
    w.writerow(antet)
    for a in activitati:
        preds = []
        for d in a.predecesori:
            pid = idnum.get(d.predecesor_id)
            if pid is None:
                continue
            lag = ''
            if d.decalaj:
                unit = 'day' if abs(d.decalaj) == 1 else 'days'
                lag = f'{"+" if d.decalaj > 0 else "-"}{abs(d.decalaj)} {unit}'
            preds.append(f'{pid}{d.tip}{lag}')
        rand = [
            idnum.get(a.id, ''), a.wbs_id, a.nume, f'{a.durata} days',
            ';'.join(preds), a.categorie_tehnologica or '', _num(a.cantitate), a.um,
            _num(getattr(a, 'valoare', 0)), _num(getattr(a, 'valoare_material', 0)),
            _num(getattr(a, 'valoare_manopera', 0)), _num(getattr(a, 'valoare_utilaj', 0)),
        ]
        if dz is not None:
            ds, df = _interval_activitate(a, dz)
            rand += [ds.isoformat(), df.isoformat()]
        w.writerow(rand)
    return out.getvalue().encode('utf-8-sig')


# ------------------------------------------------------------------ MS Project XML
def export_msproject_xml(activitati, noduri, nume_proiect='Proiect', ore_pe_zi=8,
                         data_start=None, calendar=None) -> bytes:
    """MS Project 2003 XML (importabil in MS Project).
    Cu `data_start` (si optional `calendar`): emite Start/Finish (ISO) pe Task-uri
    + StartDate pe proiect. Fara ele, output IDENTIC cu istoricul."""
    idx = _index_activitati(activitati)
    _, uid_act, _ = _numerotare(noduri, activitati)
    dz = _functie_date(activitati, data_start, calendar)
    ora_start = 8                                  # ziua de lucru incepe la 08:00
    ora_finish = ora_start + int(ore_pe_zi)
    NS = 'http://schemas.microsoft.com/project'
    ET.register_namespace('', NS)
    proj = ET.Element(f'{{{NS}}}Project')
    _sub(proj, NS, 'Name', nume_proiect)
    _sub(proj, NS, 'Title', nume_proiect)
    if dz is not None:
        _sub(proj, NS, 'StartDate', f'{dz(0).isoformat()}T{ora_start:02d}:00:00')
    _sub(proj, NS, 'MinutesPerDay', str(int(ore_pe_zi) * 60))
    _sub(proj, NS, 'HoursPerDay', str(int(ore_pe_zi)))
    tasks = ET.SubElement(proj, f'{{{NS}}}Tasks')

    for uid, n in enumerate(noduri, start=1):
        t = ET.SubElement(tasks, f'{{{NS}}}Task')
        _sub(t, NS, 'UID', str(uid))
        _sub(t, NS, 'ID', str(uid))
        _sub(t, NS, 'Name', _nume_sigur(n.nume, n.wbs_id or f'Task {uid}'))
        _sub(t, NS, 'OutlineLevel', str(n.nivel))
        _sub(t, NS, 'OutlineNumber', n.wbs_id)
        _sub(t, NS, 'WBS', n.wbs_id)
        if n.tip == 'activitate' and n.activitate_id:
            a = idx.get(n.activitate_id)
            durata = a.durata if a else 1
            _sub(t, NS, 'Summary', '0')
            _sub(t, NS, 'Manual', '0')
            if a is not None and dz is not None:
                ds, df = _interval_activitate(a, dz)
                _sub(t, NS, 'Start', f'{ds.isoformat()}T{ora_start:02d}:00:00')
                _sub(t, NS, 'Finish', f'{df.isoformat()}T{ora_finish:02d}:00:00')
            _sub(t, NS, 'Duration', f'PT{int(durata) * int(ore_pe_zi)}H0M0S')
            _sub(t, NS, 'DurationFormat', '7')
            if a:
                for d in a.predecesori:
                    pu = uid_act.get(d.predecesor_id)
                    if pu is None:
                        continue
                    link = ET.SubElement(t, f'{{{NS}}}PredecessorLink')
                    _sub(link, NS, 'PredecessorUID', str(pu))
                    _sub(link, NS, 'Type', str(_MSP_TIP.get(d.tip, 1)))
                    _sub(link, NS, 'LinkLag', str(int(d.decalaj) * int(ore_pe_zi) * 60 * 10))
                    _sub(link, NS, 'LagFormat', '7')
        else:
            _sub(t, NS, 'Summary', '1')
            _sub(t, NS, 'Duration', 'PT0H0M0S')
            _sub(t, NS, 'DurationFormat', '7')
    return _xml_bytes(proj)


# ------------------------------------------------------------------ Primavera P6 XML
def export_primavera_xml(activitati, noduri, nume_proiect='Proiect', ore_pe_zi=8,
                         data_start=None, calendar=None) -> bytes:
    """Primavera P6 XML - subset compatibil (Project / WBS / Activity / Relationship).
    Cu `data_start` (si optional `calendar`): emite PlannedStartDate/PlannedFinishDate.
    Fara ele, output IDENTIC cu istoricul."""
    uid_wbs, _, _ = _numerotare(noduri, activitati)
    dz = _functie_date(activitati, data_start, calendar)
    ora_start = 8
    ora_finish = ora_start + int(ore_pe_zi)
    root = ET.Element('APIBusinessObjects')
    proj = ET.SubElement(root, 'Project')
    _sub(proj, None, 'ObjectId', '1')
    _sub(proj, None, 'Id', 'PRJ-001')
    _sub(proj, None, 'Name', _nume_sigur(nume_proiect, 'Proiect'))

    # WBS (noduri non-activitate)
    for n in noduri:
        if n.tip == 'activitate':
            continue
        w = ET.SubElement(proj, 'WBS')
        _sub(w, None, 'ObjectId', str(uid_wbs[n.wbs_id]))
        _sub(w, None, 'Code', n.wbs_id)
        _sub(w, None, 'Name', _nume_sigur(n.nume, n.wbs_id or 'WBS'))
        if n.parinte_id and n.parinte_id in uid_wbs:
            _sub(w, None, 'ParentObjectId', str(uid_wbs[n.parinte_id]))

    # Activitati
    idx_act_parinte = {n.activitate_id: n.parinte_id
                       for n in noduri if n.tip == 'activitate'}
    for a in activitati:
        act = ET.SubElement(proj, 'Activity')
        _sub(act, None, 'ObjectId', a.id)
        _sub(act, None, 'Id', a.cod)
        _sub(act, None, 'Name', _nume_sigur(a.nume, a.cod or f'ACT-{a.id}'))
        parinte = idx_act_parinte.get(a.id)
        if parinte and parinte in uid_wbs:
            _sub(act, None, 'WBSObjectId', str(uid_wbs[parinte]))
        _sub(act, None, 'PlannedDuration', str(int(a.durata) * int(ore_pe_zi)))  # ore
        if dz is not None:
            ds, df = _interval_activitate(a, dz)
            _sub(act, None, 'PlannedStartDate', f'{ds.isoformat()}T{ora_start:02d}:00:00')
            _sub(act, None, 'PlannedFinishDate', f'{df.isoformat()}T{ora_finish:02d}:00:00')
        _sub(act, None, 'Status', 'Not Started')

    # Relatii
    for a in activitati:
        for d in a.predecesori:
            rel = ET.SubElement(proj, 'Relationship')
            _sub(rel, None, 'PredecessorActivityObjectId', d.predecesor_id)
            _sub(rel, None, 'SuccessorActivityObjectId', a.id)
            _sub(rel, None, 'Type', _P6_TIP.get(d.tip, 'Finish to Start'))
            _sub(rel, None, 'Lag', str(int(d.decalaj) * int(ore_pe_zi)))  # ore
    return _xml_bytes(root)


# ------------------------------------------------------------------------- JSON
def export_json(rezultat) -> bytes:
    """Structura completa ca JSON (foloseste RezultatPlanificare.to_dict)."""
    return json.dumps(rezultat.to_dict(), ensure_ascii=False, indent=2).encode('utf-8')


# ---- export prin nume de format (folosit de API / UI) ----
def exporta(format_: str, rezultat, nume_proiect='Proiect', ore_pe_zi=8,
            data_start=None, calendar=None):
    """Intoarce (bytes, mimetype, extensie) pentru formatul cerut.
    `data_start`/`calendar` (optionale): adauga date calendaristice Start/Finish
    in CSV / MS Project XML / Primavera XML. Fara ele, output identic cu istoricul."""
    f = (format_ or '').lower()
    if f in ('csv',):
        return (export_csv(rezultat.activitati, rezultat.noduri_wbs,
                           data_start=data_start, calendar=calendar),
                'text/csv', 'csv')
    if f in ('msproject', 'msp', 'mpp', 'xml', 'msproject_xml'):
        return (export_msproject_xml(rezultat.activitati, rezultat.noduri_wbs, nume_proiect, ore_pe_zi,
                                     data_start=data_start, calendar=calendar),
                'application/xml', 'xml')
    if f in ('primavera', 'p6', 'primavera_xml'):
        return (export_primavera_xml(rezultat.activitati, rezultat.noduri_wbs, nume_proiect, ore_pe_zi,
                                     data_start=data_start, calendar=calendar),
                'application/xml', 'xml')
    if f in ('json',):
        return export_json(rezultat), 'application/json', 'json'
    raise ValueError(f'Format de export necunoscut: {format_!r}')


# ----------------------------------------------------------------------- helpers
def _curata_xml(text: str) -> str:
    """Scoate caracterele invalide in XML 1.0 (control chars) care strica importul."""
    return _INVALID_XML.sub('', text)


def _nume_sigur(raw, fallback: str) -> str:
    """Nume non-gol si valid pentru MS Project / Primavera (resping <Name> gol).
    Curata control chars, taie spatiile; daca ramane gol -> fallback."""
    nume = _curata_xml(str(raw or '')).strip()
    return nume or fallback


def _sub(parinte, ns, tag, text):
    el = ET.SubElement(parinte, f'{{{ns}}}{tag}' if ns else tag)
    el.text = '' if text is None else _curata_xml(str(text))
    return el


def _xml_bytes(root) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='utf-8')


def _num(v) -> str:
    f = float(v or 0)
    return str(int(f)) if f == int(f) else str(f)
