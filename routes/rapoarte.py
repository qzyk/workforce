"""
EDIFICO WORKFORCE - Modul Rapoarte (Complet)
Generare rapoarte Excel/PDF: foaie prezenta, stat plata, situatie proiect, centralizator,
documente, pontaj individual, prezenta zilnica, SSM.
"""

import os
import io
import json
import hashlib
from datetime import datetime, date, timedelta
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    current_app, send_file, jsonify
)
from flask_login import login_required, current_user
from models import db, Raport, Pontaj, Angajat, Proiect, Document

rapoarte_bp = Blueprint('rapoarte', __name__)


# ============================================================
# HELPERS
# ============================================================

TIPURI_RAPOARTE = {
    'foaie_prezenta': 'Foaie Colectiva de Prezenta',
    'stat_plata': 'Stat de Plata',
    'situatie_proiect': 'Situatie Proiect',
    'centralizator_ore': 'Centralizator Ore Lunare',
    'documente_expirate': 'Raport Documente',
    'pontaj_individual': 'Pontaj Individual',
    'prezenta_zilnica': 'Prezenta Zilnica',
    'raport_ssm': 'Raport SSM',
}


def _tenant_curent():
    """Tenant-ul utilizatorului curent (None = global). Coloana nullable pe
    Utilizator (multi-tenant ready); cu un singur tenant ramane None peste tot."""
    return getattr(current_user, 'tenant_id', None)


def _save_raport(tip, titlu, filepath, format_raport, parametri=None):
    """Salveaza raportul in istoric.

    Faza 3: pe langa fisier_path (backward compat) salveaza si continut_blob +
    checksum (sha256) ca descarcarea sa mearga si dupa ce path-ul de pe disc
    devine orfan (redeploy PA), plus tenant_id pentru izolare (NULL = global).
    Blob-ul e best-effort: daca citirea fisierului esueaza, raportul tot se
    salveaza (doar path-based, ca inainte).
    """
    continut_blob = None
    checksum = None
    dimensiune = 0
    try:
        if filepath and os.path.exists(filepath):
            with open(filepath, 'rb') as fh:
                continut_blob = fh.read()
            dimensiune = len(continut_blob)
            checksum = hashlib.sha256(continut_blob).hexdigest()
    except OSError:
        continut_blob = None
        checksum = None

    raport = Raport(
        tip_raport=tip,
        titlu=titlu,
        parametri=json.dumps(parametri) if parametri else None,
        fisier_path=filepath,
        format=format_raport,
        generat_de=current_user.id,
        dimensiune_fisier=dimensiune,
        tenant_id=_tenant_curent(),
        continut_blob=continut_blob,
        checksum=checksum,
    )
    db.session.add(raport)
    db.session.commit()
    return raport


def _get_export_path(filename):
    """Returneaza calea completa pentru export."""
    export_dir = current_app.config.get('EXPORT_FOLDER', os.path.join(current_app.root_path, 'exports'))
    os.makedirs(export_dir, exist_ok=True)
    return os.path.join(export_dir, filename)


def _month_name(luna):
    names = ['', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
             'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']
    return names[luna] if 1 <= luna <= 12 else str(luna)


def _mimetype_pentru(ext):
    """MIME pentru descarcarea din blob/regenerare (send_file din BytesIO nu il
    deduce singur)."""
    return {
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'pdf': 'application/pdf',
    }.get((ext or 'xlsx').lower(), 'application/octet-stream')


def _regenereaza_xlsx(tip, parametri):
    """Regenereaza un raport XLSX din parametrii salvati (fallback descarcare
    cand path-ul de pe disc lipseste SI nu exista blob in DB).

    Returneaza bytes sau None daca tipul nu suporta regenerare deterministica
    sau parametrii sunt insuficienti. Doar tipurile derivate pur din DB se pot
    regenera; PDF-urile NU se regenereaza aici (cad pe mesajul de 404 clasic).
    """
    if not parametri:
        return None
    try:
        from rapoarte import excel_generator as eg
    except ImportError:
        return None

    try:
        if tip == 'foaie_prezenta':
            wb = eg.generate_foaie_prezenta(
                parametri['proiect_id'], parametri['luna'], parametri['an'])
        elif tip == 'stat_plata':
            wb = eg.generate_stat_plata(
                parametri.get('proiect_id'), parametri['luna'], parametri['an'])
        elif tip == 'centralizator_ore':
            wb = eg.generate_centralizator_ore(
                parametri['luna'], parametri['an'],
                parametri.get('grupare', 'angajat'))
        elif tip == 'situatie_proiect':
            ds = datetime.strptime(parametri['data_start'], '%Y-%m-%d').date() \
                if parametri.get('data_start') else None
            dsf = datetime.strptime(parametri['data_sfarsit'], '%Y-%m-%d').date() \
                if parametri.get('data_sfarsit') else None
            wb = eg.generate_situatie_proiect(parametri['proiect_id'], ds, dsf)
        elif tip == 'documente_expirate':
            wb = eg.generate_raport_documente(
                parametri.get('tip_raport', 'toate'), parametri.get('functie'))
        elif tip == 'pontaj_individual':
            ds = datetime.strptime(parametri['data_start'], '%Y-%m-%d').date()
            dsf = datetime.strptime(parametri['data_sfarsit'], '%Y-%m-%d').date()
            wb = eg.generate_pontaj_individual(parametri['angajat_id'], ds, dsf)
        elif tip == 'prezenta_zilnica':
            dz = datetime.strptime(parametri['data'], '%Y-%m-%d').date()
            wb = eg.generate_prezenta_zilnica(dz, parametri.get('proiect_id'))
        elif tip == 'raport_ssm':
            wb = eg.generate_raport_ssm(
                parametri.get('tip_document'), parametri.get('status'))
        else:
            return None
    except (KeyError, ValueError, TypeError):
        return None

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============================================================
# 1. PANOU RAPOARTE (Dashboard)
# ============================================================

@rapoarte_bp.route('/')
@login_required
def panou():
    proiecte = Proiect.query.filter(
        Proiect.status.in_(['activ', 'planificat'])
    ).order_by(Proiect.cod_proiect).all()

    angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()

    # Ultimele 5 rapoarte (izolate pe tenant; NULL = global = comportament actual)
    tid = _tenant_curent()
    recente = (Raport.query
               .filter(db.or_(Raport.tenant_id == tid, Raport.tenant_id.is_(None)))
               .order_by(Raport.data_generare.desc())
               .limit(5).all())

    return render_template('rapoarte/panou.html',
                           proiecte=proiecte,
                           angajati=angajati,
                           recente=recente,
                           tipuri_rapoarte=TIPURI_RAPOARTE,
                           today=date.today())


# ============================================================
# 2. FOAIE COLECTIVA DE PREZENTA
# ============================================================

@rapoarte_bp.route('/foaie-prezenta', methods=['POST'])
@login_required
def foaie_prezenta():
    proiect_id = request.form.get('proiect_id', type=int)
    luna = request.form.get('luna', date.today().month, type=int)
    an = request.form.get('an', date.today().year, type=int)
    include_supl = request.form.get('include_supl') == 'on'
    format_raport = request.form.get('format', 'xlsx')

    if not proiect_id:
        flash('Selectati un proiect!', 'danger')
        return redirect(url_for('rapoarte.panou'))

    proiect = Proiect.query.get(proiect_id)
    titlu = f'Foaie Prezenta {proiect.cod_proiect} {_month_name(luna)} {an}'

    try:
        if format_raport == 'pdf':
            try:
                from rapoarte.pdf_generator import generate_pdf_foaie_prezenta
                filepath, filename = generate_pdf_foaie_prezenta(proiect_id, luna, an)
                _save_raport('foaie_prezenta', titlu, filepath, 'pdf',
                             {'proiect_id': proiect_id, 'luna': luna, 'an': an})
                flash(f'Foaia de prezenta PDF a fost generata!', 'success')
                return send_file(filepath, as_attachment=True, download_name=filename)
            except ImportError:
                flash('ReportLab nu este instalat. Se genereaza Excel.', 'warning')
                format_raport = 'xlsx'

        # Excel
        from rapoarte.excel_generator import generate_foaie_prezenta
        wb = generate_foaie_prezenta(proiect_id, luna, an, include_supl)
        filename = f'foaie_prezenta_{proiect.cod_proiect}_{luna:02d}_{an}.xlsx'
        filepath = _get_export_path(filename)
        wb.save(filepath)
        _save_raport('foaie_prezenta', titlu, filepath, 'xlsx',
                     {'proiect_id': proiect_id, 'luna': luna, 'an': an})
        flash(f'Foaia de prezenta a fost generata!', 'success')
        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        flash(f'Eroare la generare: {str(e)}', 'danger')
        return redirect(url_for('rapoarte.panou'))


# ============================================================
# 3. STAT DE PLATA
# ============================================================

@rapoarte_bp.route('/stat-plata', methods=['POST'])
@login_required
def stat_plata():
    proiect_id = request.form.get('proiect_id', type=int) or None
    luna = request.form.get('luna', date.today().month, type=int)
    an = request.form.get('an', date.today().year, type=int)
    format_raport = request.form.get('format', 'xlsx')

    titlu = f'Stat Plata {_month_name(luna)} {an}'
    if proiect_id:
        proiect = Proiect.query.get(proiect_id)
        if proiect:
            titlu += f' - {proiect.cod_proiect}'

    try:
        if format_raport == 'pdf':
            try:
                from rapoarte.pdf_generator import generate_pdf_stat_plata
                filepath, filename = generate_pdf_stat_plata(proiect_id, luna, an)
                _save_raport('stat_plata', titlu, filepath, 'pdf',
                             {'proiect_id': proiect_id, 'luna': luna, 'an': an})
                flash('Statul de plata PDF a fost generat!', 'success')
                return send_file(filepath, as_attachment=True, download_name=filename)
            except ImportError:
                flash('ReportLab nu este instalat. Se genereaza Excel.', 'warning')

        from rapoarte.excel_generator import generate_stat_plata
        wb = generate_stat_plata(proiect_id, luna, an)
        label = f'{proiect_id or "toti"}_{luna:02d}_{an}'
        filename = f'stat_plata_{label}.xlsx'
        filepath = _get_export_path(filename)
        wb.save(filepath)
        _save_raport('stat_plata', titlu, filepath, 'xlsx',
                     {'proiect_id': proiect_id, 'luna': luna, 'an': an})
        flash('Statul de plata a fost generat!', 'success')
        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        flash(f'Eroare la generare: {str(e)}', 'danger')
        return redirect(url_for('rapoarte.panou'))


# ============================================================
# 4. SITUATIE PROIECT
# ============================================================

@rapoarte_bp.route('/situatie-proiect', methods=['POST'])
@login_required
def situatie_proiect():
    proiect_id = request.form.get('proiect_id', type=int)
    nivel = request.form.get('nivel', 'detaliat')
    data_start = request.form.get('data_start')
    data_sfarsit = request.form.get('data_sfarsit')
    format_raport = request.form.get('format', 'xlsx')

    if not proiect_id:
        flash('Selectati un proiect!', 'danger')
        return redirect(url_for('rapoarte.panou'))

    proiect = Proiect.query.get(proiect_id)
    ds = datetime.strptime(data_start, '%Y-%m-%d').date() if data_start else proiect.data_start
    dsf = datetime.strptime(data_sfarsit, '%Y-%m-%d').date() if data_sfarsit else date.today()

    titlu = f'Situatie {proiect.cod_proiect}'

    try:
        from rapoarte.excel_generator import generate_situatie_proiect
        wb = generate_situatie_proiect(proiect_id, ds, dsf, nivel)
        filename = f'situatie_{proiect.cod_proiect}_{datetime.now().strftime("%Y%m%d")}.xlsx'
        filepath = _get_export_path(filename)
        wb.save(filepath)
        _save_raport('situatie_proiect', titlu, filepath, 'xlsx',
                     {'proiect_id': proiect_id, 'data_start': str(ds), 'data_sfarsit': str(dsf)})
        flash('Situatia proiectului a fost generata!', 'success')
        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        flash(f'Eroare la generare: {str(e)}', 'danger')
        return redirect(url_for('rapoarte.panou'))


# ============================================================
# 5. CENTRALIZATOR ORE LUNARE
# ============================================================

@rapoarte_bp.route('/centralizator-ore', methods=['POST'])
@login_required
def centralizator_ore():
    luna = request.form.get('luna', date.today().month, type=int)
    an = request.form.get('an', date.today().year, type=int)
    grupare = request.form.get('grupare', 'angajat')

    titlu = f'Centralizator Ore {_month_name(luna)} {an}'

    try:
        from rapoarte.excel_generator import generate_centralizator_ore
        wb = generate_centralizator_ore(luna, an, grupare)
        filename = f'centralizator_{luna:02d}_{an}_{grupare}.xlsx'
        filepath = _get_export_path(filename)
        wb.save(filepath)
        _save_raport('centralizator_ore', titlu, filepath, 'xlsx',
                     {'luna': luna, 'an': an, 'grupare': grupare})
        flash('Centralizatorul de ore a fost generat!', 'success')
        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        flash(f'Eroare la generare: {str(e)}', 'danger')
        return redirect(url_for('rapoarte.panou'))


# ============================================================
# 6. RAPORT DOCUMENTE
# ============================================================

@rapoarte_bp.route('/documente-expirate', methods=['POST'])
@login_required
def documente_expirate():
    tip_raport = request.form.get('tip_raport', 'toate')
    functie_filter = request.form.get('functie', '') or None
    format_raport = request.form.get('format', 'xlsx')

    titlu = f'Raport Documente - {tip_raport}'

    try:
        from rapoarte.excel_generator import generate_raport_documente
        wb = generate_raport_documente(tip_raport, functie_filter)
        filename = f'raport_documente_{tip_raport}_{datetime.now().strftime("%Y%m%d")}.xlsx'
        filepath = _get_export_path(filename)
        wb.save(filepath)
        _save_raport('documente_expirate', titlu, filepath, 'xlsx',
                     {'tip_raport': tip_raport, 'functie': functie_filter})
        flash('Raportul de documente a fost generat!', 'success')
        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        flash(f'Eroare la generare: {str(e)}', 'danger')
        return redirect(url_for('rapoarte.panou'))


# ============================================================
# 7. PONTAJ INDIVIDUAL
# ============================================================

@rapoarte_bp.route('/pontaj-individual', methods=['POST'])
@login_required
def pontaj_individual():
    angajat_id = request.form.get('angajat_id', type=int)
    data_start = request.form.get('data_start')
    data_sfarsit = request.form.get('data_sfarsit')
    format_raport = request.form.get('format', 'xlsx')

    if not angajat_id:
        flash('Selectati un angajat!', 'danger')
        return redirect(url_for('rapoarte.panou'))

    angajat = Angajat.query.get(angajat_id)
    ds = datetime.strptime(data_start, '%Y-%m-%d').date() if data_start else date.today().replace(day=1)
    dsf = datetime.strptime(data_sfarsit, '%Y-%m-%d').date() if data_sfarsit else date.today()

    titlu = f'Pontaj {angajat.nume_complet} {ds.strftime("%d.%m")}-{dsf.strftime("%d.%m.%Y")}'

    try:
        if format_raport == 'pdf':
            try:
                from rapoarte.pdf_generator import generate_pdf_pontaj_individual
                filepath, filename = generate_pdf_pontaj_individual(angajat_id, ds, dsf)
                _save_raport('pontaj_individual', titlu, filepath, 'pdf',
                             {'angajat_id': angajat_id, 'data_start': str(ds), 'data_sfarsit': str(dsf)})
                flash('Pontajul individual PDF a fost generat!', 'success')
                return send_file(filepath, as_attachment=True, download_name=filename)
            except ImportError:
                flash('ReportLab nu este instalat. Se genereaza Excel.', 'warning')

        from rapoarte.excel_generator import generate_pontaj_individual
        wb = generate_pontaj_individual(angajat_id, ds, dsf)
        filename = f'pontaj_{angajat.nume}_{angajat.prenume}_{ds.strftime("%Y%m%d")}.xlsx'
        filepath = _get_export_path(filename)
        wb.save(filepath)
        _save_raport('pontaj_individual', titlu, filepath, 'xlsx',
                     {'angajat_id': angajat_id, 'data_start': str(ds), 'data_sfarsit': str(dsf)})
        flash('Pontajul individual a fost generat!', 'success')
        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        flash(f'Eroare la generare: {str(e)}', 'danger')
        return redirect(url_for('rapoarte.panou'))


# ============================================================
# 8. PREZENTA ZILNICA
# ============================================================

@rapoarte_bp.route('/prezenta-zilnica', methods=['POST'])
@login_required
def prezenta_zilnica():
    data_zi_str = request.form.get('data_zi')
    proiect_id = request.form.get('proiect_id', type=int) or None
    format_raport = request.form.get('format', 'xlsx')

    if not data_zi_str:
        flash('Selectati o data!', 'danger')
        return redirect(url_for('rapoarte.panou'))

    data_zi = datetime.strptime(data_zi_str, '%Y-%m-%d').date()
    titlu = f'Prezenta {data_zi.strftime("%d.%m.%Y")}'

    try:
        from rapoarte.excel_generator import generate_prezenta_zilnica
        wb = generate_prezenta_zilnica(data_zi, proiect_id)
        filename = f'prezenta_{data_zi.strftime("%Y%m%d")}.xlsx'
        filepath = _get_export_path(filename)
        wb.save(filepath)
        _save_raport('prezenta_zilnica', titlu, filepath, 'xlsx',
                     {'data': str(data_zi), 'proiect_id': proiect_id})
        flash('Raportul de prezenta zilnica a fost generat!', 'success')
        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        flash(f'Eroare la generare: {str(e)}', 'danger')
        return redirect(url_for('rapoarte.panou'))


# ============================================================
# 9. RAPORT SSM
# ============================================================

@rapoarte_bp.route('/raport-ssm', methods=['POST'])
@login_required
def raport_ssm():
    tip_document = request.form.get('tip_document', '') or None
    status_filter = request.form.get('status_ssm', '') or None
    format_raport = request.form.get('format', 'xlsx')

    titlu = f'Raport SSM {datetime.now().strftime("%d.%m.%Y")}'

    try:
        from rapoarte.excel_generator import generate_raport_ssm
        wb = generate_raport_ssm(tip_document, status_filter)
        filename = f'raport_ssm_{datetime.now().strftime("%Y%m%d")}.xlsx'
        filepath = _get_export_path(filename)
        wb.save(filepath)
        _save_raport('raport_ssm', titlu, filepath, 'xlsx',
                     {'tip_document': tip_document, 'status': status_filter})
        flash('Raportul SSM a fost generat!', 'success')
        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        flash(f'Eroare la generare: {str(e)}', 'danger')
        return redirect(url_for('rapoarte.panou'))


# ============================================================
# 10. ISTORIC RAPOARTE
# ============================================================

@rapoarte_bp.route('/istoric')
@login_required
def istoric():
    tip_filtru = request.args.get('tip', '')
    page = request.args.get('page', 1, type=int)

    query = Raport.query
    if tip_filtru:
        query = query.filter_by(tip_raport=tip_filtru)
    # Izolare tenant: rapoartele tenant-ului curent + cele globale (tenant_id NULL,
    # comportament actual / rapoarte vechi). Cu un singur tenant, tid=None -> doar NULL.
    tid = _tenant_curent()
    query = query.filter(db.or_(Raport.tenant_id == tid, Raport.tenant_id.is_(None)))

    pagination = query.order_by(Raport.data_generare.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template('rapoarte/istoric.html',
                           rapoarte=pagination.items,
                           pagination=pagination,
                           tip_filtru=tip_filtru,
                           tipuri_rapoarte=TIPURI_RAPOARTE)


# ============================================================
# 11. DESCARCARE RAPORT DIN ISTORIC
# ============================================================

@rapoarte_bp.route('/descarca/<int:id>')
@login_required
def descarca(id):
    raport = Raport.query.get_or_404(id)

    # Izolare tenant: un raport al altui tenant nu e accesibil. NULL = global
    # = vizibil pentru toti (comportament actual, rapoarte vechi fara tenant).
    tid = _tenant_curent()
    if raport.tenant_id is not None and raport.tenant_id != tid:
        flash('Raportul nu a fost gasit.', 'danger')
        return redirect(url_for('rapoarte.istoric'))

    ext = raport.format or 'xlsx'
    download_name = f'{raport.titlu}.{ext}'.replace(' ', '_')

    # 1. Fisier pe disc (cale rapida, backward compat).
    if raport.fisier_path and os.path.exists(raport.fisier_path):
        return send_file(raport.fisier_path, as_attachment=True,
                         download_name=download_name)

    # 2. Path lipsa de pe disc (orfan dupa redeploy PA) dar avem copia in DB.
    if raport.continut_blob:
        return send_file(
            io.BytesIO(raport.continut_blob),
            as_attachment=True, download_name=download_name,
            mimetype=_mimetype_pentru(ext))

    # 3. Nici path, nici blob -> incearca regenerarea din parametri (doar XLSX).
    parametri = json.loads(raport.parametri) if raport.parametri else None
    if (raport.format or 'xlsx') != 'pdf':
        continut = _regenereaza_xlsx(raport.tip_raport, parametri)
        if continut:
            return send_file(
                io.BytesIO(continut),
                as_attachment=True, download_name=download_name,
                mimetype=_mimetype_pentru('xlsx'))

    flash('Fisierul raportului nu a fost gasit pe server!', 'danger')
    return redirect(url_for('rapoarte.istoric'))


# ============================================================
# 12. STERGERE RAPORT DIN ISTORIC
# ============================================================

@rapoarte_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    if not current_user.is_manager:
        flash('Nu aveti permisiunea de a sterge rapoarte.', 'danger')
        return redirect(url_for('rapoarte.istoric'))

    raport = Raport.query.get_or_404(id)
    # Izolare tenant: nu permite stergerea unui raport al altui tenant.
    tid = _tenant_curent()
    if raport.tenant_id is not None and raport.tenant_id != tid:
        flash('Raportul nu a fost gasit.', 'danger')
        return redirect(url_for('rapoarte.istoric'))
    if raport.fisier_path and os.path.exists(raport.fisier_path):
        os.remove(raport.fisier_path)
    db.session.delete(raport)
    db.session.commit()
    flash('Raportul a fost sters din istoric.', 'warning')
    return redirect(url_for('rapoarte.istoric'))
