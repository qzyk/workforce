"""
Sistem minim de internationalizare (i18n) - dictionar Python + helper Jinja.

Nu folosim Flask-Babel pentru ca:
1. Vrem zero dependinte noi
2. Avem doar 2 limbi: RO (default) si EN
3. Stringurile sunt cele din UI BIM si workforce, nu URL-uri

Utilizare in template:
    {{ _('Salveaza') }}                    -> 'Salveaza' (RO) sau 'Save' (EN)
    {{ _('elemente_count', n=5) }}         -> '5 elemente' / '5 elements'

Utilizare in cod Python:
    from i18n import t
    msg = t('Activitate creata', 'en')     -> 'Activity created'

Limba selectata e citita din:
1. session['lang']
2. current_user.limba
3. accept-language header
4. fallback: 'ro'
"""

from flask import session, request
from flask_login import current_user

# Dictionar central de traduceri
TRANSLATIONS = {
    # === Navigare ===
    'Dashboard': {'en': 'Dashboard'},
    'Angajati': {'en': 'Employees'},
    'Proiecte': {'en': 'Projects'},
    'Pontaje': {'en': 'Timesheets'},
    'Activitati': {'en': 'Activities'},
    'Documente': {'en': 'Documents'},
    'Rapoarte': {'en': 'Reports'},
    'Setari': {'en': 'Settings'},
    'Masini': {'en': 'Vehicles'},
    'BIM': {'en': 'BIM'},
    'Profil': {'en': 'Profile'},
    'Deconectare': {'en': 'Logout'},

    # === BIM Navigation ===
    'Santiere': {'en': 'Sites'},
    'Santier': {'en': 'Site'},
    'Santier nou': {'en': 'New site'},
    'Cladiri': {'en': 'Buildings'},
    'Cladire': {'en': 'Building'},
    'Niveluri': {'en': 'Levels'},
    'Nivel': {'en': 'Level'},
    'Spatii': {'en': 'Spaces'},
    'Spatiu': {'en': 'Space'},
    'Zone': {'en': 'Zones'},
    'Zona': {'en': 'Zone'},
    'Elemente': {'en': 'Elements'},
    'Element': {'en': 'Element'},
    'Issues': {'en': 'Issues'},
    'Issue': {'en': 'Issue'},
    'Asset': {'en': 'Asset'},
    'Assets': {'en': 'Assets'},
    'Tree': {'en': 'Tree'},
    'Import IFC': {'en': 'Import IFC'},
    'Export BCF': {'en': 'Export BCF'},
    'Viewer 3D': {'en': '3D Viewer'},

    # === Actiuni comune ===
    'Salveaza': {'en': 'Save'},
    'Anuleaza': {'en': 'Cancel'},
    'Editeaza': {'en': 'Edit'},
    'Sterge': {'en': 'Delete'},
    'Adauga': {'en': 'Add'},
    'Filtreaza': {'en': 'Filter'},
    'Reset': {'en': 'Reset'},
    'Cauta': {'en': 'Search'},
    'Detalii': {'en': 'Details'},
    'Inapoi': {'en': 'Back'},
    'Confirma': {'en': 'Confirm'},
    'Trimite': {'en': 'Submit'},
    'Reincarca': {'en': 'Reload'},
    'Descarca': {'en': 'Download'},
    'Genereaza': {'en': 'Generate'},
    'Toate': {'en': 'All'},
    'Niciunul': {'en': 'None'},

    # === Status comun ===
    'Activ': {'en': 'Active'},
    'Inactiv': {'en': 'Inactive'},
    'Suspendat': {'en': 'Suspended'},
    'Finalizat': {'en': 'Completed'},
    'In lucru': {'en': 'In progress'},
    'Deschis': {'en': 'Open'},
    'Inchis': {'en': 'Closed'},
    'Aprobat': {'en': 'Approved'},
    'Respins': {'en': 'Rejected'},
    'Draft': {'en': 'Draft'},
    'Trimis': {'en': 'Submitted'},

    # === Form labels ===
    'Cod': {'en': 'Code'},
    'Nume': {'en': 'Name'},
    'Descriere': {'en': 'Description'},
    'Adresa': {'en': 'Address'},
    'Data': {'en': 'Date'},
    'Status': {'en': 'Status'},
    'Tip': {'en': 'Type'},
    'Email': {'en': 'Email'},
    'Parola': {'en': 'Password'},
    'Rol': {'en': 'Role'},
    'Limba': {'en': 'Language'},
    'Romana': {'en': 'Romanian'},
    'Engleza': {'en': 'English'},

    # === Mesaje sistem ===
    'Salvat cu succes.': {'en': 'Saved successfully.'},
    'Sters cu succes.': {'en': 'Deleted successfully.'},
    'Eroare la salvare': {'en': 'Save error'},
    'Acces interzis.': {'en': 'Access denied.'},
    'Nu sunteti autentificat.': {'en': 'You are not authenticated.'},

    # === BIM specific ===
    'Generare Raport INNOVA': {'en': 'Generate INNOVA Report'},
    'Selecteaza toti': {'en': 'Select all'},
    'Deselecteaza': {'en': 'Deselect all'},
    'Tine apasat Ctrl pentru selectie multipla': {'en': 'Hold Ctrl for multi-select'},
    'Niciun santier inca.': {'en': 'No sites yet.'},
    'Adauga primul santier': {'en': 'Add first site'},
    'Building Information Modeling': {'en': 'Building Information Modeling'},
    'Issues deschise': {'en': 'Open issues'},
    'Arbore santiere': {'en': 'Site tree'},
}


SUPPORTED_LANGS = ['ro', 'en']
DEFAULT_LANG = 'ro'


def get_current_lang():
    """Determina limba curenta cu fallback in cascada."""
    # 1. session
    if 'lang' in session and session['lang'] in SUPPORTED_LANGS:
        return session['lang']
    # 2. user.limba
    try:
        if current_user.is_authenticated and getattr(current_user, 'limba', None) in SUPPORTED_LANGS:
            return current_user.limba
    except Exception:
        pass
    # 3. Accept-Language
    try:
        if request:
            best = request.accept_languages.best_match(SUPPORTED_LANGS)
            if best:
                return best
    except Exception:
        pass
    # 4. fallback
    return DEFAULT_LANG


def t(key, lang=None, **kwargs):
    """
    Translate. Daca lang nu e specificat, foloseste get_current_lang().
    Suporta interpolare cu format params: t('elemente: {n}', n=5).
    Daca cheia lipseste, returneaza cheia ca atare (RO).
    """
    if lang is None:
        lang = get_current_lang()
    if lang == 'ro':
        translated = key
    else:
        entry = TRANSLATIONS.get(key, {})
        translated = entry.get(lang, key)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError):
            return translated
    return translated


def init_app(app):
    """Inregistreaza filtru Jinja `_` si helper context processor."""
    @app.context_processor
    def inject_i18n():
        return {
            '_': t,
            'current_lang': get_current_lang(),
            'supported_langs': SUPPORTED_LANGS,
        }

    @app.route('/limba/<lang>', methods=['POST', 'GET'])
    def set_language(lang):
        from flask import redirect, request, url_for
        if lang in SUPPORTED_LANGS:
            session['lang'] = lang
            # Salveaza si in user.limba daca e autentificat
            try:
                if current_user.is_authenticated:
                    current_user.limba = lang
                    from models import db as _db
                    _db.session.commit()
            except Exception:
                pass
        next_url = request.referrer or url_for('dashboard.index')
        return redirect(next_url)
