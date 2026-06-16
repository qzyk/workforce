"""
Rute pentru gestionarea concediilor (absence management).

Modulul activeaza modelul existent `Concediu` (models.py): adauga rutele de
scriere care lipseau (lista, creare, aprobare, respingere) + un calendar vizual
lunar de absente.

Tot modulul e gated pe feature flag 'concedii' (default OFF). Cu flag-ul OFF
toate rutele intorc 404 (zero impact, exact ca banca_preturi / contracte).

Workflow status: cerut -> aprobat | respins (vezi Concediu.STATUSURI).
Doar managerii (rol admin/manager) pot aproba sau respinge.
"""

import calendar as _calendar
from datetime import datetime, date

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, abort
)
from flask_login import login_required, current_user

from models import db, Concediu, Angajat, SarbatoareLegala
from forms.concedii_forms import ConcediuForm
from services.feature_flags import is_enabled
from services import concedii as concedii_srv

concedii_bp = Blueprint('concedii', __name__, url_prefix='/concedii')


@concedii_bp.before_request
def _gate():
    """Tot modulul e ascuns cat timp flag-ul 'concedii' e OFF."""
    if not is_enabled('concedii'):
        abort(404)


def _poate_aproba() -> bool:
    return current_user.is_authenticated and current_user.is_manager


# ============================================================
# LISTA CONCEDII - cu filtre (angajat, tip, status)
# ============================================================

@concedii_bp.route('/')
@login_required
def lista():
    angajat_id = request.args.get('angajat_id', '', type=str)
    tip = request.args.get('tip', '').strip()
    status = request.args.get('status', '').strip()

    query = Concediu.query

    if angajat_id:
        query = query.filter(Concediu.angajat_id == int(angajat_id))
    if tip:
        query = query.filter(Concediu.tip == tip)
    if status:
        query = query.filter(Concediu.status == status)

    concedii = query.order_by(Concediu.data_start.desc()).all()

    angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()

    # Numar cereri in asteptare (pentru badge in pagina)
    in_asteptare = Concediu.query.filter_by(status='cerut').count()

    return render_template('concedii/lista.html',
                           concedii=concedii,
                           angajati=angajati,
                           tipuri=Concediu.TIPURI,
                           statusuri=Concediu.STATUSURI,
                           angajat_id_filtru=angajat_id,
                           tip_filtru=tip,
                           status_filtru=status,
                           in_asteptare=in_asteptare,
                           poate_aproba=_poate_aproba())


# ============================================================
# ADAUGA CONCEDIU (cerere noua)
# ============================================================

@concedii_bp.route('/nou', methods=['GET', 'POST'])
@login_required
def nou():
    form = ConcediuForm()

    # Pre-selectie angajat din query string (ex: din fisa angajat)
    if request.method == 'GET':
        prefill = request.args.get('angajat_id', 0, type=int)
        if prefill:
            form.angajat_id.data = prefill

    if form.validate_on_submit():
        nr_zile = concedii_srv.calcul_zile_lucratoare(
            form.data_start.data, form.data_sfarsit.data
        )
        if nr_zile <= 0:
            flash('Intervalul selectat nu contine zile lucratoare.', 'warning')
            return render_template('concedii/formular.html', form=form, concediu=None)

        # Validare suprapunere cu concedii deja aprobate ale aceluiasi angajat
        conflict = concedii_srv.exista_suprapunere(
            form.angajat_id.data, form.data_start.data, form.data_sfarsit.data
        )
        if conflict:
            flash(
                'Angajatul are deja un concediu aprobat in acest interval '
                f'({conflict.data_start.strftime("%d.%m.%Y")} - '
                f'{conflict.data_sfarsit.strftime("%d.%m.%Y")}).',
                'danger'
            )
            return render_template('concedii/formular.html', form=form, concediu=None)

        concediu = Concediu(
            angajat_id=form.angajat_id.data,
            tip=form.tip.data,
            data_start=form.data_start.data,
            data_sfarsit=form.data_sfarsit.data,
            nr_zile=nr_zile,
            status='cerut',
            observatii=form.observatii.data.strip() if form.observatii.data else None,
            introdus_de=current_user.id,
        )
        db.session.add(concediu)
        db.session.commit()
        flash(
            f'Cerere de concediu inregistrata ({nr_zile} zile lucratoare). '
            'Apare cu status "Cerut" si poate fi aprobata de un manager.',
            'success'
        )
        return redirect(url_for('concedii.lista'))

    return render_template('concedii/formular.html', form=form, concediu=None)


# ============================================================
# APROBA CONCEDIU
# ============================================================

@concedii_bp.route('/<int:id>/aproba', methods=['POST'])
@login_required
def aproba(id):
    if not _poate_aproba():
        flash('Nu aveti permisiunea de a aproba concedii.', 'danger')
        return redirect(url_for('concedii.lista'))

    concediu = Concediu.query.get_or_404(id)

    if concediu.status != 'cerut':
        flash('Doar cererile cu status "Cerut" pot fi aprobate.', 'warning')
        return redirect(request.form.get('next', url_for('concedii.lista')))

    # Re-verific suprapunerea la momentul aprobarii (datele se pot fi schimbat
    # intre timp prin alta aprobare).
    conflict = concedii_srv.exista_suprapunere(
        concediu.angajat_id, concediu.data_start, concediu.data_sfarsit,
        exclude_id=concediu.id
    )
    if conflict:
        flash(
            'Nu se poate aproba: exista deja un concediu aprobat suprapus '
            f'({conflict.data_start.strftime("%d.%m.%Y")} - '
            f'{conflict.data_sfarsit.strftime("%d.%m.%Y")}).',
            'danger'
        )
        return redirect(request.form.get('next', url_for('concedii.lista')))

    concediu.status = 'aprobat'
    concediu.aprobat_de = current_user.id
    concediu.data_aprobare = datetime.utcnow()
    concediu.motiv_respingere = None
    db.session.commit()
    flash('Concediul a fost aprobat.', 'success')
    return redirect(request.form.get('next', url_for('concedii.lista')))


# ============================================================
# RESPINGE CONCEDIU
# ============================================================

@concedii_bp.route('/<int:id>/respinge', methods=['POST'])
@login_required
def respinge(id):
    if not _poate_aproba():
        flash('Nu aveti permisiunea de a respinge concedii.', 'danger')
        return redirect(url_for('concedii.lista'))

    concediu = Concediu.query.get_or_404(id)

    if concediu.status != 'cerut':
        flash('Doar cererile cu status "Cerut" pot fi respinse.', 'warning')
        return redirect(request.form.get('next', url_for('concedii.lista')))

    concediu.status = 'respins'
    concediu.motiv_respingere = (request.form.get('motiv', '') or '').strip() or None
    concediu.aprobat_de = current_user.id
    concediu.data_aprobare = datetime.utcnow()
    db.session.commit()
    flash('Cererea de concediu a fost respinsa.', 'warning')
    return redirect(request.form.get('next', url_for('concedii.lista')))


# ============================================================
# CALENDAR VIZUAL DE ABSENTE (lunar, pe angajat)
# ============================================================

@concedii_bp.route('/calendar')
@login_required
def calendar_view():
    """Vedere calendar lunar a absentelor unui angajat (refoloseste pattern-ul din pontaje)."""
    angajat_id = request.args.get('angajat_id', 0, type=int)
    luna = request.args.get('luna', date.today().month, type=int)
    anul = request.args.get('anul', date.today().year, type=int)

    angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()

    angajat = None
    calendar_data = []
    stats = {'zile_co': 0, 'zile_cm': 0, 'zile_alte': 0, 'total_zile': 0}

    if angajat_id:
        angajat = Angajat.query.get(angajat_id)
        _, days_in_month = _calendar.monthrange(anul, luna)

        # Concedii ale angajatului care ating luna (orice status, marcam aprobatele aparte)
        luna_start = date(anul, luna, 1)
        luna_sfarsit = date(anul, luna, days_in_month)
        concedii_luna = Concediu.query.filter(
            Concediu.angajat_id == angajat_id,
            Concediu.data_start <= luna_sfarsit,
            Concediu.data_sfarsit >= luna_start,
        ).all()

        # Mapez fiecare zi din luna -> concediul care o acopera (prioritate: aprobat)
        zi_concediu = {}
        for c in concedii_luna:
            d = max(c.data_start, luna_start)
            sfarsit = min(c.data_sfarsit, luna_sfarsit)
            while d <= sfarsit:
                existent = zi_concediu.get(d)
                if existent is None or (existent.status != 'aprobat' and c.status == 'aprobat'):
                    zi_concediu[d] = c
                d = date.fromordinal(d.toordinal() + 1)

        for day in range(1, days_in_month + 1):
            d = date(anul, luna, day)
            c = zi_concediu.get(d)
            is_sarb = SarbatoareLegala.query.filter_by(data=d).first()
            dow = d.weekday()

            if c:
                tip_concediu = c.tip
                tip = 'concediu'
                if c.status == 'aprobat':
                    if c.tip == 'CO':
                        stats['zile_co'] += 1
                    elif c.tip == 'CM':
                        stats['zile_cm'] += 1
                    else:
                        stats['zile_alte'] += 1
                    stats['total_zile'] += 1
            else:
                tip_concediu = None
                if is_sarb:
                    tip = 'sarbatoare'
                elif dow >= 5:
                    tip = 'weekend'
                else:
                    tip = 'lucratoare'

            calendar_data.append({
                'zi': day,
                'data': d,
                'dow': dow,
                'tip': tip,
                'concediu': c,
                'tip_concediu': tip_concediu,
                'is_today': d == date.today(),
            })

    return render_template('concedii/calendar.html',
                           angajati=angajati,
                           angajat=angajat,
                           angajat_id=angajat_id,
                           calendar_data=calendar_data,
                           first_dow=date(anul, luna, 1).weekday() if angajat_id else 0,
                           stats=stats,
                           luna=luna,
                           anul=anul)
