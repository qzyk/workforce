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

    # === Pagini lista angajati / proiecte ===
    'Adauga Angajat': {'en': 'Add Employee'},
    'Adauga Angajat Nou': {'en': 'Add New Employee'},
    'Editeaza Angajat': {'en': 'Edit Employee'},
    'Lista angajati': {'en': 'Employee list'},
    'Cauta angajat': {'en': 'Search employee'},
    'Nume complet': {'en': 'Full name'},
    'Date Personale': {'en': 'Personal Details'},
    'Date Profesionale': {'en': 'Professional Details'},
    'Salveaza si Adauga Altul': {'en': 'Save and Add Another'},
    'Anuleaza': {'en': 'Cancel'},
    'Salveaza': {'en': 'Save'},
    'Date angajare': {'en': 'Employment data'},

    # === Forma angajat - santiere ===
    'Tine apasat Ctrl (Cmd pe Mac) pentru a selecta sau deselecta mai multe.':
        {'en': 'Hold Ctrl (Cmd on Mac) to select or deselect multiple items.'},
    'Modificarile se salveaza la submit-ul formularului.':
        {'en': 'Changes are saved when you submit the form.'},
    'Nu exista proiecte active. Creeaza intai un proiect din meniu.':
        {'en': 'No active projects. Create a project from the menu first.'},
    'Adauga proiect nou': {'en': 'Add new project'},

    # === Proiect detalii - echipa ===
    'Membrii Echipei': {'en': 'Team Members'},
    'activi': {'en': 'active'},
    'in istoric': {'en': 'in history'},
    'Angajat': {'en': 'Employee'},
    'Tarif': {'en': 'Rate'},
    'Actiuni': {'en': 'Actions'},
    'Data Start': {'en': 'Start Date'},
    'Perioada': {'en': 'Period'},
    'Istoric': {'en': 'History'},
    'dezalocati anterior': {'en': 'previously unassigned'},
    'Dezaloca de pe proiect': {'en': 'Unassign from project'},
    'Re-aloca pe proiect': {'en': 'Re-assign to project'},
    'Doriti sa dezalocati angajatul': {'en': 'Unassign employee'},
    'Asocierea va aparea in tab Istoric si poate fi re-activata oricand.':
        {'en': 'The assignment will appear in the History tab and can be re-activated at any time.'},
    'Re-aloca angajatul': {'en': 'Re-assign employee'},
    'pe acest proiect?': {'en': 'to this project?'},
    'Sterge definitiv din istoric': {'en': 'Permanently delete from history'},
    'Stergere DEFINITIVA': {'en': 'PERMANENT deletion'},
    'Aceasta actiune nu poate fi anulata. Continui?':
        {'en': 'This action cannot be undone. Continue?'},
    'Niciun angajat asignat pe acest proiect.':
        {'en': 'No employees assigned to this project.'},

    # === Proiect general ===
    'Adauga proiect': {'en': 'Add project'},
    'Editeaza proiect': {'en': 'Edit project'},
    'Cod proiect': {'en': 'Project code'},
    'Buget': {'en': 'Budget'},
    'Manager proiect': {'en': 'Project manager'},
    'Proiecte active': {'en': 'Active projects'},
    'Proiecte finalizate': {'en': 'Completed projects'},

    # === Dashboard widgets ===
    'Total angajati': {'en': 'Total employees'},
    'Angajati activi': {'en': 'Active employees'},
    'Pontaje luna curenta': {'en': 'Current month timesheets'},
    'Ore luna curenta': {'en': 'Current month hours'},
    'Documente expirate': {'en': 'Expired documents'},
    'Documente expira': {'en': 'Documents expiring'},
    'Activitati saptamana': {'en': 'Activities this week'},
    'Alerte': {'en': 'Alerts'},
    'Notificari pontaj': {'en': 'Timesheet notifications'},
    'Vezi detalii': {'en': 'View details'},

    # === Pontaje ===
    'Pontaj': {'en': 'Timesheet'},
    'Pontaj nou': {'en': 'New timesheet'},
    'Ora start': {'en': 'Start time'},
    'Ora sfarsit': {'en': 'End time'},
    'Ore lucrate': {'en': 'Hours worked'},
    'Ore normale': {'en': 'Regular hours'},
    'Ore suplimentare': {'en': 'Overtime hours'},
    'Aproba pontaj': {'en': 'Approve timesheet'},
    'Respinge pontaj': {'en': 'Reject timesheet'},

    # === Documente ===
    'Document': {'en': 'Document'},
    'Documente angajat': {'en': 'Employee documents'},
    'Tip document': {'en': 'Document type'},
    'Data emitere': {'en': 'Issue date'},
    'Data expirare': {'en': 'Expiry date'},
    'Expira in': {'en': 'Expires in'},
    'Expirat': {'en': 'Expired'},

    # === Activitati ===
    'Activitate noua': {'en': 'New activity'},
    'Activitate zilnica': {'en': 'Daily activity'},
    'Activitate saptamanala': {'en': 'Weekly activity'},
    'Activitate lunara': {'en': 'Monthly activity'},
    'Panou activitati': {'en': 'Activities panel'},

    # === Empty states & errors ===
    'Niciun angajat': {'en': 'No employees'},
    'Niciun proiect': {'en': 'No projects'},
    'Nu s-au gasit rezultate.': {'en': 'No results found.'},
    'Adauga primul element': {'en': 'Add first item'},
    'Eroare': {'en': 'Error'},
    'Avertisment': {'en': 'Warning'},
    'Informatie': {'en': 'Information'},
    'Succes': {'en': 'Success'},

    # === Common UI labels ===
    'Inapoi la lista': {'en': 'Back to list'},
    'Vezi mai mult': {'en': 'See more'},
    'Optiuni': {'en': 'Options'},
    'Pagina': {'en': 'Page'},
    'din': {'en': 'of'},
    'Primul': {'en': 'First'},
    'Anterior': {'en': 'Previous'},
    'Urmator': {'en': 'Next'},
    'Ultimul': {'en': 'Last'},

    # === Faza 10 - Contract Controls ===
    'Contracte': {'en': 'Contracts'},
    'Contract': {'en': 'Contract'},
    'Contract nou': {'en': 'New contract'},
    'Editeaza Contract': {'en': 'Edit contract'},
    'Toate contractele': {'en': 'All contracts'},
    'Procese verbale': {'en': 'Site minutes'},
    'Proces verbal': {'en': 'Site minute'},
    'Proces verbal nou': {'en': 'New site minute'},
    'PV nou': {'en': 'New minute'},
    'Editeaza PV': {'en': 'Edit minute'},
    'Adauga PV': {'en': 'Add minute'},
    'Niciun PV gasit': {'en': 'No minutes found'},
    'Niciun PV asociat': {'en': 'No associated minutes.'},
    'Sigur stergi acest PV?': {'en': 'Delete this minute?'},
    'Termene contractuale': {'en': 'Contractual deadlines'},
    'Termen contractual': {'en': 'Contractual deadline'},
    'Termen contractual nou': {'en': 'New contractual deadline'},
    'Editeaza termen': {'en': 'Edit deadline'},
    'Termen nou': {'en': 'New deadline'},
    'Adauga termen': {'en': 'Add deadline'},
    'Niciun termen inregistrat.': {'en': 'No deadline registered.'},
    'Sigur stergi acest termen?': {'en': 'Delete this deadline?'},
    'Sigur stergi acest contract?': {'en': 'Delete this contract?'},
    'Acte aditionale': {'en': 'Amendments'},
    'Act aditional la': {'en': 'Amendment to'},
    'Adauga act aditional': {'en': 'Add amendment'},
    'acte aditionale': {'en': 'amendments'},
    'Niciun act aditional.': {'en': 'No amendments.'},
    'Niciun contract gasit': {'en': 'No contracts found'},
    'Creeaza primul contract pentru a porni modulul de Contract Controls.':
        {'en': 'Create your first contract to start the Contract Controls module.'},
    'Nr. contract': {'en': 'Contract no.'},
    'Numar PV': {'en': 'Minute no.'},
    'Data semnare': {'en': 'Signing date'},
    'Data emitere': {'en': 'Issue date'},
    'Data scadenta': {'en': 'Due date'},
    'Data realizare': {'en': 'Completion date'},
    'Data finalizare planificata': {'en': 'Planned end date'},
    'NTP proiectare': {'en': 'NTP design'},
    'NTP executie': {'en': 'NTP execution'},
    'Valoare': {'en': 'Value'},
    'Valoare totala': {'en': 'Total value'},
    'Valori financiare': {'en': 'Financial values'},
    'Moneda': {'en': 'Currency'},
    'Beneficiar': {'en': 'Beneficiary'},
    'Antreprenor': {'en': 'Contractor'},
    'Obiect': {'en': 'Object'},
    'Obiect contract': {'en': 'Contract object'},
    'Obiectul PV': {'en': 'Minute object'},
    'Observatii': {'en': 'Notes'},
    'Concluzii': {'en': 'Conclusions'},
    'Identificare': {'en': 'Identification'},
    'Asociere': {'en': 'Association'},
    'Date-cheie': {'en': 'Key dates'},
    'Date contract': {'en': 'Contract details'},
    'Parti contractante': {'en': 'Parties'},
    'Continut': {'en': 'Content'},
    'Participanti': {'en': 'Participants'},
    'PV semnat': {'en': 'Minute signed'},
    'Semnat': {'en': 'Signed'},
    'Tip': {'en': 'Type'},
    'Tip termen': {'en': 'Deadline type'},
    'Tip proces verbal': {'en': 'Minute type'},
    'Denumire': {'en': 'Name'},
    'Denumire termen': {'en': 'Deadline name'},
    'Descriere': {'en': 'Description'},
    'Responsabil': {'en': 'Responsible'},
    'Zile alerta inainte': {'en': 'Alert days before'},
    'Zile alerta inainte de scadenta': {'en': 'Alert days before due date'},
    'Active': {'en': 'Active'},
    'Suspendate': {'en': 'Suspended'},
    'Finalizate': {'en': 'Completed'},
    'Activ': {'en': 'Active'},
    'Suspendat': {'en': 'Suspended'},
    'Reziliat': {'en': 'Terminated'},
    'Finalizat': {'en': 'Completed'},
    'Realizat': {'en': 'Completed'},
    'Intarziat': {'en': 'Delayed'},
    'In curs': {'en': 'In progress'},
    'Proiect': {'en': 'Project'},
    'Toate': {'en': 'All'},
    'Detalii': {'en': 'Details'},
    'Cautare': {'en': 'Search'},
    'Filtreaza': {'en': 'Filter'},
    'Actiuni': {'en': 'Actions'},
    'Sterge': {'en': 'Delete'},
    'Anulare': {'en': 'Cancel'},
    'Adauga': {'en': 'Add'},
    'Nr. contract, beneficiar, antreprenor...': {'en': 'Contract no., beneficiary, contractor...'},
    'Numele beneficiarului': {'en': 'Beneficiary name'},
    'Numele antreprenorului': {'en': 'Contractor name'},
    'Contract parinte (pentru acte aditionale)': {'en': 'Parent contract (for amendments)'},
    'Contract (optional)': {'en': 'Contract (optional)'},
    'Tip):': {'en': 'Type:'},
    'PV semnat de toti participantii': {'en': 'Minute signed by all participants'},
    'Participanti (cate unul pe linie, format: Nume | Functie | Organizatie)':
        {'en': 'Participants (one per line, format: Name | Role | Organization)'},
    'Folositi | (pipe) ca separator. Liniile goale sunt ignorate.':
        {'en': 'Use | (pipe) as separator. Empty lines are ignored.'},
    'Ex. Receptie partiala etaj 3': {'en': 'E.g. Partial reception floor 3'},
    'Fara contract specific': {'en': 'No specific contract'},
    'Niciun responsabil': {'en': 'No assignee'},
    'Niciunul (contract principal)': {'en': 'None (main contract)'},
    'Nr.': {'en': 'No.'},

    # === Faza 12 - Cantitati lunare + Situatii + Rapoarte ===
    'Cantitati lunare': {'en': 'Monthly quantities'},
    'Cant. luna': {'en': 'Qty month'},
    'Cant. oferta': {'en': 'Qty offer'},
    'Cant. cumul.': {'en': 'Qty cumul.'},
    'Val. luna': {'en': 'Val. month'},
    'Val. oferta': {'en': 'Val. offer'},
    'Val. cumul.': {'en': 'Val. cumul.'},
    'Pret unit.': {'en': 'Unit price'},
    'Pret': {'en': 'Price'},
    'Pret unitar': {'en': 'Unit price'},
    'Cant. luna': {'en': 'Qty month'},
    'Salveaza cantitati luna': {'en': 'Save quantities for month'},
    'Valideaza': {'en': 'Validate'},
    'Validat': {'en': 'Validated'},
    'Neinregistrat': {'en': 'Not registered'},
    'Note': {'en': 'Notes'},
    'Note...': {'en': 'Notes...'},
    'Cod sau denumire...': {'en': 'Code or name...'},
    'Nicio pozitie pentru filtrele alese.': {'en': 'No item for chosen filters.'},
    'Situatii lunare': {'en': 'Monthly reports'},
    'Situatie lunara': {'en': 'Monthly report'},
    'Situatie lunara noua': {'en': 'New monthly report'},
    'Situatie noua': {'en': 'New report'},
    'Genereaza situatie': {'en': 'Generate report'},
    'Nicio situatie inregistrata': {'en': 'No reports registered'},
    'Genereaza prima situatie din cantitatile executate validate ale unei luni.':
        {'en': 'Generate the first report from validated executed quantities of a month.'},
    'Situatia se genereaza automat din cantitatile executate VALIDATE ale lunii alese.':
        {'en': 'Report is auto-generated from VALIDATED executed quantities of chosen month.'},
    'Daca exista deja o situatie pentru aceasta luna, va fi actualizata (re-calculata) cu noile cantitati.':
        {'en': 'If a report already exists for this month, it will be updated (recalculated) with new quantities.'},
    'Perioada': {'en': 'Period'},
    'Numar': {'en': 'Number'},
    'Numar situatie': {'en': 'Report number'},
    'Status initial': {'en': 'Initial status'},
    'Valoare luna': {'en': 'Month value'},
    'Cumulat la zi': {'en': 'Cumulative to date'},
    'Avans': {'en': 'Progress'},
    'Avans total': {'en': 'Total progress'},
    'Procent avans total': {'en': 'Total progress percent'},
    'Draft': {'en': 'Draft'},
    'Emisa': {'en': 'Issued'},
    'Aprobata beneficiar': {'en': 'Approved by beneficiary'},
    'Aprobata': {'en': 'Approved'},
    'Platita': {'en': 'Paid'},
    'Respinsa': {'en': 'Rejected'},
    'Tranzitii valide': {'en': 'Valid transitions'},
    'Sigur treci la status': {'en': 'Confirm transition to status'},
    'Afiseaza doar pozitiile cu activitate (cant. luna sau cumulat). Totalurile includ toate pozitiile.':
        {'en': 'Showing only items with activity (qty month or cumul). Totals include all items.'},
    'Nicio pozitie BoQ in oferta asociata.': {'en': 'No BoQ items in associated offer.'},
    'Rapoarte lunare': {'en': 'Monthly reports'},
    'Raport lunar lucrari': {'en': 'Monthly work report'},
    'Genereaza raport': {'en': 'Generate report'},
    'Genereaza primul raport': {'en': 'Generate first report'},
    'Genereaza raport lunar lucrari': {'en': 'Generate monthly work report'},
    'Regenereaza': {'en': 'Regenerate'},
    'Niciun raport generat': {'en': 'No report generated'},
    'Raportul agregheaza orele de manopera din Pontaj + progresul din Activitati + taskuri din Program de referinta pentru o luna selectata.':
        {'en': 'Report aggregates labor hours from Timesheets + progress from Activities + tasks from Reference Schedule for a selected month.'},
    'Raportul agregheaza datele din 3 surse pentru luna aleasa':
        {'en': 'Report aggregates data from 3 sources for chosen month'},
    'Pontaj': {'en': 'Timesheet'},
    'RaportActivitate': {'en': 'ActivityReport'},
    'TaskProgram': {'en': 'TaskProgram'},
    'Ore manopera': {'en': 'Labor hours'},
    'Taskuri acoperite': {'en': 'Tasks covered'},
    'Taskuri din Program acoperite in aceasta luna':
        {'en': 'Tasks from Program covered this month'},
    'Niciun task din Program de referinta nu se intersecteaza cu aceasta luna.':
        {'en': 'No tasks from Reference Schedule intersect with this month.'},
    'Progres descriere': {'en': 'Progress description'},
    'Progres descriere (manual - se adauga la cele auto-extrase)':
        {'en': 'Progress description (manual - adds to auto-extracted)'},
    'Optional: descriere manuala progres luna...':
        {'en': 'Optional: manual progress description for the month...'},
    'Data intocmire': {'en': 'Issue date'},
    'Progres': {'en': 'Progress'},
    'Realizare': {'en': 'Completion'},
    'Sigur stergi aceasta situatie?': {'en': 'Delete this report?'},
    'An': {'en': 'Year'},
    'Luna': {'en': 'Month'},
    'Categorie': {'en': 'Category'},
    'Capitol': {'en': 'Chapter'},
    'Cod articol': {'en': 'Item code'},
    'Cod': {'en': 'Code'},
    'Cantitate': {'en': 'Quantity'},
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
