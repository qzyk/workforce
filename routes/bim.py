"""
INNOVA WORKFORCE - Modul BIM (Building Information Modeling)
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
            return render_template('bim/viewer_xeokit.html', model=model)

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
