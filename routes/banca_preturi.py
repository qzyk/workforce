"""
Blueprint pentru Banca de preturi de resurse.

Endpoints:
  GET       /banca-preturi/                 - lista + cautare + filtre (tip, categorie)
  GET POST  /banca-preturi/nou              - adauga pret (admin/manager)
  GET POST  /banca-preturi/<id>/editeaza    - editeaza pret (admin/manager)
  POST      /banca-preturi/<id>/sterge      - sterge pret (admin/manager)
  GET       /banca-preturi/api/pret/<cod>   - pret de referinta (mediana) JSON

Tot modulul e gated pe feature flag 'banca-preturi' (default OFF).
Write-urile cer rol admin/manager si au audit log.
"""

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort,
)
from flask_login import login_required, current_user

import services.audit as audit_svc
from services.feature_flags import is_enabled
from services import banca_preturi as bp_srv
from models import db, PretResursa
from forms.banca_preturi_forms import PretResursaForm

banca_preturi_bp = Blueprint('banca_preturi', __name__, url_prefix='/banca-preturi')

_AUDIT_FIELDS = ['tip', 'cod', 'denumire', 'um', 'categorie', 'pret_unitar',
                 'furnizor', 'sursa']


@banca_preturi_bp.before_request
def _gate():
    if not is_enabled('banca-preturi'):
        abort(404)


def _poate_scrie() -> bool:
    return current_user.is_authenticated and current_user.rol in ('admin', 'manager')


@banca_preturi_bp.route('/')
@login_required
def lista():
    q = request.args.get('q', '').strip() or None
    tip = request.args.get('tip', '').strip() or None
    categorie = request.args.get('categorie', '').strip() or None
    rezultate = bp_srv.cauta(q=q, tip=tip, categorie=categorie, limit=200)
    sumar = bp_srv.rezumat()
    return render_template('banca_preturi/lista.html',
                           rezultate=rezultate, sumar=sumar, q=q or '',
                           tip=tip or '', categorie=categorie or '',
                           categorii=bp_srv.categorii_existente(),
                           tipuri=PretResursa.TIPURI,
                           poate_scrie=_poate_scrie())


def _aplica_form(p: PretResursa, form: PretResursaForm) -> None:
    p.tip = form.tip.data
    p.cod = (form.cod.data or '').strip()
    p.denumire = (form.denumire.data or '').strip()
    p.um = (form.um.data or '').strip() or None
    p.categorie = ((form.categorie.data or '').strip()
                   or bp_srv.clasifica_resursa(p.tip, p.denumire, p.cod, p.um))
    p.pret_unitar = form.pret_unitar.data
    p.furnizor = (form.furnizor.data or '').strip() or None
    p.sursa = (form.sursa.data or '').strip() or None
    p.data_pret = form.data_pret.data


@banca_preturi_bp.route('/nou', methods=['GET', 'POST'])
@login_required
def nou():
    if not _poate_scrie():
        abort(403)
    form = PretResursaForm()
    if form.validate_on_submit():
        p = PretResursa(moneda='RON', introdus_de=current_user.id)
        _aplica_form(p, form)
        db.session.add(p)
        db.session.commit()
        audit_svc.log_create('pret_resursa', p.id,
                             new_values=audit_svc.snapshot(p, _AUDIT_FIELDS))
        flash(f'Pretul {p.cod} ({p.tip}) a fost adaugat in banca.', 'success')
        return redirect(url_for('banca_preturi.lista', q=p.cod))
    return render_template('banca_preturi/formular.html', form=form, pret=None)


@banca_preturi_bp.route('/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def editeaza(id):
    if not _poate_scrie():
        abort(403)
    p = PretResursa.query.get_or_404(id)
    form = PretResursaForm(obj=p)
    if form.validate_on_submit():
        old = audit_svc.snapshot(p, _AUDIT_FIELDS)
        _aplica_form(p, form)
        db.session.commit()
        audit_svc.log_update('pret_resursa', p.id, old_values=old,
                             new_values=audit_svc.snapshot(p, _AUDIT_FIELDS))
        flash(f'Pretul {p.cod} a fost actualizat.', 'success')
        return redirect(url_for('banca_preturi.lista', q=p.cod))
    return render_template('banca_preturi/formular.html', form=form, pret=p)


@banca_preturi_bp.route('/<int:id>/sterge', methods=['POST'])
@login_required
def sterge(id):
    if not _poate_scrie():
        abort(403)
    p = PretResursa.query.get_or_404(id)
    old = audit_svc.snapshot(p, _AUDIT_FIELDS)
    cod = p.cod
    db.session.delete(p)
    db.session.commit()
    audit_svc.log_delete('pret_resursa', id, old_values=old)
    flash(f'Pretul {cod} a fost sters din banca.', 'success')
    return redirect(url_for('banca_preturi.lista'))


@banca_preturi_bp.route('/api/pret/<path:cod>')
@login_required
def api_pret(cod):
    tip = request.args.get('tip', '').strip() or None
    pret = bp_srv.pret_referinta(cod, tip=tip)
    return jsonify({
        'cod': cod, 'tip': tip,
        'pret_referinta': float(pret) if pret is not None else None,
    })
