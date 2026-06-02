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
def export_csv(activitati, noduri) -> bytes:
    """CSV cu predecesori stil MS Project (ex: '12FS', '12FS+2 days', '12SS-1 day')."""
    _, _, idnum = _numerotare(noduri, activitati)
    out = io.StringIO()
    w = csv.writer(out, delimiter=',')
    w.writerow(['ID', 'WBS', 'Activity Name', 'Duration', 'Predecessors', 'Category',
                'Quantity', 'UM', 'Valoare', 'Material', 'Manopera', 'Utilaje'])
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
        w.writerow([
            idnum.get(a.id, ''), a.wbs_id, a.nume, f'{a.durata} days',
            ';'.join(preds), a.categorie_tehnologica or '', _num(a.cantitate), a.um,
            _num(getattr(a, 'valoare', 0)), _num(getattr(a, 'valoare_material', 0)),
            _num(getattr(a, 'valoare_manopera', 0)), _num(getattr(a, 'valoare_utilaj', 0)),
        ])
    return out.getvalue().encode('utf-8-sig')


# ------------------------------------------------------------------ MS Project XML
def export_msproject_xml(activitati, noduri, nume_proiect='Proiect', ore_pe_zi=8) -> bytes:
    """MS Project 2003 XML (importabil in MS Project)."""
    idx = _index_activitati(activitati)
    _, uid_act, _ = _numerotare(noduri, activitati)
    NS = 'http://schemas.microsoft.com/project'
    ET.register_namespace('', NS)
    proj = ET.Element(f'{{{NS}}}Project')
    _sub(proj, NS, 'Name', nume_proiect)
    _sub(proj, NS, 'Title', nume_proiect)
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
def export_primavera_xml(activitati, noduri, nume_proiect='Proiect', ore_pe_zi=8) -> bytes:
    """Primavera P6 XML - subset compatibil (Project / WBS / Activity / Relationship)."""
    uid_wbs, _, _ = _numerotare(noduri, activitati)
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
def exporta(format_: str, rezultat, nume_proiect='Proiect', ore_pe_zi=8):
    """Intoarce (bytes, mimetype, extensie) pentru formatul cerut."""
    f = (format_ or '').lower()
    if f in ('csv',):
        return export_csv(rezultat.activitati, rezultat.noduri_wbs), 'text/csv', 'csv'
    if f in ('msproject', 'msp', 'mpp', 'xml', 'msproject_xml'):
        return (export_msproject_xml(rezultat.activitati, rezultat.noduri_wbs, nume_proiect, ore_pe_zi),
                'application/xml', 'xml')
    if f in ('primavera', 'p6', 'primavera_xml'):
        return (export_primavera_xml(rezultat.activitati, rezultat.noduri_wbs, nume_proiect, ore_pe_zi),
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
