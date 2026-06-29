"""
Blueprint pentru locatii proiect cu integrare Mapbox.

Endpoints:
  CRUD locatii:
    GET    /locatii/proiect/<int:proiect_id>              - lista (HTML + JSON via ?format=json)
    GET    POST /locatii/proiect/<int:proiect_id>/nou     - create
    GET    POST /locatii/<int:id>/editeaza                - update
    POST   /locatii/<int:id>/sterge                       - delete

  Map queries:
    GET    /locatii/proiect/<int:proiect_id>/within-bounds - bbox JSON query

  Server-side geocoding:
    POST   /locatii/api/geocode                            - {adresa} -> {lat, lng}

Permisiuni: @login_required. Toate write-urile au audit log.
Niciun flag-gating - feature vizibila din start (low risk, util pentru oricine).
"""

import os
from datetime import datetime
from decimal import Decimal

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort,
    jsonify, current_app,
)
from flask_login import login_required, current_user

from models import db, LocatieProiect
from forms.locatie_forms import LocatieProiectForm
import services.audit as audit_svc
from services.geocoding import geocodeaza_adresa, is_configured as geocoding_configured
from services.security.tenant_access import (
    get_project_location_or_404,
    get_project_or_404,
    query_project_locations_for_tenant,
    tenant_id_for_new_record_or_403,
)


locatii_bp = Blueprint('locatii', __name__)


def _wants_json() -> bool:
    """True daca clientul cere JSON (?format=json sau Accept: application/json)."""
    if request.args.get('format') == 'json':
        return True
    if request.accept_mimetypes.best == 'application/json':
        return True
    return False


# ============================================================
# CRUD
# ============================================================

@locatii_bp.route('/proiect/<int:proiect_id>')
@login_required
def lista(proiect_id):
    """Lista locatii pentru un proiect. Dual format: HTML sau JSON."""
    proiect = get_project_or_404(proiect_id)
    tip_filtru = (request.args.get('tip') or '').strip()
    status_filtru = (request.args.get('status') or '').strip()

    query = query_project_locations_for_tenant(project_id=proiect.id)
    if tip_filtru:
        query = query.filter_by(tip=tip_filtru)
    if status_filtru:
        query = query.filter_by(status=status_filtru)
    locatii = query.order_by(LocatieProiect.nume).all()

    if _wants_json():
        # GeoJSON FeatureCollection pentru consum direct in Mapbox
        features = [l.to_geojson_feature() for l in locatii
                    if l.are_coordonate]
        return jsonify({
            'type': 'FeatureCollection',
            'features': [f for f in features if f is not None],
            'count': len(locatii),
            'count_with_coords': len([l for l in locatii if l.are_coordonate]),
        })

    return render_template(
        'locatii/lista.html',
        proiect=proiect, locatii=locatii,
        tip_filtru=tip_filtru, status_filtru=status_filtru,
        tipuri=LocatieProiect.TIPURI, statuses=LocatieProiect.STATUSES,
        geocoding_disponibil=geocoding_configured(),
    )


@locatii_bp.route('/proiect/<int:proiect_id>/nou', methods=['GET', 'POST'])
@login_required
def nou(proiect_id):
    proiect = get_project_or_404(proiect_id)
    form = LocatieProiectForm()
    if request.method == 'GET':
        form.status.data = 'activ'
        form.tip.data = 'santier'

    if form.validate_on_submit():
        try:
            tenant_id = tenant_id_for_new_record_or_403()
            l = LocatieProiect(
                tenant_id=tenant_id,
                proiect_id=proiect.id,
                nume=form.nume.data.strip(),
                descriere=form.descriere.data or None,
                tip=form.tip.data,
                status=form.status.data,
                adresa_text=(form.adresa_text.data or '').strip() or None,
                judet=(form.judet.data or '').strip() or None,
                localitate=(form.localitate.data or '').strip() or None,
                latitudine=form.latitudine.data,
                longitudine=form.longitudine.data,
                creat_de_id=current_user.id,
            )
            # Geocoding optional la salvare
            if form.geocodeaza.data and l.adresa_text:
                rezultat = geocodeaza_adresa(
                    l.adresa_text, judet=l.judet, localitate=l.localitate
                )
                if rezultat:
                    l.latitudine = Decimal(str(rezultat['lat']))
                    l.longitudine = Decimal(str(rezultat['lng']))
                    l.adresa_normalizata = rezultat['normalized_address']
                    if rezultat.get('judet') and not l.judet:
                        l.judet = rezultat['judet']
                    if rezultat.get('localitate') and not l.localitate:
                        l.localitate = rezultat['localitate']
                    l.geocoded_at = datetime.utcnow()
                else:
                    flash('Geocodarea adresei nu a returnat rezultate. '
                          'Verifica adresa sau introdu coordonate manual.', 'warning')
            db.session.add(l)
            db.session.flush()
            audit_svc.log_create('locatie_proiect', l.id, new_values={
                'proiect_id': proiect.id, 'nume': l.nume, 'tip': l.tip,
                'are_coordonate': l.are_coordonate,
            }, tenant_id=tenant_id)
            db.session.commit()
            flash(f'Locatia "{l.nume}" a fost adaugata.', 'success')
            return redirect(url_for('locatii.lista', proiect_id=proiect.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')

    return render_template('locatii/formular.html',
                           form=form, proiect=proiect, locatie=None,
                           geocoding_disponibil=geocoding_configured())


@locatii_bp.route('/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def editeaza(id):
    l = get_project_location_or_404(id)
    proiect = l.proiect
    form = LocatieProiectForm(obj=l)
    if request.method == 'GET':
        form.locatie_id.data = l.id

    if form.validate_on_submit():
        try:
            audit_fields = ['nume', 'tip', 'status', 'latitudine',
                            'longitudine', 'adresa_text']
            before = audit_svc.snapshot(l, audit_fields)
            l.nume = form.nume.data.strip()
            l.descriere = form.descriere.data or None
            l.tip = form.tip.data
            l.status = form.status.data
            l.adresa_text = (form.adresa_text.data or '').strip() or None
            l.judet = (form.judet.data or '').strip() or None
            l.localitate = (form.localitate.data or '').strip() or None
            l.latitudine = form.latitudine.data
            l.longitudine = form.longitudine.data
            # Re-geocoding optional
            if form.geocodeaza.data and l.adresa_text:
                rezultat = geocodeaza_adresa(
                    l.adresa_text, judet=l.judet, localitate=l.localitate
                )
                if rezultat:
                    l.latitudine = Decimal(str(rezultat['lat']))
                    l.longitudine = Decimal(str(rezultat['lng']))
                    l.adresa_normalizata = rezultat['normalized_address']
                    l.geocoded_at = datetime.utcnow()
                else:
                    flash('Geocodarea nu a returnat rezultate.', 'warning')
            audit_svc.log_update('locatie_proiect', l.id, before,
                                 audit_svc.snapshot(l, audit_fields),
                                 tenant_id=l.tenant_id)
            db.session.commit()
            flash('Locatia a fost actualizata.', 'success')
            return redirect(url_for('locatii.lista', proiect_id=proiect.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Eroare la salvare: {e}', 'danger')

    return render_template('locatii/formular.html',
                           form=form, proiect=proiect, locatie=l,
                           geocoding_disponibil=geocoding_configured())


@locatii_bp.route('/<int:id>/sterge', methods=['POST'])
@login_required
def sterge(id):
    l = get_project_location_or_404(id)
    proiect_id = l.proiect_id
    try:
        audit_svc.log_delete('locatie_proiect', l.id, old_values={
            'nume': l.nume, 'tip': l.tip, 'proiect_id': proiect_id,
        }, tenant_id=l.tenant_id)
        nume = l.nume
        db.session.delete(l)
        db.session.commit()
        flash(f'Locatia "{nume}" a fost stearsa.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Eroare la stergere: {e}', 'danger')
    return redirect(url_for('locatii.lista', proiect_id=proiect_id))


# ============================================================
# Bbox query (pentru lazy-load la pan/zoom hartă)
# ============================================================

@locatii_bp.route('/proiect/<int:proiect_id>/within-bounds')
@login_required
def within_bounds(proiect_id):
    """
    GET /locatii/proiect/<id>/within-bounds?sw_lat=..&sw_lng=..&ne_lat=..&ne_lng=..
    Returneaza GeoJSON FeatureCollection cu locatiile din bbox.
    """
    proiect = get_project_or_404(proiect_id)
    from decimal import InvalidOperation
    try:
        sw_lat = Decimal(request.args.get('sw_lat', '-90'))
        sw_lng = Decimal(request.args.get('sw_lng', '-180'))
        ne_lat = Decimal(request.args.get('ne_lat', '90'))
        ne_lng = Decimal(request.args.get('ne_lng', '180'))
    except (ValueError, TypeError, InvalidOperation):
        return jsonify({'error': 'bbox params invalide'}), 400

    locatii = query_project_locations_for_tenant(project_id=proiect.id).filter(
        LocatieProiect.latitudine.between(sw_lat, ne_lat),
        LocatieProiect.longitudine.between(sw_lng, ne_lng),
    ).all()
    features = [l.to_geojson_feature() for l in locatii if l.are_coordonate]
    return jsonify({
        'type': 'FeatureCollection',
        'features': [f for f in features if f is not None],
    })


# ============================================================
# Server-side geocoding endpoint (Mapbox secret token NU se expune)
# ============================================================

@locatii_bp.route('/api/geocode', methods=['POST'])
@login_required
def api_geocode():
    """
    POST /locatii/api/geocode
    Body JSON: {"adresa": "Strada X", "judet": "Cluj", "localitate": "Cluj-Napoca"}

    Returneaza: {"lat": float, "lng": float, "normalized_address": str, ...}
    sau {"error": "..."} cu status 503/400.

    Secret token-ul Mapbox e folosit DOAR pe server, NU se expune in raspuns.
    """
    if not geocoding_configured():
        return jsonify({
            'error': 'not_configured',
            'message': 'MAPBOX_PUBLIC_TOKEN / MAPBOX_SECRET_TOKEN nu sunt setate.',
        }), 503

    data = request.get_json(silent=True) or {}
    adresa = (data.get('adresa') or '').strip()
    if not adresa:
        return jsonify({'error': 'adresa goala'}), 400
    judet = (data.get('judet') or '').strip() or None
    localitate = (data.get('localitate') or '').strip() or None

    rezultat = geocodeaza_adresa(adresa, judet=judet, localitate=localitate)
    if not rezultat:
        return jsonify({
            'error': 'no_results',
            'message': 'Niciun rezultat pentru adresa data.',
        }), 404

    return jsonify(rezultat)
