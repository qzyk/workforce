"""
EDIFICO WORKFORCE - Rute autentificare
Login, logout, profil, schimbare parola
Cu rate limiting, role_required decorator, remember me
"""

import functools
from datetime import datetime, timedelta
from collections import defaultdict

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Utilizator

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# ============================================================
# RATE LIMITING - Protectie brute force
# ============================================================
_login_attempts = defaultdict(list)  # {ip_or_email: [timestamp, ...]}
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _is_locked_out(key):
    """Verifica daca un IP/email este blocat dupa prea multe incercari."""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
    # Curata incercarile vechi
    _login_attempts[key] = [t for t in _login_attempts[key] if t > cutoff]
    return len(_login_attempts[key]) >= MAX_ATTEMPTS


def _record_failed_attempt(key):
    """Inregistreaza o tentativa esuata de login."""
    _login_attempts[key].append(datetime.utcnow())


def _clear_attempts(key):
    """Sterge incercarile dupa un login reusit."""
    _login_attempts.pop(key, None)


def _get_lockout_remaining(key):
    """Returneaza minutele ramase pana la deblocare."""
    if not _login_attempts.get(key):
        return 0
    oldest_in_window = min(_login_attempts[key])
    unlock_time = oldest_in_window + timedelta(minutes=LOCKOUT_MINUTES)
    remaining = (unlock_time - datetime.utcnow()).total_seconds() / 60
    return max(0, int(remaining) + 1)


# ============================================================
# DECORATOR - Restrictie pe rol
# ============================================================
def role_required(*roluri):
    """
    Decorator care restrictioneaza accesul la o ruta doar pentru anumite roluri.
    Utilizare: @role_required('admin', 'manager')
    """
    def decorator(f):
        @functools.wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.rol not in roluri:
                flash('Nu aveti permisiunea de a accesa aceasta pagina.', 'danger')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============================================================
# RUTE AUTENTIFICARE
# ============================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Pagina de autentificare cu protectie brute force."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        parola = request.form.get('parola', '')
        remember = bool(request.form.get('remember'))
        client_ip = request.remote_addr

        # Verificare lockout pe IP si email
        if _is_locked_out(client_ip):
            mins = _get_lockout_remaining(client_ip)
            flash(f'Prea multe incercari esuate. Contul este blocat pentru inca {mins} minute.', 'danger')
            return render_template('auth/login.html', email=email, locked=True, lockout_minutes=mins)

        if _is_locked_out(email):
            mins = _get_lockout_remaining(email)
            flash(f'Prea multe incercari esuate pentru acest email. Asteptati {mins} minute.', 'danger')
            return render_template('auth/login.html', email=email, locked=True, lockout_minutes=mins)

        # Validare input
        if not email or not parola:
            flash('Va rugam completati ambele campuri.', 'warning')
            return render_template('auth/login.html', email=email)

        # Cautare utilizator
        user = Utilizator.query.filter_by(email=email).first()

        if user and user.check_password(parola):
            # Verificare cont activ
            if not user.activ:
                flash('Contul dumneavoastra este dezactivat. Contactati administratorul.', 'danger')
                return render_template('auth/login.html', email=email)

            # Login reusit
            _clear_attempts(client_ip)
            _clear_attempts(email)

            login_user(user, remember=remember, duration=timedelta(days=30) if remember else None)
            user.ultima_conectare = datetime.utcnow()
            db.session.commit()

            flash(f'Bine ati venit, {user.get_full_name()}!', 'success')
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))
        else:
            # Login esuat
            _record_failed_attempt(client_ip)
            _record_failed_attempt(email)
            remaining = MAX_ATTEMPTS - len(_login_attempts.get(client_ip, []))

            if remaining > 0:
                flash(f'Email sau parola incorecta. Mai aveti {remaining} incercari.', 'danger')
            else:
                mins = LOCKOUT_MINUTES
                flash(f'Prea multe incercari esuate. Contul este blocat pentru {mins} minute.', 'danger')

            return render_template('auth/login.html', email=email)

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Deconectare utilizator si redirect la login."""
    logout_user()
    flash('Ati fost deconectat cu succes.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profil', methods=['GET', 'POST'])
@login_required
def profil():
    """Vizualizare si editare profil utilizator curent."""
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        prenume = request.form.get('prenume', '').strip()
        email_nou = request.form.get('email', '').strip().lower()

        if not nume or not prenume:
            flash('Numele si prenumele sunt obligatorii.', 'danger')
            return render_template('auth/profil.html')

        # Verificare email unic daca s-a schimbat
        if email_nou != current_user.email:
            exista = Utilizator.query.filter_by(email=email_nou).first()
            if exista:
                flash('Aceasta adresa de email este deja folosita.', 'danger')
                return render_template('auth/profil.html')

        current_user.nume = nume
        current_user.prenume = prenume
        current_user.email = email_nou
        db.session.commit()
        flash('Profilul a fost actualizat cu succes!', 'success')
        return redirect(url_for('auth.profil'))

    return render_template('auth/profil.html')


@auth_bp.route('/schimba-parola', methods=['GET', 'POST'])
@login_required
def schimba_parola():
    """Schimbare parola cu validare completa."""
    if request.method == 'POST':
        parola_veche = request.form.get('parola_veche', '')
        parola_noua = request.form.get('parola_noua', '')
        confirma = request.form.get('confirma_parola', '')

        errors = []
        if not current_user.check_password(parola_veche):
            errors.append('Parola actuala este incorecta.')
        if len(parola_noua) < 6:
            errors.append('Parola noua trebuie sa aiba minim 6 caractere.')
        if parola_noua != confirma:
            errors.append('Parolele noi nu corespund.')
        if parola_veche == parola_noua:
            errors.append('Parola noua trebuie sa fie diferita de cea actuala.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('auth/schimba_parola.html')

        current_user.set_password(parola_noua)
        db.session.commit()
        flash('Parola a fost schimbata cu succes!', 'success')
        return redirect(url_for('auth.profil'))

    return render_template('auth/schimba_parola.html')
