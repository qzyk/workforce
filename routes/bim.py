"""
EDIFICO WORKFORCE - Modul BIM (Building Information Modeling)
Blueprint: /bim

Rutele expun:
- /bim                       -> dashboard / tree-view
- /bim/santiere              -> CRUD santiere
- /bim/cladiri               -> CRUD cladiri
- /bim/elemente              -> CRUD elemente BIM + filtre
- /bim/issues                -> CRUD issues BIM
- /bim/api/tree              -> JSON tree (santier > cladire > nivel > spatiu > element)
- /bim/api/elemente          -> JSON elemente (filtre: tip, status, cladire, nivel)
- /bim/api/element/<id>      -> JSON detaliu element + activitati workforce asociate
"""

import json
import os
from datetime import datetime, date
from functools import wraps
from io import BytesIO

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, abort, send_file, current_app
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import (
    BIMModelVersion, BIMRule, RuleViolation, ClashRun, ClashResult,
    BIMTaskSchedule, BIMCostItem,
    Senzor, SensorReading, SensorAlert,
    BIMComment, UserPresence, RealtimeEvent,
    BIMRoleAssignment, ApiToken, Utilizator,
    db, Santier, Cladire, Nivel, Zona, Spatiu, ElementBIM, Asset,
    IssueBIM, ModelBIM, Proiect, RaportActivitate, Pontaj,
    ExternalMapping,
)
from services import ifc_import as ifc_service
from services import bim_quality
from services import audit as audit_svc
from services import bim_workflow
from services import bim_rules as rules_svc
from services import clash_detection as clash_svc
from services import bim_4d as fourd_svc
from services import bim_5d as fived_svc
from services import iot_ingest as iot_ingest_svc
from services import iot_query as iot_query_svc
from services import realtime as rt_svc
from services import presence as presence_svc
from services import rbac as rbac_svc
from services import api_tokens as tokens_svc
from services import cobie_export as cobie_svc
from services import bcf_io as bcf_svc
from services import openapi as openapi_svc
from services import feature_flags as ff_svc
from services import feature_flags
from services import aps_viewer

bim_bp = Blueprint('bim', __name__, url_prefix='/bim')


# ============================================================
# DECORATORI / PERMISIUNI
# ============================================================

def manager_or_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.rol not in ('admin', 'manager'):
            flash('Doar managerii / administratorii pot edita BIM.', 'danger')
            return redirect(url_for('bim.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# DASHBOARD / TREE-VIEW
# ============================================================

@bim_bp.route('/')
@login_required
def dashboard():
    """Pagina principala BIM - prezentare santiere si statistici."""
    santiere = Santier.query.order_by(Santier.cod).all()
    nr_cladiri = Cladire.query.count()
    nr_elemente = ElementBIM.query.count()
    nr_issues_deschise = IssueBIM.query.filter(
        IssueBIM.status.in_(['deschis', 'in_lucru'])
    ).count()
    return render_template('bim/dashboard.html',
        santiere=santiere,
        nr_cladiri=nr_cladiri,
        nr_elemente=nr_elemente,
        nr_issues_deschise=nr_issues_deschise,
    )


# ============================================================
# SANTIERE - CRUD
# ============================================================

@bim_bp.route('/santiere')
@login_required
def santiere_lista():
    santiere = Santier.query.order_by(Santier.cod).all()
    return render_template('bim/santiere_lista.html', santiere=santiere)


@bim_bp.route('/santier/<int:id>')
@login_required
def santier_detaliu(id):
    s = Santier.query.get_or_404(id)
    return render_template('bim/santier_detaliu.html', santier=s)


@bim_bp.route('/santier/nou', methods=['GET', 'POST'])
@login_required
@manager_or_admin
def santier_nou():
    if request.method == 'POST':
        try:
            s = Santier(
                cod=request.form.get('cod', '').strip(),
                nume=request.form.get('nume', '').strip(),
                descriere=request.form.get('descriere', '').strip(),
                adresa=request.form.get('adresa', '').strip(),
                oras=request.form.get('oras', '').strip(),
                judet=request.form.get('judet', '').strip(),
                proiect_id=request.form.get('proiect_id', type=int) or None,
            )
            if not s.cod or not s.nume:
                flash('Codul si numele sunt obligatorii.', 'danger')
                return redirect(request.url)
            db.session.add(s)
            db.session.flush()  # populate s.id pentru audit
            audit_svc.log_create('santier', s.id, new_values={
                'cod': s.cod, 'nume': s.nume, 'oras': s.oras, 'judet': s.judet,
            })
            db.session.commit()
            flash(f'Santier "{s.nume}" creat.', 'success')
            return redirect(url_for('bim.santier_detaliu', id=s.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')

    proiecte = Proiect.query.filter(Proiect.status.in_(['activ', 'planificat'])).order_by(Proiect.cod_proiect).all()
    return render_template('bim/santier_formular.html', santier=None, proiecte=proiecte)


@bim_bp.route('/santier/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
@manager_or_admin
def santier_editeaza(id):
    s = Santier.query.get_or_404(id)
    if request.method == 'POST':
        try:
            audit_fields = ['cod', 'nume', 'descriere', 'adresa', 'oras', 'judet', 'proiect_id']
            before = audit_svc.snapshot(s, audit_fields)
            s.cod = request.form.get('cod', '').strip()
            s.nume = request.form.get('nume', '').strip()
            s.descriere = request.form.get('descriere', '').strip()
            s.adresa = request.form.get('adresa', '').strip()
            s.oras = request.form.get('oras', '').strip()
            s.judet = request.form.get('judet', '').strip()
            s.proiect_id = request.form.get('proiect_id', type=int) or None
            audit_svc.log_update('santier', s.id, before, audit_svc.snapshot(s, audit_fields))
            db.session.commit()
            flash(f'Santier "{s.nume}" actualizat.', 'success')
            return redirect(url_for('bim.santier_detaliu', id=s.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')

    proiecte = Proiect.query.filter(Proiect.status.in_(['activ', 'planificat'])).order_by(Proiect.cod_proiect).all()
    return render_template('bim/santier_formular.html', santier=s, proiecte=proiecte)


@bim_bp.route('/santier/<int:id>/sterge', methods=['POST'])
@login_required
@manager_or_admin
def santier_sterge(id):
    s = Santier.query.get_or_404(id)
    try:
        audit_svc.log_delete('santier', s.id, old_values={
            'cod': s.cod, 'nume': s.nume, 'oras': s.oras, 'judet': s.judet,
        })
        nume_sters = s.nume
        db.session.delete(s)
        db.session.commit()
        flash(f'Santier "{nume_sters}" sters.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    return redirect(url_for('bim.santiere_lista'))


# ============================================================
# ELEMENTE BIM - listare + filtrare
# ============================================================

@bim_bp.route('/elemente')
@login_required
def elemente_lista():
    f_tip = request.args.get('tip', '').strip()
    f_status = request.args.get('status', '').strip()
    f_cladire = request.args.get('cladire_id', type=int) or None

    q = ElementBIM.query
    if f_tip:
        q = q.filter_by(tip_element=f_tip)
    if f_status:
        q = q.filter_by(status=f_status)
    if f_cladire:
        q = q.filter_by(cladire_id=f_cladire)

    elemente = q.order_by(ElementBIM.cod).limit(200).all()
    cladiri = Cladire.query.order_by(Cladire.cod).all()
    tipuri = ElementBIM.TIPURI
    return render_template('bim/elemente_lista.html',
        elemente=elemente,
        cladiri=cladiri,
        tipuri=tipuri,
        f_tip=f_tip, f_status=f_status, f_cladire=f_cladire,
    )


@bim_bp.route('/element/<int:id>')
@login_required
def element_detaliu(id):
    e = ElementBIM.query.get_or_404(id)
    # Activitati workforce asociate
    rapoarte = RaportActivitate.query.filter_by(element_bim_id=e.id).order_by(
        RaportActivitate.data.desc()
    ).limit(20).all()
    pontaje = Pontaj.query.filter_by(element_bim_id=e.id).order_by(
        Pontaj.data.desc()
    ).limit(20).all()
    issues = IssueBIM.query.filter_by(element_bim_id=e.id).order_by(
        IssueBIM.data_creare.desc()
    ).all()
    # Quick navigation: alte elemente in aceeasi zona/nivel/cladire
    quick_jump = []
    if e.spatiu_id:
        quick_jump = ElementBIM.query.filter(
            ElementBIM.spatiu_id == e.spatiu_id,
            ElementBIM.id != e.id,
        ).limit(8).all()
    elif e.nivel_id:
        quick_jump = ElementBIM.query.filter(
            ElementBIM.nivel_id == e.nivel_id,
            ElementBIM.id != e.id,
        ).limit(8).all()
    elif e.cladire_id:
        quick_jump = ElementBIM.query.filter(
            ElementBIM.cladire_id == e.cladire_id,
            ElementBIM.id != e.id,
        ).limit(8).all()

    return render_template('bim/element_detaliu.html',
        element=e,
        rapoarte=rapoarte,
        pontaje=pontaje,
        issues=issues,
        quick_jump=quick_jump,
    )


# ============================================================
# ISSUES BIM
# ============================================================

@bim_bp.route('/issues')
@login_required
def issues_lista():
    f_status = request.args.get('status', '').strip()
    f_severitate = request.args.get('severitate', '').strip()
    f_tip = request.args.get('tip', '').strip()

    q = IssueBIM.query
    if f_status:
        q = q.filter_by(status=f_status)
    if f_severitate:
        q = q.filter_by(severitate=f_severitate)
    if f_tip:
        q = q.filter_by(tip=f_tip)

    issues = q.order_by(IssueBIM.data_creare.desc()).limit(100).all()
    return render_template('bim/issues_lista.html',
        issues=issues,
        f_status=f_status, f_severitate=f_severitate, f_tip=f_tip,
        TIPURI=IssueBIM.TIPURI,
        SEVERITATI=IssueBIM.SEVERITATI,
        STATUSURI=IssueBIM.STATUSURI,
    )


# ============================================================
# API JSON - pentru tree-view & ajax filtering
# ============================================================

@bim_bp.route('/api/tree')
@login_required
def api_tree():
    """Returneaza arborele BIM complet ca JSON."""
    rezultat = []
    for s in Santier.query.order_by(Santier.cod).all():
        s_node = {
            'tip': 'santier',
            'id': s.id,
            'cod': s.cod,
            'nume': s.nume,
            'cladiri': []
        }
        for c in s.cladiri.order_by(Cladire.cod):
            c_node = {
                'tip': 'cladire',
                'id': c.id,
                'cod': c.cod,
                'nume': c.nume,
                'niveluri': []
            }
            for n in c.niveluri.order_by(Nivel.ordine):
                n_node = {
                    'tip': 'nivel',
                    'id': n.id,
                    'cod': n.cod,
                    'nume': n.nume,
                    'ordine': n.ordine,
                    'spatii': []
                }
                for sp in n.spatii.order_by(Spatiu.cod):
                    sp_node = {
                        'tip': 'spatiu',
                        'id': sp.id,
                        'cod': sp.cod,
                        'nume': sp.nume,
                        'tip_spatiu': sp.tip_spatiu,
                        'nr_elemente': sp.elemente.count(),
                    }
                    n_node['spatii'].append(sp_node)
                c_node['niveluri'].append(n_node)
            s_node['cladiri'].append(c_node)
        rezultat.append(s_node)
    return jsonify(rezultat)


@bim_bp.route('/api/element/<int:id>')
@login_required
def api_element(id):
    """JSON detaliu element BIM + activitati / issues asociate."""
    e = ElementBIM.query.get_or_404(id)
    return jsonify({
        'id': e.id,
        'cod': e.cod,
        'nume': e.nume,
        'tip_element': e.tip_element,
        'tip_label': e.tip_label,
        'tip_categorie': e.tip_categorie,
        'status': e.status,
        'cale_completa': e.cale_completa,
        'cantitate': float(e.cantitate) if e.cantitate else None,
        'unitate_masura': e.unitate_masura,
        'ifc_global_id': e.ifc_global_id,
        'asset': {
            'producator': e.asset.producator,
            'model': e.asset.model,
            'serial': e.asset.serial,
            'in_garantie': e.asset.in_garantie,
            'urmatoarea_mentenanta': e.asset.urmatoarea_mentenanta.isoformat() if e.asset and e.asset.urmatoarea_mentenanta else None,
        } if e.asset else None,
        'nr_activitati': RaportActivitate.query.filter_by(element_bim_id=e.id).count(),
        'nr_issues_deschise': IssueBIM.query.filter_by(element_bim_id=e.id).filter(
            IssueBIM.status.in_(['deschis', 'in_lucru'])
        ).count(),
    })


@bim_bp.route('/api/santier/<int:santier_id>/cladiri')
@login_required
def api_cladiri_santier(santier_id):
    """Cladirile dintr-un santier (pentru cascada picker)."""
    cladiri = Cladire.query.filter_by(santier_id=santier_id).order_by(Cladire.cod).all()
    return jsonify([{'id': c.id, 'cod': c.cod, 'nume': c.nume} for c in cladiri])


@bim_bp.route('/api/cladire/<int:cladire_id>/niveluri')
@login_required
def api_niveluri_cladire(cladire_id):
    """Niveluri dintr-o cladire."""
    niveluri = Nivel.query.filter_by(cladire_id=cladire_id).order_by(Nivel.ordine).all()
    return jsonify([{'id': n.id, 'cod': n.cod, 'nume': n.nume, 'ordine': n.ordine} for n in niveluri])


@bim_bp.route('/api/nivel/<int:nivel_id>/spatii')
@login_required
def api_spatii_nivel(nivel_id):
    """Spatii dintr-un nivel."""
    spatii = Spatiu.query.filter_by(nivel_id=nivel_id).order_by(Spatiu.cod).all()
    return jsonify([{'id': sp.id, 'cod': sp.cod, 'nume': sp.nume, 'tip_spatiu': sp.tip_spatiu} for sp in spatii])


@bim_bp.route('/api/search')
@login_required
def api_search():
    """Search global BIM (autocomplete)."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    like = f'%{q}%'
    rezultat = []
    # Elemente
    for e in ElementBIM.query.filter(db.or_(
        ElementBIM.cod.ilike(like), ElementBIM.nume.ilike(like)
    )).limit(10).all():
        rezultat.append({
            'tip': 'element', 'id': e.id, 'cod': e.cod, 'label': e.cod + ' (' + e.tip_label + ')',
            'cale': e.cale_completa, 'url': url_for('bim.element_detaliu', id=e.id),
        })
    # Spatii
    for sp in Spatiu.query.filter(db.or_(
        Spatiu.cod.ilike(like), Spatiu.nume.ilike(like)
    )).limit(5).all():
        rezultat.append({
            'tip': 'spatiu', 'id': sp.id, 'cod': sp.cod, 'label': sp.cod + ' - ' + (sp.nume or ''),
            'cale': '', 'url': '#',  # TODO: spatiu_detaliu
        })
    # Santiere
    for s in Santier.query.filter(db.or_(
        Santier.cod.ilike(like), Santier.nume.ilike(like)
    )).limit(5).all():
        rezultat.append({
            'tip': 'santier', 'id': s.id, 'cod': s.cod, 'label': s.cod + ' - ' + s.nume,
            'cale': '', 'url': url_for('bim.santier_detaliu', id=s.id),
        })
    return jsonify(rezultat)


@bim_bp.route('/api/elemente')
@login_required
def api_elemente():
    """Lista elemente filtrabila pentru AJAX (multi-select etc.)."""
    f_cladire = request.args.get('cladire_id', type=int)
    f_nivel = request.args.get('nivel_id', type=int)
    f_spatiu = request.args.get('spatiu_id', type=int)
    f_tip = request.args.get('tip', '').strip()
    f_q = request.args.get('q', '').strip()

    q = ElementBIM.query
    if f_cladire:
        q = q.filter_by(cladire_id=f_cladire)
    if f_nivel:
        q = q.filter_by(nivel_id=f_nivel)
    if f_spatiu:
        q = q.filter_by(spatiu_id=f_spatiu)
    if f_tip:
        q = q.filter_by(tip_element=f_tip)
    if f_q:
        like = f'%{f_q}%'
        q = q.filter(db.or_(
            ElementBIM.cod.ilike(like),
            ElementBIM.nume.ilike(like),
        ))

    elemente = q.order_by(ElementBIM.cod).limit(50).all()
    return jsonify([{
        'id': e.id,
        'cod': e.cod,
        'nume': e.nume,
        'tip_element': e.tip_element,
        'tip_label': e.tip_label,
        'cale_completa': e.cale_completa,
    } for e in elemente])


# ============================================================
# IFC IMPORT / EXPORT
# ============================================================

@bim_bp.route('/import/ifc', methods=['GET', 'POST'])
@login_required
@manager_or_admin
def import_ifc_view():
    """Pagina de import IFC + procesare upload."""
    rezultat = None
    if request.method == 'POST':
        file = request.files.get('ifc_file')
        if not file or not file.filename:
            flash('Selectati un fisier IFC.', 'danger')
            return redirect(request.url)
        if not file.filename.lower().endswith('.ifc'):
            flash('Doar fisiere .ifc sunt acceptate.', 'danger')
            return redirect(request.url)

        # Salvez fisierul temporar
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'ifc')
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(upload_dir, f'{timestamp}_{safe_name}')
        file.save(path)

        santier_id = request.form.get('santier_id', type=int) or None
        dry_run = bool(request.form.get('dry_run'))

        rezultat = ifc_service.import_ifc(path, santier_id=santier_id, dry_run=dry_run)

        # Inregistrez modelul in tabela bim_modele (chiar daca dry_run)
        try:
            stats = rezultat.get('statistici', {})
            m = ModelBIM(
                santier_id=rezultat.get('santier_id') or santier_id,
                nume=safe_name,
                tip='ifc',
                fisier_path=os.path.relpath(path, current_app.root_path),
                fisier_marime=os.path.getsize(path),
                nr_elemente=stats.get('elemente_create', 0),
                nr_spatii=stats.get('spatii_create', 0),
                procesare_status='procesat' if rezultat['status'] == 'ok' else 'eroare',
                procesare_log=rezultat.get('mesaj', ''),
                incarcat_de_id=current_user.id,
            )
            db.session.add(m)
            db.session.flush()
            audit_svc.log_create('model_bim', m.id, new_values={
                'nume': m.nume, 'tip': m.tip, 'fisier_marime': m.fisier_marime,
                'nr_elemente': m.nr_elemente, 'procesare_status': m.procesare_status,
                'santier_id': m.santier_id,
            })
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            rezultat['errors'].append(f'log model: {e}')

        if rezultat['status'] == 'ok':
            flash(rezultat['mesaj'], 'success')
        else:
            flash(rezultat['mesaj'], 'danger')

    santiere = Santier.query.order_by(Santier.cod).all()
    return render_template('bim/import_ifc.html',
        santiere=santiere,
        rezultat=rezultat,
        ifcopenshell_disponibil=ifc_service.is_available(),
    )


@bim_bp.route('/export/bcf')
@login_required
def export_bcf():
    """Export BCF cu toate issues (sau filtrate)."""
    f_status = request.args.get('status', '').strip()
    q = IssueBIM.query
    if f_status:
        q = q.filter_by(status=f_status)
    else:
        q = q.filter(IssueBIM.status.in_(['deschis', 'in_lucru']))
    issues = q.all()
    if not issues:
        flash('Nu exista issues de exportat.', 'warning')
        return redirect(url_for('bim.issues_lista'))

    bcf_zip = ifc_service.export_bcf(issues)
    filename = f'bim_issues_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.bcf'
    return send_file(
        bcf_zip,
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name=filename,
    )


# ============================================================
# MODELE BIM - CRUD (intern IFC + viewer extern)
# ============================================================

@bim_bp.route('/modele')
@login_required
def modele_lista():
    modele = ModelBIM.query.order_by(ModelBIM.data_incarcare.desc()).all()
    return render_template('bim/modele_lista.html', modele=modele)


@bim_bp.route('/model/extern/nou', methods=['GET', 'POST'])
@login_required
@manager_or_admin
def model_extern_nou():
    """Adauga un model BIM gazduit extern (Trimble/Autodesk/BIMx/...)"""
    if request.method == 'POST':
        try:
            extern_url = request.form.get('extern_url', '').strip()
            if not extern_url:
                flash('URL-ul extern e obligatoriu.', 'danger')
                return redirect(request.url)
            m = ModelBIM(
                nume=request.form.get('nume', '').strip() or 'Viewer extern',
                descriere=request.form.get('descriere', '').strip(),
                tip='viewer_extern',
                versiune=request.form.get('versiune', '').strip(),
                autor=request.form.get('autor', '').strip(),
                extern_url=extern_url,
                santier_id=request.form.get('santier_id', type=int) or None,
                cladire_id=request.form.get('cladire_id', type=int) or None,
                procesare_status='extern',
                incarcat_de_id=current_user.id,
            )
            db.session.add(m)
            db.session.commit()
            flash(f'Viewer extern "{m.nume}" inregistrat.', 'success')
            return redirect(url_for('bim.modele_lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare: {e}', 'danger')

    santiere = Santier.query.order_by(Santier.cod).all()
    cladiri = Cladire.query.order_by(Cladire.cod).all()
    return render_template('bim/model_extern_formular.html',
        model=None, santiere=santiere, cladiri=cladiri,
        viewere_preset=ModelBIM.VIEWERE_EXTERNE,
    )


@bim_bp.route('/model/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
@manager_or_admin
def model_editeaza(id):
    m = ModelBIM.query.get_or_404(id)
    if request.method == 'POST':
        try:
            m.nume = request.form.get('nume', '').strip() or m.nume
            m.descriere = request.form.get('descriere', '').strip()
            m.versiune = request.form.get('versiune', '').strip()
            m.autor = request.form.get('autor', '').strip()
            if m.tip == 'viewer_extern':
                new_url = request.form.get('extern_url', '').strip()
                if new_url:
                    m.extern_url = new_url
            m.santier_id = request.form.get('santier_id', type=int) or None
            m.cladire_id = request.form.get('cladire_id', type=int) or None
            db.session.commit()
            flash('Model actualizat.', 'success')
            return redirect(url_for('bim.modele_lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare: {e}', 'danger')

    santiere = Santier.query.order_by(Santier.cod).all()
    cladiri = Cladire.query.order_by(Cladire.cod).all()
    template = 'bim/model_extern_formular.html' if m.tip == 'viewer_extern' else 'bim/model_extern_formular.html'
    return render_template(template, model=m, santiere=santiere, cladiri=cladiri,
                           viewere_preset=ModelBIM.VIEWERE_EXTERNE)


@bim_bp.route('/model/<int:id>/sterge', methods=['POST'])
@login_required
@manager_or_admin
def model_sterge(id):
    m = ModelBIM.query.get_or_404(id)
    nume = m.nume
    try:
        db.session.delete(m)
        db.session.commit()
        flash(f'Model "{nume}" sters.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    return redirect(url_for('bim.modele_lista'))


@bim_bp.route('/api/modele-pentru-element/<int:element_id>')
@login_required
def api_modele_pentru_element(element_id):
    """
    Returneaza toate modelele BIM (intern+extern) asociate cu santierul / cladirea
    elementului, plus URL-uri pre-substituite cu IFC GlobalId pentru highlight.
    """
    e = ElementBIM.query.get_or_404(element_id)
    cladire_id = e.cladire_id
    santier_id = e.cladire.santier_id if e.cladire else None
    guid = e.ifc_global_id

    q = ModelBIM.query
    if santier_id and cladire_id:
        q = q.filter(db.or_(
            ModelBIM.santier_id == santier_id,
            ModelBIM.cladire_id == cladire_id,
        ))
    elif santier_id:
        q = q.filter_by(santier_id=santier_id)
    elif cladire_id:
        q = q.filter_by(cladire_id=cladire_id)
    else:
        q = q.filter(False)  # nu returnam nimic

    rezultat = []
    for m in q.all():
        item = {
            'id': m.id,
            'nume': m.nume,
            'tip': m.tip,
            'tip_label': m.label_tip,
            'is_intern': m.is_viewer_intern,
            'is_extern': m.is_viewer_extern,
            'url_intern': url_for('bim.viewer', model_id=m.id) + (f'?highlight={guid}' if guid else '') if m.is_viewer_intern else None,
            'url_extern': m.get_external_url_for_guid(guid) if m.is_viewer_extern else None,
        }
        rezultat.append(item)
    return jsonify(rezultat)


# ============================================================
# 3D VIEWER (IFC.js / web-ifc-viewer)
# ============================================================

@bim_bp.route('/viewer/<int:model_id>')
@login_required
def viewer(model_id):
    """
    Pagina viewer 3D pentru un ModelBIM IFC.

    Routing prioritar (Faza 2 BIM):
    1. APS configurat + URN APS pentru model -> redirect la Forge Viewer
    2. Feature flag 'bim-viewer-3d' ON -> viewer_xeokit.html (xeokit-sdk)
    3. Default -> viewer.html (web-ifc-viewer, legacy)

    Quick override: ?legacy=1 forteaza viewer-ul vechi.
    """
    model = ModelBIM.query.get_or_404(model_id)
    if model.tip != 'ifc' or not model.fisier_path:
        flash('Viewer-ul 3D suporta doar fisiere IFC incarcate.', 'warning')
        return redirect(url_for('bim.dashboard'))

    # Override manual pentru a folosi viewer-ul legacy
    force_legacy = request.args.get('legacy') == '1'

    if not force_legacy:
        # Prioritate 1: APS Viewer daca e configurat si modelul are URN
        aps_url = aps_viewer.get_viewer_url(model)
        if aps_url:
            return redirect(aps_url)

        # Prioritate 2: xeokit-sdk daca flag-ul e activ
        if feature_flags.is_enabled('bim-viewer-3d'):
            from models import GanttPlan
            tid = getattr(current_user, 'tenant_id', None)
            qp = GanttPlan.query
            qp = (qp.filter((GanttPlan.tenant_id == tid) | (GanttPlan.tenant_id.is_(None)))
                  if tid is not None else qp.filter(GanttPlan.tenant_id.is_(None)))
            planuri = qp.order_by(GanttPlan.data_creare.desc()).all()
            return render_template('bim/viewer_xeokit.html', model=model, planuri=planuri)

    # Fallback: viewer-ul existent (web-ifc-viewer)
    return render_template('bim/viewer.html', model=model)


@bim_bp.route('/viewer/<int:model_id>/file')
@login_required
def viewer_file(model_id):
    """Trimite fisierul IFC pentru viewer."""
    model = ModelBIM.query.get_or_404(model_id)
    if not model.fisier_path:
        abort(404)
    abs_path = os.path.join(current_app.root_path, model.fisier_path)
    if not os.path.exists(abs_path):
        abort(404)
    return send_file(abs_path, mimetype='application/octet-stream')


# ============================================================
# 4D - PUNTE GANTT -> BIM (construction sequencing)
# ============================================================
def _elemente_model(model):
    """Elementele unui model: prin model_bim_id, altfel prin santierul modelului."""
    els = ElementBIM.query.filter_by(model_bim_id=model.id).all()
    if not els and getattr(model, 'santier_id', None):
        els = (ElementBIM.query.join(Cladire, ElementBIM.cladire_id == Cladire.id)
               .filter(Cladire.santier_id == model.santier_id).all())
    return els


@bim_bp.route('/model/<int:model_id>/genereaza-4d', methods=['POST'])
@login_required
def genereaza_4d(model_id):
    """Genereaza schedule-urile 4D pentru elementele modelului, dintr-un plan Gantt salvat."""
    model = ModelBIM.query.get_or_404(model_id)
    from models import GanttPlan
    from services.gantt.pipeline import MotorPlanificare
    from services.gantt import import_engine, store as gstore
    from services import bim_4d_bridge

    plan = db.session.get(GanttPlan, int(request.form['plan_id'])) \
        if request.form.get('plan_id') else None
    if not plan:
        flash('Alege un plan Gantt salvat pentru a genera 4D.', 'warning')
        return redirect(url_for('bim.viewer', model_id=model_id))

    mapare = rand_antet = None
    if plan.mapare_json:
        try:
            d = json.loads(plan.mapare_json)
            mapare, rand_antet = d.get('coloane'), d.get('rand_antet')
        except Exception:
            pass
    tid = getattr(current_user, 'tenant_id', None)
    motor = MotorPlanificare(tenant_id=tid)
    try:
        articole, _ = import_engine.importa(plan.continut, plan.ext, motor.setari,
                                            mapare_manuala=mapare, rand_antet_manual=rand_antet)
        rezultat = motor.proceseaza(articole)
    except import_engine.EroareImport as e:
        flash(f'Nu pot citi planul: {e}', 'danger')
        return redirect(url_for('bim.viewer', model_id=model_id))

    stats = bim_4d_bridge.genereaza_din_rezultat(
        _elemente_model(model), rezultat, plan.data_start or date.today(),
        gstore.mapare_tip_element(tid), tenant_id=tid,
        user_id=getattr(current_user, 'id', None))
    flash(f"4D generat din planul „{plan.nume}\": {stats['create']} create, "
          f"{stats['actualizate']} actualizate, {stats['sarite']} elemente fara categorie.",
          'success')
    return redirect(url_for('bim.viewer', model_id=model_id))


@bim_bp.route('/model/<int:model_id>/genereaza-4d-secventa', methods=['POST'])
@login_required
def genereaza_4d_secventa(model_id):
    """4D fara plan: auto-secventiere a elementelor pe nivel + ordine de constructie."""
    model = ModelBIM.query.get_or_404(model_id)
    from services import bim_4d_bridge
    try:
        durata = int(request.form.get('durata') or 90)
    except (TypeError, ValueError):
        durata = 90
    durata = max(5, min(durata, 2000))
    stats = bim_4d_bridge.genereaza_secventa(
        _elemente_model(model), date.today(), durata,
        tenant_id=getattr(current_user, 'tenant_id', None),
        user_id=getattr(current_user, 'id', None))
    flash(f"Auto-secventiere pe {durata} zile: {stats['create']} create, "
          f"{stats['actualizate']} actualizate.", 'success')
    return redirect(url_for('bim.viewer', model_id=model_id))


@bim_bp.route('/viewer/<int:model_id>/4d-data')
@login_required
def viewer_4d_data(model_id):
    """JSON pentru player-ul 4D: elemente (guid) + ferestre de date + stare."""
    model = ModelBIM.query.get_or_404(model_id)
    from models import BIMTaskSchedule
    from services import bim_4d_bridge
    elemente = _elemente_model(model)
    ids = [e.id for e in elemente]
    scheds = {}
    if ids:
        for s in BIMTaskSchedule.query.filter(BIMTaskSchedule.element_bim_id.in_(ids)).all():
            scheds.setdefault(s.element_bim_id, s)
    perechi = [(e, scheds[e.id]) for e in elemente if e.id in scheds]
    return jsonify(bim_4d_bridge.date_4d(perechi))


# ============================================================
# QTO - antemasuratoare (BoQ) din model BIM
# ============================================================
def _qto_rows(model):
    from services import ifc_qto
    if model.fisier_path:
        abs_path = os.path.join(current_app.root_path, model.fisier_path)
        if os.path.exists(abs_path):
            rows = ifc_qto.qto_din_ifc(abs_path)
            if rows:
                return rows
    return ifc_qto.qto_din_elemente(_elemente_model(model))


@bim_bp.route('/model/<int:model_id>/qto')
@login_required
def qto(model_id):
    """Antemasuratoare (QTO) din model: cantitati pe tip de element."""
    model = ModelBIM.query.get_or_404(model_id)
    rows = _qto_rows(model)
    return render_template('bim/qto.html', model=model, rows=rows,
                           total_nr=sum(r['nr'] for r in rows))


@bim_bp.route('/model/<int:model_id>/qto.csv')
@login_required
def qto_csv(model_id):
    import csv as _csv
    from io import StringIO
    model = ModelBIM.query.get_or_404(model_id)
    rows = _qto_rows(model)
    out = StringIO()
    w = _csv.writer(out, delimiter=';')
    w.writerow(['cod_articol', 'denumire', 'um', 'cantitate'])      # format F3 -> upload in Gantt
    for r in rows:
        w.writerow([r['tip'].upper(), r['label'], r['um'], r['cantitate']])
    return send_file(BytesIO(out.getvalue().encode('utf-8-sig')), mimetype='text/csv',
                     as_attachment=True, download_name=f'qto_model_{model_id}.csv')


# ============================================================
# DATA QUALITY & VALIDATION REPORTS
# ============================================================

@bim_bp.route('/quality')
@login_required
@manager_or_admin
def quality_report():
    """Pagina de rapoarte de calitate BIM."""
    raport = bim_quality.run_all_reports(
        db, RaportActivitate, ElementBIM, Spatiu, ExternalMapping,
        Santier, Cladire, Nivel, Zona, Asset, IssueBIM, ModelBIM,
    )
    return render_template('bim/quality_report.html', raport=raport)


@bim_bp.route('/api/quality')
@login_required
@manager_or_admin
def api_quality():
    """JSON pentru CI/dashboard - rapoarte de calitate."""
    raport = bim_quality.run_all_reports(
        db, RaportActivitate, ElementBIM, Spatiu, ExternalMapping,
        Santier, Cladire, Nivel, Zona, Asset, IssueBIM, ModelBIM,
    )
    return jsonify(raport)


# ============================================================
# EXTERNAL MAPPING - CRUD + lookup invers
# ============================================================

@bim_bp.route('/api/external-mapping', methods=['GET', 'POST'])
@login_required
def api_external_mapping():
    """GET: lookup invers (?source_system=ifc&extern_id=GUID).
       POST: adauga/actualizeaza mapping."""
    if request.method == 'GET':
        ss = request.args.get('source_system', '').strip()
        eid = request.args.get('extern_id', '').strip()
        if not ss or not eid:
            return jsonify({'error': 'source_system + extern_id required'}), 400
        mappings = ExternalMapping.query.filter_by(source_system=ss, extern_id=eid).all()
        return jsonify([{
            'id': m.id, 'entity_type': m.entity_type, 'entity_id': m.entity_id,
            'source_system': m.source_system, 'extern_id': m.extern_id,
            'last_synced_at': m.last_synced_at.isoformat() if m.last_synced_at else None,
        } for m in mappings])

    # POST - admin/manager only
    if current_user.rol not in ('admin', 'manager'):
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json(silent=True) or request.form.to_dict()
    et = data.get('entity_type', '').strip()
    eid = data.get('entity_id')
    ss = data.get('source_system', '').strip()
    extid = data.get('extern_id', '').strip()
    if not et or not eid or not ss or not extid:
        return jsonify({'error': 'entity_type, entity_id, source_system, extern_id required'}), 400

    try:
        m = ExternalMapping.add_or_update(
            entity_type=et, entity_id=int(eid),
            source_system=ss, extern_id=extid,
            metadata=data.get('metadata'),
        )
        db.session.commit()
        return jsonify({'id': m.id, 'created_or_updated': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bim_bp.route('/api/elemente/catalog')
@login_required
def api_elemente_catalog():
    """
    Export catalog elemente pentru integrare BI/dashboard externe.
    Returneaza JSON cu toate elementele + identificatori cross-system.
    """
    elemente = ElementBIM.query.limit(2000).all()
    rezultat = []
    for e in elemente:
        # Lookup mapping-uri externe pentru acest element
        mappings = ExternalMapping.query.filter_by(
            entity_type='element_bim', entity_id=e.id
        ).all()
        rezultat.append({
            'id': e.id,
            'cod': e.cod,
            'nume': e.nume,
            'tip_element': e.tip_element,
            'tip_label': e.tip_label,
            'status': e.status,
            'cale_completa': e.cale_completa,
            'ifc_global_id': e.ifc_global_id,
            'extern_id': e.extern_id,
            'source_system': e.source_system,
            'cladire_id': e.cladire_id,
            'spatiu_id': e.spatiu_id,
            'last_synced_at': e.last_synced_at.isoformat() if e.last_synced_at else None,
            'external_mappings': [{
                'source_system': m.source_system,
                'extern_id': m.extern_id,
            } for m in mappings],
        })
    return jsonify({
        'total': len(rezultat),
        'elements': rezultat,
    })


# ============================================================
# CDE WORKFLOW + VERSIONING (Faza 3)
# Activate prin feature flag 'bim-model-versioning' (default OFF).
# Cand flag-ul e OFF rutele raman accesibile dar UI-ul nu le link-uieste.
# ============================================================

def _ensure_versioning_enabled():
    """Helper: redirect la dashboard daca flag-ul e off."""
    if not ff_svc.is_enabled('bim-model-versioning'):
        flash('Feature-ul versioning nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    return None


@bim_bp.route('/model/<int:model_id>/versiuni')
@login_required
def model_versiuni(model_id):
    """Lista versiunilor unui ModelBIM (workflow CDE)."""
    redir = _ensure_versioning_enabled()
    if redir:
        return redir
    model = ModelBIM.query.get_or_404(model_id)
    versiuni = (BIMModelVersion.query
                .filter_by(model_id=model_id)
                .order_by(BIMModelVersion.data_creare.desc())
                .all())
    return render_template('bim/model_versiuni.html', model=model, versiuni=versiuni,
                           statusuri=BIMModelVersion.STATUSURI)


@bim_bp.route('/model/<int:model_id>/versiune-noua', methods=['GET', 'POST'])
@login_required
def model_versiune_noua(model_id):
    """Creeaza o versiune noua pentru model (status='wip' initial)."""
    redir = _ensure_versioning_enabled()
    if redir:
        return redir
    model = ModelBIM.query.get_or_404(model_id)

    if request.method == 'POST':
        try:
            v = bim_workflow.create_new_version(
                model=model,
                versiune=request.form.get('versiune', '').strip(),
                user=current_user,
                disciplina=request.form.get('disciplina', '').strip(),
                descriere=request.form.get('descriere', '').strip(),
                # fisier_path / extern_url: optional in formular MVP
                extern_url=request.form.get('extern_url', '').strip() or None,
            )
            flash(f'Versiunea "{v.versiune}" creata in stare WIP.', 'success')
            return redirect(url_for('bim.model_versiuni', model_id=model.id))
        except bim_workflow.WorkflowError as e:
            flash(str(e), 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la creare versiune: {e}', 'danger')

    return render_template('bim/model_versiune_formular.html', model=model)


@bim_bp.route('/model-version/<int:version_id>/transition', methods=['POST'])
@login_required
def model_version_transition(version_id):
    """
    Aplica o tranzitie de status (wip->shared, shared->published, etc.).
    Necesita CSRF + autorizare (vezi bim_workflow.can_user_transition).
    """
    redir = _ensure_versioning_enabled()
    if redir:
        return redir

    v = BIMModelVersion.query.get_or_404(version_id)
    new_status = request.form.get('status', '').strip().lower()
    comentariu = request.form.get('comentariu', '').strip() or None

    try:
        bim_workflow.transition(v, new_status, current_user, comentariu=comentariu)
        flash(f'Versiunea "{v.versiune}" -> {v.label_status}.', 'success')
    except bim_workflow.WorkflowError as e:
        flash(str(e), 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la tranzitie: {e}', 'danger')

    return redirect(url_for('bim.model_versiuni', model_id=v.model_id))


@bim_bp.route('/api/model/<int:model_id>/versiuni')
@login_required
def api_model_versiuni(model_id):
    """JSON: versiunile unui model (toate sau filtrate)."""
    if not ff_svc.is_enabled('bim-model-versioning'):
        return jsonify({'enabled': False, 'versions': []}), 200

    status_filter = request.args.get('status')
    q = BIMModelVersion.query.filter_by(model_id=model_id)
    if status_filter:
        q = q.filter_by(status=status_filter)
    versiuni = q.order_by(BIMModelVersion.data_creare.desc()).all()
    return jsonify({
        'enabled': True,
        'count': len(versiuni),
        'versions': [{
            'id': v.id,
            'versiune': v.versiune,
            'disciplina': v.disciplina,
            'status': v.status,
            'label_status': v.label_status,
            'data_creare': v.data_creare.isoformat() if v.data_creare else None,
            'data_publicare': v.data_publicare.isoformat() if v.data_publicare else None,
            'creat_de_id': v.creat_de_id,
            'is_official': v.is_official,
            'descriere': v.descriere,
        } for v in versiuni],
    })


# ============================================================
# FEDERATION (Faza 3) - viewer multi-model pe santier
# Activate prin feature flag 'bim-federation' (default OFF).
# ============================================================

@bim_bp.route('/santier/<int:santier_id>/viewer-federat')
@login_required
def viewer_federat(santier_id):
    """Viewer federat: toate modelele 'published' ale santierului overlap."""
    if not ff_svc.is_enabled('bim-federation'):
        flash('Federation nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.santier_detaliu', id=santier_id))

    santier = Santier.query.get_or_404(santier_id)
    versiuni = bim_workflow.get_published_versions_for_santier(santier_id)

    if not versiuni:
        flash('Niciun model publicat (published) pentru acest santier inca.', 'warning')
        return redirect(url_for('bim.santier_detaliu', id=santier.id))

    # Construim lista de URL-uri pentru viewer client-side
    modele_data = []
    for v in versiuni:
        # Preferam fisierul versiunii daca exista, altfel cel al modelului
        if v.fisier_path:
            ifc_url = url_for('bim.api_model_version_file', version_id=v.id)
        elif v.model.fisier_path:
            ifc_url = url_for('bim.viewer_file', model_id=v.model_id)
        else:
            continue
        modele_data.append({
            'version_id': v.id,
            'model_id': v.model_id,
            'nume': v.model.nume,
            'versiune': v.versiune,
            'disciplina': v.disciplina or 'GEN',
            'ifc_url': ifc_url,
        })

    return render_template('bim/viewer_federat.html',
                           santier=santier, modele=modele_data,
                           versiuni=versiuni)


@bim_bp.route('/api/model-version/<int:version_id>/file')
@login_required
def api_model_version_file(version_id):
    """Trimite fisierul IFC al unei versiuni specifice (pentru viewer federat)."""
    v = BIMModelVersion.query.get_or_404(version_id)
    # Numai versiunile partajate sau publicate sunt servite (sau de catre creator)
    if v.status not in ('shared', 'published') and v.creat_de_id != current_user.id:
        if current_user.rol not in ('admin', 'manager'):
            abort(403)
    if not v.fisier_path:
        abort(404)
    abs_path = os.path.join(current_app.root_path, v.fisier_path)
    if not os.path.exists(abs_path):
        abort(404)
    return send_file(abs_path, mimetype='application/octet-stream')


# ============================================================
# RULE ENGINE (Faza 4)
# ============================================================

def _ensure_rules_enabled():
    if not ff_svc.is_enabled('bim-rule-engine'):
        flash('Rule engine nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    return None


@bim_bp.route('/rules')
@login_required
def rules_lista():
    redir = _ensure_rules_enabled()
    if redir:
        return redir
    rules = BIMRule.query.order_by(BIMRule.cod).all()
    counts = {}
    for r in rules:
        counts[r.id] = RuleViolation.query.filter_by(rule_id=r.id, status='noua').count()
    return render_template('bim/rules_lista.html', rules=rules, counts=counts,
                           categorii=BIMRule.CATEGORII, tipuri=BIMRule.TIPURI)


@bim_bp.route('/rule/nou', methods=['GET', 'POST'])
@login_required
@manager_or_admin
def rule_nou():
    redir = _ensure_rules_enabled()
    if redir:
        return redir
    if request.method == 'POST':
        try:
            definition = json.loads(request.form.get('definitie_json', '{}'))
        except (ValueError, TypeError):
            flash('JSON invalid in definitie.', 'danger')
            return redirect(request.url)
        try:
            rule = rules_svc.create_rule(
                cod=request.form.get('cod', '').strip(),
                nume=request.form.get('nume', '').strip(),
                tip=request.form.get('tip', 'required_properties'),
                definition=definition,
                descriere=request.form.get('descriere', '').strip(),
                categorie=request.form.get('categorie', 'best_practice'),
                severitate=request.form.get('severitate', 'medie'),
                user=current_user,
            )
            flash(f'Regula "{rule.cod}" creata.', 'success')
            return redirect(url_for('bim.rules_lista'))
        except ValueError as e:
            flash(str(e), 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la creare: {e}', 'danger')
    return render_template('bim/rule_formular.html',
                           categorii=BIMRule.CATEGORII, tipuri=BIMRule.TIPURI,
                           severitati=BIMRule.SEVERITATI)


@bim_bp.route('/rules/run', methods=['POST'])
@login_required
@manager_or_admin
def rules_run():
    redir = _ensure_rules_enabled()
    if redir:
        return redir
    santier_id = request.form.get('santier_id', type=int)
    scope = {'santier_id': santier_id} if santier_id else None
    try:
        result = rules_svc.run_rules(scope=scope, user=current_user)
        flash(
            f'Rulare finalizata: {result["total_rules"]} reguli, '
            f'{result["total_violations"]} violari ({result["duration_ms"]}ms).',
            'success' if result['total_violations'] == 0 else 'warning',
        )
    except Exception as e:
        flash(f'Eroare la rulare reguli: {e}', 'danger')
    return redirect(url_for('bim.violations_lista'))


@bim_bp.route('/violations')
@login_required
def violations_lista():
    redir = _ensure_rules_enabled()
    if redir:
        return redir
    status = request.args.get('status', 'noua')
    q = RuleViolation.query
    if status:
        q = q.filter_by(status=status)
    violations = q.order_by(RuleViolation.data_detectie.desc()).limit(500).all()
    return render_template('bim/violations_lista.html',
                           violations=violations, status_filter=status)


@bim_bp.route('/violation/<int:violation_id>/promote', methods=['POST'])
@login_required
@manager_or_admin
def violation_promote(violation_id):
    v = RuleViolation.query.get_or_404(violation_id)
    try:
        issue_id = rules_svc.violation_to_issue(v, current_user)
        flash(f'Violare promovata in issue #{issue_id}.', 'success')
    except PermissionError as e:
        flash(str(e), 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la promovare: {e}', 'danger')
    return redirect(url_for('bim.violations_lista'))


# ============================================================
# CLASH DETECTION (Faza 4)
# ============================================================

def _ensure_clash_enabled():
    if not ff_svc.is_enabled('bim-clash-detection'):
        flash('Clash detection nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    return None


@bim_bp.route('/clash')
@login_required
def clash_lista():
    redir = _ensure_clash_enabled()
    if redir:
        return redir
    runs = ClashRun.query.order_by(ClashRun.data_rulare.desc()).limit(50).all()
    santiere = Santier.query.order_by(Santier.cod).all()
    return render_template('bim/clash_lista.html', runs=runs, santiere=santiere)


@bim_bp.route('/clash/run', methods=['POST'])
@login_required
@manager_or_admin
def clash_run():
    redir = _ensure_clash_enabled()
    if redir:
        return redir
    santier_id = request.form.get('santier_id', type=int)
    model_id = request.form.get('model_id', type=int)
    tip = request.form.get('tip', 'mixed')
    if not santier_id and not model_id:
        flash('Trebuie ales santier sau model.', 'danger')
        return redirect(url_for('bim.clash_lista'))
    try:
        result = clash_svc.run_clash_detection(
            santier_id=santier_id, model_id=model_id, tip=tip, user=current_user,
        )
        flash(
            f'Clash detection: {result["total_clashes"]} clash-uri ({result["duration_ms"]}ms).',
            'success' if result['total_clashes'] == 0 else 'warning',
        )
        return redirect(url_for('bim.clash_detaliu', run_id=result['run_id']))
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la detectia clash: {e}', 'danger')
    return redirect(url_for('bim.clash_lista'))


@bim_bp.route('/clash/<int:run_id>')
@login_required
def clash_detaliu(run_id):
    redir = _ensure_clash_enabled()
    if redir:
        return redir
    run = ClashRun.query.get_or_404(run_id)
    severity_filter = request.args.get('severitate')
    q = ClashResult.query.filter_by(run_id=run_id)
    if severity_filter:
        q = q.filter_by(severitate=severity_filter)
    rezultate = q.order_by(ClashResult.severitate.desc(), ClashResult.id).limit(500).all()
    return render_template('bim/clash_detaliu.html', run=run, rezultate=rezultate,
                           severity_filter=severity_filter)


@bim_bp.route('/api/clash/<int:run_id>')
@login_required
def api_clash(run_id):
    if not ff_svc.is_enabled('bim-clash-detection'):
        return jsonify({'enabled': False, 'results': []}), 200
    run = ClashRun.query.get_or_404(run_id)
    rezultate = ClashResult.query.filter_by(run_id=run_id).all()
    return jsonify({
        'enabled': True,
        'run_id': run.id,
        'tip': run.tip,
        'total_clash_uri': run.nr_clash_uri,
        'by_severity': {
            'critica': run.nr_critica, 'mare': run.nr_mare,
            'medie': run.nr_medie, 'mica': run.nr_mica,
        },
        'results': [{
            'id': r.id,
            'element_a_id': r.element_a_id,
            'element_b_id': r.element_b_id,
            'tip': r.tip,
            'severitate': r.severitate,
            'status': r.status,
            'mesaj': r.mesaj,
            'detalii': json.loads(r.detalii_json) if r.detalii_json else {},
        } for r in rezultate],
    })


# ============================================================
# 4D SCHEDULE (Faza 5)
# Activare: feature flag 'bim-4d-schedule' (default OFF).
# ============================================================

def _ensure_4d_enabled():
    if not ff_svc.is_enabled('bim-4d-schedule'):
        flash('4D Schedule nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    return None


@bim_bp.route('/element/<int:element_id>/schedule', methods=['GET', 'POST'])
@login_required
@manager_or_admin
def element_schedule_form(element_id):
    """Adauga sau editeaza schedule entries pentru un element."""
    redir = _ensure_4d_enabled()
    if redir:
        return redir
    element = ElementBIM.query.get_or_404(element_id)
    schedules = (BIMTaskSchedule.query
                 .filter_by(element_bim_id=element_id)
                 .order_by(BIMTaskSchedule.data_start_plan)
                 .all())

    if request.method == 'POST':
        try:
            faza = request.form.get('faza', '').strip().lower()
            data_start = datetime.strptime(request.form.get('data_start_plan'), '%Y-%m-%d').date()
            data_sfarsit = datetime.strptime(request.form.get('data_sfarsit_plan'), '%Y-%m-%d').date()
            disciplina = request.form.get('disciplina', '').strip().upper() or None
            descriere = request.form.get('descriere', '').strip() or None
            sched = fourd_svc.create_schedule(
                element_bim_id=element_id, faza=faza,
                data_start_plan=data_start, data_sfarsit_plan=data_sfarsit,
                disciplina=disciplina, descriere=descriere,
                user=current_user,
            )
            flash(f'Schedule "{sched.faza}" creat pentru elementul {element.cod}.', 'success')
            return redirect(url_for('bim.element_schedule_form', element_id=element_id))
        except ValueError as e:
            flash(str(e), 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la creare schedule: {e}', 'danger')

    return render_template('bim/element_schedule.html',
                           element=element, schedules=schedules,
                           faze_tipice=BIMTaskSchedule.FAZE_TIPICE,
                           statusuri=BIMTaskSchedule.STATUSURI)


@bim_bp.route('/schedule/<int:schedule_id>/progres', methods=['POST'])
@login_required
@manager_or_admin
def schedule_update_progress(schedule_id):
    """Actualizeaza progresul (0..100) pentru un schedule entry."""
    redir = _ensure_4d_enabled()
    if redir:
        return redir
    sched = BIMTaskSchedule.query.get_or_404(schedule_id)
    try:
        progres = int(request.form.get('progres_pct', 0))
        status = request.form.get('status', '').strip() or None
        fourd_svc.update_progress(sched, progres, status=status, user=current_user)
        flash(f'Progres actualizat la {progres}%.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare: {e}', 'danger')
    return redirect(url_for('bim.element_schedule_form', element_id=sched.element_bim_id))


@bim_bp.route('/santier/<int:santier_id>/4d-timeline')
@login_required
def santier_4d_timeline(santier_id):
    """Timeline Gantt-style pentru toate schedule-urile unui santier."""
    redir = _ensure_4d_enabled()
    if redir:
        return redir
    santier = Santier.query.get_or_404(santier_id)
    timeline = fourd_svc.get_timeline_for_santier(santier_id)
    progress = fourd_svc.compute_santier_progress(santier_id)
    return render_template('bim/santier_4d_timeline.html',
                           santier=santier, timeline=timeline,
                           progress=progress)


@bim_bp.route('/api/santier/<int:santier_id>/visible-at')
@login_required
def api_visible_at(santier_id):
    """JSON: ID-urile elementelor vizibile la o anumita data (4D viewer)."""
    if not ff_svc.is_enabled('bim-4d-schedule'):
        return jsonify({'enabled': False, 'visible_element_ids': []}), 200
    data_str = request.args.get('data')
    try:
        data = datetime.strptime(data_str, '%Y-%m-%d').date() if data_str else date.today()
    except (ValueError, TypeError):
        return jsonify({'error': 'data invalida (folositi YYYY-MM-DD)'}), 400
    visible = fourd_svc.get_visible_elements_at_date(santier_id, data)
    return jsonify({
        'enabled': True,
        'data': data.isoformat(),
        'count': len(visible),
        'visible_element_ids': visible,
    })


# ============================================================
# 5D COST (Faza 5)
# Activare: feature flag 'bim-5d-cost' (default OFF).
# ============================================================

def _ensure_5d_enabled():
    if not ff_svc.is_enabled('bim-5d-cost'):
        flash('5D Cost nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    return None


@bim_bp.route('/element/<int:element_id>/cost', methods=['GET', 'POST'])
@login_required
@manager_or_admin
def element_cost_form(element_id):
    """Adauga sau editeaza cost items pentru un element."""
    redir = _ensure_5d_enabled()
    if redir:
        return redir
    element = ElementBIM.query.get_or_404(element_id)
    items = (BIMCostItem.query
             .filter_by(element_bim_id=element_id)
             .order_by(BIMCostItem.categorie, BIMCostItem.id)
             .all())

    if request.method == 'POST':
        try:
            from decimal import Decimal
            cantitate = Decimal(request.form.get('cantitate', '0'))
            pret_unitar = Decimal(request.form.get('pret_unitar', '0'))
            item = fived_svc.create_cost_item(
                element_bim_id=element_id,
                descriere=request.form.get('descriere', '').strip(),
                cantitate=float(cantitate),
                pret_unitar=float(pret_unitar),
                categorie=request.form.get('categorie', 'material'),
                unitate=request.form.get('unitate', 'buc'),
                faza=request.form.get('faza', '').strip() or None,
                tip=request.form.get('tip', 'planificat'),
                referinta_extern=request.form.get('referinta_extern', '').strip(),
                user=current_user,
            )
            flash(f'Item cost adaugat: {item.descriere} ({item.total:.2f} {item.valuta}).', 'success')
            return redirect(url_for('bim.element_cost_form', element_id=element_id))
        except ValueError as e:
            flash(str(e), 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare: {e}', 'danger')

    breakdown = fived_svc.cost_total_element(element_id)
    return render_template('bim/element_cost.html',
                           element=element, items=items,
                           breakdown=breakdown,
                           categorii=BIMCostItem.CATEGORII,
                           tipuri=BIMCostItem.TIPURI,
                           unitati=BIMCostItem.UNITATI)


@bim_bp.route('/santier/<int:santier_id>/5d-dashboard')
@login_required
def santier_5d_dashboard(santier_id):
    """Dashboard cost cu breakdown per disciplina/cladire/tip element + plan vs real."""
    redir = _ensure_5d_enabled()
    if redir:
        return redir
    santier = Santier.query.get_or_404(santier_id)
    breakdown_plan = fived_svc.cost_breakdown_santier(santier_id, tip='planificat')
    breakdown_real = fived_svc.cost_breakdown_santier(santier_id, tip='real')
    delta = fived_svc.cost_planificat_vs_real(santier_id)
    return render_template('bim/santier_5d_dashboard.html',
                           santier=santier,
                           breakdown_plan=breakdown_plan,
                           breakdown_real=breakdown_real,
                           delta=delta)


@bim_bp.route('/api/element/<int:element_id>/cost')
@login_required
def api_element_cost(element_id):
    """JSON: breakdown cost per element pe categorii."""
    if not ff_svc.is_enabled('bim-5d-cost'):
        return jsonify({'enabled': False, 'total': 0}), 200
    return jsonify({
        'enabled': True,
        **fived_svc.cost_total_element(element_id),
    })


# ============================================================
# IoT / DIGITAL TWIN (Faza 6)
# Activare: feature flag 'bim-iot-sensors' (default OFF).
# Ingest API foloseste token auth (X-Sensor-Token); restul rutelor
# - sesiune normala Flask-Login.
# ============================================================

def _ensure_iot_enabled():
    if not ff_svc.is_enabled('bim-iot-sensors'):
        flash('IoT/Digital Twin nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    return None


# ---------- INGEST API (token auth, CSRF exempt) ----------

@bim_bp.route('/api/sensors/ingest', methods=['POST'])
def api_sensors_ingest():
    """
    Ingest endpoint pentru gateway-uri IoT. Token auth.
    Body JSON: { "valoare": 23.5, "ts": "2026-05-10T12:34:56Z" (opt),
                  "calitate": "ok" (opt), "meta": {...} (opt) }
    Header: X-Sensor-Token: <api_key 64 hex chars>

    Nu necesita login. Nu necesita CSRF (e API).
    """
    if not ff_svc.is_enabled('bim-iot-sensors'):
        return jsonify({'error': 'feature disabled'}), 403

    token = request.headers.get('X-Sensor-Token', '').strip()
    if not token:
        return jsonify({'error': 'X-Sensor-Token header lipseste'}), 401

    senzor = iot_ingest_svc.authenticate_token(token)
    if not senzor:
        return jsonify({'error': 'token invalid sau senzor inactiv'}), 401

    data = request.get_json(silent=True) or {}
    if 'valoare' not in data:
        return jsonify({'error': 'campul valoare e obligatoriu'}), 400

    try:
        valoare = float(data['valoare'])
    except (ValueError, TypeError):
        return jsonify({'error': 'valoare trebuie sa fie numerica'}), 400

    ts = None
    if data.get('ts'):
        try:
            ts_str = str(data['ts']).rstrip('Z')
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            return jsonify({'error': 'ts invalid; folositi ISO 8601'}), 400

    try:
        result = iot_ingest_svc.ingest_reading(
            senzor, valoare,
            ts=ts,
            calitate=data.get('calitate', 'ok'),
            meta=data.get('meta'),
        )
        return jsonify(result), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'ingest failed: {e}'}), 500


# Exempt CSRF pentru ruta de ingest (API token-based, fara cookie session)
try:
    from flask_wtf.csrf import CSRFProtect  # type: ignore
    from flask import current_app as _ca
    # Vom inregistra exemption-ul in app.py / sau prin context dupa import
except ImportError:
    pass


# ---------- SENZOR CRUD (sesiune) ----------

@bim_bp.route('/sensors')
@login_required
def sensors_lista():
    """Lista globala senzori."""
    redir = _ensure_iot_enabled()
    if redir:
        return redir
    senzori = Senzor.query.order_by(Senzor.cod).all()
    return render_template('bim/sensors_lista.html',
                           senzori=senzori, tipuri=Senzor.TIPURI)


@bim_bp.route('/sensor/nou', methods=['GET', 'POST'])
@login_required
@manager_or_admin
def sensor_nou():
    """Creeaza un senzor nou cu API key auto-generat."""
    redir = _ensure_iot_enabled()
    if redir:
        return redir

    element_id = request.args.get('element_bim_id', type=int)
    spatiu_id = request.args.get('spatiu_id', type=int)
    cladire_id = request.args.get('cladire_id', type=int)

    if request.method == 'POST':
        try:
            def _opt_float(v):
                v = (v or '').strip()
                return float(v) if v else None

            senzor = iot_ingest_svc.create_senzor(
                cod=request.form.get('cod', '').strip(),
                nume=request.form.get('nume', '').strip(),
                tip=request.form.get('tip', '').strip(),
                unitate=request.form.get('unitate', '').strip() or None,
                element_bim_id=request.form.get('element_bim_id', type=int),
                spatiu_id=request.form.get('spatiu_id', type=int),
                cladire_id=request.form.get('cladire_id', type=int),
                threshold_min=_opt_float(request.form.get('threshold_min')),
                threshold_max=_opt_float(request.form.get('threshold_max')),
                descriere=request.form.get('descriere', ''),
                producator=request.form.get('producator', ''),
                model_hardware=request.form.get('model_hardware', ''),
                serial=request.form.get('serial', ''),
                user=current_user,
            )
            flash(f'Senzor "{senzor.cod}" creat. API key (afisat o singura data): {senzor.api_key}', 'success')
            return redirect(url_for('bim.sensor_detaliu', sensor_id=senzor.id))
        except ValueError as e:
            flash(str(e), 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la creare senzor: {e}', 'danger')

    return render_template('bim/sensor_formular.html',
                           tipuri=Senzor.TIPURI,
                           unitati_default=Senzor.UNITATI_DEFAULT,
                           element_bim_id=element_id,
                           spatiu_id=spatiu_id,
                           cladire_id=cladire_id)


@bim_bp.route('/sensor/<int:sensor_id>')
@login_required
def sensor_detaliu(sensor_id):
    """Detaliu senzor cu istoric + chart."""
    redir = _ensure_iot_enabled()
    if redir:
        return redir
    senzor = Senzor.query.get_or_404(sensor_id)
    agg = request.args.get('agg', '1h')  # default agg pe oră
    history = iot_query_svc.get_history(sensor_id, agg=agg)
    alerts = (SensorAlert.query.filter_by(senzor_id=sensor_id)
              .order_by(SensorAlert.data_alerta.desc()).limit(50).all())
    return render_template('bim/sensor_detaliu.html',
                           senzor=senzor, history=history,
                           alerts=alerts, agg=agg)


@bim_bp.route('/sensor/<int:sensor_id>/rotate-key', methods=['POST'])
@login_required
@manager_or_admin
def sensor_rotate_key(sensor_id):
    senzor = Senzor.query.get_or_404(sensor_id)
    try:
        new_key = iot_ingest_svc.rotate_api_key(senzor)
        flash(f'Token rotat. Noul API key (afisat o singura data): {new_key}', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la rotatie token: {e}', 'danger')
    return redirect(url_for('bim.sensor_detaliu', sensor_id=sensor_id))


# ---------- ALERTS ----------

@bim_bp.route('/alerts')
@login_required
def alerts_lista():
    """Alerte deschise + recent rezolvate."""
    redir = _ensure_iot_enabled()
    if redir:
        return redir
    status = request.args.get('status', 'noua')
    q = SensorAlert.query
    if status:
        q = q.filter_by(status=status)
    alerts = q.order_by(SensorAlert.data_alerta.desc()).limit(500).all()
    return render_template('bim/alerts_lista.html',
                           alerts=alerts, status_filter=status)


@bim_bp.route('/alert/<int:alert_id>/transition', methods=['POST'])
@login_required
@manager_or_admin
def alert_transition(alert_id):
    alert = SensorAlert.query.get_or_404(alert_id)
    new_status = request.form.get('status', '').strip()
    try:
        iot_ingest_svc.transition_alert(alert, new_status, current_user)
        flash(f'Alerta -> {new_status}', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare: {e}', 'danger')
    return redirect(url_for('bim.alerts_lista'))


# ---------- API QUERY ----------

@bim_bp.route('/api/element/<int:element_id>/state')
@login_required
def api_element_state(element_id):
    """JSON cu current state al senzorilor atasati la element."""
    if not ff_svc.is_enabled('bim-iot-sensors'):
        return jsonify({'enabled': False, 'sensors': []}), 200
    return jsonify({'enabled': True,
                    **iot_query_svc.get_current_state_element(element_id)})


@bim_bp.route('/api/sensor/<int:sensor_id>/history')
@login_required
def api_sensor_history(sensor_id):
    """JSON cu istoricul time-series (raw / 1h / 1d)."""
    if not ff_svc.is_enabled('bim-iot-sensors'):
        return jsonify({'enabled': False, 'data': []}), 200
    agg = request.args.get('agg', '1h')
    from_str = request.args.get('from')
    to_str = request.args.get('to')
    try:
        from_ts = datetime.fromisoformat(from_str.rstrip('Z')) if from_str else None
        to_ts = datetime.fromisoformat(to_str.rstrip('Z')) if to_str else None
        return jsonify({'enabled': True,
                        **iot_query_svc.get_history(sensor_id,
                                                     from_ts=from_ts, to_ts=to_ts, agg=agg)})
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'parametri invalizi: {e}'}), 400


# ============================================================
# REAL-TIME COLLAB + KANBAN (Faza 7)
# Activare: bim-realtime-collab, bim-issue-kanban (default OFF)
# ============================================================

def _ensure_realtime_enabled():
    if not ff_svc.is_enabled('bim-realtime-collab'):
        flash('Real-time collab nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    return None


def _ensure_kanban_enabled():
    if not ff_svc.is_enabled('bim-issue-kanban'):
        flash('Kanban issues nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    return None


# ---------- KANBAN ----------

@bim_bp.route('/kanban')
@bim_bp.route('/kanban/santier/<int:santier_id>')
@login_required
def kanban(santier_id=None):
    """Kanban board pentru IssueBIM. Coloane = status workflow."""
    redir = _ensure_kanban_enabled()
    if redir:
        return redir

    santier = Santier.query.get(santier_id) if santier_id else None
    q = IssueBIM.query
    if santier_id:
        # Filtru pe santier prin cladire / nivel / spatiu / element
        cladiri_ids = [c.id for c in Cladire.query.filter_by(santier_id=santier_id).all()]
        if cladiri_ids:
            from sqlalchemy import or_
            q = q.filter(or_(
                IssueBIM.cladire_id.in_(cladiri_ids),
                IssueBIM.element_bim_id.in_(
                    db.session.query(ElementBIM.id).filter(ElementBIM.cladire_id.in_(cladiri_ids))
                ),
            ))
        else:
            q = q.filter(IssueBIM.id == -1)  # niciun rezultat

    issues = q.order_by(IssueBIM.severitate.desc(), IssueBIM.id.desc()).limit(500).all()

    # Grupare pe status (coloanele kanban)
    coloane = {
        'deschis': [],
        'in_lucru': [],
        'rezolvat': [],
        'verificat': [],
        'inchis': [],
    }
    for iss in issues:
        coloane.setdefault(iss.status, []).append(iss)

    # Presence (cine vede acelasi kanban)
    active_users = []
    if ff_svc.is_enabled('bim-realtime-collab'):
        active_users = presence_svc.get_active_users(
            context_type='kanban', context_id=santier_id or 0,
        )

    # Latest event id (pentru SSE start)
    latest_event_id = rt_svc.get_latest_event_id() if ff_svc.is_enabled('bim-realtime-collab') else 0

    santiere = Santier.query.order_by(Santier.cod).all()

    return render_template('bim/kanban.html',
                           santier=santier, santiere=santiere,
                           coloane=coloane,
                           active_users=active_users,
                           latest_event_id=latest_event_id,
                           realtime_enabled=ff_svc.is_enabled('bim-realtime-collab'))


@bim_bp.route('/issue/<int:issue_id>/status', methods=['POST'])
@login_required
def issue_change_status(issue_id):
    """
    Schimba status-ul unui issue (drag & drop kanban).
    Body: status=<noul_status>. Publica RealtimeEvent.
    """
    issue = IssueBIM.query.get_or_404(issue_id)
    new_status = (request.form.get('status') or request.json.get('status') if request.is_json else request.form.get('status'))
    if not new_status:
        return jsonify({'error': 'status missing'}), 400

    valid_statuses = ('deschis', 'in_lucru', 'rezolvat', 'verificat', 'inchis', 'anulat')
    if new_status not in valid_statuses:
        return jsonify({'error': f'status invalid: {new_status}'}), 400

    if current_user.rol not in ('admin', 'manager') and new_status in ('verificat', 'inchis'):
        return jsonify({'error': 'doar admin/manager poate verifica/inchide'}), 403

    old_status = issue.status
    issue.status = new_status

    audit_svc.log_update('issue_bim', issue.id,
                          old_values={'status': old_status},
                          new_values={'status': new_status})

    # Publica eveniment real-time (best-effort, nu blocam la eroare)
    if ff_svc.is_enabled('bim-realtime-collab'):
        santier_id = None
        if issue.cladire_id:
            cladire = Cladire.query.get(issue.cladire_id)
            santier_id = cladire.santier_id if cladire else None
        try:
            rt_svc.publish_event(
                'issue_status_change',
                santier_id=santier_id,
                payload={'issue_id': issue.id, 'old_status': old_status,
                         'new_status': new_status, 'titlu': issue.titlu[:120]},
                user_id=current_user.id,
                commit=False,  # vom commit la final intr-o singura tranzactie
            )
        except Exception:
            pass

    db.session.commit()

    if request.is_json or request.headers.get('Accept', '').startswith('application/json'):
        return jsonify({'ok': True, 'status': new_status})
    flash(f'Issue #{issue.id}: {old_status} → {new_status}', 'success')
    return redirect(request.referrer or url_for('bim.kanban'))


# ---------- COMMENTS ----------

@bim_bp.route('/issue/<int:issue_id>/comments', methods=['GET', 'POST'])
@login_required
def issue_comments(issue_id):
    """List/add comments pe issue."""
    issue = IssueBIM.query.get_or_404(issue_id)

    if request.method == 'POST':
        if not ff_svc.is_enabled('bim-realtime-collab'):
            return jsonify({'error': 'feature disabled'}), 403
        text = (request.form.get('text') or
                (request.json.get('text') if request.is_json else None) or '').strip()
        if not text:
            return jsonify({'error': 'text obligatoriu'}), 400
        if len(text) > 5000:
            return jsonify({'error': 'text prea lung (max 5000)'}), 400

        parent_id = request.form.get('parent_id', type=int)
        comment = BIMComment(
            issue_id=issue.id,
            parent_id=parent_id,
            autor_id=current_user.id,
            text=text,
        )
        db.session.add(comment)
        db.session.flush()

        # Publica event
        santier_id = None
        if issue.cladire_id:
            cladire = Cladire.query.get(issue.cladire_id)
            santier_id = cladire.santier_id if cladire else None
        try:
            rt_svc.publish_event(
                'comment_new',
                santier_id=santier_id,
                payload={
                    'comment_id': comment.id,
                    'issue_id': issue.id,
                    'autor_id': current_user.id,
                    'autor_nume': f'{current_user.nume} {current_user.prenume}',
                    'text_preview': text[:200],
                },
                user_id=current_user.id,
                commit=False,
            )
        except Exception:
            pass

        audit_svc.log_create('bim_comment', comment.id,
                              new_values={'issue_id': issue.id, 'text_len': len(text)})
        db.session.commit()

        if request.is_json:
            return jsonify({'ok': True, 'comment_id': comment.id,
                            'text': text,
                            'autor_nume': f'{current_user.nume} {current_user.prenume}',
                            'data_creare': comment.data_creare.isoformat()})
        return redirect(url_for('bim.issue_comments', issue_id=issue_id))

    comments = (BIMComment.query.filter_by(issue_id=issue_id, sters=False)
                .order_by(BIMComment.data_creare).all())

    return render_template('bim/issue_comments.html',
                           issue=issue, comments=comments,
                           realtime_enabled=ff_svc.is_enabled('bim-realtime-collab'))


@bim_bp.route('/api/issue/<int:issue_id>/comments')
@login_required
def api_issue_comments(issue_id):
    """JSON list comments."""
    comments = (BIMComment.query.filter_by(issue_id=issue_id, sters=False)
                .order_by(BIMComment.data_creare).all())
    return jsonify({
        'issue_id': issue_id,
        'count': len(comments),
        'comments': [{
            'id': c.id,
            'autor_id': c.autor_id,
            'autor_nume': f'{c.autor.nume} {c.autor.prenume}' if c.autor else '?',
            'text': c.text,
            'parent_id': c.parent_id,
            'data_creare': c.data_creare.isoformat() if c.data_creare else None,
        } for c in comments],
    })


# ---------- PRESENCE ----------

@bim_bp.route('/api/presence/heartbeat', methods=['POST'])
@login_required
def presence_heartbeat():
    """Update presence pentru user-ul curent."""
    if not ff_svc.is_enabled('bim-realtime-collab'):
        return jsonify({'enabled': False}), 200

    context_type = (request.json.get('context_type') if request.is_json
                    else request.form.get('context_type'))
    context_id_raw = (request.json.get('context_id') if request.is_json
                      else request.form.get('context_id'))
    context_id = None
    try:
        if context_id_raw is not None and context_id_raw != '':
            context_id = int(context_id_raw)
    except (ValueError, TypeError):
        context_id = None

    presence_svc.heartbeat(
        current_user.id,
        user_nume=f'{current_user.nume} {current_user.prenume}',
        context_type=context_type,
        context_id=context_id,
    )
    return jsonify({'ok': True, 'context_type': context_type, 'context_id': context_id})


# ---------- SSE STREAM ----------

@bim_bp.route('/api/events/stream')
@login_required
def events_stream():
    """
    SSE stream cu evenimentele noi. Filtre prin query string:
    ?santier_id=X, ?since=<event_id>

    Stream se inchide dupa max 30s (limita PA). Clientul reconnecteaza.
    """
    if not ff_svc.is_enabled('bim-realtime-collab'):
        return jsonify({'enabled': False}), 403

    santier_id = request.args.get('santier_id', type=int)
    proiect_id = request.args.get('proiect_id', type=int)
    since = request.args.get('since', default=0, type=int)

    from flask import Response

    def generate():
        # Iese din generator inainte de a face commit (sa nu blocam DB)
        for chunk in rt_svc.sse_stream(santier_id=santier_id,
                                         proiect_id=proiect_id,
                                         start_after_id=since,
                                         max_duration_seconds=30):
            yield chunk

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


# ============================================================
# GOVERNANCE - Faza 8 (RBAC fin + API tokens + COBie + BCF + OpenAPI)
# Activare: feature flags 'bim-rbac-fine', 'bim-cobie-export',
#           'bim-bcf-full', 'bim-public-api' (default OFF)
# ============================================================

# ---------- RBAC ROLE ASSIGNMENTS ----------

@bim_bp.route('/roles')
@login_required
@manager_or_admin
def roles_lista():
    """Lista asignari de roluri (admin/manager only)."""
    if not ff_svc.is_enabled('bim-rbac-fine'):
        flash('RBAC fin nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    asignari = (BIMRoleAssignment.query.filter_by(activ=True)
                .order_by(BIMRoleAssignment.user_id, BIMRoleAssignment.rol)
                .all())
    users = Utilizator.query.filter_by(activ=True).order_by(Utilizator.nume).all()
    santiere = Santier.query.order_by(Santier.cod).all()
    return render_template('bim/roles_lista.html',
                           asignari=asignari, users=users, santiere=santiere,
                           roluri=BIMRoleAssignment.ROLURI,
                           scope_types=BIMRoleAssignment.SCOPE_TYPES)


@bim_bp.route('/role/nou', methods=['POST'])
@login_required
@manager_or_admin
def role_nou():
    """Creeaza o asignare de rol."""
    if not ff_svc.is_enabled('bim-rbac-fine'):
        flash('RBAC fin nu e activat.', 'danger')
        return redirect(url_for('bim.dashboard'))
    try:
        user_id = request.form.get('user_id', type=int)
        rol = request.form.get('rol', '').strip()
        scope_type = request.form.get('scope_type', 'global').strip()
        scope_id = request.form.get('scope_id', type=int)
        scope_disciplina = request.form.get('scope_disciplina', '').strip() or None
        if not user_id or not rol:
            flash('user si rol sunt obligatorii.', 'danger')
            return redirect(url_for('bim.roles_lista'))
        rbac_svc.assign_role(user_id, rol,
                              scope_type=scope_type, scope_id=scope_id,
                              scope_disciplina=scope_disciplina,
                              created_by=current_user)
        flash(f'Asignare rol "{rol}" creata.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare: {e}', 'danger')
    return redirect(url_for('bim.roles_lista'))


@bim_bp.route('/role/<int:asgn_id>/revoke', methods=['POST'])
@login_required
@manager_or_admin
def role_revoke(asgn_id):
    asgn = BIMRoleAssignment.query.get_or_404(asgn_id)
    rbac_svc.revoke_role(asgn, user=current_user)
    flash(f'Asignare #{asgn_id} dezactivata.', 'info')
    return redirect(url_for('bim.roles_lista'))


# ---------- API TOKENS ----------

@bim_bp.route('/tokens')
@login_required
def tokens_lista():
    """Lista API tokens (user-ul curent vede doar tokens proprii, admin vede tot)."""
    if not ff_svc.is_enabled('bim-public-api'):
        flash('API publica nu e activata pentru acest tenant.', 'info')
        return redirect(url_for('bim.dashboard'))
    q = ApiToken.query
    if current_user.rol != 'admin':
        q = q.filter_by(owner_id=current_user.id)
    tokens = q.order_by(ApiToken.data_creare.desc()).all()
    return render_template('bim/tokens_lista.html', tokens=tokens,
                           scopes_disponibile=ApiToken.SCOPES_DISPONIBILE)


@bim_bp.route('/token/nou', methods=['POST'])
@login_required
def token_nou():
    """Creeaza un API token. Token-ul plain se afiseaza o singura data."""
    if not ff_svc.is_enabled('bim-public-api'):
        flash('API publica nu e activata.', 'danger')
        return redirect(url_for('bim.dashboard'))
    try:
        nume = request.form.get('nume', '').strip()
        descriere = request.form.get('descriere', '').strip()
        scopes = request.form.getlist('scopes')
        expires_days = request.form.get('expires_days', type=int)
        tok = tokens_svc.create_token(
            nume=nume, owner_id=current_user.id, scopes=scopes,
            descriere=descriere or None, expires_days=expires_days,
        )
        flash(f'Token "{tok.nume}" creat. **API KEY (afisat o singura data)**: {tok.token}',
              'warning')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la creare token: {e}', 'danger')
    return redirect(url_for('bim.tokens_lista'))


@bim_bp.route('/token/<int:token_id>/revoke', methods=['POST'])
@login_required
def token_revoke(token_id):
    tok = ApiToken.query.get_or_404(token_id)
    if tok.owner_id != current_user.id and current_user.rol != 'admin':
        abort(403)
    tokens_svc.revoke_token(tok)
    flash(f'Token "{tok.nume}" revocat.', 'info')
    return redirect(url_for('bim.tokens_lista'))


# ---------- COBie EXPORT ----------

@bim_bp.route('/santier/<int:santier_id>/cobie.xlsx')
@login_required
def cobie_export_santier(santier_id):
    """Export COBie xlsx pentru un santier."""
    if not ff_svc.is_enabled('bim-cobie-export'):
        flash('COBie export nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.santier_detaliu', id=santier_id))
    santier = Santier.query.get_or_404(santier_id)
    try:
        buf = cobie_svc.generate_cobie_workbook(santier_id,
                                                 generated_by=current_user.email)
    except Exception as e:
        flash(f'Eroare la generare COBie: {e}', 'danger')
        return redirect(url_for('bim.santier_detaliu', id=santier_id))

    audit_svc.log('export_cobie', 'santier', santier_id,
                  new_values={'format': 'cobie_xlsx'}, commit=True)

    from flask import send_file
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'COBie-{santier.cod}-{datetime.utcnow().strftime("%Y%m%d")}.xlsx',
    )


# ---------- BCF EXPORT / IMPORT ----------

@bim_bp.route('/issues/export-bcf')
@login_required
def bcf_export_all():
    """Export toate issues ca .bcfzip."""
    if not ff_svc.is_enabled('bim-bcf-full'):
        flash('BCF complet nu e activat pentru acest tenant.', 'info')
        return redirect(url_for('bim.issues_lista'))
    try:
        buf = bcf_svc.export_bcfzip()
    except ValueError as e:
        flash(str(e), 'warning')
        return redirect(url_for('bim.issues_lista'))

    audit_svc.log('export_bcf', 'bim_issue_bulk', None,
                  new_values={'format': 'bcfzip_21'}, commit=True)

    from flask import send_file
    return send_file(
        buf, mimetype='application/octet-stream',
        as_attachment=True,
        download_name=f'issues-{datetime.utcnow().strftime("%Y%m%d-%H%M")}.bcfzip',
    )


@bim_bp.route('/issues/import-bcf', methods=['POST'])
@login_required
@manager_or_admin
def bcf_import_endpoint():
    """Import .bcfzip cu issues."""
    if not ff_svc.is_enabled('bim-bcf-full'):
        flash('BCF complet nu e activat.', 'danger')
        return redirect(url_for('bim.issues_lista'))
    f = request.files.get('bcf_file')
    if not f or not f.filename:
        flash('Fisier BCF lipseste.', 'danger')
        return redirect(url_for('bim.issues_lista'))
    if not (f.filename.lower().endswith('.bcfzip') or f.filename.lower().endswith('.bcf')):
        flash('Fisier trebuie sa fie .bcfzip', 'danger')
        return redirect(url_for('bim.issues_lista'))
    try:
        stats = bcf_svc.import_bcfzip(f, user=current_user)
        flash(f'BCF import: {stats["created"]} create, {stats["updated"]} update, '
              f'{stats["skipped"]} skip, {len(stats["errors"])} erori.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare import BCF: {e}', 'danger')
    return redirect(url_for('bim.issues_lista'))


# ---------- OPENAPI SPEC ----------

@bim_bp.route('/api/openapi.json')
def api_openapi_spec():
    """OpenAPI 3.0 spec - public, fara auth."""
    return jsonify(openapi_svc.generate_openapi_spec())


@bim_bp.route('/api/docs')
def api_docs():
    """Pagina HTML cu documentatie API (Swagger UI via CDN)."""
    return render_template('bim/api_docs.html')


# ---------- PUBLIC API v1 (token-auth) ----------

@bim_bp.route('/api/v1/issues')
@tokens_svc.api_token_required('bim:read')
def api_v1_issues():
    """Lista issues - protejat cu API token (scope bim:read)."""
    status = request.args.get('status')
    q = IssueBIM.query
    if status:
        q = q.filter_by(status=status)
    issues = q.order_by(IssueBIM.id.desc()).limit(200).all()
    return jsonify({
        'count': len(issues),
        'data': [{
            'id': i.id,
            'cod': i.cod,
            'titlu': i.titlu,
            'descriere': i.descriere,
            'tip': i.tip,
            'severitate': i.severitate,
            'status': i.status,
            'bcf_topic_guid': i.bcf_topic_guid,
            'element_bim_id': i.element_bim_id,
        } for i in issues],
    })


@bim_bp.route('/api/v1/element/<int:element_id>/state')
@tokens_svc.api_token_required('iot:read')
def api_v1_element_state(element_id):
    """Current state senzori pentru un element - protejat cu API token."""
    return jsonify(iot_query_svc.get_current_state_element(element_id))


# ============================================================
# DIAGNOSTICS — pagina de debug pentru env Python + dependinte BIM
# Util cand pip install pare facut dar lib-uri nu apar (PA venv etc.)
# ============================================================

@bim_bp.route('/diagnostics')
@login_required
@manager_or_admin
def bim_diagnostics():
    """
    Afiseaza info despre mediul Python actual + status dependinte BIM.
    Pe PythonAnywhere ajuta sa identifici daca pip install s-a facut
    in venv-ul corect (cel care ruleaza app-ul).
    """
    import sys
    try:
        ifc_info = ifc_service.detection_info()
    except Exception as e:
        ifc_info = {'error': str(e), 'available': False}

    # Verific si alte lib-uri importante BIM
    other_libs = {}
    for lib_name in ('openpyxl', 'reportlab', 'PIL', 'pandas'):
        try:
            mod = __import__(lib_name)
            other_libs[lib_name] = {
                'available': True,
                'version': getattr(mod, '__version__', 'unknown'),
            }
        except ImportError as e:
            other_libs[lib_name] = {'available': False, 'error': str(e)}

    # Feature flags status
    flag_status = {}
    for flag_key in ff_svc.KNOWN_FLAGS.keys():
        flag_status[flag_key] = ff_svc.is_enabled(flag_key)

    return render_template('bim/diagnostics.html',
                           ifc_info=ifc_info,
                           other_libs=other_libs,
                           python_executable=sys.executable,
                           python_version=sys.version,
                           flag_status=flag_status)
