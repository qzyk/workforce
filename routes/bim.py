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
from datetime import datetime, date
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, abort
)
from flask_login import login_required, current_user

from models import (
    db, Santier, Cladire, Nivel, Zona, Spatiu, ElementBIM, Asset,
    IssueBIM, ModelBIM, Proiect, RaportActivitate, Pontaj,
)

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
    return render_template('bim/element_detaliu.html',
        element=e,
        rapoarte=rapoarte,
        pontaje=pontaje,
        issues=issues,
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
