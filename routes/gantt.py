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
from services.gantt import import_engine, export as export_engine, store
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


def _invalideaza_motor():
    """Forteaza reincarcarea configului la urmatorul import (dupa editari in admin)."""
    global _motor_cache
    _motor_cache = None


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


# -------------------------------------------------- temp / mapare / profil
def _salveaza_temp(continut: bytes, ext: str) -> str:
    """Salveaza continutul intr-un fisier temporar; intoarce token-ul (uuid hex)."""
    os.makedirs(_DIR_TEMP, exist_ok=True)
    _curata_temp()
    token = uuid.uuid4().hex
    with open(os.path.join(_DIR_TEMP, f'{token}{ext}'), 'wb') as f:
        f.write(continut)
    return token


def _citeste_temp(token: str):
    """(continut, ext) pentru un token salvat, sau (None, None)."""
    if not token or not re.fullmatch(r'[0-9a-f]{32}', token):
        return None, None
    for e in _EXT_OK:
        p = os.path.join(_DIR_TEMP, f'{token}{e}')
        if os.path.exists(p):
            with open(p, 'rb') as f:
                return f.read(), e
    return None, None


def _semnaturi_fisier(continut: bytes, ext: str) -> list:
    """Semnaturile (amprente antet) ale primelor randuri din primul sheet cu continut."""
    try:
        sheeturi = import_engine._citeste_sheeturi(continut, (ext or '').lstrip('.'))
    except Exception:
        return []
    for _nume, randuri in sheeturi:
        if not any(any(c is not None and str(c).strip() for c in r) for r in randuri):
            continue
        sigs = []
        for r in randuri[:15]:
            s = store.semnatura_antet(r)
            if s and s not in sigs:
                sigs.append(s)
        return sigs
    return []


def _semnatura_la_rand(continut: bytes, ext: str, rand_antet: int) -> str:
    """Amprenta randului de antet ales (din primul sheet cu continut)."""
    try:
        sheeturi = import_engine._citeste_sheeturi(continut, (ext or '').lstrip('.'))
    except Exception:
        return ''
    for _nume, randuri in sheeturi:
        if not any(any(c is not None and str(c).strip() for c in r) for r in randuri):
            continue
        if 0 <= (rand_antet or 0) < len(randuri):
            return store.semnatura_antet(randuri[rand_antet])
        return ''
    return ''


def _profil_pt_fisier(continut: bytes, ext: str, tenant_id=None):
    """Cauta un profil invatat care se potriveste fisierului. (profil, mapare, rand_antet)."""
    for sig in _semnaturi_fisier(continut, ext):
        prof = store.gaseste_profil(sig, tenant_id)
        if prof:
            mapare, rand_antet = store.profil_mapare(prof)
            if mapare:
                return prof, mapare, rand_antet
    return None, None, None


def _pipeline_din_temp(continut: bytes, ext: str, mapare=None, rand_antet=None):
    """Ruleaza pipeline-ul (auto sau cu mapare manuala). (RezultatPlanificare, raport)."""
    if mapare:
        articole, raport = import_engine.importa(
            continut, ext, _motor().setari,
            mapare_manuala=mapare, rand_antet_manual=rand_antet)
        rezultat = _motor().proceseaza(articole)
        rezultat.statistici['import'] = raport
        return rezultat, raport
    return _motor().genereaza_din_fisier(continut, ext)


def _set_mapare_sesiune(mapare, rand_antet):
    """Tine maparea manuala in sesiune (pentru export-ul ulterior, determinist)."""
    import json
    if mapare:
        session['gantt_mapare'] = json.dumps(mapare)
        session['gantt_rand_antet'] = rand_antet
    else:
        session.pop('gantt_mapare', None)
        session.pop('gantt_rand_antet', None)


def _mapare_sesiune():
    """(mapare, rand_antet) din sesiune sau (None, None)."""
    import json
    m = session.get('gantt_mapare')
    if not m:
        return None, None
    try:
        return json.loads(m), session.get('gantt_rand_antet')
    except Exception:
        return None, None


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
    nume_fisier = fisier.filename
    tid = getattr(current_user, 'tenant_id', None)
    mapare_folosita, rand_antet_folosit = None, None
    try:
        rezultat, raport_import = _motor().genereaza_din_fisier(continut, ext)
    except import_engine.EroareImport:
        # 1) incearca un profil de mapare invatat anterior (acelasi tip de fisier)
        prof, mapare, rand_antet = _profil_pt_fisier(continut, ext, tid)
        if prof:
            try:
                rezultat, raport_import = _pipeline_din_temp(continut, ext, mapare, rand_antet)
                store.marcheaza_utilizare(prof)
                mapare_folosita, rand_antet_folosit = mapare, rand_antet
                flash(f'Am aplicat automat profilul de mapare invatat "{prof.nume}".', 'info')
            except import_engine.EroareImport:
                prof = None
        if not prof:
            # 2) du utilizatorul la wizard-ul de mapare manuala
            token = _salveaza_temp(continut, ext)
            session['gantt_wizard_token'] = token
            session['gantt_wizard_ext'] = ext
            session['gantt_wizard_nume'] = nume_fisier
            flash('Nu am putut detecta automat structura fisierului. '
                  'Mapeaza coloanele manual mai jos - profilul se salveaza pentru data viitoare.',
                  'warning')
            return redirect(url_for('gantt.mapare'))
    except Exception as e:  # robustete: nu lasam 500 fara mesaj
        flash(f'Eroare la procesare: {e}', 'danger')
        return redirect(url_for('gantt.index'))

    # salveaza fisierul temporar pentru export ulterior (re-ruleaza pipeline determinist)
    token = _salveaza_temp(continut, ext)
    session['gantt_token'] = token
    session['gantt_ext'] = ext
    session['gantt_nume'] = os.path.splitext(os.path.basename(nume_fisier))[0]
    _set_mapare_sesiune(mapare_folosita, rand_antet_folosit)

    return render_template('gantt/rezultat.html', rezultat=rezultat,
                           raport_import=raport_import, token=token,
                           nume_fisier=nume_fisier)


@gantt_bp.route('/export/<token>/<fmt>')
@login_required
def export_fisier(token, fmt):
    if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
        abort(404)
    # cauta fisierul (independent de sesiune, dar token e secret/uuid)
    continut, ext = _citeste_temp(token)
    if not continut:
        flash('Sesiunea de preview a expirat. Reincarca fisierul F3.', 'warning')
        return redirect(url_for('gantt.index'))

    # aplica aceeasi mapare manuala ca la preview (daca a fost una) -> export consistent
    mapare, rand_antet = (None, None)
    if session.get('gantt_token') == token:
        mapare, rand_antet = _mapare_sesiune()
    try:
        rezultat, _ = _pipeline_din_temp(continut, ext, mapare, rand_antet)
    except import_engine.EroareImport:
        flash('Nu pot regenera planificarea pentru export. Reincarca fisierul F3.', 'warning')
        return redirect(url_for('gantt.index'))
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


@gantt_bp.route('/mapare', methods=['GET', 'POST'])
@login_required
def mapare():
    """Wizard de mapare manuala a coloanelor (cand auto-detectia esueaza).
    La confirmare, salveaza un profil reutilizabil pe semnatura antetului."""
    token = session.get('gantt_wizard_token')
    nume_fisier = session.get('gantt_wizard_nume', 'fisier')
    continut, ext_real = _citeste_temp(token)
    ext = session.get('gantt_wizard_ext') or ext_real
    if not continut:
        flash('Sesiunea de mapare a expirat. Reincarca fisierul F3.', 'warning')
        return redirect(url_for('gantt.index'))

    if request.method == 'POST':
        try:
            nr_coloane = int(request.form.get('nr_coloane', 0) or 0)
        except ValueError:
            nr_coloane = 0
        mapare = {}
        for i in range(nr_coloane):
            camp = (request.form.get(f'col_{i}') or '').strip()
            if camp and camp != 'ignora':
                mapare[camp] = i
        try:
            rand_antet = int(request.form.get('rand_antet', 0) or 0)
        except ValueError:
            rand_antet = 0

        if 'denumire' not in mapare or not ('um' in mapare or 'cantitate' in mapare):
            flash('Maparea trebuie sa includa coloana de denumire si una de '
                  'unitate de masura sau cantitate.', 'danger')
            return redirect(url_for('gantt.mapare'))

        try:
            rezultat, raport_import = _pipeline_din_temp(continut, ext, mapare, rand_antet)
        except import_engine.EroareImport as e:
            flash(f'Maparea aleasa nu a produs articole: {e}', 'danger')
            return redirect(url_for('gantt.mapare'))

        # invata: salveaza profilul pe semnatura randului de antet ales
        if request.form.get('salveaza_profil', '1') == '1':
            semn = _semnatura_la_rand(continut, ext, rand_antet) or (
                _semnaturi_fisier(continut, ext)[:1] or [''])[0]
            if semn:
                store.salveaza_profil(
                    nume=(request.form.get('nume_profil') or nume_fisier),
                    semnatura=semn, coloane_map=mapare, rand_antet=rand_antet,
                    sursa='wizard', tenant_id=getattr(current_user, 'tenant_id', None),
                    user_id=getattr(current_user, 'id', None))

        # treci in fluxul de rezultat/export
        session['gantt_token'] = token
        session['gantt_ext'] = ext
        session['gantt_nume'] = os.path.splitext(os.path.basename(nume_fisier))[0]
        _set_mapare_sesiune(mapare, rand_antet)
        session.pop('gantt_wizard_token', None)
        session.pop('gantt_wizard_ext', None)
        session.pop('gantt_wizard_nume', None)
        flash('Mapare aplicata. Profilul a fost salvat pentru fisiere similare.', 'success')
        return render_template('gantt/rezultat.html', rezultat=rezultat,
                               raport_import=raport_import, token=token,
                               nume_fisier=nume_fisier)

    # GET: analizeaza fisierul si arata grila de mapare
    try:
        analiza = import_engine.analizeaza(continut, ext, _motor().setari)
    except import_engine.EroareImport as e:
        flash(f'Nu pot citi fisierul: {e}', 'danger')
        return redirect(url_for('gantt.index'))

    # alege un sheet reprezentativ (primul cu antet, altfel primul cu continut)
    sheet = next((s for s in analiza['sheeturi'] if s['antet_gasit']), None) \
        or next((s for s in analiza['sheeturi'] if s['are_continut']), None) \
        or (analiza['sheeturi'][0] if analiza['sheeturi'] else None)
    harta_inv = {v: k for k, v in (sheet['harta'].items() if sheet else {})}
    rand_antet_def = (sheet['rand_antet'] if sheet and sheet['rand_antet'] is not None else 0)

    return render_template('gantt/mapare.html', analiza=analiza, sheet=sheet,
                           harta_inv=harta_inv, nr_coloane=analiza['nr_coloane'],
                           campuri=analiza['campuri'], rand_antet_def=rand_antet_def,
                           nume_fisier=nume_fisier)


# ============================================================ ADMIN CONFIG
@gantt_bp.route('/config')
@login_required
def config():
    """Pagina de administrare: sinonime coloane, reguli clasificare, profiluri mapare."""
    from collections import OrderedDict
    tid = getattr(current_user, 'tenant_id', None)
    campuri = ['cod_articol', 'denumire', 'um', 'cantitate', 'obiect', 'tronson', 'categorie']

    sin_grup = OrderedDict((c, {'active': [], 'inactive': []}) for c in campuri)
    for s in store.lista_sinonime(tid):
        g = sin_grup.setdefault(s.camp, {'active': [], 'inactive': []})
        (g['active'] if s.activ else g['inactive']).append(s)

    reg_grup = OrderedDict()
    for r in store.lista_reguli(tid):
        g = reg_grup.setdefault(r.categorie, {'active': [], 'inactive': []})
        (g['active'] if r.activ else g['inactive']).append(r)

    profiluri = []
    for p in store.lista_profiluri(tid):
        col, ra = store.profil_mapare(p)
        profiluri.append({'p': p, 'rand_antet': ra,
                          'rezumat': ', '.join(f'{k}→c{v}' for k, v in col.items())})

    return render_template('gantt/config.html', sin_grup=sin_grup, reg_grup=reg_grup,
                           profiluri=profiluri, campuri=campuri)


@gantt_bp.route('/config/sinonim', methods=['POST'])
@login_required
def config_sinonim_add():
    _row, err = store.adauga_sinonim(
        request.form.get('camp'), request.form.get('sinonim'),
        tenant_id=getattr(current_user, 'tenant_id', None),
        user_id=getattr(current_user, 'id', None))
    _invalideaza_motor()
    flash(err or 'Sinonim adaugat.', 'warning' if err else 'success')
    return redirect(url_for('gantt.config') + '#sinonime')


@gantt_bp.route('/config/regula', methods=['POST'])
@login_required
def config_regula_add():
    _row, err = store.adauga_regula(
        request.form.get('categorie'), request.form.get('tip_regula', 'cuvant'),
        request.form.get('valoare'), request.form.get('prioritate', 100),
        tenant_id=getattr(current_user, 'tenant_id', None),
        user_id=getattr(current_user, 'id', None))
    _invalideaza_motor()
    flash(err or 'Regula adaugata.', 'warning' if err else 'success')
    return redirect(url_for('gantt.config') + '#reguli')


@gantt_bp.route('/config/<entitate>/<int:id_>/comuta', methods=['POST'])
@login_required
def config_comuta(entitate, id_):
    if entitate not in ('sinonim', 'regula'):
        abort(404)
    row = store.comuta_activ(entitate, id_, getattr(current_user, 'tenant_id', None))
    _invalideaza_motor()
    flash('Stare actualizata.' if row else 'Nu am gasit randul.',
          'success' if row else 'warning')
    return redirect(url_for('gantt.config'))


@gantt_bp.route('/config/<entitate>/<int:id_>/sterge', methods=['POST'])
@login_required
def config_sterge(entitate, id_):
    if entitate not in ('sinonim', 'regula', 'profil'):
        abort(404)
    ok = store.sterge_rand(entitate, id_, getattr(current_user, 'tenant_id', None))
    if entitate in ('sinonim', 'regula'):
        _invalideaza_motor()
    flash('Sters definitiv.' if ok else 'Nu am gasit randul.', 'success' if ok else 'warning')
    return redirect(url_for('gantt.config'))


@gantt_bp.route('/config/profil/<int:id_>/redenumeste', methods=['POST'])
@login_required
def config_profil_redenumeste(id_):
    ok = store.redenumeste_profil(id_, request.form.get('nume', ''),
                                  getattr(current_user, 'tenant_id', None))
    flash('Profil redenumit.' if ok else 'Nu am gasit profilul.',
          'success' if ok else 'warning')
    return redirect(url_for('gantt.config') + '#profiluri')


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
