"""
Blueprint GANTT F3 -> structura de planificare.

UI:
  GET  /gantt/                    pagina de upload F3
  POST /gantt/genereaza           upload -> pipeline -> preview (token salvat temporar)
  GET  /gantt/export/<token>/<fmt>  descarca CSV / MS Project XML / Primavera XML / JSON

REST API (stateless, JSON; exceptate CSRF in app.py) - mapeaza specificatia:
  POST /gantt/api/import          (multipart) -> articole + raport
  POST /gantt/api/classify        {articole}  -> activitati clasificate
  POST /gantt/api/generate-wbs    {activitati} -> activitati + noduri WBS
  POST /gantt/api/generate-dependencies {activitati} -> activitati cu predecesori
  POST /gantt/api/validate        {activitati} -> raport validare
  POST /gantt/api/export          {activitati, format} -> fisier
  POST /gantt/api/pipeline        (multipart) -> rezultat complet (import->validare)
"""
from __future__ import annotations

import os
import re
import tempfile
import time
import uuid

from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   send_file, jsonify, session, abort)
from flask_login import login_required, current_user

from services.gantt.pipeline import MotorPlanificare
from services.gantt.modele import Activitate, ArticolF3, RezultatPlanificare
from services.gantt import import_engine, export as export_engine
from services.gantt.wbs import genereaza_wbs
from services.gantt.dependinte import genereaza_dependinte
from services.gantt.validare import valideaza

gantt_bp = Blueprint('gantt', __name__, url_prefix='/gantt')

_DIR_TEMP = os.path.join(tempfile.gettempdir(), 'edifico_gantt')
_EXT_OK = {'.xlsx', '.xlsm', '.xls', '.csv', '.xml'}
_motor_cache = None


def _motor() -> MotorPlanificare:
    """Instanta MotorPlanificare reutilizata (config incarcat o singura data)."""
    global _motor_cache
    if _motor_cache is None:
        _motor_cache = MotorPlanificare()
    return _motor_cache


def _curata_temp(varsta_max_s: int = 7200):
    """Sterge fisierele temporare mai vechi de varsta_max_s (best-effort)."""
    try:
        acum = time.time()
        for f in os.listdir(_DIR_TEMP):
            cale = os.path.join(_DIR_TEMP, f)
            if os.path.isfile(cale) and acum - os.path.getmtime(cale) > varsta_max_s:
                os.remove(cale)
    except OSError:
        pass


# ============================================================ UI
@gantt_bp.route('/')
@login_required
def index():
    return render_template('gantt/index.html')


@gantt_bp.route('/genereaza', methods=['POST'])
@login_required
def genereaza():
    fisier = request.files.get('fisier')
    if not fisier or not fisier.filename:
        flash('Selecteaza un fisier F3 (.xlsx sau .csv).', 'warning')
        return redirect(url_for('gantt.index'))
    ext = os.path.splitext(fisier.filename)[1].lower()
    if ext not in _EXT_OK:
        flash(f'Format nesuportat: {ext}. Accept .xlsx, .xls, .csv.', 'danger')
        return redirect(url_for('gantt.index'))

    continut = fisier.read()
    try:
        rezultat, raport_import = _motor().genereaza_din_fisier(continut, ext)
    except import_engine.EroareImport as e:
        flash(f'Import esuat: {e}', 'danger')
        return redirect(url_for('gantt.index'))
    except Exception as e:  # robustete: nu lasam 500 fara mesaj
        flash(f'Eroare la procesare: {e}', 'danger')
        return redirect(url_for('gantt.index'))

    # salveaza fisierul temporar pentru export ulterior (re-ruleaza pipeline determinist)
    os.makedirs(_DIR_TEMP, exist_ok=True)
    _curata_temp()
    token = uuid.uuid4().hex
    with open(os.path.join(_DIR_TEMP, f'{token}{ext}'), 'wb') as f:
        f.write(continut)
    session['gantt_token'] = token
    session['gantt_ext'] = ext
    session['gantt_nume'] = os.path.splitext(os.path.basename(fisier.filename))[0]

    return render_template('gantt/rezultat.html', rezultat=rezultat,
                           raport_import=raport_import, token=token,
                           nume_fisier=fisier.filename)


@gantt_bp.route('/export/<token>/<fmt>')
@login_required
def export_fisier(token, fmt):
    if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
        abort(404)
    ext = session.get('gantt_ext', '.xlsx') if session.get('gantt_token') == token else None
    # cauta fisierul (independent de sesiune, dar token e secret/uuid)
    cale = None
    for e in _EXT_OK:
        p = os.path.join(_DIR_TEMP, f'{token}{e}')
        if os.path.exists(p):
            cale, ext = p, e
            break
    if not cale:
        flash('Sesiunea de preview a expirat. Reincarca fisierul F3.', 'warning')
        return redirect(url_for('gantt.index'))

    with open(cale, 'rb') as f:
        continut = f.read()
    rezultat, _ = _motor().genereaza_din_fisier(continut, ext)
    nume = session.get('gantt_nume', 'planificare')
    try:
        data, mime, ext_out = export_engine.exporta(
            fmt, rezultat, nume_proiect=nume,
            ore_pe_zi=_motor().setari.get('ore_pe_zi', 8))
    except ValueError:
        abort(404)
    import io
    return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True,
                     download_name=f'planificare_{nume}.{ext_out}')


# ============================================================ REST API (JSON)
def _articole_din_payload(date) -> list:
    return [ArticolF3.from_dict(d) for d in (date.get('articole') or [])]


def _activitati_din_payload(date) -> list:
    return [Activitate.from_dict(d) for d in (date.get('activitati') or [])]


@gantt_bp.route('/api/import', methods=['POST'])
@login_required
def api_import():
    fisier = request.files.get('fisier')
    if not fisier:
        return jsonify({'eroare': 'Lipseste fisierul (camp "fisier").'}), 400
    ext = os.path.splitext(fisier.filename or '')[1].lower()
    try:
        articole, raport = import_engine.importa(fisier.read(), ext, _motor().setari)
    except import_engine.EroareImport as e:
        return jsonify({'eroare': str(e)}), 422
    return jsonify({'raport': raport, 'articole': [a.to_dict() for a in articole]})


@gantt_bp.route('/api/classify', methods=['POST'])
@login_required
def api_classify():
    articole = _articole_din_payload(request.get_json(silent=True) or {})
    activitati = _motor().clasifica_articole(articole)
    return jsonify({'activitati': [a.to_dict() for a in activitati]})


@gantt_bp.route('/api/generate-wbs', methods=['POST'])
@login_required
def api_wbs():
    activitati = _activitati_din_payload(request.get_json(silent=True) or {})
    noduri = genereaza_wbs(activitati, _motor().dependinte.get('ordine_categorii', []))
    return jsonify({
        'activitati': [a.to_dict() for a in activitati],
        'noduri_wbs': [n.to_dict() for n in noduri],
    })


@gantt_bp.route('/api/generate-dependencies', methods=['POST'])
@login_required
def api_dependencies():
    activitati = _activitati_din_payload(request.get_json(silent=True) or {})
    dep = _motor().dependinte
    nr = genereaza_dependinte(activitati, dep.get('relatii', []),
                              dep.get('intra_categorie', 'secvential'),
                              dep.get('ordine_categorii', []))
    return jsonify({'nr_dependente': nr,
                    'activitati': [a.to_dict() for a in activitati]})


@gantt_bp.route('/api/validate', methods=['POST'])
@login_required
def api_validate():
    activitati = _activitati_din_payload(request.get_json(silent=True) or {})
    return jsonify(valideaza(activitati).to_dict())


@gantt_bp.route('/api/export', methods=['POST'])
@login_required
def api_export():
    date = request.get_json(silent=True) or {}
    activitati = _activitati_din_payload(date)
    fmt = date.get('format', 'csv')
    # regeneram WBS pentru numerotare consistenta daca nu e furnizat
    noduri = genereaza_wbs(activitati, _motor().dependinte.get('ordine_categorii', []))
    rez = RezultatPlanificare(activitati=activitati, noduri_wbs=noduri)
    try:
        data, mime, ext = export_engine.exporta(fmt, rez, ore_pe_zi=_motor().setari.get('ore_pe_zi', 8))
    except ValueError as e:
        return jsonify({'eroare': str(e)}), 400
    import io
    return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True,
                     download_name=f'planificare.{ext}')


@gantt_bp.route('/api/pipeline', methods=['POST'])
@login_required
def api_pipeline():
    fisier = request.files.get('fisier')
    if not fisier:
        return jsonify({'eroare': 'Lipseste fisierul (camp "fisier").'}), 400
    ext = os.path.splitext(fisier.filename or '')[1].lower()
    try:
        rezultat, _ = _motor().genereaza_din_fisier(fisier.read(), ext)
    except import_engine.EroareImport as e:
        return jsonify({'eroare': str(e)}), 422
    return jsonify(rezultat.to_dict())
