"""
EDIFICO WORKFORCE - Dashboard principal
Calculeaza statistici complete pentru panoul de control
"""

import json
import calendar
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, jsonify, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func, case, and_, or_, extract

from models import db, Angajat, Proiect, Pontaj, Document, Concediu, AngajatProiect
from services.security.tenant_access import (
    query_bim_elements_for_tenant,
    query_bim_issues_for_tenant,
    query_bim_models_for_tenant,
    query_contracts_for_tenant,
    query_for_tenant,
    query_gantt_plans_for_tenant,
    query_legacy_documents_for_tenant,
    query_sites_for_tenant,
    query_timesheets_for_tenant,
)

dashboard_bp = Blueprint('dashboard', __name__)

ZILE_SAPTAMANA_RO = ['Luni', 'Marti', 'Miercuri', 'Joi', 'Vineri', 'Sambata', 'Duminica']


@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Dashboard principal cu toate statisticile."""
    today = date.today()
    luna_start = today.replace(day=1)
    angajati_query = query_for_tenant(Angajat)
    proiecte_query = query_for_tenant(Proiect)
    pontaje_query = query_timesheets_for_tenant()
    documente_query = query_legacy_documents_for_tenant()

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
    total_angajati_activi = angajati_query.filter_by(status='activ').count()

    proiecte_active = proiecte_query.filter_by(status='activ').count()

    # Ore lucrate luna curenta (pontaje aprobate)
    ore_luna_curenta = pontaje_query.with_entities(
        func.coalesce(func.sum(Pontaj.ore_lucrate), 0)
    ).filter(
        Pontaj.data >= luna_start,
        Pontaj.status == 'aprobat'
    ).scalar()
    ore_luna_curenta = float(ore_luna_curenta)

    # Ore luna trecuta (pentru trend)
    ore_luna_trecuta = query_timesheets_for_tenant().with_entities(
        func.coalesce(func.sum(Pontaj.ore_lucrate), 0)
    ).filter(
        Pontaj.data >= luna_trecuta_start,
        Pontaj.data <= luna_trecuta_sfarsit,
        Pontaj.status == 'aprobat'
    ).scalar()
    ore_luna_trecuta = float(ore_luna_trecuta)

    # Documente expirate
    documente_expirate = documente_query.filter(
        Document.data_expirare.isnot(None),
        Document.data_expirare < today
    ).count()

    # Documente expira in curand (30 zile)
    documente_expira_curand = query_legacy_documents_for_tenant().filter(
        Document.data_expirare.isnot(None),
        Document.data_expirare >= today,
        Document.data_expirare <= today + timedelta(days=30)
    ).count()

    # Trend-uri fata de luna trecuta
    angajati_luna_trecuta = query_for_tenant(Angajat).filter(
        Angajat.status == 'activ',
        Angajat.data_angajare <= luna_trecuta_sfarsit
    ).count()
    trend_angajati = _calculeaza_trend(total_angajati_activi, angajati_luna_trecuta)

    proiecte_luna_trecuta = query_for_tenant(Proiect).filter(
        Proiect.status == 'activ',
        Proiect.data_start <= luna_trecuta_sfarsit
    ).count()
    trend_proiecte = _calculeaza_trend(proiecte_active, proiecte_luna_trecuta)

    trend_ore = _calculeaza_trend(ore_luna_curenta, ore_luna_trecuta)

    # ========================================
    # ANGAJATI FARA PONTAJ AZI
    # ========================================
    angajati_cu_pontaj_azi = query_timesheets_for_tenant().with_entities(
        Pontaj.angajat_id
    ).filter(
        Pontaj.data == today
    ).subquery()

    angajati_fara_pontaj_azi = query_for_tenant(Angajat).filter(
        Angajat.status == 'activ',
        ~Angajat.id.in_(db.session.query(angajati_cu_pontaj_azi))
    ).count()

    # ========================================
    # COST MANOPERA LUNA CURENTA
    # ========================================
    cost_manopera_luna = query_timesheets_for_tenant().join(
        Angajat, Pontaj.angajat_id == Angajat.id
    ).with_entities(
        func.coalesce(
            func.sum(Pontaj.ore_lucrate * Angajat.salariu_baza / 168),
            0
        )
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
        pontati = query_timesheets_for_tenant().with_entities(
            Pontaj.angajat_id
        ).filter(Pontaj.data == zi).distinct().count()
        procent = round(pontati / total_angajati_activi * 100) if total_angajati_activi > 0 else 0
        prezenta_saptamana[ZILE_SAPTAMANA_RO[i]] = procent

    # ========================================
    # TOP 5 PROIECTE DUPA ORE LUCRATE
    # ========================================
    top_proiecte_ore = query_timesheets_for_tenant().join(
        Proiect, Pontaj.proiect_id == Proiect.id
    ).with_entities(
        Proiect.id,
        Proiect.cod_proiect,
        Proiect.nume,
        func.coalesce(func.sum(Pontaj.ore_lucrate), 0).label('total_ore')
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
    pontaje_pending = query_timesheets_for_tenant().join(
        Angajat, Pontaj.angajat_id == Angajat.id
    ).join(
        Proiect, Pontaj.proiect_id == Proiect.id
    ).with_entities(
        Pontaj, Angajat, Proiect
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
            pontati = query_timesheets_for_tenant().with_entities(
                Pontaj.angajat_id
            ).filter(Pontaj.data == zi).distinct().count()
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
    distributie_functii = query_for_tenant(Angajat).with_entities(
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

    pontaje_asteptare = query_timesheets_for_tenant().filter_by(status='trimis').count()
    if pontaje_asteptare > 0 and current_user.is_manager:
        alerte.append({
            'tip': 'info',
            'icon': 'fa-hourglass-half',
            'mesaj': f'{pontaje_asteptare} pontaje asteapta aprobare',
            'url': url_for('pontaje.lista', status='trimis')
        })

    # Concedii active azi
    angajati_scope = query_for_tenant(Angajat).with_entities(Angajat.id)
    concedii_active = Concediu.query.filter(
        Concediu.angajat_id.in_(angajati_scope),
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

    # Ghid „pasul urmator" (U4): adaptiv dupa stadiul contului
    from models import GanttPlan
    ghid_nr_proiecte = query_for_tenant(Proiect).count()
    ghid_nr_planuri = query_gantt_plans_for_tenant().count()

    return render_template('dashboard.html',
                           ghid_nr_proiecte=ghid_nr_proiecte,
                           ghid_nr_planuri=ghid_nr_planuri,
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
        'angajati_activi': query_for_tenant(Angajat).filter_by(status='activ').count(),
        'proiecte_active': query_for_tenant(Proiect).filter_by(status='activ').count(),
        'ore_luna': float(query_timesheets_for_tenant().with_entities(
            func.coalesce(func.sum(Pontaj.ore_lucrate), 0)
        ).filter(Pontaj.data >= luna_start, Pontaj.status == 'aprobat').scalar()),
        'doc_expirate': query_legacy_documents_for_tenant().filter(
            Document.data_expirare.isnot(None),
            Document.data_expirare < today
        ).count(),
        'pontaje_pending': query_timesheets_for_tenant().filter_by(status='trimis').count(),
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


@dashboard_bp.route('/dashboard/executiv')
@login_required
def executiv():
    """Dashboard executiv cross-modul: proiecte, cost, BIM, avans (portofoliu)."""
    from models import (Contract, OfertaContract, GanttPlan, SituatieLunara,
                        ModelBIM, ElementBIM, IssueBIM)

    def safe(fn, d=0):
        try:
            return fn()
        except Exception:
            return d

    def suma(query, model, camp):
        return float(query.with_entities(func.coalesce(func.sum(getattr(model, camp)), 0))
                     .scalar() or 0)

    kpi = {
        'proiecte_active': safe(lambda: query_for_tenant(Proiect).filter_by(status='activ').count()),
        'proiecte_total': safe(lambda: query_for_tenant(Proiect).count()),
        'contracte_val': safe(lambda: suma(query_contracts_for_tenant(), Contract, 'valoare_totala'), 0.0),
        'deviz_val': safe(lambda: suma(query_for_tenant(OfertaContract), OfertaContract, 'valoare_totala'), 0.0),
        'gantt_planuri': safe(lambda: query_gantt_plans_for_tenant().count()),
        'gantt_cost': safe(lambda: suma(query_gantt_plans_for_tenant(), GanttPlan, 'cost_total'), 0.0),
        'bim_modele': safe(lambda: query_bim_models_for_tenant().count()),
        'bim_elemente': safe(lambda: query_bim_elements_for_tenant().count()),
        'bim_issues': safe(lambda: query_bim_issues_for_tenant().filter(IssueBIM.status != 'inchis').count()),
    }

    from services.evm import risc_proiect
    proiecte = []
    for p in safe(lambda: query_for_tenant(Proiect).order_by(Proiect.data_creare.desc()).limit(40).all(), []):
        sit = safe(lambda: query_for_tenant(SituatieLunara).filter_by(proiect_id=p.id)
                   .order_by(SituatieLunara.id.desc()).first(), None)
        proiecte.append({
            'p': p,
            'avans': float(sit.procent_avans_total) if sit and sit.procent_avans_total else 0.0,
            'contracte': safe(lambda: query_contracts_for_tenant().filter_by(proiect_id=p.id).count()),
            'planuri': safe(lambda: query_gantt_plans_for_tenant().filter_by(proiect_id=p.id).count()),
            'santiere': safe(lambda: p.legaturi_santiere.count()),
            'risc': safe(lambda: (risc_proiect(p.id) or {}).get('status'), None),
        })
    return render_template('dashboard_executiv.html', kpi=kpi, proiecte=proiecte)


@dashboard_bp.route('/dashboard/verifica-riscuri', methods=['POST'])
@login_required
def verifica_riscuri():
    """Genereaza notificari EVM pentru proiectele la risc (manual)."""
    from services.notificari_job import alerteaza_evm_risc
    n = alerteaza_evm_risc(
        proiect_query=query_for_tenant(Proiect).filter_by(status='activ')
    )
    flash(f'{n} alerte EVM generate — vezi notificari.' if n
          else 'Niciun proiect activ la risc EVM.', 'info' if n else 'success')
    return redirect(url_for('dashboard.executiv'))


@dashboard_bp.route('/cauta')
@login_required
def cauta():
    """Cautare globala (autocomplete header): proiecte, planuri, angajati, santiere, contracte."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    like = f'%{q}%'
    tid = getattr(current_user, 'tenant_id', None)
    out = []

    for p in query_for_tenant(Proiect).filter(or_(Proiect.cod_proiect.ilike(like),
                                                  Proiect.nume.ilike(like))).limit(6).all():
        out.append({'tip': 'proiect', 'label': f'{p.cod_proiect} · {p.nume}',
                    'cale': 'Proiect', 'url': url_for('proiecte.hub', id=p.id)})

    from models import GanttPlan, Santier
    for pl in query_gantt_plans_for_tenant().filter(GanttPlan.nume.ilike(like)).limit(5).all():
        out.append({'tip': 'plan', 'label': pl.nume, 'cale': 'Plan Gantt',
                    'url': url_for('gantt.plan', id_=pl.id)})

    for a in query_for_tenant(Angajat).filter(or_(Angajat.nume.ilike(like),
                                                  Angajat.prenume.ilike(like))).limit(5).all():
        out.append({'tip': 'angajat', 'label': f'{a.nume} {a.prenume}',
                    'cale': a.functie or 'Angajat', 'url': url_for('angajati.detalii', id=a.id)})

    for s in query_sites_for_tenant().filter(or_(Santier.cod.ilike(like),
                                                 Santier.nume.ilike(like))).limit(5).all():
        out.append({'tip': 'santier', 'label': f'{s.cod} · {s.nume}', 'cale': 'Santier',
                    'url': url_for('bim.santier_detaliu', id=s.id)})

    try:
        from services.feature_flags import is_enabled
        if is_enabled('controale-contract', tenant_id=tid):
            from models import Contract
            for c in query_contracts_for_tenant().filter(Contract.nr_contract.ilike(like)).limit(5).all():
                out.append({'tip': 'contract', 'label': c.nr_contract, 'cale': 'Contract',
                            'url': url_for('contracte.detalii', id=c.id)})
    except Exception:
        pass

    return jsonify(out)


@dashboard_bp.route('/ghid')
@login_required
def ghid():
    """Ghid de utilizator (pentru incepatori, fara termeni tehnici)."""
    return render_template('ghid.html')
