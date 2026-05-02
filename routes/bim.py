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
    db, Santier, Cladire, Nivel, Zona, Spatiu, ElementBIM, Asset,
    IssueBIM, ModelBIM, Proiect, RaportActivitate, Pontaj,
    ExternalMapping,
)
from services import ifc_import as ifc_service
from services import bim_quality

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
            s.cod = request.form.get('cod', '').strip()
            s.nume = request.form.get('nume', '').strip()
            s.descriere = request.form.get('descriere', '').strip()
            s.adresa = request.form.get('adresa', '').strip()
            s.oras = request.form.get('oras', '').strip()
            s.judet = request.form.get('judet', '').strip()
            s.proiect_id = request.form.get('proiect_id', type=int) or None
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
        db.session.delete(s)
        db.session.commit()
        flash(f'Santier "{s.nume}" sters.', 'info')
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
    """Pagina viewer 3D pentru un ModelBIM IFC."""
    model = ModelBIM.query.get_or_404(model_id)
    if model.tip != 'ifc' or not model.fisier_path:
        flash('Viewer-ul 3D suporta doar fisiere IFC incarcate.', 'warning')
        return redirect(url_for('bim.dashboard'))
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
