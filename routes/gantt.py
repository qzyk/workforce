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
from datetime import date

from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   send_file, jsonify, session, abort)
from flask_login import login_required, current_user

from services.gantt.pipeline import MotorPlanificare
from services.gantt.modele import Activitate, ArticolF3, RezultatPlanificare
from services.gantt import import_engine, export as export_engine, store, diagrama
from services.gantt.wbs import genereaza_wbs
from services.gantt.dependinte import genereaza_dependinte
from services.gantt.validare import valideaza

gantt_bp = Blueprint('gantt', __name__, url_prefix='/gantt')

_DIR_TEMP = os.path.join(tempfile.gettempdir(), 'edifico_gantt')
_EXT_OK = {'.xlsx', '.xlsm', '.xls', '.csv', '.xml'}
_motor_cache: dict = {}        # tenant_id -> MotorPlanificare (config per tenant)


def _tenant_curent():
    """tenant_id-ul utilizatorului curent (None = global / fara tenant)."""
    try:
        return getattr(current_user, 'tenant_id', None)
    except Exception:
        return None


def _motor() -> MotorPlanificare:
    """Instanta MotorPlanificare reutilizata, PE TENANT (config per organizatie).

    Bugfix: cache-ul global unic ignora regulile per-tenant pe fluxul implicit -
    acum cheia include tenant_id, deci fiecare tenant isi vede propriile reguli.
    """
    tid = _tenant_curent()
    motor = _motor_cache.get(tid)
    if motor is None:
        motor = _motor_cache[tid] = MotorPlanificare(tenant_id=tid)
    return motor


def _invalideaza_motor():
    """Forteaza reincarcarea configului la urmatorul import (dupa editari in admin).
    Invalideaza tot cache-ul (toate tenanturile) - simplu si sigur; limitarea
    cunoscuta ramane: doar procesul curent (pe PA e un singur proces web)."""
    _motor_cache.clear()


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


def _pipeline_din_temp(continut: bytes, ext: str, mapare=None, rand_antet=None,
                       preturi_boq=None, clasifica=None):
    """Ruleaza pipeline-ul (auto sau cu mapare manuala). (RezultatPlanificare, raport).
    Cu `preturi_boq` (din deviz) -> motor fresh ce costa activitatile pe preturi reale (5D).
    `clasifica` None -> se ia din sesiune (alegerea utilizatorului din wizard)."""
    if clasifica is None:
        clasifica = _clasifica_sesiune()
    motor = (MotorPlanificare(tenant_id=getattr(current_user, 'tenant_id', None),
                              preturi_boq=preturi_boq) if preturi_boq else _motor())
    if mapare:
        articole, raport = import_engine.importa(
            continut, ext, motor.setari, mapare_manuala=mapare, rand_antet_manual=rand_antet)
    else:
        articole, raport = import_engine.importa(continut, ext, motor.setari)
    rezultat = motor.proceseaza(articole, clasifica=clasifica)
    rezultat.statistici['import'] = raport
    return rezultat, raport


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


def _set_clasifica_sesiune(val: bool):
    """Tine alegerea 'clasifica automat' in sesiune (consistenta in tot wizard-ul)."""
    session['gantt_clasifica'] = bool(val)


def _clasifica_sesiune() -> bool:
    """Alegerea curenta de clasificare (implicit True = clasifica automat)."""
    return session.get('gantt_clasifica', True)


def _calendar_activ(plan=None):
    """CalendarLucru pentru fluxul curent DOAR cu flag-ul 'gantt-calendar' ON,
    altfel None (comportament istoric, doar Lu-Vi)."""
    try:
        from services.gantt import calendar_db
        return calendar_db.calendar_daca_activ(plan, _tenant_curent())
    except Exception:
        return None


def _tracking_on() -> bool:
    """True cand flag-ul 'gantt-tracking' e activ pentru tenantul curent."""
    try:
        from services.feature_flags import is_enabled
        return bool(is_enabled('gantt-tracking', _tenant_curent()))
    except Exception:
        return False


def _evm_pro_on() -> bool:
    """True cand flag-ul 'gantt-evm-pro' e activ pentru tenantul curent."""
    try:
        from services.feature_flags import is_enabled
        return bool(is_enabled('gantt-evm-pro', _tenant_curent()))
    except Exception:
        return False


def _evm_pe_plan(p):
    """EVM pe plan din tracking (Faza 3), DOAR cu flag ON + baseline/progres; None altfel."""
    if p is None:
        return None
    try:
        from services.gantt import evm_pro
        return evm_pro.evm_pe_plan(p, _tenant_curent(), data_stare=date.today(),
                                   calendar=_calendar_activ(p))
    except Exception:
        return None


def _progrese_active(plan_id):
    """{cheie: procent} pentru bare, DOAR cu flag ON; None altfel (progres 0 istoric)."""
    if not plan_id:
        return None
    try:
        from services.gantt import tracking_db
        return tracking_db.progrese_active(plan_id, _tenant_curent())
    except Exception:
        return None


def _baseline_activ(plan):
    """Snapshot baseline activ pentru overlay, DOAR cu flag ON; None altfel."""
    if plan is None:
        return None
    try:
        from services.gantt import tracking_db
        return tracking_db.baseline_activ(plan, _tenant_curent())
    except Exception:
        return None


def _render_rezultat(rezultat, raport_import, token, nume_fisier, plan_id=None):
    """Randeaza preview-ul rezultat + diagrama Gantt (4D) + optiunea de salvare."""
    session['gantt_nume_fisier'] = nume_fisier
    try:
        from models import Proiect
        proiecte = Proiect.query.order_by(Proiect.nume).all()
    except Exception:
        proiecte = []
    plan = None
    if plan_id:
        try:
            from models import db, GanttPlan
            plan = db.session.get(GanttPlan, plan_id)
        except Exception:
            plan = None
    calendar = _calendar_activ(plan)         # None cu flag OFF (zero regresie)
    from services.gantt import resurse_timp
    try:
        resurse = resurse_timp.histograma_resurse(rezultat, date.today(),
                                                  calendar=calendar)
    except Exception:
        resurse = None
    # Faza 2 tracking: progres real pe bare + overlay baseline, DOAR cu flag ON.
    progrese = _progrese_active(plan_id)     # None cu flag OFF -> bare cu progres 0
    baseline = _baseline_activ(plan)         # None cu flag OFF -> fara overlay
    return render_template(
        'gantt/rezultat.html', rezultat=rezultat, raport_import=raport_import,
        token=token, nume_fisier=nume_fisier,
        diagrama=diagrama.sarcini_gantt(rezultat, date.today(), calendar=calendar,
                                        progrese=progrese, baseline=baseline),
        resurse=resurse, tracking_on=_tracking_on(),
        proiecte=proiecte, plan_id=plan_id, clasifica=_clasifica_sesiune())


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
    # alegerea utilizatorului: clasifica automat (checkbox) — implicit DA
    clasifica = 'clasifica' in request.form
    _set_clasifica_sesiune(clasifica)
    mapare_folosita, rand_antet_folosit = None, None
    try:
        rezultat, raport_import = _motor().genereaza_din_fisier(continut, ext,
                                                                clasifica=clasifica)
    except import_engine.EroareImport:
        # 1) incearca un profil de mapare invatat anterior (acelasi tip de fisier)
        prof, mapare, rand_antet = _profil_pt_fisier(continut, ext, tid)
        if prof:
            try:
                rezultat, raport_import = _pipeline_din_temp(continut, ext, mapare, rand_antet,
                                                             clasifica=clasifica)
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

    return _render_rezultat(rezultat, raport_import, token, nume_fisier)


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
    # cu flag-ul 'gantt-calendar' ON: export cu date reale (start = azi, ca preview-ul)
    calendar = _calendar_activ()
    try:
        data, mime, ext_out = export_engine.exporta(
            fmt, rezultat, nume_proiect=nume,
            ore_pe_zi=_motor().setari.get('ore_pe_zi', 8),
            data_start=(date.today() if calendar is not None else None),
            calendar=calendar)
    except ValueError:
        abort(404)
    import io
    return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True,
                     download_name=f'planificare_{nume}.{ext_out}')


@gantt_bp.route('/export-f2/<token>')
@login_required
def export_f2(token):
    """Centralizator F2 (cost pe categorie de lucrare, descompus material/manopera/utilaj) - CSV."""
    if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
        abort(404)
    continut, ext = _citeste_temp(token)
    if not continut:
        flash('Sesiunea de preview a expirat. Reincarca fisierul F3.', 'warning')
        return redirect(url_for('gantt.index'))
    mapare, rand_antet = (None, None)
    if session.get('gantt_token') == token:
        mapare, rand_antet = _mapare_sesiune()
    try:
        rezultat, _ = _pipeline_din_temp(continut, ext, mapare, rand_antet)
    except import_engine.EroareImport:
        flash('Nu pot regenera centralizatorul. Reincarca fisierul F3.', 'warning')
        return redirect(url_for('gantt.index'))
    import csv as _csv
    import io
    st = rezultat.statistici
    out = io.StringIO()
    w = _csv.writer(out, delimiter=';')
    w.writerow(['Categorie lucrare', 'Nr articole', 'Material', 'Manopera', 'Utilaje', 'Total'])
    for r in st.get('centralizator_f2', []):
        w.writerow([r['categorie'], r['nr'], r['material'], r['manopera'], r['utilaj'], r['total']])
    w.writerow(['TOTAL', st.get('nr_activitati', 0), st.get('cost_material', 0),
                st.get('cost_manopera', 0), st.get('cost_utilaj', 0), st.get('cost_total', 0)])
    nume = session.get('gantt_nume', 'planificare')
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')), mimetype='text/csv',
                     as_attachment=True, download_name=f'centralizator_f2_{nume}.csv')


# ============================================================ PLANURI SALVATE
def _plan_sau_404(id_):
    from models import db, GanttPlan
    p = db.session.get(GanttPlan, id_)
    if not p or getattr(p, 'tenant_id', None) not in (None, getattr(current_user, 'tenant_id', None)):
        abort(404)
    return p


def _mapare_din_plan(p):
    import json
    if not p.mapare_json:
        return None, None
    try:
        d = json.loads(p.mapare_json)
        return d.get('coloane'), d.get('rand_antet')
    except Exception:
        return None, None


def _preturi_plan(p):
    """Preturi reale din deviz (5D) pentru proiectul planului, sau None."""
    if not getattr(p, 'proiect_id', None):
        return None
    try:
        from services.deviz_link import preturi_proiect, are_preturi
        pb = preturi_proiect(p.proiect_id)
        return pb if are_preturi(pb) else None
    except Exception:
        return None


@gantt_bp.route('/salveaza', methods=['POST'])
@login_required
def salveaza():
    token = request.form.get('token') or session.get('gantt_token')
    continut, ext = _citeste_temp(token)
    if not continut:
        flash('Sesiunea a expirat. Reincarca fisierul F3.', 'warning')
        return redirect(url_for('gantt.index'))
    nume = (request.form.get('nume') or session.get('gantt_nume') or 'Plan').strip()[:160]
    try:
        proiect_id = int(request.form.get('proiect_id')) if request.form.get('proiect_id') else None
    except (TypeError, ValueError):
        proiect_id = None

    mapare, rand_antet = (_mapare_sesiune() if session.get('gantt_token') == token else (None, None))
    try:
        rezultat, _ = _pipeline_din_temp(continut, ext, mapare, rand_antet)
    except import_engine.EroareImport as e:
        flash(f'Nu pot salva planul: {e}', 'danger')
        return redirect(url_for('gantt.index'))

    import json
    from models import db, GanttPlan
    from services import audit
    st = rezultat.statistici
    plan = GanttPlan(
        nume=nume, nume_fisier=session.get('gantt_nume_fisier'), ext=ext, continut=continut,
        mapare_json=(json.dumps({'coloane': mapare, 'rand_antet': rand_antet}) if mapare else None),
        data_start=date.today(),
        nr_activitati=st.get('nr_activitati', 0), durata_zile=st.get('durata_totala_zile', 0),
        cost_total=st.get('cost_total', 0) or 0,
        proiect_id=proiect_id, tenant_id=getattr(current_user, 'tenant_id', None),
        creat_de_id=getattr(current_user, 'id', None))
    db.session.add(plan)
    db.session.commit()
    audit.log('create', 'gantt_plan', plan.id,
              new_values={'nume': nume, 'proiect_id': proiect_id}, commit=True)
    flash(f'Plan "{nume}" salvat.', 'success')
    if request.form.get('actiune') == 'wbs':
        # salveaza + seedeaza arborele + deschide direct editorul WBS (din previzualizare)
        from services.gantt import wbs_editor
        wbs_editor.seed_arbore(plan, rezultat.noduri_wbs)
        return redirect(url_for('gantt.plan_wbs', id_=plan.id))
    return redirect(url_for('gantt.plan', id_=plan.id))


@gantt_bp.route('/planuri')
@login_required
def planuri():
    from sqlalchemy import or_
    from models import GanttPlan
    tid = getattr(current_user, 'tenant_id', None)
    q = GanttPlan.query
    q = q.filter(or_(GanttPlan.tenant_id == tid, GanttPlan.tenant_id.is_(None))) if tid is not None \
        else q.filter(GanttPlan.tenant_id.is_(None))
    return render_template('gantt/planuri.html',
                           planuri=q.order_by(GanttPlan.data_creare.desc()).all())


@gantt_bp.route('/plan/<int:id_>')
@login_required
def plan(id_):
    p = _plan_sau_404(id_)
    mapare, rand_antet = _mapare_din_plan(p)
    try:
        rezultat, raport_import = _pipeline_din_temp(p.continut, p.ext, mapare, rand_antet,
                                                     preturi_boq=_preturi_plan(p))
    except import_engine.EroareImport as e:
        flash(f'Nu pot deschide planul: {e}', 'danger')
        return redirect(url_for('gantt.planuri'))
    _aplica_arbore_salvat(rezultat, p.id)        # WBS editat are prioritate fata de auto
    token = _salveaza_temp(p.continut, p.ext)    # pt. butoanele de export din rezultat
    session['gantt_token'] = token
    session['gantt_ext'] = p.ext
    session['gantt_nume'] = p.nume
    _set_mapare_sesiune(mapare, rand_antet)
    return _render_rezultat(rezultat, raport_import, token, p.nume_fisier or p.nume, plan_id=p.id)


@gantt_bp.route('/plan/<int:id_>/sterge', methods=['POST'])
@login_required
def plan_sterge(id_):
    from models import db
    from services import audit
    p = _plan_sau_404(id_)
    db.session.delete(p)
    db.session.commit()
    audit.log('delete', 'gantt_plan', id_, commit=True)
    flash('Plan sters.', 'success')
    return redirect(url_for('gantt.planuri'))


@gantt_bp.route('/plan/<int:id_>/export/<fmt>')
@login_required
def plan_export(id_, fmt):
    p = _plan_sau_404(id_)
    mapare, rand_antet = _mapare_din_plan(p)
    # cu flag-ul 'gantt-calendar' ON: export cu date reale din data de start a planului
    calendar = _calendar_activ(p)
    try:
        rezultat, _ = _pipeline_din_temp(p.continut, p.ext, mapare, rand_antet,
                                         preturi_boq=_preturi_plan(p))
        _aplica_arbore_salvat(rezultat, p.id)    # export-ul respecta WBS-ul editat
        data, mime, ext_out = export_engine.exporta(
            fmt, rezultat, nume_proiect=p.nume, ore_pe_zi=_motor().setari.get('ore_pe_zi', 8),
            data_start=((p.data_start or date.today()) if calendar is not None else None),
            calendar=calendar)
    except (import_engine.EroareImport, ValueError):
        abort(404)
    import io
    return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True,
                     download_name=f'planificare_{p.nume}.{ext_out}')


# ===================== TRACKING (Faza 2: baseline + progres) =====================
def _rezultat_plan(p):
    """Re-ruleaza pipeline-ul determinist pe sursa unui plan salvat (cu preturi 5D
    si arbore WBS editat). Intoarce RezultatPlanificare sau None la eroare de import."""
    mapare, rand_antet = _mapare_din_plan(p)
    try:
        rezultat, _ = _pipeline_din_temp(p.continut, p.ext, mapare, rand_antet,
                                         preturi_boq=_preturi_plan(p))
    except import_engine.EroareImport:
        return None
    _aplica_arbore_salvat(rezultat, p.id)
    return rezultat


@gantt_bp.route('/plan/<int:id_>/baseline', methods=['POST'])
@login_required
def plan_baseline(id_):
    """Ingheata baseline-ul curent al planului (plan de referinta)."""
    if not _tracking_on():
        abort(404)
    p = _plan_sau_404(id_)
    rezultat = _rezultat_plan(p)
    if rezultat is None:
        flash('Nu pot regenera planul pentru baseline. Reincarca fisierul F3.', 'danger')
        return redirect(url_for('gantt.plan', id_=p.id))
    from services.gantt import tracking_db
    from services import audit
    nume = (request.form.get('nume') or '').strip() or None
    bl = tracking_db.inghetare_baseline(
        p, rezultat, nume=nume, tenant_id=_tenant_curent(),
        creat_de_id=getattr(current_user, 'id', None))
    audit.log('create', 'gantt_baseline', bl.id,
              new_values={'plan_id': p.id, 'nume': bl.nume}, commit=True)
    flash(f'Baseline "{bl.nume}" inghetat. Comparatia curent-vs-baseline e disponibila '
          'in pagina de urmarire.', 'success')
    return redirect(url_for('gantt.plan_tracking', id_=p.id))


@gantt_bp.route('/plan/<int:id_>/baseline/<int:bid>')
@login_required
def plan_baseline_compara(id_, bid):
    """Comparatie curent vs baseline (chei disparute / noi raportate, nu eroare)."""
    if not _tracking_on():
        abort(404)
    p = _plan_sau_404(id_)
    from models import db, GanttBaseline
    bl = db.session.get(GanttBaseline, bid)
    if bl is None or bl.plan_id != p.id:
        abort(404)
    rezultat = _rezultat_plan(p)
    if rezultat is None:
        flash('Nu pot regenera planul pentru comparatie.', 'danger')
        return redirect(url_for('gantt.plan_tracking', id_=p.id))
    import json
    from services.gantt import tracking
    snap = json.loads(bl.continut_json) if bl.continut_json else {}
    comparatie = tracking.compara_baseline(rezultat, snap)
    return render_template('gantt/plan_compara.html', p=p, baseline=bl,
                           comparatie=comparatie)


@gantt_bp.route('/plan/<int:id_>/tracking')
@login_required
def plan_tracking(id_):
    """Pagina de urmarire executie: introducere progres bulk + comparatie baseline."""
    if not _tracking_on():
        abort(404)
    p = _plan_sau_404(id_)
    rezultat = _rezultat_plan(p)
    if rezultat is None:
        flash('Nu pot deschide planul pentru urmarire. Reincarca fisierul F3.', 'danger')
        return redirect(url_for('gantt.planuri'))
    from services.gantt import tracking_db, tracking
    progrese_det = tracking_db.progrese_detaliat(p.id)
    progrese_simplu = {ck: v['procent'] for ck, v in progrese_det.items()}
    # sumar EV / durata ramasa pe baza progresului curent
    sumar = tracking.aplica_progres(
        list(rezultat.activitati or []),
        {ck: {'procent': v['procent']} for ck, v in progrese_det.items()},
        data_stare=date.today())
    from models import GanttBaseline
    baselines = (GanttBaseline.query.filter_by(plan_id=p.id)
                 .order_by(GanttBaseline.data_creare.desc()).all())
    # Faza 3: EVM pe plan (PV din baseline, EV din progres, forecast). None cu flag
    # OFF sau fara baseline/progres -> sectiunea EVM nu se afiseaza.
    evm = _evm_pe_plan(p)
    return render_template('gantt/plan_tracking.html', p=p, rezultat=rezultat,
                           activitati=(rezultat.activitati or []),
                           progrese=progrese_simplu, progrese_det=progrese_det,
                           sumar=sumar, baselines=baselines,
                           evm=evm, evm_pro_on=_evm_pro_on())


@gantt_bp.route('/plan/<int:id_>/progres', methods=['POST'])
@login_required
def plan_progres(id_):
    """Adauga progres fizic (bulk). Accepta JSON (API) sau form (din pagina tracking)."""
    if not _tracking_on():
        abort(404)
    p = _plan_sau_404(id_)
    intrari = []
    data_stare = None
    if request.is_json:
        body = request.get_json(silent=True) or {}
        intrari = body.get('progrese') or body.get('intrari') or []
        try:
            data_stare = date.fromisoformat(body['data_stare'][:10]) if body.get('data_stare') else None
        except (ValueError, TypeError, KeyError):
            data_stare = None
    else:
        # form bulk: campuri "pct_<cheie>" (+ optional data_stare comuna)
        try:
            data_stare = date.fromisoformat(request.form['data_stare'][:10]) \
                if request.form.get('data_stare') else None
        except (ValueError, TypeError, KeyError):
            data_stare = None
        for k, v in request.form.items():
            if k.startswith('pct_') and (v or '').strip() != '':
                intrari.append({'cheie': k[4:], 'procent': v})
    from services.gantt import tracking_db
    from services import audit
    nr = tracking_db.adauga_progres_bulk(
        p, intrari, data_stare=data_stare, sursa='manual',
        tenant_id=_tenant_curent(), creat_de_id=getattr(current_user, 'id', None))
    audit.log('update', 'gantt_plan', p.id,
              new_values={'progres_intrari': nr}, commit=True)
    if request.is_json:
        return jsonify({'ok': True, 'adaugate': nr})
    flash(f'{nr} inregistrari de progres salvate.', 'success')
    return redirect(url_for('gantt.plan_tracking', id_=p.id))


@gantt_bp.route('/plan/<int:id_>/evm')
@login_required
def plan_evm(id_):
    """EVM pe plan din tracking (Faza 3): PV din baseline, EV din progres, forecast.

    JSON. Optional ?data_stare=YYYY-MM-DD (implicit azi). Cu flag 'gantt-evm-pro' OFF
    sau plan fara baseline/progres -> 404 (fara EVM pe plan, comportament neschimbat)."""
    if not _evm_pro_on():
        abort(404)
    p = _plan_sau_404(id_)
    try:
        data_stare = (date.fromisoformat(request.args['data_stare'][:10])
                      if request.args.get('data_stare') else date.today())
    except (ValueError, TypeError):
        data_stare = date.today()
    from services.gantt import evm_pro
    rez = evm_pro.evm_pe_plan(p, _tenant_curent(), data_stare=data_stare,
                              calendar=_calendar_activ(p))
    if rez is None:
        abort(404)
    return jsonify(rez)


# ===================== EDITOR WBS (pe plan salvat) =====================
def _aplica_arbore_salvat(rezultat, plan_id):
    """Daca planul are arbore WBS salvat, inlocuieste WBS-ul auto cu cel editat."""
    from services.gantt import wbs_editor
    if plan_id and wbs_editor.arbore_exista(plan_id):
        noduri_db = wbs_editor.noduri_plan(plan_id)
        rezultat.noduri_wbs = wbs_editor.wbs_din_arbore(rezultat.activitati, noduri_db)
    return rezultat


def _arbore_nested(plan_id):
    """(arbore_nested, grupuri_flat) pentru editorul WBS."""
    from services.gantt import wbs_editor
    noduri = wbs_editor.noduri_plan(plan_id)
    by_parent: dict = {}
    for n in noduri:
        by_parent.setdefault(n.parinte_id, []).append(n)
    for k in by_parent:
        by_parent[k].sort(key=lambda x: (x.ordine, x.id))
    grupuri = [n for n in noduri if n.tip == 'grup']

    def build(pid):
        return [{'nod': n, 'copii': build(n.id)} for n in by_parent.get(pid, [])]
    return build(None), grupuri


@gantt_bp.route('/plan/<int:id_>/wbs')
@login_required
def plan_wbs(id_):
    """Editor WBS pentru un plan salvat. Seedeaza arborele din auto la prima intrare."""
    from services.gantt import wbs_editor
    p = _plan_sau_404(id_)
    if not wbs_editor.arbore_exista(p.id):
        mapare, rand_antet = _mapare_din_plan(p)
        try:
            rezultat, _ = _pipeline_din_temp(p.continut, p.ext, mapare, rand_antet)
        except import_engine.EroareImport as e:
            flash(f'Nu pot genera WBS-ul: {e}', 'danger')
            return redirect(url_for('gantt.plan', id_=p.id))
        wbs_editor.seed_arbore(p, rezultat.noduri_wbs)
    arbore, grupuri = _arbore_nested(p.id)
    return render_template('gantt/wbs_editor.html', p=p, arbore=arbore, grupuri=grupuri)


@gantt_bp.route('/plan/<int:id_>/wbs/op', methods=['POST'])
@login_required
def plan_wbs_op(id_):
    """Operatii editor: redenumeste / sus / jos / muta / adauga / sterge / reset."""
    from services.gantt import wbs_editor
    p = _plan_sau_404(id_)
    act = request.form.get('actiune')
    nod_id = request.form.get('nod_id', type=int)
    if act == 'redenumeste':
        wbs_editor.redenumeste(p.id, nod_id, request.form.get('nume'))
    elif act in ('sus', 'jos'):
        wbs_editor.muta(p.id, nod_id, act)
    elif act == 'muta':
        wbs_editor.muta_in_grup(p.id, nod_id, request.form.get('grup_id', type=int) or None)
    elif act == 'adauga':
        if wbs_editor.adauga_grup(p, request.form.get('nume'),
                                  request.form.get('parinte_id', type=int) or None):
            flash('Grup adaugat.', 'success')
    elif act == 'sterge':
        wbs_editor.sterge_nod(p.id, nod_id)
    elif act == 'reset':
        wbs_editor.reset(p.id)
        flash('WBS resetat la structura automata.', 'success')
        return redirect(url_for('gantt.plan', id_=p.id))
    return redirect(url_for('gantt.plan_wbs', id_=p.id))


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
    mapare_reguli = {}            # categoria Gantt suprascrisa in DB -> randul (pentru stergere)
    for r in store.lista_reguli(tid):
        if r.tip_regula == 'mapare_categorie':
            mapare_reguli[r.valoare] = r
            continue              # nu poluam tabelul de clasificare
        if r.tip_regula not in ('cuvant', 'prefix_cod'):
            continue
        g = reg_grup.setdefault(r.categorie, {'active': [], 'inactive': []})
        (g['active'] if r.activ else g['inactive']).append(r)

    profiluri = []
    for p in store.lista_profiluri(tid):
        col, ra = store.profil_mapare(p)
        profiluri.append({'p': p, 'rand_antet': ra,
                          'rezumat': ', '.join(f'{k}→c{v}' for k, v in col.items())})

    # F2: maparea categoriilor Gantt -> categorie_lucrare (taxonomie unica)
    mapare = dict(sorted(store.mapare_categorii(tid).items()))

    return render_template('gantt/config.html', sin_grup=sin_grup, reg_grup=reg_grup,
                           profiluri=profiluri, campuri=campuri,
                           mapare=mapare, mapare_reguli=mapare_reguli,
                           tarife=store.lista_tarife(tid))


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


@gantt_bp.route('/config/mapare', methods=['POST'])
@login_required
def config_mapare_add():
    """Suprascrie maparea unei categorii Gantt -> categorie_lucrare (F2)."""
    _row, err = store.adauga_regula(
        request.form.get('categorie_lucrare'), 'mapare_categorie',
        request.form.get('categorie_gantt'),
        tenant_id=getattr(current_user, 'tenant_id', None),
        user_id=getattr(current_user, 'id', None))
    _invalideaza_motor()
    flash(err or 'Mapare salvata.', 'warning' if err else 'success')
    return redirect(url_for('gantt.config') + '#mapare')


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


@gantt_bp.route('/config/tarif', methods=['POST'])
@login_required
def config_tarif_set():
    cat = request.form.get('categorie')
    um = request.form.get('um')
    tid = getattr(current_user, 'tenant_id', None)
    uid = getattr(current_user, 'id', None)
    _row, err = store.seteaza_tarif(cat, request.form.get('tarif'), um, tenant_id=tid, user_id=uid)
    err2 = None
    rand = request.form.get('randament')
    if rand not in (None, ''):
        _r2, err2 = store.seteaza_randament(cat, rand, um, tenant_id=tid, user_id=uid)
    _invalideaza_motor()
    flash(err or err2 or 'Tarif si randament actualizate.',
          'warning' if (err or err2) else 'success')
    return redirect(url_for('gantt.config') + '#tarife')


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


# ============================================================
# Ingestie obiectiv: arbore Obiectiv (F1) -> Obiect (F2) -> GanttPlan (F3)
# ============================================================

@gantt_bp.route('/obiective')
@login_required
def obiective_lista():
    from models import Obiectiv
    obiective = Obiectiv.query.order_by(Obiectiv.data_creare.desc()).all()
    return render_template('gantt/obiective_lista.html', obiective=obiective)


@gantt_bp.route('/obiective/incarca', methods=['POST'])
@login_required
def obiective_incarca():
    """Ingestie obiectiv din UI: upload multiplu (F1 + F2-uri + F3-uri .xls/.xlsx).

    Fisierele se salveaza intr-un director temporar cu numele originale
    (clasificarea F1/F2/F3 se face dupa numele fisierului), apoi trec prin
    acelasi flux ca CLI-ul `ingereaza-obiectiv` (idempotent)."""
    import shutil
    import tempfile
    from werkzeug.utils import secure_filename
    from services.ingestie_obiectiv import ingereaza

    fisiere = [f for f in request.files.getlist('fisiere') if f and f.filename]
    if not fisiere:
        flash('Selecteaza fisierele obiectivului (F1 + F2-uri + F3-uri).', 'warning')
        return redirect(url_for('gantt.obiective_lista'))
    # Nume explicit intotdeauna: fara el, ingestia ar folosi numele folderului
    # temporar (ex "obiectiv_x3opb34y") - bug prins pe prod.
    nume = (request.form.get('nume') or '').strip()
    if not nume:
        nume = f'Obiectiv {date.today().strftime("%d.%m.%Y")}'

    tmpdir = tempfile.mkdtemp(prefix='obiectiv_')
    try:
        salvate = 0
        for f in fisiere:
            fn = secure_filename(f.filename)
            if not fn.lower().endswith(('.xls', '.xlsx')):
                continue
            f.save(os.path.join(tmpdir, fn))
            salvate += 1
        if not salvate:
            flash('Niciun fisier .xls/.xlsx valid in selectie.', 'warning')
            return redirect(url_for('gantt.obiective_lista'))
        stats = ingereaza(tmpdir, nume, creat_de_id=current_user.id)
        flash(f"Obiectiv \"{stats['nume_obiectiv']}\": {stats['nr_obiecte']} obiecte, "
              f"{stats['nr_planuri']} liste F3 "
              f"({stats['planuri_create']} noi, {stats['planuri_actualizate']} actualizate).",
              'success')
        return redirect(url_for('gantt.obiectiv_detalii', id=stats['obiectiv_id']))
    except Exception as e:
        flash(f'Ingestia a esuat: {e}', 'danger')
        return redirect(url_for('gantt.obiective_lista'))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@gantt_bp.route('/obiectiv/<int:id>')
@login_required
def obiectiv_detalii(id):
    from models import Obiectiv
    ob = Obiectiv.query.get_or_404(id)
    return render_template('gantt/obiectiv_detalii.html', ob=ob)


def _slug_obiectiv(nume):
    return re.sub(r'[^A-Za-z0-9]+', '_', nume or 'obiectiv').strip('_')[:50] or 'obiectiv'


@gantt_bp.route('/obiectiv/<int:id>/export.xlsx')
@login_required
def obiectiv_export_xlsx(id):
    from io import BytesIO
    from models import Obiectiv
    from services.export_obiectiv import export_xlsx
    ob = Obiectiv.query.get_or_404(id)
    data = export_xlsx(id)
    return send_file(BytesIO(data), as_attachment=True,
                     download_name=f'Centralizator_{_slug_obiectiv(ob.nume)}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@gantt_bp.route('/obiectiv/<int:id>/planifica')
@login_required
def obiectiv_planifica(id):
    """Planificare Gantt consolidata din obiectiv (F1): toate listele F3,
    cu drill-down F1 -> F2 (obiect) -> F3 (lista) in WBS. Trece prin fluxul
    existent (CSV intern -> pipeline -> rezultat cu diagrama/exporturi)."""
    from models import Obiectiv
    from services.gantt import planificare_obiectiv
    ob = Obiectiv.query.get_or_404(id)
    csv_bytes, raport_cons = planificare_obiectiv.csv_obiectiv(id)
    if not raport_cons['nr_articole']:
        flash('Nicio lista F3 parsabila in acest obiectiv. '
              f"Erori: {raport_cons['erori']}.", 'warning')
        return redirect(url_for('gantt.obiectiv_detalii', id=id))
    if raport_cons['erori']:
        liste_err = [l['lista'] for l in raport_cons['liste'] if l.get('eroare')]
        flash(f"{raport_cons['erori']} liste F3 nu s-au putut parsa si au fost "
              f"sarite: {', '.join(liste_err[:5])}", 'warning')
    token = _salveaza_temp(csv_bytes, '.csv')
    try:
        rezultat, raport_import = _motor().genereaza_din_fisier(csv_bytes, '.csv')
    except import_engine.EroareImport as e:
        flash(f'Planificarea a esuat: {e}', 'danger')
        return redirect(url_for('gantt.obiectiv_detalii', id=id))
    return _render_rezultat(rezultat, raport_import, token, f'Obiectiv: {ob.nume}')


@gantt_bp.route('/obiectiv/<int:id>/export.pdf')
@login_required
def obiectiv_export_pdf(id):
    from io import BytesIO
    from models import Obiectiv
    from services.export_obiectiv import export_pdf
    ob = Obiectiv.query.get_or_404(id)
    data = export_pdf(id)
    return send_file(BytesIO(data), as_attachment=True,
                     download_name=f'Centralizator_{_slug_obiectiv(ob.nume)}.pdf',
                     mimetype='application/pdf')
