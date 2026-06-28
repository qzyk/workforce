"""
EDIFICO WORKFORCE - Modul Tenant Management
Blueprint: /admin/tenants

Permite super-admin sa CRUD tenants si sa atribuie utilizatorii la tenants.
Ruta active doar daca MULTI_TENANT_MODE != 'off'.
"""

import json
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, abort, current_app
)
from flask_login import login_required, current_user

from models import db, Tenant, Utilizator, Angajat, Proiect
from services.security.tenant_access import require_super_admin_for_global_scope

tenants_bp = Blueprint('tenants', __name__, url_prefix='/admin/tenants')


def super_admin_required(f):
    """Doar admin-ul fara tenant_id (super-admin) poate gestiona tenants."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.rol != 'admin':
            flash('Doar super-administratorii pot gestiona tenants.', 'danger')
            abort(403)
        require_super_admin_for_global_scope()
        return f(*args, **kwargs)
    return wrapper


@tenants_bp.route('/')
@login_required
@super_admin_required
def lista():
    tenants = Tenant.query.order_by(Tenant.cod).all()
    # Pentru fiecare, numar utilizatori + angajati + proiecte
    stats = {}
    for t in tenants:
        stats[t.id] = {
            'utilizatori': Utilizator.query.filter_by(tenant_id=t.id).count(),
            'angajati': Angajat.query.filter_by(tenant_id=t.id).count(),
            'proiecte': Proiect.query.filter_by(tenant_id=t.id).count(),
        }
    # Stats pentru date "fara tenant"
    untenanted = {
        'utilizatori': Utilizator.query.filter_by(tenant_id=None).count(),
        'angajati': Angajat.query.filter_by(tenant_id=None).count(),
        'proiecte': Proiect.query.filter_by(tenant_id=None).count(),
    }
    return render_template('tenants/lista.html',
        tenants=tenants, stats=stats, untenanted=untenanted,
        mode=current_app.config.get('MULTI_TENANT_MODE', 'off'),
    )


@tenants_bp.route('/nou', methods=['GET', 'POST'])
@login_required
@super_admin_required
def nou():
    if request.method == 'POST':
        try:
            cod = request.form.get('cod', '').strip().lower()
            nume = request.form.get('nume', '').strip()
            if not cod or not nume:
                flash('Cod si nume sunt obligatorii.', 'danger')
                return redirect(request.url)
            if Tenant.query.filter_by(cod=cod).first():
                flash(f'Tenant cu cod "{cod}" exista deja.', 'danger')
                return redirect(request.url)
            t = Tenant(
                cod=cod, nume=nume,
                activ=bool(request.form.get('activ', '1')),
                config_json=request.form.get('config_json', '').strip() or None,
            )
            db.session.add(t)
            db.session.commit()
            flash(f'Tenant "{nume}" creat.', 'success')
            return redirect(url_for('tenants.lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare: {e}', 'danger')

    return render_template('tenants/formular.html', tenant=None)


@tenants_bp.route('/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
@super_admin_required
def editeaza(id):
    t = Tenant.query.get_or_404(id)
    if request.method == 'POST':
        try:
            t.nume = request.form.get('nume', '').strip() or t.nume
            t.activ = bool(request.form.get('activ'))
            cfg = request.form.get('config_json', '').strip()
            if cfg:
                # Validare JSON
                try:
                    json.loads(cfg)
                    t.config_json = cfg
                except json.JSONDecodeError:
                    flash('Config JSON invalid.', 'warning')
            else:
                t.config_json = None
            db.session.commit()
            flash('Tenant actualizat.', 'success')
            return redirect(url_for('tenants.lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare: {e}', 'danger')

    return render_template('tenants/formular.html', tenant=t)


@tenants_bp.route('/<int:id>/sterge', methods=['POST'])
@login_required
@super_admin_required
def sterge(id):
    t = Tenant.query.get_or_404(id)
    nume = t.nume
    nr_users = Utilizator.query.filter_by(tenant_id=t.id).count()
    if nr_users > 0:
        flash(f'Nu pot sterge "{nume}" - are {nr_users} utilizatori asociati. '
              'Mai intai de-asociaza utilizatorii (tenant_id=NULL) sau muta-i.', 'danger')
        return redirect(url_for('tenants.lista'))
    try:
        db.session.delete(t)
        db.session.commit()
        flash(f'Tenant "{nume}" sters.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    return redirect(url_for('tenants.lista'))


@tenants_bp.route('/<int:id>/utilizatori')
@login_required
@super_admin_required
def utilizatori(id):
    t = Tenant.query.get_or_404(id)
    utilizatori_in = Utilizator.query.filter_by(tenant_id=t.id).order_by(Utilizator.nume).all()
    utilizatori_libere = Utilizator.query.filter_by(tenant_id=None).order_by(Utilizator.nume).all()
    return render_template('tenants/utilizatori.html',
        tenant=t,
        utilizatori_in=utilizatori_in,
        utilizatori_libere=utilizatori_libere,
    )


@tenants_bp.route('/<int:tenant_id>/utilizatori/<int:user_id>/atribuie', methods=['POST'])
@login_required
@super_admin_required
def atribuie_utilizator(tenant_id, user_id):
    t = Tenant.query.get_or_404(tenant_id)
    u = Utilizator.query.get_or_404(user_id)
    u.tenant_id = t.id
    db.session.commit()
    flash(f'Utilizator {u.email} atribuit la tenant {t.cod}.', 'success')
    return redirect(url_for('tenants.utilizatori', id=tenant_id))


@tenants_bp.route('/<int:tenant_id>/utilizatori/<int:user_id>/dezatribuie', methods=['POST'])
@login_required
@super_admin_required
def dezatribuie_utilizator(tenant_id, user_id):
    u = Utilizator.query.get_or_404(user_id)
    if u.tenant_id != tenant_id:
        flash('Utilizatorul nu apartine acestui tenant.', 'warning')
    else:
        u.tenant_id = None
        db.session.commit()
        flash(f'Utilizator {u.email} dezatribuit.', 'info')
    return redirect(url_for('tenants.utilizatori', id=tenant_id))
