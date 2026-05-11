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
    # === Navigare principala ===
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
    'Autentificare': {'en': 'Sign in'},
    'Tenants': {'en': 'Tenants'},

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
    'Modele 3D': {'en': '3D Models'},
    'Data Quality': {'en': 'Data Quality'},
    'Import IFC': {'en': 'Import IFC'},
    'Export BCF': {'en': 'Export BCF'},
    'Viewer 3D': {'en': '3D Viewer'},
    'Modele': {'en': 'Models'},
    'Senzori IoT': {'en': 'IoT Sensors'},
    'Alerte': {'en': 'Alerts'},
    'Kanban': {'en': 'Kanban'},
    'Reguli': {'en': 'Rules'},
    'Clash detection': {'en': 'Clash detection'},
    'Roluri': {'en': 'Roles'},
    'Tokens': {'en': 'Tokens'},
    'API': {'en': 'API'},
    'Versiuni': {'en': 'Versions'},
    'Versiune': {'en': 'Version'},
    'Viewer federat': {'en': 'Federated viewer'},
    'Schedule 4D': {'en': '4D Schedule'},
    'Cost 5D': {'en': '5D Cost'},
    'Timeline 4D': {'en': '4D Timeline'},
    'Dashboard Cost 5D': {'en': '5D Cost Dashboard'},

    # === Activitati submenu ===
    'Toate': {'en': 'All'},
    'Saptamanale': {'en': 'Weekly'},
    'Lunare': {'en': 'Monthly'},

    # === Actiuni comune ===
    'Salveaza': {'en': 'Save'},
    'Anuleaza': {'en': 'Cancel'},
    'Editeaza': {'en': 'Edit'},
    'Sterge': {'en': 'Delete'},
    'Adauga': {'en': 'Add'},
    'Filtreaza': {'en': 'Filter'},
    'Filtre': {'en': 'Filters'},
    'Reset': {'en': 'Reset'},
    'Cauta': {'en': 'Search'},
    'Detalii': {'en': 'Details'},
    'Inapoi': {'en': 'Back'},
    'Confirma': {'en': 'Confirm'},
    'Trimite': {'en': 'Submit'},
    'Reincarca': {'en': 'Reload'},
    'Descarca': {'en': 'Download'},
    'Genereaza': {'en': 'Generate'},
    'Niciunul': {'en': 'None'},
    'Continua': {'en': 'Continue'},
    'Aproba': {'en': 'Approve'},
    'Respinge': {'en': 'Reject'},
    'Vezi': {'en': 'View'},
    'Nou': {'en': 'New'},
    'Adauga nou': {'en': 'Add new'},
    'Export': {'en': 'Export'},
    'Import': {'en': 'Import'},
    'Upload': {'en': 'Upload'},
    'Salveaza modificarile': {'en': 'Save changes'},
    'Promoveaza': {'en': 'Promote'},
    'Revoca': {'en': 'Revoke'},
    'Asignaza': {'en': 'Assign'},

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
    'Planificat': {'en': 'Planned'},
    'Verificat': {'en': 'Verified'},
    'Anulat': {'en': 'Cancelled'},
    'Amanat': {'en': 'Postponed'},
    'Publicat': {'en': 'Published'},
    'Partajat': {'en': 'Shared'},
    'Arhivat': {'en': 'Archived'},
    'Noua': {'en': 'New'},
    'Confirmata': {'en': 'Confirmed'},
    'Falsa': {'en': 'False'},
    'Rezolvata': {'en': 'Resolved'},

    # === Form labels ===
    'Cod': {'en': 'Code'},
    'Nume': {'en': 'Name'},
    'Prenume': {'en': 'First name'},
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
    'Telefon': {'en': 'Phone'},
    'CNP': {'en': 'National ID'},
    'Functie': {'en': 'Position'},
    'Disciplina': {'en': 'Discipline'},
    'Categorie': {'en': 'Category'},
    'Severitate': {'en': 'Severity'},
    'Titlu': {'en': 'Title'},
    'Autor': {'en': 'Author'},
    'Cantitate': {'en': 'Quantity'},
    'Unitate': {'en': 'Unit'},
    'Pret unitar': {'en': 'Unit price'},
    'Total': {'en': 'Total'},
    'Valoare': {'en': 'Value'},
    'Comentariu': {'en': 'Comment'},
    'Note': {'en': 'Notes'},
    'Optional': {'en': 'Optional'},
    'Obligatoriu': {'en': 'Required'},

    # === Date / Time ===
    'Astazi': {'en': 'Today'},
    'Ieri': {'en': 'Yesterday'},
    'Maine': {'en': 'Tomorrow'},
    'Luna': {'en': 'Month'},
    'Saptamana': {'en': 'Week'},
    'An': {'en': 'Year'},
    'Zile': {'en': 'Days'},
    'Ore': {'en': 'Hours'},
    'Minute': {'en': 'Minutes'},
    'Data inceput': {'en': 'Start date'},
    'Data sfarsit': {'en': 'End date'},
    'Data start': {'en': 'Start date'},
    'Data start planificat': {'en': 'Planned start date'},
    'Data sfarsit planificat': {'en': 'Planned end date'},
    'Data creare': {'en': 'Created on'},
    'Data modificare': {'en': 'Modified on'},

    # === Severitati / Categorii BIM ===
    'mica': {'en': 'low'},
    'medie': {'en': 'medium'},
    'mare': {'en': 'high'},
    'critica': {'en': 'critical'},
    'Mica': {'en': 'Low'},
    'Medie': {'en': 'Medium'},
    'Mare': {'en': 'High'},
    'Critica': {'en': 'Critical'},

    # === Header / search / notifications ===
    'Cauta BIM (cod element / spatiu / santier)...': {'en': 'Search BIM (element code / space / site)...'},
    'Notificari': {'en': 'Notifications'},
    'Nicio notificare': {'en': 'No notifications'},
    'documente necesita atentie': {'en': 'documents need attention'},
    'pontaje in asteptare': {'en': 'timesheets pending'},

    # === Sidebar specific ===
    'Instaleaza app': {'en': 'Install app'},
    'Workforce Manager': {'en': 'Workforce Manager'},

    # === Mesaje sistem ===
    'Salvat cu succes.': {'en': 'Saved successfully.'},
    'Sters cu succes.': {'en': 'Deleted successfully.'},
    'Eroare la salvare': {'en': 'Save error'},
    'Acces interzis.': {'en': 'Access denied.'},
    'Nu sunteti autentificat.': {'en': 'You are not authenticated.'},
    'Trebuie sa fiti autentificat pentru a accesa aceasta pagina.':
        {'en': 'You must be signed in to access this page.'},

    # === Login page ===
    'Bine ati venit': {'en': 'Welcome'},
    'Conectati-va la cont': {'en': 'Sign in to your account'},
    'Tine-ma minte': {'en': 'Remember me'},
    'Conturi demo': {'en': 'Demo accounts'},
    'Date contact: edifico.space': {'en': 'Contact: edifico.space'},
    'Conectare': {'en': 'Sign in'},
    'Ai uitat parola?': {'en': 'Forgot password?'},
    'Managementul fortei de munca in constructii':
        {'en': 'Construction workforce management'},

    # === Dashboard widgets ===
    'Statistici generale': {'en': 'General statistics'},
    'Bine ai venit': {'en': 'Welcome'},
    'Zile de nastere': {'en': 'Birthdays'},
    'La multi ani': {'en': 'Happy birthday'},
    'Astazi este ziua de nastere a': {'en': 'Today is the birthday of'},
    'Vezi toate': {'en': 'View all'},
    'Total': {'en': 'Total'},
    'Numar': {'en': 'Count'},

    # === BIM specific ===
    'Generare Raport EDIFICO': {'en': 'Generate EDIFICO Report'},
    'Selecteaza toti': {'en': 'Select all'},
    'Deselecteaza': {'en': 'Deselect all'},
    'Tine apasat Ctrl pentru selectie multipla':
        {'en': 'Hold Ctrl for multi-select'},
    'Niciun santier inca.': {'en': 'No sites yet.'},
    'Adauga primul santier': {'en': 'Add first site'},
    'Building Information Modeling': {'en': 'Building Information Modeling'},
    'Issues deschise': {'en': 'Open issues'},
    'Arbore santiere': {'en': 'Site tree'},

    # === BIM dashboard buttons ===
    'Reguli model checking': {'en': 'Model checking rules'},
    'Versiuni model': {'en': 'Model versions'},
    'Adauga senzor': {'en': 'Add sensor'},
    'Comentarii': {'en': 'Comments'},

    # === Footer ===
    'Toate drepturile rezervate.': {'en': 'All rights reserved.'},
    'One platform, all your sites': {'en': 'One platform, all your sites'},

    # === Profile / password / modal ===
    'Schimba parola': {'en': 'Change password'},
    'Confirmare stergere': {'en': 'Confirm deletion'},
    'Sunteti sigur ca doriti sa stergeti acest element?':
        {'en': 'Are you sure you want to delete this item?'},
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
