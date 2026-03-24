"""
INNOVA WORKFORCE - Dashboard principal
Calculeaza statistici complete pentru panoul de control
"""

import json
import calendar
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, case, and_, or_, extract

from models import db, Angajat, Proiect, Pontaj, Document, Concediu, AngajatProiect

dashboard_bp = Blueprint('dashboard', __name__)

ZILE_SAPTAMANA_RO = ['Luni', 'Marti', 'Miercuri', 'Joi', 'Vineri', 'Sambata', 'Duminica']


@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Dashboard principal cu toate statisticile."""
    today = date.today()
    luna_start = today.replace(day=1)

    # Luna trecuta (pentru trend)
    if today.month == 1:
        luna_trecuta_start = date(today.year - 1, 12, 1)
        luna_trecuta_sfarsit = date(today.year - 1, 12, 31)
    else:
        luna_trecuta_start = date(today.year, today.month - 1, 1)
        last_day = calendar.monthrange(today.year, today.month - 1)[1]
        luna_trecuta_sfarsit = date(today.year, today.month - 1, last_day)

    # ========================================
    # CARDURI STATISTICI PRINCIPALE
    # ========================================
    total_angajati_activi = Angajat.query.filter_by(status='activ').count()

    proiecte_active = Proiect.query.filter_by(status='activ').count()

    # Ore lucrate luna curenta (pontaje aprobate)
    ore_luna_curenta = db.session.query(
        func.coalesce(func.sum(Pontaj.ore_lucrate), 0)
    ).filter(
        Pontaj.data >= luna_start,
        Pontaj.status == 'aprobat'
    ).scalar()
    ore_luna_curenta = float(ore_luna_curenta)

    # Ore luna trecuta (pentru trend)
    ore_luna_trecuta = db.session.query(
        func.coalesce(func.sum(Pontaj.ore_lucrate), 0)
    ).filter(
        Pontaj.data >= luna_trecuta_start,
        Pontaj.data <= luna_trecuta_sfarsit,
        Pontaj.status == 'aprobat'
    ).scalar()
    ore_luna_trecuta = float(ore_luna_trecuta)

    # Documente expirate
    documente_expirate = Document.query.filter(
        Document.data_expirare.isnot(None),
        Document.data_expirare < today
    ).count()

    # Documente expira in curand (30 zile)
    documente_expira_curand = Document.query.filter(
        Document.data_expirare.isnot(None),
        Document.data_expirare >= today,
        Document.data_expirare <= today + timedelta(days=30)
    ).count()

    # Trend-uri fata de luna trecuta
    angajati_luna_trecuta = Angajat.query.filter(
        Angajat.status == 'activ',
        Angajat.data_angajare <= luna_trecuta_sfarsit
    ).count()
    trend_angajati = _calculeaza_trend(total_angajati_activi, angajati_luna_trecuta)

    proiecte_luna_trecuta = Proiect.query.filter(
        Proiect.status == 'activ',
        Proiect.data_start <= luna_trecuta_sfarsit
    ).count()
    trend_proiecte = _calculeaza_trend(proiecte_active, proiecte_luna_trecuta)

    trend_ore = _calculeaza_trend(ore_luna_curenta, ore_luna_trecuta)

    # ========================================
    # ANGAJATI FARA PONTAJ AZI
    # ========================================
    angajati_cu_pontaj_azi = db.session.query(Pontaj.angajat_id).filter(
        Pontaj.data == today
    ).subquery()

    angajati_fara_pontaj_azi = Angajat.query.filter(
        Angajat.status == 'activ',
        ~Angajat.id.in_(db.session.query(angajati_cu_pontaj_azi))
    ).count()

    # ========================================
    # COST MANOPERA LUNA CURENTA
    # ========================================
    cost_manopera_luna = db.session.query(
        func.coalesce(
            func.sum(Pontaj.ore_lucrate * Angajat.salariu_baza / 168),
            0
        )
    ).join(
        Angajat, Pontaj.angajat_id == Angajat.id
    ).filter(
        Pontaj.data >= luna_start,
        Pontaj.status == 'aprobat',
        Angajat.salariu_baza.isnot(None)
    ).scalar()
    cost_manopera_luna = float(cost_manopera_luna) if cost_manopera_luna else 0

    # ========================================
    # PREZENTA SAPTAMANA CURENTA
    # ========================================
    # Gasim luni-ul saptamanii curente
    luni_saptamana = today - timedelta(days=today.weekday())
    prezenta_saptamana = {}
    for i in range(min(5, today.weekday() + 1)):  # doar pana la ziua curenta, max vineri
        zi = luni_saptamana + timedelta(days=i)
        pontati = Pontaj.query.filter(Pontaj.data == zi).distinct(Pontaj.angajat_id).count()
        procent = round(pontati / total_angajati_activi * 100) if total_angajati_activi > 0 else 0
        prezenta_saptamana[ZILE_SAPTAMANA_RO[i]] = procent

    # ========================================
    # TOP 5 PROIECTE DUPA ORE LUCRATE
    # ========================================
    top_proiecte_ore = db.session.query(
        Proiect.id,
        Proiect.cod_proiect,
        Proiect.nume,
        func.coalesce(func.sum(Pontaj.ore_lucrate), 0).label('total_ore')
    ).join(
        Pontaj, Pontaj.proiect_id == Proiect.id
    ).filter(
        Proiect.status == 'activ',
        Pontaj.status == 'aprobat'
    ).group_by(
        Proiect.id, Proiect.cod_proiect, Proiect.nume
    ).order_by(
        func.sum(Pontaj.ore_lucrate).desc()
    ).limit(5).all()

    # Calculeaza max ore pentru progress bar
    max_ore_proiect = float(top_proiecte_ore[0].total_ore) if top_proiecte_ore else 1

    # ========================================
    # ULTIMELE 10 PONTAJE PENDING
    # ========================================
    pontaje_pending = db.session.query(
        Pontaj, Angajat, Proiect
    ).join(
        Angajat, Pontaj.angajat_id == Angajat.id
    ).join(
        Proiect, Pontaj.proiect_id == Proiect.id
    ).filter(
        Pontaj.status == 'trimis'
    ).order_by(
        Pontaj.data.desc()
    ).limit(10).all()

    # ========================================
    # GRAFIC PREZENTA 30 ZILE (Chart.js JSON)
    # ========================================
    grafic_prezenta_labels = []
    grafic_prezenta_data = []
    for i in range(29, -1, -1):
        zi = today - timedelta(days=i)
        if zi.weekday() < 5:  # doar zile lucratoare
            pontati = Pontaj.query.filter(Pontaj.data == zi).distinct(Pontaj.angajat_id).count()
            grafic_prezenta_labels.append(zi.strftime('%d.%m'))
            grafic_prezenta_data.append(pontati)

    grafic_prezenta_json = json.dumps({
        'labels': grafic_prezenta_labels,
        'data': grafic_prezenta_data,
        'total_angajati': total_angajati_activi
    })

    # ========================================
    # GRAFIC DISTRIBUTIE FUNCTII (Chart.js JSON)
    # ========================================
    distributie_functii = db.session.query(
        Angajat.functie,
        func.count(Angajat.id)
    ).filter(
        Angajat.status == 'activ'
    ).group_by(
        Angajat.functie
    ).all()

    # Map functie key la label frumos
    functii_labels_map = dict(Angajat.FUNCTII)
    grafic_functii_json = json.dumps({
        'labels': [functii_labels_map.get(f, f) for f, _ in distributie_functii],
        'data': [int(c) for _, c in distributie_functii]
    })

    # ========================================
    # ALERTE URGENTE
    # ========================================
    alerte = []

    if documente_expirate > 0:
        alerte.append({
            'tip': 'danger',
            'icon': 'fa-file-circle-exclamation',
            'mesaj': f'{documente_expirate} documente sunt expirate!',
            'url': url_for('documente.lista', status='expirat')
        })

    if documente_expira_curand > 0:
        alerte.append({
            'tip': 'warning',
            'icon': 'fa-clock',
            'mesaj': f'{documente_expira_curand} documente expira in 30 de zile',
            'url': url_for('documente.lista', status='in_curand')
        })

    if angajati_fara_pontaj_azi > 0 and today.weekday() < 5:
        alerte.append({
            'tip': 'info',
            'icon': 'fa-user-clock',
            'mesaj': f'{angajati_fara_pontaj_azi} angajati nu au pontaj azi',
            'url': url_for('pontaje.adauga')
        })

    pontaje_asteptare = Pontaj.query.filter_by(status='trimis').count()
    if pontaje_asteptare > 0 and current_user.is_manager:
        alerte.append({
            'tip': 'info',
            'icon': 'fa-hourglass-half',
            'mesaj': f'{pontaje_asteptare} pontaje asteapta aprobare',
            'url': url_for('pontaje.lista', status='trimis')
        })

    # Concedii active azi
    concedii_active = Concediu.query.filter(
        Concediu.data_start <= today,
        Concediu.data_sfarsit >= today,
        Concediu.status == 'aprobat'
    ).count()

    if concedii_active > 0:
        alerte.append({
            'tip': 'secondary',
            'icon': 'fa-umbrella-beach',
            'mesaj': f'{concedii_active} angajati in concediu azi',
            'url': '#'
        })

    # ========================================
    # COUNTS PENTRU SIDEBAR BADGES
    # ========================================
    badge_counts = {
        'pontaje_pending': pontaje_asteptare if current_user.is_manager else 0,
        'documente_alerta': documente_expirate + documente_expira_curand,
        'total_alerte': len(alerte)
    }

    return render_template('dashboard.html',
                           # Carduri principale
                           total_angajati_activi=total_angajati_activi,
                           proiecte_active=proiecte_active,
                           ore_luna_curenta=ore_luna_curenta,
                           documente_expirate=documente_expirate,
                           documente_expira_curand=documente_expira_curand,
                           # Trends
                           trend_angajati=trend_angajati,
                           trend_proiecte=trend_proiecte,
                           trend_ore=trend_ore,
                           # Extra stats
                           angajati_fara_pontaj_azi=angajati_fara_pontaj_azi,
                           cost_manopera_luna=cost_manopera_luna,
                           prezenta_saptamana=prezenta_saptamana,
                           # Tabele
                           top_proiecte_ore=top_proiecte_ore,
                           max_ore_proiect=max_ore_proiect,
                           pontaje_pending=pontaje_pending,
                           # Grafice JSON
                           grafic_prezenta_json=grafic_prezenta_json,
                           grafic_functii_json=grafic_functii_json,
                           # Alerte
                           alerte=alerte,
                           badge_counts=badge_counts)


@dashboard_bp.route('/api/dashboard-stats')
@login_required
def api_stats():
    """API endpoint pentru auto-refresh dashboard."""
    today = date.today()
    luna_start = today.replace(day=1)

    return jsonify({
        'angajati_activi': Angajat.query.filter_by(status='activ').count(),
        'proiecte_active': Proiect.query.filter_by(status='activ').count(),
        'ore_luna': float(db.session.query(
            func.coalesce(func.sum(Pontaj.ore_lucrate), 0)
        ).filter(Pontaj.data >= luna_start, Pontaj.status == 'aprobat').scalar()),
        'doc_expirate': Document.query.filter(
            Document.data_expirare.isnot(None),
            Document.data_expirare < today
        ).count(),
        'pontaje_pending': Pontaj.query.filter_by(status='trimis').count(),
        'timestamp': datetime.utcnow().isoformat()
    })


def _calculeaza_trend(valoare_curenta, valoare_precedenta):
    """Calculeaza procentul de trend (+/-)."""
    if valoare_precedenta == 0:
        if valoare_curenta > 0:
            return {'procent': 100, 'directie': 'up'}
        return {'procent': 0, 'directie': 'flat'}
    diferenta = ((valoare_curenta - valoare_precedenta) / valoare_precedenta) * 100
    if diferenta > 0:
        return {'procent': round(diferenta, 1), 'directie': 'up'}
    elif diferenta < 0:
        return {'procent': round(abs(diferenta), 1), 'directie': 'down'}
    return {'procent': 0, 'directie': 'flat'}
