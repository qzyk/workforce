"""
EDIFICO WORKFORCE - Rute Setari Administrative
Firma, Utilizatori CRUD, Sarbatori, Backup, Jurnal activitate, Setari generale
"""

import os
import json
import shutil
import zipfile
import functools
from datetime import datetime, date, timedelta
from io import BytesIO

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify, send_file, current_app, abort
)
from flask_login import login_required, current_user
from models import (
    db, Utilizator, Angajat, Proiect, Pontaj, Document,
    Raport, Concediu, SarbatoareLegala
)

setari_bp = Blueprint('setari', __name__)


# ============================================================
# DECORATORI SECURITATE
# ============================================================

def admin_required(f):
    """Permite accesul doar administratorilor."""
    @functools.wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash('Aceasta sectiune este disponibila doar pentru administratori.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


def manager_or_admin(f):
    """Permite accesul managerilor si administratorilor."""
    @functools.wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_manager:
            flash('Nu aveti permisiunea de a accesa aceasta pagina.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# CONFIG JSON - Setari persistente
# ============================================================

def _get_config_path():
    return os.path.join(current_app.root_path, 'database', 'app_config.json')


def _load_config():
    path = _get_config_path()
    defaults = {
        'firma_nume': 'EDIFICO CONSTRUCT SRL',
        'firma_cui': 'RO12345678',
        'firma_reg_com': 'J40/1234/2020',
        'firma_adresa': 'Bucuresti, Sector 1, Str. Constructorilor nr. 10',
        'firma_telefon': '+40 21 123 4567',
        'firma_email': 'office@edifico-construct.ro',
        'firma_banca': 'Banca Transilvania',
        'firma_iban': 'RO49BTRL00000000000000',
        'firma_reprezentant': 'Popescu Adrian',
        'firma_functie_repr': 'Administrator',
        'ore_lucru_zi': 8,
        'zile_lucru_luna': 21,
        'salariu_minim': 3700,
        'moneda': 'RON',
        'format_data': 'dd.mm.yyyy',
        'backup_auto': True,
        'notificari_email': False,
        'zile_alerta_documente': 30,
        'cleanup_export_zile': 30,
    }
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def _save_config(data):
    path = _get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# JURNAL ACTIVITATE - Helper
# ============================================================

_jurnal_path = None

def _get_jurnal_path():
    return os.path.join(current_app.root_path, 'database', 'jurnal.json')


def log_action(actiune, detalii='', utilizator=None):
    """Inregistreaza o actiune in jurnalul de activitate."""
    path = _get_jurnal_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'utilizator': utilizator or (current_user.get_full_name() if current_user and current_user.is_authenticated else 'System'),
        'utilizator_id': current_user.id if current_user and current_user.is_authenticated else None,
        'actiune': actiune,
        'detalii': detalii,
        'ip': request.remote_addr if request else None
    }

    entries = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
        except Exception:
            entries = []

    entries.insert(0, entry)
    # Pastreaza ultimele 1000 intrari
    entries = entries[:1000]

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def log_action_decorator(actiune_template):
    """Decorator care logheaza automat actiunile."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            result = f(*args, **kwargs)
            try:
                log_action(actiune_template)
            except Exception:
                pass
            return result
        return wrapper
    return decorator


# ============================================================
# RUTA PRINCIPALA SETARI
# ============================================================

@setari_bp.route('/')
@admin_required
def index():
    """Panou principal setari."""
    return redirect(url_for('setari.firma'))


# ============================================================
# SETARI FIRMA
# ============================================================

@setari_bp.route('/firma', methods=['GET', 'POST'])
@admin_required
def firma():
    """Setari date firma / companie."""
    cfg = _load_config()

    if request.method == 'POST':
        for key in ['firma_nume', 'firma_cui', 'firma_reg_com', 'firma_adresa',
                     'firma_telefon', 'firma_email', 'firma_banca', 'firma_iban',
                     'firma_reprezentant', 'firma_functie_repr']:
            cfg[key] = request.form.get(key, '').strip()

        _save_config(cfg)
        log_action('Actualizare date firma', f'Firma: {cfg["firma_nume"]}')
        flash('Datele firmei au fost salvate cu succes!', 'success')
        return redirect(url_for('setari.firma'))

    return render_template('setari/firma.html', config=cfg)


# ============================================================
# GESTIONARE UTILIZATORI
# ============================================================

@setari_bp.route('/utilizatori')
@admin_required
def utilizatori():
    """Lista utilizatori cu filtrare si paginare."""
    page = request.args.get('page', 1, type=int)
    rol_filtru = request.args.get('rol', '')
    cautare = request.args.get('q', '').strip()

    query = Utilizator.query

    if rol_filtru:
        query = query.filter_by(rol=rol_filtru)
    if cautare:
        search = f'%{cautare}%'
        query = query.filter(
            db.or_(
                Utilizator.nume.ilike(search),
                Utilizator.prenume.ilike(search),
                Utilizator.email.ilike(search)
            )
        )

    query = query.order_by(Utilizator.data_creare.desc())
    pagination = query.paginate(page=page, per_page=20, error_out=False)

    stats = {
        'total': Utilizator.query.count(),
        'activi': Utilizator.query.filter_by(activ=True).count(),
        'admini': Utilizator.query.filter_by(rol='admin').count(),
        'manageri': Utilizator.query.filter_by(rol='manager').count(),
        'operatori': Utilizator.query.filter_by(rol='operator').count(),
    }

    return render_template('setari/utilizatori.html',
                           utilizatori=pagination.items,
                           pagination=pagination,
                           stats=stats,
                           rol_filtru=rol_filtru,
                           cautare=cautare)


@setari_bp.route('/utilizatori/adauga', methods=['GET', 'POST'])
@admin_required
def adauga_utilizator():
    """Adaugare utilizator nou."""
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        prenume = request.form.get('prenume', '').strip()
        email = request.form.get('email', '').strip().lower()
        parola = request.form.get('parola', '')
        rol = request.form.get('rol', 'operator')

        errors = []
        if not nume or not prenume:
            errors.append('Numele si prenumele sunt obligatorii.')
        if not email:
            errors.append('Emailul este obligatoriu.')
        elif Utilizator.query.filter_by(email=email).first():
            errors.append('Aceasta adresa de email este deja folosita.')
        if len(parola) < 6:
            errors.append('Parola trebuie sa aiba minim 6 caractere.')
        if rol not in ('admin', 'manager', 'operator'):
            errors.append('Rol invalid.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('setari/utilizator_formular.html',
                                   edit=False, user=None)

        user = Utilizator(
            nume=nume, prenume=prenume, email=email,
            rol=rol, activ=True
        )
        user.set_password(parola)
        db.session.add(user)
        db.session.commit()

        log_action('Adaugare utilizator', f'{user.get_full_name()} ({user.email}) - rol: {user.rol}')
        flash(f'Utilizatorul {user.get_full_name()} a fost creat cu succes!', 'success')
        return redirect(url_for('setari.utilizatori'))

    return render_template('setari/utilizator_formular.html', edit=False, user=None)


@setari_bp.route('/utilizatori/<int:id>/editeaza', methods=['GET', 'POST'])
@admin_required
def editeaza_utilizator(id):
    """Editare utilizator existent."""
    user = Utilizator.query.get_or_404(id)

    if request.method == 'POST':
        user.nume = request.form.get('nume', '').strip()
        user.prenume = request.form.get('prenume', '').strip()
        email_nou = request.form.get('email', '').strip().lower()
        rol = request.form.get('rol', 'operator')

        errors = []
        if not user.nume or not user.prenume:
            errors.append('Numele si prenumele sunt obligatorii.')
        if email_nou != user.email:
            if Utilizator.query.filter_by(email=email_nou).first():
                errors.append('Aceasta adresa de email este deja folosita.')
        if rol not in ('admin', 'manager', 'operator'):
            errors.append('Rol invalid.')

        # Nu permite schimbarea rolului propriului cont
        if user.id == current_user.id and rol != current_user.rol:
            errors.append('Nu puteti schimba propriul rol.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('setari/utilizator_formular.html',
                                   edit=True, user=user)

        user.email = email_nou
        user.rol = rol
        db.session.commit()

        log_action('Editare utilizator', f'{user.get_full_name()} ({user.email})')
        flash('Utilizatorul a fost actualizat!', 'success')
        return redirect(url_for('setari.utilizatori'))

    return render_template('setari/utilizator_formular.html', edit=True, user=user)


@setari_bp.route('/utilizatori/<int:id>/reset-parola', methods=['POST'])
@admin_required
def reset_parola(id):
    """Resetare parola utilizator."""
    user = Utilizator.query.get_or_404(id)
    parola_noua = request.form.get('parola_noua', '')

    if len(parola_noua) < 6:
        flash('Parola trebuie sa aiba minim 6 caractere.', 'danger')
        return redirect(url_for('setari.utilizatori'))

    user.set_password(parola_noua)
    db.session.commit()

    log_action('Reset parola', f'Utilizator: {user.get_full_name()} ({user.email})')
    flash(f'Parola pentru {user.get_full_name()} a fost resetata!', 'success')
    return redirect(url_for('setari.utilizatori'))


@setari_bp.route('/utilizatori/<int:id>/toggle-status', methods=['POST'])
@admin_required
def toggle_utilizator(id):
    """Activare/dezactivare cont utilizator."""
    user = Utilizator.query.get_or_404(id)

    if user.id == current_user.id:
        flash('Nu puteti dezactiva propriul cont!', 'danger')
        return redirect(url_for('setari.utilizatori'))

    user.activ = not user.activ
    db.session.commit()

    status_text = 'activat' if user.activ else 'dezactivat'
    log_action(f'Utilizator {status_text}', f'{user.get_full_name()} ({user.email})')
    flash(f'Contul {user.get_full_name()} a fost {status_text}.', 'success')
    return redirect(url_for('setari.utilizatori'))


# ============================================================
# SARBATORI LEGALE
# ============================================================

SARBATORI_ROMANIA = [
    ('01-01', 'Anul Nou'),
    ('01-02', 'Anul Nou (ziua 2)'),
    ('01-06', 'Boboteaza'),
    ('01-24', 'Ziua Unirii Principatelor'),
    ('05-01', 'Ziua Muncii'),
    ('06-01', 'Ziua Copilului'),
    ('08-15', 'Adormirea Maicii Domnului'),
    ('11-30', 'Sfantul Andrei'),
    ('12-01', 'Ziua Nationala a Romaniei'),
    ('12-25', 'Craciunul'),
    ('12-26', 'Craciunul (ziua 2)'),
]

# Sarbatori mobile ortodoxe (aproximative per an)
PASTE_ORTODOX = {
    2024: ('05-05', '05-06'),
    2025: ('04-20', '04-21'),
    2026: ('04-12', '04-13'),
    2027: ('05-02', '05-03'),
    2028: ('04-16', '04-17'),
}
VINEREA_MARE = {
    2024: '05-03', 2025: '04-18', 2026: '04-10',
    2027: '04-30', 2028: '04-14',
}
RUSALII = {
    2024: ('06-23', '06-24'), 2025: ('06-08', '06-09'),
    2026: ('05-31', '06-01'), 2027: ('06-20', '06-21'),
    2028: ('06-04', '06-05'),
}


@setari_bp.route('/sarbatori')
@admin_required
def sarbatori():
    """Gestionare sarbatori legale."""
    an = request.args.get('an', date.today().year, type=int)
    sarbatori_list = SarbatoareLegala.query.filter_by(an=an).order_by(SarbatoareLegala.data).all()
    ani_disponibili = db.session.query(
        db.distinct(SarbatoareLegala.an)
    ).order_by(SarbatoareLegala.an.desc()).all()
    ani_disponibili = [a[0] for a in ani_disponibili]

    # Adauga anul curent si urmator daca nu exista
    for a in [date.today().year, date.today().year + 1]:
        if a not in ani_disponibili:
            ani_disponibili.append(a)
    ani_disponibili.sort(reverse=True)

    return render_template('setari/sarbatori.html',
                           sarbatori=sarbatori_list,
                           an=an,
                           ani_disponibili=ani_disponibili)


@setari_bp.route('/sarbatori/importa/<int:an>', methods=['POST'])
@admin_required
def importa_sarbatori(an):
    """Importa sarbatorile legale din Romania pentru un an."""
    if an < 2020 or an > 2035:
        flash('An invalid.', 'danger')
        return redirect(url_for('setari.sarbatori', an=an))

    # Sterge sarbatorile existente pentru anul respectiv
    SarbatoareLegala.query.filter_by(an=an).delete()
    db.session.flush()

    count = 0
    added_dates = set()

    def _add_sarbatoare(data_s, denumire):
        nonlocal count
        if data_s in added_dates:
            return  # Evita duplicatele (ex: Rusalii ziua 2 = Ziua Copilului)
        added_dates.add(data_s)
        s = SarbatoareLegala(data=data_s, denumire=denumire, an=an)
        db.session.add(s)
        count += 1

    # Sarbatori fixe
    for md, denumire in SARBATORI_ROMANIA:
        month, day = map(int, md.split('-'))
        try:
            _add_sarbatoare(date(an, month, day), denumire)
        except ValueError:
            pass

    # Vinerea Mare
    if an in VINEREA_MARE:
        md = VINEREA_MARE[an]
        month, day = map(int, md.split('-'))
        _add_sarbatoare(date(an, month, day), 'Vinerea Mare (Ortodoxa)')

    # Paste Ortodox
    if an in PASTE_ORTODOX:
        for i, md in enumerate(PASTE_ORTODOX[an]):
            month, day = map(int, md.split('-'))
            _add_sarbatoare(date(an, month, day),
                           f'Pastele Ortodox{"" if i == 0 else " (ziua 2)"}')

    # Rusalii
    if an in RUSALII:
        for i, md in enumerate(RUSALII[an]):
            month, day = map(int, md.split('-'))
            denumire = f'Rusaliile{"" if i == 0 else " / Ziua Copilului"}' if date(an, month, day) == date(an, 6, 1) else f'Rusaliile{"" if i == 0 else " (ziua 2)"}'
            _add_sarbatoare(date(an, month, day), denumire)

    db.session.commit()
    log_action('Import sarbatori', f'An: {an}, {count} sarbatori importate')
    flash(f'{count} sarbatori legale importate pentru anul {an}!', 'success')
    return redirect(url_for('setari.sarbatori', an=an))


@setari_bp.route('/sarbatori/adauga', methods=['POST'])
@admin_required
def adauga_sarbatoare():
    """Adauga o sarbatoare legala."""
    data_str = request.form.get('data', '')
    denumire = request.form.get('denumire', '').strip()

    if not data_str or not denumire:
        flash('Data si denumirea sunt obligatorii.', 'danger')
        return redirect(url_for('setari.sarbatori'))

    try:
        data_s = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Format data invalid.', 'danger')
        return redirect(url_for('setari.sarbatori'))

    # Verifica unicitate
    exista = SarbatoareLegala.query.filter_by(data=data_s).first()
    if exista:
        flash(f'Exista deja o sarbatoare pe data {data_s.strftime("%d.%m.%Y")}.', 'warning')
        return redirect(url_for('setari.sarbatori', an=data_s.year))

    s = SarbatoareLegala(data=data_s, denumire=denumire, an=data_s.year)
    db.session.add(s)
    db.session.commit()

    log_action('Adaugare sarbatoare', f'{denumire} - {data_s.strftime("%d.%m.%Y")}')
    flash(f'Sarbatoarea "{denumire}" a fost adaugata!', 'success')
    return redirect(url_for('setari.sarbatori', an=data_s.year))


@setari_bp.route('/sarbatori/<int:id>/sterge', methods=['POST'])
@admin_required
def sterge_sarbatoare(id):
    """Sterge o sarbatoare legala."""
    s = SarbatoareLegala.query.get_or_404(id)
    an = s.an
    denumire = s.denumire
    db.session.delete(s)
    db.session.commit()

    log_action('Stergere sarbatoare', f'{denumire}')
    flash(f'Sarbatoarea "{denumire}" a fost stearsa.', 'success')
    return redirect(url_for('setari.sarbatori', an=an))


# ============================================================
# BACKUP & RESTORE
# ============================================================

@setari_bp.route('/backup')
@admin_required
def backup():
    """Pagina backup si restore."""
    backup_dir = os.path.join(current_app.root_path, 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    backups = []
    for f in sorted(os.listdir(backup_dir), reverse=True):
        if f.endswith('.zip'):
            fpath = os.path.join(backup_dir, f)
            size = os.path.getsize(fpath)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            backups.append({
                'fisier': f,
                'dimensiune': size,
                'data': mtime
            })

    # Info DB
    db_path = os.path.join(current_app.root_path, 'database', 'workforce.db')
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0

    # Info uploads
    uploads_dir = current_app.config['UPLOAD_FOLDER']
    uploads_size = 0
    uploads_count = 0
    if os.path.exists(uploads_dir):
        for root, dirs, files in os.walk(uploads_dir):
            for f in files:
                uploads_size += os.path.getsize(os.path.join(root, f))
                uploads_count += 1

    return render_template('setari/backup.html',
                           backups=backups,
                           db_size=db_size,
                           uploads_size=uploads_size,
                           uploads_count=uploads_count)


@setari_bp.route('/backup/creeaza', methods=['POST'])
@admin_required
def creeaza_backup():
    """Creeaza un backup complet (DB + uploads)."""
    backup_dir = os.path.join(current_app.root_path, 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'backup_{timestamp}.zip'
    filepath = os.path.join(backup_dir, filename)

    try:
        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Backup baza de date
            db_path = os.path.join(current_app.root_path, 'database', 'workforce.db')
            if os.path.exists(db_path):
                zf.write(db_path, 'database/workforce.db')

            # Backup config
            cfg_path = _get_config_path()
            if os.path.exists(cfg_path):
                zf.write(cfg_path, 'database/app_config.json')

            # Backup uploads
            uploads_dir = current_app.config['UPLOAD_FOLDER']
            if os.path.exists(uploads_dir):
                for root, dirs, files in os.walk(uploads_dir):
                    for f in files:
                        full_path = os.path.join(root, f)
                        arc_name = os.path.relpath(full_path, current_app.root_path)
                        zf.write(full_path, arc_name)

        size = os.path.getsize(filepath)
        log_action('Creare backup', f'{filename} ({size / (1024*1024):.1f} MB)')
        flash(f'Backup creat cu succes: {filename}', 'success')
    except Exception as e:
        flash(f'Eroare la crearea backup-ului: {str(e)}', 'danger')

    return redirect(url_for('setari.backup'))


@setari_bp.route('/backup/<filename>/descarca')
@admin_required
def descarca_backup(filename):
    """Descarca un fisier backup."""
    if '..' in filename or '/' in filename:
        abort(403)

    backup_dir = os.path.join(current_app.root_path, 'backups')
    filepath = os.path.join(backup_dir, filename)

    if not os.path.exists(filepath):
        flash('Fisierul backup nu a fost gasit.', 'danger')
        return redirect(url_for('setari.backup'))

    log_action('Descarcare backup', filename)
    return send_file(filepath, as_attachment=True, download_name=filename)


@setari_bp.route('/backup/<filename>/sterge', methods=['POST'])
@admin_required
def sterge_backup(filename):
    """Sterge un fisier backup."""
    if '..' in filename or '/' in filename:
        abort(403)

    backup_dir = os.path.join(current_app.root_path, 'backups')
    filepath = os.path.join(backup_dir, filename)

    if os.path.exists(filepath):
        os.remove(filepath)
        log_action('Stergere backup', filename)
        flash(f'Backup-ul {filename} a fost sters.', 'success')
    else:
        flash('Fisierul nu a fost gasit.', 'danger')

    return redirect(url_for('setari.backup'))


# ============================================================
# JURNAL ACTIVITATE
# ============================================================

@setari_bp.route('/jurnal')
@admin_required
def jurnal():
    """Vizualizare jurnal activitate."""
    page = request.args.get('page', 1, type=int)
    cautare = request.args.get('q', '').strip()
    per_page = 30

    path = _get_jurnal_path()
    entries = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
        except Exception:
            entries = []

    # Filtrare
    if cautare:
        search_lower = cautare.lower()
        entries = [e for e in entries if
                   search_lower in e.get('actiune', '').lower() or
                   search_lower in e.get('detalii', '').lower() or
                   search_lower in e.get('utilizator', '').lower()]

    # Paginare manuala
    total = len(entries)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    entries_page = entries[start:start + per_page]

    pagination = {
        'page': page,
        'pages': total_pages,
        'total': total,
        'per_page': per_page,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1,
    }

    return render_template('setari/jurnal.html',
                           entries=entries_page,
                           pagination=pagination,
                           cautare=cautare)


@setari_bp.route('/jurnal/curata', methods=['POST'])
@admin_required
def curata_jurnal():
    """Curata jurnalul de activitate."""
    path = _get_jurnal_path()
    if os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump([], f)
    flash('Jurnalul de activitate a fost curatat.', 'success')
    return redirect(url_for('setari.jurnal'))


# ============================================================
# SETARI GENERALE
# ============================================================

@setari_bp.route('/generale', methods=['GET', 'POST'])
@admin_required
def generale():
    """Setari generale aplicatie."""
    cfg = _load_config()

    if request.method == 'POST':
        cfg['ore_lucru_zi'] = request.form.get('ore_lucru_zi', 8, type=int)
        cfg['zile_lucru_luna'] = request.form.get('zile_lucru_luna', 21, type=int)
        cfg['salariu_minim'] = request.form.get('salariu_minim', 3700, type=int)
        cfg['moneda'] = request.form.get('moneda', 'RON').strip()
        cfg['zile_alerta_documente'] = request.form.get('zile_alerta_documente', 30, type=int)
        cfg['cleanup_export_zile'] = request.form.get('cleanup_export_zile', 30, type=int)
        cfg['backup_auto'] = bool(request.form.get('backup_auto'))
        cfg['notificari_email'] = bool(request.form.get('notificari_email'))

        _save_config(cfg)
        log_action('Actualizare setari generale')
        flash('Setarile generale au fost salvate!', 'success')
        return redirect(url_for('setari.generale'))

    return render_template('setari/generale.html', config=cfg)


# ============================================================
# CURATARE EXPORTURI VECHI
# ============================================================

@setari_bp.route('/curata-exporturi', methods=['POST'])
@admin_required
def curata_exporturi():
    """Sterge fisierele de export mai vechi de X zile."""
    cfg = _load_config()
    zile = cfg.get('cleanup_export_zile', 30)
    cutoff = datetime.now() - timedelta(days=zile)

    export_dir = current_app.config['EXPORT_FOLDER']
    count = 0
    if os.path.exists(export_dir):
        for f in os.listdir(export_dir):
            fpath = os.path.join(export_dir, f)
            if os.path.isfile(fpath):
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if mtime < cutoff:
                    os.remove(fpath)
                    count += 1

    log_action('Curatare exporturi', f'{count} fisiere sterse (mai vechi de {zile} zile)')
    flash(f'{count} fisiere de export vechi au fost sterse.', 'success')
    return redirect(url_for('setari.generale'))


# ============================================================
# INFORMATII SISTEM
# ============================================================

@setari_bp.route('/info-sistem')
@admin_required
def info_sistem():
    """Returneaza informatii sistem ca JSON (AJAX)."""
    db_path = os.path.join(current_app.root_path, 'database', 'workforce.db')
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0

    return jsonify({
        'angajati': Angajat.query.count(),
        'angajati_activi': Angajat.query.filter_by(status='activ').count(),
        'proiecte': Proiect.query.count(),
        'proiecte_active': Proiect.query.filter_by(status='activ').count(),
        'pontaje': Pontaj.query.count(),
        'documente': Document.query.count(),
        'utilizatori': Utilizator.query.count(),
        'rapoarte': Raport.query.count(),
        'db_size': db_size,
    })


@setari_bp.route('/module')
@admin_required
def module():
    """Activare/dezactivare functii (feature flags) din UI, nu din REPL."""
    from collections import OrderedDict
    from services import feature_flags as ff
    tid = getattr(current_user, 'tenant_id', None)
    etichete = {'bim': 'BIM', 'controale': 'Contract Controls', 'planificare': 'Planificare Gantt'}
    grupuri = OrderedDict()
    for key, desc in sorted(ff.KNOWN_FLAGS.items()):
        grup = key.split('-')[0]
        grupuri.setdefault(etichete.get(grup, grup.title()), []).append({
            'key': key, 'descriere': desc, 'activ': ff.is_enabled(key, tid),
        })
    return render_template('setari/module.html', grupuri=grupuri)


@setari_bp.route('/module/toggle', methods=['POST'])
@admin_required
def module_toggle():
    from services import feature_flags as ff
    key = request.form.get('key')
    if key in ff.KNOWN_FLAGS:
        tid = getattr(current_user, 'tenant_id', None)
        nou = not ff.is_enabled(key, tid)
        ff.set_flag(key, nou, tenant_id=tid)
        log_action('toggle_flag', f'{key}={nou}')
        flash(f'Functia "{key}" a fost {"activata" if nou else "dezactivata"}.', 'success')
    else:
        flash('Functie necunoscuta.', 'warning')
    return redirect(url_for('setari.module'))
