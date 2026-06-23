"""
Captura rapida din teren (mobil-first).

Operatorul/managerul logheaza de pe telefon, in cateva tap-uri:
  - Pontaj rapid: proiect + ore + (azi) -> Pontaj draft (se rafineaza la editare)
  - Raporteaza problema: titlu + severitate -> IssueBIM (observatie)

Foloseste tabelele existente (Pontaj, IssueBIM) — fara model/migrare noua.
Sustine taglinea "One platform, all your sites": datele intra direct din teren.
"""
from __future__ import annotations

from datetime import date

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort)
from flask_login import login_required, current_user

from models import db, Proiect, Angajat, Pontaj, IssueBIM, Santier, Cladire
from services.feature_flags import is_enabled

teren_bp = Blueprint('teren', __name__, url_prefix='/teren')


def _teren_bulk_activ():
    """
    True daca flag-ul 'teren-pontaj-bulk' e activ. Degradeaza la False (OFF)
    in afara unui context de request - fail-safe, comportament istoric.
    """
    try:
        return is_enabled('teren-pontaj-bulk')
    except Exception:
        return False


def _proiecte_active():
    """Proiectele pe care are sens sa pontezi/raportezi (activ + planificat)."""
    return (Proiect.query
            .filter(Proiect.status.in_(['activ', 'planificat']))
            .order_by(Proiect.status.asc(), Proiect.nume.asc()).all())


def _angajat_curent():
    """Best-effort: angajatul logat, dupa email (nu exista FK user->angajat)."""
    em = (getattr(current_user, 'email', None) or '').strip().lower()
    if not em:
        return None
    return (Angajat.query
            .filter(db.func.lower(Angajat.email) == em,
                    Angajat.data_incetare.is_(None))
            .first())


def _angajati_activi():
    return (Angajat.query.filter(Angajat.data_incetare.is_(None))
            .order_by(Angajat.nume.asc(), Angajat.prenume.asc()).all())


@teren_bp.route('/')
@login_required
def index():
    azi = date.today()
    eu = _angajat_curent()
    pontaje_azi = []
    if eu:
        pontaje_azi = (Pontaj.query.filter_by(angajat_id=eu.id, data=azi)
                       .order_by(Pontaj.id.desc()).all())
    return render_template('teren/index.html', azi=azi, eu=eu,
                           pontaje_azi=pontaje_azi,
                           bulk_activ=_teren_bulk_activ())


@teren_bp.route('/pontaj', methods=['GET', 'POST'])
@login_required
def pontaj():
    proiecte = _proiecte_active()
    angajati = _angajati_activi()
    eu = _angajat_curent()

    if request.method == 'POST':
        from routes.pontaje import _detect_tip_zi
        try:
            proiect_id = int(request.form.get('proiect_id') or 0)
            angajat_id = int(request.form.get('angajat_id') or 0)
        except ValueError:
            proiect_id = angajat_id = 0
        try:
            ore = float((request.form.get('ore') or '8').replace(',', '.'))
        except ValueError:
            ore = 8.0
        ore = max(0.5, min(24.0, ore))

        d = date.today()
        ds = (request.form.get('data') or '').strip()
        if ds:
            try:
                d = date.fromisoformat(ds)
            except ValueError:
                pass

        if not proiect_id or not angajat_id:
            flash('Alege proiectul si angajatul.', 'danger')
            return redirect(url_for('teren.pontaj'))

        exista = Pontaj.query.filter_by(angajat_id=angajat_id, data=d).first()
        if exista:
            flash('Exista deja un pontaj pentru acest angajat in ziua aleasa. '
                  'Editeaza-l din Pontaje.', 'warning')
            return redirect(url_for('teren.index'))

        p = Pontaj(
            angajat_id=angajat_id, proiect_id=proiect_id, data=d,
            ore_lucrate=ore, ore_normale=ore,
            tip_zi=_detect_tip_zi(d), status='draft',
            observatii=(request.form.get('observatii') or '').strip()[:500] or '',
            introdus_de=getattr(current_user, 'id', None),
        )
        db.session.add(p)
        db.session.commit()
        flash(f'Pontaj salvat ({ore:g}h, {d.strftime("%d.%m")}). Orele suplimentare '
              'se ajusteaza la editare in Pontaje.', 'success')
        return redirect(url_for('teren.index'))

    return render_template('teren/pontaj.html', proiecte=proiecte,
                           angajati=angajati, eu=eu, azi=date.today())


@teren_bp.route('/problema', methods=['GET', 'POST'])
@login_required
def problema():
    santiere = Santier.query.order_by(Santier.nume.asc()).all()

    if request.method == 'POST':
        titlu = (request.form.get('titlu') or '').strip()
        if not titlu:
            flash('Scrie un titlu pentru problema.', 'danger')
            return redirect(url_for('teren.problema'))
        sev = request.form.get('severitate') or 'medie'
        if sev not in ('mica', 'medie', 'mare', 'critica'):
            sev = 'medie'
        # legare optionala la un santier (prima cladire a lui), best-effort
        cladire_id = None
        try:
            sid = int(request.form.get('santier_id') or 0)
        except ValueError:
            sid = 0
        if sid:
            cl = Cladire.query.filter_by(santier_id=sid).order_by(Cladire.id).first()
            cladire_id = cl.id if cl else None

        iss = IssueBIM(
            titlu=titlu[:200],
            descriere=(request.form.get('descriere') or '').strip()[:2000] or None,
            tip='observatie', severitate=sev, status='deschis',
            cladire_id=cladire_id,
            raportat_de_id=getattr(current_user, 'id', None),
        )
        db.session.add(iss)
        db.session.commit()
        flash('Problema raportata. O gasesti in BIM > Issues.', 'success')
        return redirect(url_for('teren.index'))

    return render_template('teren/problema.html', santiere=santiere)


@teren_bp.route('/pontaj-echipa', methods=['GET', 'POST'])
@login_required
def pontaj_echipa():
    """
    Pontaj de echipa pe teren (wf-4): multi-select angajati pe un proiect/zi,
    salvat in bloc. Reutilizeaza logica din pontaje.creeaza_pontaje_bulk (calcul
    ore + validare anti-duplicat/anti-suprapunere). Captura GPS optionala
    client-side (navigator.geolocation); lipsa GPS NU blocheaza pontajul.

    Gated pe flag-ul 'teren-pontaj-bulk' (default OFF). Cu OFF, ruta raspunde 404
    (modulul Teren ramane neschimbat - doar pontaj individual).
    """
    if not _teren_bulk_activ():
        abort(404)

    from routes.pontaje import creeaza_pontaje_bulk

    proiecte = _proiecte_active()
    angajati = _angajati_activi()
    azi = date.today()

    if request.method == 'POST':
        try:
            proiect_id = int(request.form.get('proiect_id') or 0)
        except ValueError:
            proiect_id = 0

        d = azi
        ds = (request.form.get('data') or '').strip()
        if ds:
            try:
                d = date.fromisoformat(ds)
            except ValueError:
                pass

        angajat_ids = request.form.getlist('angajat_ids')
        if not proiect_id or not angajat_ids:
            flash('Alege proiectul si cel putin un angajat.', 'danger')
            return redirect(url_for('teren.pontaj_echipa'))

        # Ore comune pentru toata echipa (formular de teren simplificat).
        ora_start = (request.form.get('ora_start') or '08:00').strip() or '08:00'
        ora_sfarsit = (request.form.get('ora_sfarsit') or '16:00').strip() or '16:00'
        obs = (request.form.get('observatii') or '').strip()[:500]

        randuri = [{
            'angajat_id': aid,
            'ora_start': ora_start,
            'ora_sfarsit': ora_sfarsit,
            'observatii': obs,
        } for aid in angajat_ids]

        actiune = request.form.get('actiune', 'draft')

        # GPS optional (client-side). Coordonate valide -> sursa 'gps', altfel NULL.
        lat = lng = sursa = None
        lat_raw = (request.form.get('latitudine') or '').strip()
        lng_raw = (request.form.get('longitudine') or '').strip()
        if lat_raw and lng_raw:
            try:
                lat_v = float(lat_raw)
                lng_v = float(lng_raw)
                # Validare domeniu coordonate; in afara -> ignora (NU blocheaza).
                if -90.0 <= lat_v <= 90.0 and -180.0 <= lng_v <= 180.0:
                    lat, lng, sursa = lat_v, lng_v, 'gps'
            except ValueError:
                pass

        count_ok, count_skip, create = creeaza_pontaje_bulk(
            proiect_id, d, randuri, actiune=actiune,
            lat=lat, lng=lng, sursa_gps=sursa,
        )
        db.session.commit()

        # Audit best-effort pe actiunea de echipa (sensibila: creare in masa).
        try:
            from services import audit
            audit.log(
                'pontaj_echipa_teren', 'pontaj',
                new_values={
                    'proiect_id': proiect_id,
                    'data': d.isoformat(),
                    'count_ok': count_ok,
                    'count_skip': count_skip,
                    'cu_gps': sursa == 'gps',
                },
                commit=True,
            )
        except Exception:
            pass

        gps_txt = ' (cu GPS)' if sursa == 'gps' else ''
        flash(f'{count_ok} pontaje de echipa salvate{gps_txt}. '
              f'{count_skip} omise (existau deja in ziua aleasa). '
              'Orele suplimentare se ajusteaza la editare in Pontaje.', 'success')
        return redirect(url_for('teren.index'))

    return render_template('teren/pontaj_echipa.html', proiecte=proiecte,
                           angajati=angajati, azi=azi)
