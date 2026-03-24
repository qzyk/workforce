"""
INNOVA WORKFORCE - Modul Rapoarte Activitate Zilnica
Blueprint: /activitati
"""

import json
import os
from datetime import datetime, date, timedelta
from decimal import Decimal
from functools import wraps
from io import BytesIO

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, send_file, current_app
)
from flask_login import login_required, current_user

from models import (
    db, Angajat, Proiect, Pontaj, TipInstalatie,
    AngajatProiect, SarbatoareLegala,
    RaportActivitate, CategorieActivitate
)

activitati_bp = Blueprint('activitati', __name__, url_prefix='/activitati')


# ============================================================
# DECORATORI
# ============================================================

def manager_or_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ('admin', 'manager'):
            flash('Acces permis doar managerilor si administratorilor.', 'danger')
            return redirect(url_for('activitati.panou'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# HELPERI
# ============================================================

def _get_zile_lucratoare(an, luna):
    """Returneaza numarul de zile lucratoare din luna."""
    import calendar
    sarbatori = set()
    sarb_query = SarbatoareLegala.query.filter_by(an=an).all()
    for s in sarb_query:
        if s.data.month == luna:
            sarbatori.add(s.data.day)

    cal = calendar.monthcalendar(an, luna)
    zile = 0
    for week in cal:
        for i in range(5):  # Luni-Vineri
            day = week[i]
            if day != 0 and day not in sarbatori:
                zile += 1
    return zile


def _get_saptamana_bounds(an, saptamana):
    """Returneaza (luni, duminica) pentru saptamana ISO data."""
    from datetime import date as d_date
    jan4 = d_date(an, 1, 4)
    start_year = jan4 - timedelta(days=jan4.isoweekday() - 1)
    luni = start_year + timedelta(weeks=saptamana - 1)
    duminica = luni + timedelta(days=6)
    return luni, duminica


def _get_angajat_for_user(user):
    """Incearca sa gaseasca angajatul asociat utilizatorului logat (dupa email)."""
    if user and user.email:
        return Angajat.query.filter_by(email=user.email, status='activ').first()
    return None


# ============================================================
# RUTA PRINCIPALA - PANOU ACTIVITATI
# ============================================================

@activitati_bp.route('/')
@login_required
def panou():
    """Panou principal activitati."""
    today = date.today()
    angajat_curent = _get_angajat_for_user(current_user)

    # Date personale
    activitate_azi = None
    activitati_saptamana = []
    activitati_luna = []
    zile_cu_activitate_sapt = 0
    zile_cu_activitate_luna = 0
    zile_lucratoare_luna = _get_zile_lucratoare(today.year, today.month)
    proiecte_saptamana = set()
    activitati_aprobate_luna = 0
    activitati_pending_luna = 0

    if angajat_curent:
        # Activitate azi
        activitate_azi = RaportActivitate.query.filter_by(
            angajat_id=angajat_curent.id, data=today
        ).first()

        # Saptamana curenta
        luni = today - timedelta(days=today.weekday())
        duminica = luni + timedelta(days=6)
        activitati_saptamana = RaportActivitate.query.filter(
            RaportActivitate.angajat_id == angajat_curent.id,
            RaportActivitate.data >= luni,
            RaportActivitate.data <= duminica
        ).all()
        zile_cu_activitate_sapt = len(set(a.data for a in activitati_saptamana))
        proiecte_saptamana = set(a.proiect_id for a in activitati_saptamana)

        # Luna curenta
        prima_zi = today.replace(day=1)
        activitati_luna = RaportActivitate.query.filter(
            RaportActivitate.angajat_id == angajat_curent.id,
            RaportActivitate.data >= prima_zi,
            RaportActivitate.data <= today
        ).all()
        zile_cu_activitate_luna = len(set(a.data for a in activitati_luna))
        activitati_aprobate_luna = sum(1 for a in activitati_luna if a.status == 'aprobat')
        activitati_pending_luna = sum(1 for a in activitati_luna if a.status in ('draft', 'trimis'))

    # Tabel activitati recente (manageri vad tot, operatorii doar ale lor)
    query = RaportActivitate.query

    # Filtre
    f_angajat = request.args.get('angajat_id', '', type=int) or None
    f_proiect = request.args.get('proiect_id', '', type=int) or None
    f_instalatie = request.args.get('tip_instalatie_id', '', type=int) or None
    f_status = request.args.get('status', '')
    f_data_start = request.args.get('data_start', '')
    f_data_end = request.args.get('data_end', '')

    if current_user.rol == 'operator' and angajat_curent:
        query = query.filter_by(angajat_id=angajat_curent.id)
    elif current_user.rol == 'operator':
        query = query.filter_by(id=-1)  # no results

    if f_angajat:
        query = query.filter_by(angajat_id=f_angajat)
    if f_proiect:
        query = query.filter_by(proiect_id=f_proiect)
    if f_instalatie:
        query = query.filter_by(tip_instalatie_id=f_instalatie)
    if f_status:
        query = query.filter_by(status=f_status)
    if f_data_start:
        try:
            ds = datetime.strptime(f_data_start, '%Y-%m-%d').date()
            query = query.filter(RaportActivitate.data >= ds)
        except ValueError:
            pass
    if f_data_end:
        try:
            de = datetime.strptime(f_data_end, '%Y-%m-%d').date()
            query = query.filter(RaportActivitate.data <= de)
        except ValueError:
            pass

    activitati_recente = query.order_by(RaportActivitate.data.desc(), RaportActivitate.introdus_la.desc()).limit(50).all()

    # Aprobare count (pentru manageri)
    pending_aprobare = 0
    if current_user.rol in ('admin', 'manager'):
        pending_aprobare = RaportActivitate.query.filter_by(status='trimis').count()

    # Dropdown-uri filtre
    angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()
    proiecte = Proiect.query.filter(Proiect.status.in_(['activ', 'planificat'])).order_by(Proiect.cod_proiect).all()
    instalatii = TipInstalatie.query.filter_by(activ=True).order_by(TipInstalatie.ordine).all()

    return render_template('activitati/panou.html',
        today=today,
        angajat_curent=angajat_curent,
        activitate_azi=activitate_azi,
        activitati_saptamana=activitati_saptamana,
        zile_cu_activitate_sapt=zile_cu_activitate_sapt,
        proiecte_saptamana=proiecte_saptamana,
        activitati_luna=activitati_luna,
        zile_cu_activitate_luna=zile_cu_activitate_luna,
        zile_lucratoare_luna=zile_lucratoare_luna,
        activitati_aprobate_luna=activitati_aprobate_luna,
        activitati_pending_luna=activitati_pending_luna,
        activitati_recente=activitati_recente,
        pending_aprobare=pending_aprobare,
        angajati=angajati,
        proiecte=proiecte,
        instalatii=instalatii,
        f_angajat=f_angajat,
        f_proiect=f_proiect,
        f_instalatie=f_instalatie,
        f_status=f_status,
        f_data_start=f_data_start,
        f_data_end=f_data_end,
    )


# ============================================================
# ADAUGA ACTIVITATE
# ============================================================

@activitati_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    """Formular adaugare activitate noua."""
    if request.method == 'POST':
        return _salveaza_activitate(None)

    today = date.today()
    angajat_curent = _get_angajat_for_user(current_user)

    # Pre-completare din pontaj
    pontaj_azi = None
    if angajat_curent:
        pontaj_azi = Pontaj.query.filter_by(angajat_id=angajat_curent.id, data=today).first()

    angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()
    proiecte = Proiect.query.filter(Proiect.status.in_(['activ', 'planificat'])).order_by(Proiect.cod_proiect).all()
    instalatii = TipInstalatie.query.filter_by(activ=True).order_by(TipInstalatie.ordine).all()
    categorii = CategorieActivitate.query.filter_by(activa=True).order_by(CategorieActivitate.ordine).all()

    return render_template('activitati/formular.html',
        activitate=None,
        today=today,
        angajat_curent=angajat_curent,
        pontaj_azi=pontaj_azi,
        angajati=angajati,
        proiecte=proiecte,
        instalatii=instalatii,
        categorii=categorii,
    )


@activitati_bp.route('/adauga-rapida', methods=['GET', 'POST'])
@login_required
def adauga_rapida():
    """Formular simplificat (modal AJAX)."""
    if request.method == 'POST':
        return _salveaza_activitate(None, rapida=True)

    angajat_curent = _get_angajat_for_user(current_user)
    proiecte = Proiect.query.filter(Proiect.status.in_(['activ', 'planificat'])).order_by(Proiect.cod_proiect).all()
    instalatii = TipInstalatie.query.filter_by(activ=True).order_by(TipInstalatie.ordine).all()

    return render_template('activitati/formular_rapid.html',
        angajat_curent=angajat_curent,
        proiecte=proiecte,
        instalatii=instalatii,
    )


# ============================================================
# DETALIU + EDITARE + ACTIUNI
# ============================================================

@activitati_bp.route('/<int:id>')
@login_required
def detaliu(id):
    """Detaliu raport activitate."""
    activitate = RaportActivitate.query.get_or_404(id)
    angajat_curent = _get_angajat_for_user(current_user)

    # Verificare acces
    if current_user.rol == 'operator' and angajat_curent:
        if activitate.angajat_id != angajat_curent.id:
            flash('Nu aveti acces la aceasta activitate.', 'danger')
            return redirect(url_for('activitati.panou'))

    # Pontaj din aceeasi zi
    pontaj_zi = Pontaj.query.filter_by(
        angajat_id=activitate.angajat_id, data=activitate.data
    ).first()

    return render_template('activitati/detaliu.html',
        activitate=activitate,
        pontaj_zi=pontaj_zi,
    )


@activitati_bp.route('/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def editeaza(id):
    """Editare activitate existenta."""
    activitate = RaportActivitate.query.get_or_404(id)

    # Doar draft-urile pot fi editate de autori
    angajat_curent = _get_angajat_for_user(current_user)
    if current_user.rol == 'operator':
        if not angajat_curent or activitate.angajat_id != angajat_curent.id:
            flash('Nu aveti acces la aceasta activitate.', 'danger')
            return redirect(url_for('activitati.panou'))
        if activitate.status not in ('draft', 'respins'):
            flash('Activitatea nu mai poate fi editata.', 'warning')
            return redirect(url_for('activitati.detaliu', id=id))

    if request.method == 'POST':
        return _salveaza_activitate(activitate)

    angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()
    proiecte = Proiect.query.filter(Proiect.status.in_(['activ', 'planificat'])).order_by(Proiect.cod_proiect).all()
    instalatii = TipInstalatie.query.filter_by(activ=True).order_by(TipInstalatie.ordine).all()
    categorii = CategorieActivitate.query.filter_by(activa=True).order_by(CategorieActivitate.ordine).all()

    return render_template('activitati/formular.html',
        activitate=activitate,
        today=date.today(),
        angajat_curent=angajat_curent,
        pontaj_azi=None,
        angajati=angajati,
        proiecte=proiecte,
        instalatii=instalatii,
        categorii=categorii,
    )


def _salveaza_activitate(activitate, rapida=False):
    """Logica comuna salvare activitate (add/edit)."""
    try:
        angajat_id = request.form.get('angajat_id', type=int)
        proiect_id = request.form.get('proiect_id', type=int)
        data_str = request.form.get('data', '')
        tip_instalatie_id = request.form.get('tip_instalatie_id', type=int) or None
        categorie_id = request.form.get('categorie_activitate_id', type=int) or None
        zona_lucru = request.form.get('zona_lucru', '').strip()
        activitate_principala = request.form.get('activitate_principala', '').strip()
        activitate_detaliata = request.form.get('activitate_detaliata', '').strip()
        cantitate = request.form.get('cantitate_executata', '')
        um = request.form.get('unitate_masura', '').strip()
        procent = request.form.get('procent_realizare', type=int)
        probleme = request.form.get('probleme_intampinate', '').strip()
        solutii = request.form.get('solutii_aplicate', '').strip()
        observatii = request.form.get('observatii', '').strip()
        necesita_aprobare = bool(request.form.get('necesita_aprobare_tehnica'))
        actiune = request.form.get('actiune', 'draft')  # draft / trimite / alta

        # Validare
        if not angajat_id or not proiect_id:
            flash('Angajatul si proiectul sunt obligatorii.', 'danger')
            return redirect(request.url)
        if not activitate_principala:
            flash('Activitatea principala este obligatorie.', 'danger')
            return redirect(request.url)
        if not data_str:
            flash('Data este obligatorie.', 'danger')
            return redirect(request.url)

        data_val = datetime.strptime(data_str, '%Y-%m-%d').date()

        # Materiale JSON
        materiale_json = '[]'
        mat_denumiri = request.form.getlist('mat_denumire[]')
        mat_cantitati = request.form.getlist('mat_cantitate[]')
        mat_um = request.form.getlist('mat_um[]')
        if mat_denumiri:
            materiale = []
            for i in range(len(mat_denumiri)):
                if mat_denumiri[i].strip():
                    materiale.append({
                        'denumire': mat_denumiri[i].strip(),
                        'cantitate': mat_cantitati[i].strip() if i < len(mat_cantitati) else '',
                        'um': mat_um[i].strip() if i < len(mat_um) else ''
                    })
            materiale_json = json.dumps(materiale, ensure_ascii=False)

        echipamente = request.form.get('echipamente_folosite', '').strip()

        if activitate is None:
            activitate = RaportActivitate()
            db.session.add(activitate)

        activitate.angajat_id = angajat_id
        activitate.proiect_id = proiect_id
        activitate.data = data_val
        activitate.tip_instalatie_id = tip_instalatie_id
        activitate.categorie_activitate_id = categorie_id
        activitate.zona_lucru = zona_lucru
        activitate.activitate_principala = activitate_principala[:500]
        activitate.activitate_detaliata = activitate_detaliata[:2000] if activitate_detaliata else None
        activitate.materiale_folosite = materiale_json
        activitate.echipamente_folosite = echipamente or None
        activitate.cantitate_executata = Decimal(cantitate) if cantitate else None
        activitate.unitate_masura = um or None
        activitate.procent_realizare = min(100, max(0, procent)) if procent is not None else None
        activitate.probleme_intampinate = probleme or None
        activitate.solutii_aplicate = solutii or None
        activitate.observatii = observatii or None
        activitate.necesita_aprobare_tehnica = necesita_aprobare

        if actiune == 'trimite':
            activitate.status = 'trimis'
        elif activitate.status == 'respins':
            activitate.status = 'draft'

        db.session.commit()

        if actiune == 'trimite':
            flash('Activitatea a fost trimisa spre aprobare.', 'success')
        else:
            flash('Activitatea a fost salvata ca draft.', 'success')

        if actiune == 'alta':
            return redirect(url_for('activitati.adauga'))

        if rapida:
            return jsonify({'success': True, 'id': activitate.id})

        return redirect(url_for('activitati.detaliu', id=activitate.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la salvare: {str(e)}', 'danger')
        return redirect(request.url)


@activitati_bp.route('/<int:id>/trimite', methods=['POST'])
@login_required
def trimite(id):
    """Schimba status draft -> trimis."""
    activitate = RaportActivitate.query.get_or_404(id)
    if activitate.status != 'draft':
        flash('Doar activitatile draft pot fi trimise.', 'warning')
    else:
        activitate.status = 'trimis'
        db.session.commit()
        flash('Activitatea a fost trimisa spre aprobare.', 'success')
    return redirect(url_for('activitati.detaliu', id=id))


@activitati_bp.route('/<int:id>/aproba', methods=['POST'])
@login_required
@manager_or_admin
def aproba(id):
    """Aprobare activitate (manager/admin)."""
    activitate = RaportActivitate.query.get_or_404(id)
    activitate.status = 'aprobat'
    activitate.aprobat_de_id = current_user.id
    activitate.data_aprobare = datetime.utcnow()
    db.session.commit()
    flash('Activitatea a fost aprobata.', 'success')
    return redirect(url_for('activitati.detaliu', id=id))


@activitati_bp.route('/<int:id>/respinge', methods=['POST'])
@login_required
@manager_or_admin
def respinge(id):
    """Respingere activitate cu motiv."""
    activitate = RaportActivitate.query.get_or_404(id)
    motiv = request.form.get('motiv_respingere', '').strip()
    activitate.status = 'respins'
    activitate.motiv_respingere = motiv or 'Fara motiv specificat'
    db.session.commit()
    flash('Activitatea a fost respinsa.', 'warning')
    return redirect(url_for('activitati.detaliu', id=id))


@activitati_bp.route('/<int:id>/sterge', methods=['POST'])
@login_required
def sterge(id):
    """Sterge activitate (doar draft)."""
    activitate = RaportActivitate.query.get_or_404(id)
    angajat_curent = _get_angajat_for_user(current_user)

    if current_user.rol == 'operator':
        if not angajat_curent or activitate.angajat_id != angajat_curent.id:
            flash('Nu aveti acces.', 'danger')
            return redirect(url_for('activitati.panou'))
    if activitate.status not in ('draft', 'respins') and current_user.rol != 'admin':
        flash('Doar activitatile draft/respinse pot fi sterse.', 'warning')
        return redirect(url_for('activitati.detaliu', id=id))

    db.session.delete(activitate)
    db.session.commit()
    flash('Activitatea a fost stearsa.', 'info')
    return redirect(url_for('activitati.panou'))


# ============================================================
# ACTIVITATILE MELE
# ============================================================

@activitati_bp.route('/ale-mele')
@login_required
def ale_mele():
    """Activitatile angajatului curent logat."""
    angajat_curent = _get_angajat_for_user(current_user)
    if not angajat_curent:
        flash('Nu sunteti asociat unui angajat.', 'warning')
        return redirect(url_for('activitati.panou'))

    luna = request.args.get('luna', date.today().month, type=int)
    an = request.args.get('an', date.today().year, type=int)

    activitati = RaportActivitate.query.filter(
        RaportActivitate.angajat_id == angajat_curent.id,
        db.extract('month', RaportActivitate.data) == luna,
        db.extract('year', RaportActivitate.data) == an,
    ).order_by(RaportActivitate.data.desc()).all()

    return render_template('activitati/ale_mele.html',
        angajat=angajat_curent,
        activitati=activitati,
        luna=luna,
        an=an,
    )


@activitati_bp.route('/ale-mele/saptamana')
@login_required
def ale_mele_saptamana():
    """View saptamanal personal."""
    angajat_curent = _get_angajat_for_user(current_user)
    if not angajat_curent:
        flash('Nu sunteti asociat unui angajat.', 'warning')
        return redirect(url_for('activitati.panou'))

    today = date.today()
    an = request.args.get('an', today.year, type=int)
    sapt = request.args.get('saptamana', today.isocalendar()[1], type=int)
    luni, duminica = _get_saptamana_bounds(an, sapt)

    activitati = RaportActivitate.query.filter(
        RaportActivitate.angajat_id == angajat_curent.id,
        RaportActivitate.data >= luni,
        RaportActivitate.data <= duminica,
    ).order_by(RaportActivitate.data).all()

    # Group by day
    zile = {}
    for i in range(7):
        zi = luni + timedelta(days=i)
        zile[zi] = [a for a in activitati if a.data == zi]

    return render_template('activitati/saptamana.html',
        angajat=angajat_curent,
        an=an, saptamana=sapt,
        luni=luni, duminica=duminica,
        zile=zile,
        activitati=activitati,
    )


@activitati_bp.route('/ale-mele/luna')
@login_required
def ale_mele_luna():
    """View lunar personal."""
    return redirect(url_for('activitati.ale_mele',
                            luna=request.args.get('luna', date.today().month),
                            an=request.args.get('an', date.today().year)))


# ============================================================
# APROBARE
# ============================================================

@activitati_bp.route('/aprobare')
@login_required
@manager_or_admin
def aprobare():
    """Lista activitati in asteptare de aprobare."""
    activitati = RaportActivitate.query.filter_by(status='trimis').order_by(
        RaportActivitate.data.desc()
    ).all()

    return render_template('activitati/aprobare.html',
        activitati=activitati,
    )


@activitati_bp.route('/aprobare/masa', methods=['POST'])
@login_required
@manager_or_admin
def aprobare_masa():
    """Aprobare in masa."""
    ids = request.form.getlist('activitate_ids[]')
    actiune = request.form.get('actiune', 'aproba')  # aproba / respinge
    motiv = request.form.get('motiv_respingere', '').strip()

    count = 0
    for aid in ids:
        try:
            a = RaportActivitate.query.get(int(aid))
            if a and a.status == 'trimis':
                if actiune == 'aproba':
                    a.status = 'aprobat'
                    a.aprobat_de_id = current_user.id
                    a.data_aprobare = datetime.utcnow()
                else:
                    a.status = 'respins'
                    a.motiv_respingere = motiv or 'Respins in masa'
                count += 1
        except (ValueError, TypeError):
            continue

    db.session.commit()

    if actiune == 'aproba':
        flash(f'{count} activitati aprobate.', 'success')
    else:
        flash(f'{count} activitati respinse.', 'warning')
    return redirect(url_for('activitati.aprobare'))


# ============================================================
# CALENDAR
# ============================================================

@activitati_bp.route('/calendar')
@login_required
def calendar_view():
    """Calendar activitati."""
    today = date.today()
    luna = request.args.get('luna', today.month, type=int)
    an = request.args.get('an', today.year, type=int)
    f_angajat = request.args.get('angajat_id', type=int) or None
    f_proiect = request.args.get('proiect_id', type=int) or None
    view_type = request.args.get('view', 'lunar')  # lunar / saptamanal

    angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()
    proiecte = Proiect.query.filter(Proiect.status.in_(['activ', 'planificat'])).order_by(Proiect.cod_proiect).all()
    instalatii = TipInstalatie.query.filter_by(activ=True).order_by(TipInstalatie.ordine).all()

    return render_template('activitati/calendar.html',
        today=today,
        luna=luna, an=an,
        f_angajat=f_angajat,
        f_proiect=f_proiect,
        view_type=view_type,
        angajati=angajati,
        proiecte=proiecte,
        instalatii=instalatii,
    )


@activitati_bp.route('/api/calendar-data')
@login_required
def api_calendar_data():
    """Date JSON pentru calendar."""
    an = request.args.get('an', date.today().year, type=int)
    luna = request.args.get('luna', date.today().month, type=int)
    f_angajat = request.args.get('angajat_id', type=int) or None
    f_proiect = request.args.get('proiect_id', type=int) or None

    import calendar
    _, last_day = calendar.monthrange(an, luna)
    prima_zi = date(an, luna, 1)
    ultima_zi = date(an, luna, last_day)

    query = RaportActivitate.query.filter(
        RaportActivitate.data >= prima_zi,
        RaportActivitate.data <= ultima_zi,
    )

    if f_angajat:
        query = query.filter_by(angajat_id=f_angajat)
    if f_proiect:
        query = query.filter_by(proiect_id=f_proiect)

    # Operators see only their own
    if current_user.rol == 'operator':
        angajat_curent = _get_angajat_for_user(current_user)
        if angajat_curent:
            query = query.filter_by(angajat_id=angajat_curent.id)
        else:
            query = query.filter_by(id=-1)

    activitati = query.order_by(RaportActivitate.data).all()

    # Sarbatori
    sarbatori = set()
    for s in SarbatoareLegala.query.filter_by(an=an).all():
        if s.data.month == luna:
            sarbatori.add(s.data.day)

    # Group by day
    days = {}
    for a in activitati:
        day_str = a.data.isoformat()
        if day_str not in days:
            days[day_str] = []
        days[day_str].append({
            'id': a.id,
            'angajat': a.angajat.nume_complet if a.angajat else '?',
            'proiect': a.proiect.cod_proiect if a.proiect else '?',
            'activitate': a.activitate_scurta,
            'status': a.status,
            'instalatie_cod': a.tip_instalatie.cod if a.tip_instalatie else None,
            'instalatie_culoare': a.tip_instalatie.culoare_hex if a.tip_instalatie else '#546E7A',
        })

    return jsonify({
        'an': an,
        'luna': luna,
        'zile': days,
        'sarbatori': list(sarbatori),
    })


@activitati_bp.route('/api/categorii/<int:tip_instalatie_id>')
@login_required
def api_categorii(tip_instalatie_id):
    """Categorii activitate filtrate pe tip instalatie (AJAX)."""
    categorii = CategorieActivitate.query.filter(
        db.or_(
            CategorieActivitate.tip_instalatie_id == tip_instalatie_id,
            CategorieActivitate.tip_instalatie_id.is_(None)
        ),
        CategorieActivitate.activa == True
    ).order_by(CategorieActivitate.ordine).all()

    return jsonify([{
        'id': c.id,
        'denumire': c.denumire,
        'um_default': c.unitate_masura_default,
        'universal': c.tip_instalatie_id is None,
    } for c in categorii])


# ============================================================
# EXPORTURI EXCEL
# ============================================================

@activitati_bp.route('/raport/saptamanal')
@login_required
def raport_saptamanal():
    """Generator export saptamanal."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    today = date.today()
    an = request.args.get('an', today.year, type=int)
    sapt = request.args.get('saptamana', today.isocalendar()[1], type=int)
    luni, duminica = _get_saptamana_bounds(an, sapt)

    activitati = RaportActivitate.query.filter(
        RaportActivitate.data >= luni,
        RaportActivitate.data <= duminica,
    ).order_by(RaportActivitate.angajat_id, RaportActivitate.data).all()

    wb = Workbook()
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    header_font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    header_fill = PatternFill(start_color='1A237E', end_color='1A237E', fill_type='solid')

    # Sheet 1: Rezumat Saptamana
    ws = wb.active
    ws.title = 'Rezumat Saptamana'

    ws.merge_cells('A1:H1')
    ws['A1'] = f'Raport Activitati - Saptamana {sapt} ({luni.strftime("%d.%m.%Y")} - {duminica.strftime("%d.%m.%Y")})'
    ws['A1'].font = Font(name='Arial', bold=True, size=14, color='1A237E')

    # Headers
    zile_labels = ['Luni', 'Marti', 'Miercuri', 'Joi', 'Vineri', 'Sambata', 'Duminica']
    headers = ['Angajat'] + [f'{zl}\n{(luni + timedelta(days=i)).strftime("%d.%m")}' for i, zl in enumerate(zile_labels)]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = thin_border

    # Group by angajat
    from collections import defaultdict
    angajat_activitati = defaultdict(lambda: defaultdict(list))
    for a in activitati:
        angajat_activitati[a.angajat_id][a.data.weekday()].append(a)

    row = 4
    for ang_id, zile_dict in angajat_activitati.items():
        ang = Angajat.query.get(ang_id)
        ws.cell(row=row, column=1, value=ang.nume_complet if ang else '?').font = Font(name='Arial', bold=True, size=9)
        ws.cell(row=row, column=1).border = thin_border

        for day_idx in range(7):
            acts = zile_dict.get(day_idx, [])
            if acts:
                text = '\n'.join(f'{a.proiect.cod_proiect}: {a.activitate_scurta}' for a in acts)
            else:
                text = '-'
            cell = ws.cell(row=row, column=day_idx + 2, value=text)
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            cell.font = Font(name='Arial', size=8)
            cell.border = thin_border

        row += 1

    ws.column_dimensions['A'].width = 22
    for col_idx in range(2, 9):
        ws.column_dimensions[chr(64 + col_idx)].width = 20

    # Sheet 2: Detalii
    ws2 = wb.create_sheet('Detalii')
    detail_headers = ['Data', 'Angajat', 'Proiect', 'Instalatie', 'Zona', 'Activitate',
                       'Cantitate', 'U.M.', 'Materiale', 'Probleme', 'Status']
    for col_idx, h in enumerate(detail_headers, 1):
        cell = ws2.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    for row_idx, a in enumerate(activitati, 2):
        ws2.cell(row=row_idx, column=1, value=a.data.strftime('%d.%m.%Y')).border = thin_border
        ws2.cell(row=row_idx, column=2, value=a.angajat.nume_complet if a.angajat else '').border = thin_border
        ws2.cell(row=row_idx, column=3, value=a.proiect.cod_proiect if a.proiect else '').border = thin_border
        ws2.cell(row=row_idx, column=4, value=a.tip_instalatie.cod if a.tip_instalatie else '').border = thin_border
        ws2.cell(row=row_idx, column=5, value=a.zona_lucru or '').border = thin_border
        ws2.cell(row=row_idx, column=6, value=a.activitate_principala).border = thin_border
        ws2.cell(row=row_idx, column=7, value=float(a.cantitate_executata) if a.cantitate_executata else '').border = thin_border
        ws2.cell(row=row_idx, column=8, value=a.unitate_masura or '').border = thin_border
        ws2.cell(row=row_idx, column=9, value=', '.join(m['denumire'] for m in a.materiale_lista)).border = thin_border
        ws2.cell(row=row_idx, column=10, value=a.probleme_intampinate or '').border = thin_border
        ws2.cell(row=row_idx, column=11, value=a.status.title()).border = thin_border

    for col_idx in range(1, 12):
        ws2.column_dimensions[chr(64 + col_idx)].width = 18

    # Sheet 3: Sinteza per Proiect
    ws3 = wb.create_sheet('Sinteza per Proiect')
    proiect_acts = defaultdict(list)
    for a in activitati:
        proiect_acts[a.proiect_id].append(a)

    row = 1
    for pid, acts in proiect_acts.items():
        p = Proiect.query.get(pid)
        ws3.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        ws3.cell(row=row, column=1, value=f'{p.cod_proiect} - {p.nume}' if p else '?')
        ws3.cell(row=row, column=1).font = Font(name='Arial', bold=True, size=11, color='1A237E')
        row += 1

        for col_idx, h in enumerate(['Data', 'Angajat', 'Activitate', 'Cantitate', 'U.M.', 'Status'], 1):
            cell = ws3.cell(row=row, column=col_idx, value=h)
            cell.font = Font(name='Arial', bold=True, size=9)
            cell.fill = PatternFill(start_color='E8EAF6', end_color='E8EAF6', fill_type='solid')
            cell.border = thin_border
        row += 1

        for a in acts:
            ws3.cell(row=row, column=1, value=a.data.strftime('%d.%m.%Y')).border = thin_border
            ws3.cell(row=row, column=2, value=a.angajat.nume_complet if a.angajat else '').border = thin_border
            ws3.cell(row=row, column=3, value=a.activitate_principala).border = thin_border
            ws3.cell(row=row, column=4, value=float(a.cantitate_executata) if a.cantitate_executata else '').border = thin_border
            ws3.cell(row=row, column=5, value=a.unitate_masura or '').border = thin_border
            ws3.cell(row=row, column=6, value=a.status.title()).border = thin_border
            row += 1
        row += 1

    for col_idx in range(1, 7):
        ws3.column_dimensions[chr(64 + col_idx)].width = 20

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'Activitati_Saptamana_{sapt}_{an}.xlsx'
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@activitati_bp.route('/raport/lunar')
@login_required
def raport_lunar():
    """Generator export lunar."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    today = date.today()
    luna = request.args.get('luna', today.month, type=int)
    an = request.args.get('an', today.year, type=int)

    import calendar
    _, last_day = calendar.monthrange(an, luna)
    prima_zi = date(an, luna, 1)
    ultima_zi = date(an, luna, last_day)
    luni_ro = ['', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
               'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

    activitati = RaportActivitate.query.filter(
        RaportActivitate.data >= prima_zi,
        RaportActivitate.data <= ultima_zi,
    ).order_by(RaportActivitate.angajat_id, RaportActivitate.data).all()

    # Pontaje din aceeasi perioada
    pontaje = Pontaj.query.filter(
        Pontaj.data >= prima_zi, Pontaj.data <= ultima_zi
    ).all()
    pontaj_map = {}
    for p in pontaje:
        pontaj_map[(p.angajat_id, p.data.isoformat())] = float(p.ore_lucrate) if p.ore_lucrate else 0

    wb = Workbook()
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    header_font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    header_fill = PatternFill(start_color='1A237E', end_color='1A237E', fill_type='solid')

    # Sheet 1: Foaie Activitate Lunara
    ws = wb.active
    ws.title = 'Foaie Activitate Lunara'
    ws.merge_cells('A1:G1')
    ws['A1'] = f'Raport Activitati - {luni_ro[luna]} {an}'
    ws['A1'].font = Font(name='Arial', bold=True, size=14, color='1A237E')

    from collections import defaultdict
    angajat_acts = defaultdict(list)
    for a in activitati:
        angajat_acts[a.angajat_id].append(a)

    row = 3
    for ang_id, acts in angajat_acts.items():
        ang = Angajat.query.get(ang_id)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
        ws.cell(row=row, column=1, value=ang.nume_complet if ang else '?')
        ws.cell(row=row, column=1).font = Font(name='Arial', bold=True, size=12, color='1A237E')
        row += 1

        for col_idx, h in enumerate(['Data', 'Proiect', 'Tip Instalatie', 'Activitate', 'Cantitate', 'Ore Pontate', 'Obs'], 1):
            cell = ws.cell(row=row, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
        row += 1

        for a in acts:
            ore = pontaj_map.get((a.angajat_id, a.data.isoformat()), '')
            ws.cell(row=row, column=1, value=a.data.strftime('%d.%m.%Y')).border = thin_border
            ws.cell(row=row, column=2, value=a.proiect.cod_proiect if a.proiect else '').border = thin_border
            ws.cell(row=row, column=3, value=a.tip_instalatie.cod if a.tip_instalatie else '').border = thin_border
            ws.cell(row=row, column=4, value=a.activitate_principala).border = thin_border
            ws.cell(row=row, column=5, value=f'{float(a.cantitate_executata)} {a.unitate_masura or ""}' if a.cantitate_executata else '').border = thin_border
            ws.cell(row=row, column=6, value=ore).border = thin_border
            ws.cell(row=row, column=7, value=a.observatii or '').border = thin_border
            row += 1
        row += 2

    for col_idx, w in enumerate([12, 15, 14, 40, 14, 12, 20], 1):
        ws.column_dimensions[chr(64 + col_idx)].width = w

    # Sheet 2: Centralizator
    ws2 = wb.create_sheet('Centralizator')
    inst_codes = [t.cod for t in TipInstalatie.query.filter_by(activ=True).order_by(TipInstalatie.ordine).all()]
    cent_headers = ['Angajat'] + inst_codes + ['Total Zile']
    for col_idx, h in enumerate(cent_headers, 1):
        cell = ws2.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    row = 2
    for ang_id, acts in angajat_acts.items():
        ang = Angajat.query.get(ang_id)
        ws2.cell(row=row, column=1, value=ang.nume_complet if ang else '?').border = thin_border

        inst_zile = defaultdict(set)
        for a in acts:
            cod = a.tip_instalatie.cod if a.tip_instalatie else 'ALTA'
            inst_zile[cod].add(a.data)

        total_zile = len(set(a.data for a in acts))
        for col_idx, ic in enumerate(inst_codes, 2):
            ws2.cell(row=row, column=col_idx, value=len(inst_zile.get(ic, set()))).border = thin_border
        ws2.cell(row=row, column=len(inst_codes) + 2, value=total_zile).border = thin_border
        row += 1

    for col_idx in range(1, len(cent_headers) + 1):
        ws2.column_dimensions[chr(64 + col_idx)].width = 14

    # Sheet 3: Per Proiect
    ws3 = wb.create_sheet('Per Proiect')
    proiect_acts = defaultdict(list)
    for a in activitati:
        proiect_acts[a.proiect_id].append(a)

    row = 1
    for pid, acts in proiect_acts.items():
        p = Proiect.query.get(pid)
        ws3.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        ws3.cell(row=row, column=1, value=f'{p.cod_proiect} - {p.nume}' if p else '?')
        ws3.cell(row=row, column=1).font = Font(name='Arial', bold=True, size=11, color='1A237E')
        row += 1
        for col_idx, h in enumerate(['Categorie', 'Total Activitati', 'Cantitate Totala', 'U.M.', 'Angajati'], 1):
            cell = ws3.cell(row=row, column=col_idx, value=h)
            cell.font = Font(name='Arial', bold=True, size=9)
            cell.fill = PatternFill(start_color='E8EAF6', end_color='E8EAF6', fill_type='solid')
            cell.border = thin_border
        row += 1

        cat_stats = defaultdict(lambda: {'count': 0, 'cantitate': 0, 'um': '', 'angajati': set()})
        for a in acts:
            cat_name = a.categorie_activitate.denumire if a.categorie_activitate else 'Altele'
            cat_stats[cat_name]['count'] += 1
            if a.cantitate_executata:
                cat_stats[cat_name]['cantitate'] += float(a.cantitate_executata)
                cat_stats[cat_name]['um'] = a.unitate_masura or ''
            cat_stats[cat_name]['angajati'].add(a.angajat_id)

        for cat_name, stats in cat_stats.items():
            ws3.cell(row=row, column=1, value=cat_name).border = thin_border
            ws3.cell(row=row, column=2, value=stats['count']).border = thin_border
            ws3.cell(row=row, column=3, value=round(stats['cantitate'], 2) if stats['cantitate'] else '').border = thin_border
            ws3.cell(row=row, column=4, value=stats['um']).border = thin_border
            ws3.cell(row=row, column=5, value=len(stats['angajati'])).border = thin_border
            row += 1
        row += 1

    for col_idx in range(1, 6):
        ws3.column_dimensions[chr(64 + col_idx)].width = 20

    # Sheet 4: Probleme Raportate
    ws4 = wb.create_sheet('Probleme Raportate')
    prob_headers = ['Data', 'Angajat', 'Proiect', 'Problema', 'Solutie Aplicata']
    for col_idx, h in enumerate(prob_headers, 1):
        cell = ws4.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    row = 2
    for a in activitati:
        if a.probleme_intampinate:
            ws4.cell(row=row, column=1, value=a.data.strftime('%d.%m.%Y')).border = thin_border
            ws4.cell(row=row, column=2, value=a.angajat.nume_complet if a.angajat else '').border = thin_border
            ws4.cell(row=row, column=3, value=a.proiect.cod_proiect if a.proiect else '').border = thin_border
            ws4.cell(row=row, column=4, value=a.probleme_intampinate).border = thin_border
            ws4.cell(row=row, column=5, value=a.solutii_aplicate or '').border = thin_border
            row += 1

    for col_idx in range(1, 6):
        ws4.column_dimensions[chr(64 + col_idx)].width = 25

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'Activitati_Luna_{luni_ro[luna]}_{an}.xlsx'
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@activitati_bp.route('/raport/anual')
@login_required
def raport_anual():
    """Generator export anual."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.chart import BarChart, Reference

    an = request.args.get('an', date.today().year, type=int)
    luni_ro = ['', 'Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    luni_full = ['', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
                 'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

    prima_zi = date(an, 1, 1)
    ultima_zi = date(an, 12, 31)

    activitati = RaportActivitate.query.filter(
        RaportActivitate.data >= prima_zi,
        RaportActivitate.data <= ultima_zi,
    ).order_by(RaportActivitate.angajat_id, RaportActivitate.data).all()

    wb = Workbook()
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    header_font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    header_fill = PatternFill(start_color='1A237E', end_color='1A237E', fill_type='solid')

    # Sheet 1: Sumar Anual
    ws = wb.active
    ws.title = 'Sumar Anual'
    ws.merge_cells('A1:N1')
    ws['A1'] = f'Raport Activitati Anual - {an}'
    ws['A1'].font = Font(name='Arial', bold=True, size=14, color='1A237E')

    headers = ['Angajat'] + luni_ro[1:] + ['Total']
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    from collections import defaultdict
    angajat_lunar = defaultdict(lambda: defaultdict(int))
    for a in activitati:
        angajat_lunar[a.angajat_id][a.data.month] += 1

    row = 4
    for ang_id, lunar in angajat_lunar.items():
        ang = Angajat.query.get(ang_id)
        ws.cell(row=row, column=1, value=ang.nume_complet if ang else '?').border = thin_border
        total = 0
        for m in range(1, 13):
            val = lunar.get(m, 0)
            ws.cell(row=row, column=m + 1, value=val).border = thin_border
            total += val
        ws.cell(row=row, column=14, value=total).border = thin_border
        ws.cell(row=row, column=14).font = Font(name='Arial', bold=True)
        row += 1

    ws.column_dimensions['A'].width = 22
    for c in range(2, 15):
        ws.column_dimensions[chr(64 + c)].width = 8

    # Add chart
    if row > 4:
        chart = BarChart()
        chart.type = 'col'
        chart.title = f'Activitati per Angajat - {an}'
        chart.y_axis.title = 'Nr. Activitati'
        data = Reference(ws, min_col=2, max_col=13, min_row=3, max_row=row - 1)
        cats = Reference(ws, min_col=1, min_row=4, max_row=row - 1)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        chart.shape = 4
        chart.width = 30
        chart.height = 15
        ws.add_chart(chart, f'A{row + 2}')

    # Sheet 2: Statistici
    ws2 = wb.create_sheet('Statistici')
    ws2.merge_cells('A1:D1')
    ws2['A1'] = f'Statistici Activitati - {an}'
    ws2['A1'].font = Font(name='Arial', bold=True, size=14, color='1A237E')

    # Top activitati ca frecventa
    ws2.cell(row=3, column=1, value='Top Categorii Activitati').font = Font(name='Arial', bold=True, size=11)
    cat_freq = defaultdict(int)
    for a in activitati:
        cat_name = a.categorie_activitate.denumire if a.categorie_activitate else 'Altele'
        cat_freq[cat_name] += 1

    ws2.cell(row=4, column=1, value='Categorie').font = Font(name='Arial', bold=True)
    ws2.cell(row=4, column=2, value='Frecventa').font = Font(name='Arial', bold=True)
    row = 5
    for cat, freq in sorted(cat_freq.items(), key=lambda x: -x[1])[:20]:
        ws2.cell(row=row, column=1, value=cat).border = thin_border
        ws2.cell(row=row, column=2, value=freq).border = thin_border
        row += 1

    # Distributie per tip instalatie
    ws2.cell(row=row + 1, column=1, value='Distributie per Tip Instalatie').font = Font(name='Arial', bold=True, size=11)
    inst_freq = defaultdict(int)
    for a in activitati:
        cod = a.tip_instalatie.cod if a.tip_instalatie else 'N/A'
        inst_freq[cod] += 1

    row += 2
    ws2.cell(row=row, column=1, value='Instalatie').font = Font(name='Arial', bold=True)
    ws2.cell(row=row, column=2, value='Nr. Activitati').font = Font(name='Arial', bold=True)
    row += 1
    for inst, freq in sorted(inst_freq.items(), key=lambda x: -x[1]):
        ws2.cell(row=row, column=1, value=inst).border = thin_border
        ws2.cell(row=row, column=2, value=freq).border = thin_border
        row += 1

    ws2.column_dimensions['A'].width = 35
    ws2.column_dimensions['B'].width = 15

    # Sheet 3: Raport Management
    ws3 = wb.create_sheet('Raport Management')
    ws3.merge_cells('A1:D1')
    ws3['A1'] = f'Raport Management - {an}'
    ws3['A1'].font = Font(name='Arial', bold=True, size=14, color='1A237E')

    ws3.cell(row=3, column=1, value='Total activitati raportate:').font = Font(bold=True)
    ws3.cell(row=3, column=2, value=len(activitati))
    ws3.cell(row=4, column=1, value='Angajati cu rapoarte:').font = Font(bold=True)
    ws3.cell(row=4, column=2, value=len(angajat_lunar))
    ws3.cell(row=5, column=1, value='Proiecte active:').font = Font(bold=True)
    proiecte_set = set(a.proiect_id for a in activitati)
    ws3.cell(row=5, column=2, value=len(proiecte_set))

    # Probleme recurente
    ws3.cell(row=7, column=1, value='Probleme Raportate').font = Font(name='Arial', bold=True, size=11, color='C62828')
    probleme = [a for a in activitati if a.probleme_intampinate]
    ws3.cell(row=8, column=1, value='Total probleme raportate:').font = Font(bold=True)
    ws3.cell(row=8, column=2, value=len(probleme))

    row = 10
    for col_idx, h in enumerate(['Luna', 'Nr. Probleme', 'Proiecte Afectate'], 1):
        ws3.cell(row=row, column=col_idx, value=h).font = Font(bold=True)
    row += 1
    prob_lunar = defaultdict(lambda: {'count': 0, 'proiecte': set()})
    for a in probleme:
        prob_lunar[a.data.month]['count'] += 1
        prob_lunar[a.data.month]['proiecte'].add(a.proiect_id)
    for m in range(1, 13):
        if m in prob_lunar:
            ws3.cell(row=row, column=1, value=luni_full[m]).border = thin_border
            ws3.cell(row=row, column=2, value=prob_lunar[m]['count']).border = thin_border
            ws3.cell(row=row, column=3, value=len(prob_lunar[m]['proiecte'])).border = thin_border
            row += 1

    ws3.column_dimensions['A'].width = 30
    ws3.column_dimensions['B'].width = 18
    ws3.column_dimensions['C'].width = 18

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'Activitati_Anual_{an}.xlsx'
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@activitati_bp.route('/raport/proiect')
@login_required
def raport_proiect():
    """Raport activitati per proiect."""
    proiect_id = request.args.get('proiect_id', type=int)
    if not proiect_id:
        flash('Selectati un proiect.', 'warning')
        return redirect(url_for('activitati.panou'))

    proiect = Proiect.query.get_or_404(proiect_id)
    activitati = RaportActivitate.query.filter_by(proiect_id=proiect_id).order_by(
        RaportActivitate.data.desc()
    ).all()

    return render_template('activitati/raport_proiect.html',
        proiect=proiect,
        activitati=activitati,
    )
