"""
Blueprint pentru Banca de preturi de resurse.

Endpoints:
  GET  /banca-preturi/                 - lista + cautare + sumar pe tip (HTML)
  GET  /banca-preturi/api/pret/<cod>   - pret de referinta (mediana) JSON

Tot modulul e gated pe feature flag 'banca-preturi' (default OFF).
Read-only (importul se face din CLI 'import-preturi'). @login_required.
"""

from flask import (
    Blueprint, render_template, request, jsonify, abort,
)
from flask_login import login_required

from services.feature_flags import is_enabled
from services import banca_preturi as bp_srv
from models import PretResursa

banca_preturi_bp = Blueprint('banca_preturi', __name__, url_prefix='/banca-preturi')


@banca_preturi_bp.before_request
def _gate():
    if not is_enabled('banca-preturi'):
        abort(404)


@banca_preturi_bp.route('/')
@login_required
def lista():
    q = request.args.get('q', '').strip() or None
    tip = request.args.get('tip', '').strip() or None
    rezultate = bp_srv.cauta(q=q, tip=tip, limit=200)
    sumar = bp_srv.rezumat()
    return render_template('banca_preturi/lista.html',
                           rezultate=rezultate, sumar=sumar, q=q or '',
                           tip=tip or '', tipuri=PretResursa.TIPURI)


@banca_preturi_bp.route('/api/pret/<path:cod>')
@login_required
def api_pret(cod):
    tip = request.args.get('tip', '').strip() or None
    pret = bp_srv.pret_referinta(cod, tip=tip)
    return jsonify({
        'cod': cod, 'tip': tip,
        'pret_referinta': float(pret) if pret is not None else None,
    })
