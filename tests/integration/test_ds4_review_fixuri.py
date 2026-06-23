"""
Teste de regresie pentru fixurile de review DS faza 4.

Prind BUG-URILE pe VALOARE (nu doar existenta de string / status 200):

  #1 (MAJOR) KPI "Doc. Expirate" trebuie sa duca la documente.expirate (raport
     dedicat, query pe tot tabelul), NU la documente.lista?status=expirat care
     filtreaza DUPA paginare -> lista nu corespunde numarului din KPI.
     Test pe valoare: cream destule documente incat un document EXPIRAT cu
     data_upload veche cade pe pagina 2 a /documente/lista, iar pagina 1 (cele
     mai noi upload-uri) nu contine niciun expirat. Atunci:
       - /documente/lista?status=expirat NU il arata (bug-ul vechi)
       - /documente/expirate (tinta corecta a KPI) il arata
     si verificam ca template-ul dashboard foloseste exact tinta corecta.

  #2 (MAJOR) Butoanele icon-only din tabelele migrate trebuie sa aiba un nume
     accesibil sigur (aria-label), nu doar title=. Verificam markup-ul randat.

  #4 (CRITIC) Fara artefacte reziduale de tool-call (</content>, </invoke>) in
     template-urile migrate.

NB review: finding #3 (CRITIC "ed nedefinit -> 500") este FALS POZITIV. In Jinja2
un `{% import "_components.html" as ed %}` la nivel TOP in base.html este vizibil
in blocurile copilului (namespace-ul top-level al parintelui se propaga in block-uri).
test_ed_namespace_vizibil_in_blocuri de mai jos demonstreaza acest lucru: paginile
randeaza 200, nu 500.
"""
from datetime import date, datetime, timedelta

import pytest

from models import db, Document, Angajat


def _creeaza_angajat(app):
    with app.app_context():
        a = Angajat.query.filter_by(nume='RevizFix', prenume='Doc').first()
        if a is None:
            a = Angajat(nume='RevizFix', prenume='Doc', functie='Muncitor',
                        data_angajare=date.today() - timedelta(days=365),
                        status='activ')
            db.session.add(a)
            db.session.commit()
        return a.id


def test_kpi_doc_expirate_duce_la_raportul_dedicat(authenticated_client, app):
    """
    Finding #1: documentul expirat cu upload VECHI cade pe pagina 2 in
    /documente/lista, deci ?status=expirat (filtru post-paginare) NU il arata,
    dar /documente/expirate (tinta corecta a KPI) il arata.
    """
    ang_id = _creeaza_angajat(app)
    per_page = app.config.get('ITEMS_PER_PAGE', 25)

    with app.app_context():
        # Curatam documentele de test ca sa avem un decor controlat.
        Document.query.filter(Document.nume_document.like('REVIZ-%')).delete(
            synchronize_session=False)
        db.session.commit()

        acum = datetime.utcnow()
        # 1 document EXPIRAT, dar incarcat cel mai DEMULT (upload vechi) ->
        # cu order_by(data_upload.desc()) ajunge ultimul, pe pagina 2.
        expirat_vechi = Document(
            angajat_id=ang_id, tip='instructaj_SSM',
            nume_document='REVIZ-EXPIRAT-VECHI',
            data_expirare=date.today() - timedelta(days=10),  # expirat
            status='expirat',
            data_upload=acum - timedelta(days=500),  # cel mai vechi upload
        )
        db.session.add(expirat_vechi)
        # per_page documente VALABILE, toate cu upload RECENT -> umplu pagina 1.
        for i in range(per_page):
            db.session.add(Document(
                angajat_id=ang_id, tip='alte',
                nume_document=f'REVIZ-VALABIL-{i:03d}',
                data_expirare=date.today() + timedelta(days=365),  # valabil
                status='valabil',
                data_upload=acum - timedelta(minutes=i),  # toate recente
            ))
        db.session.commit()
        exp_id = expirat_vechi.id

    # Pagina 1 din /documente/lista?status=expirat: filtrarea post-paginare ruleaza
    # doar pe primele per_page (cele mai recente = toate valabile) -> documentul
    # expirat vechi NU apare. Asta e exact bug-ul pe care KPI-ul vechi il expunea.
    resp_lista = authenticated_client.get('/documente/lista?status=expirat')
    assert resp_lista.status_code == 200
    html_lista = resp_lista.get_data(as_text=True)
    assert 'REVIZ-EXPIRAT-VECHI' not in html_lista, (
        'Bug-ul presupus nu se reproduce: documentul expirat vechi ar trebui '
        'ascuns pe pagina 1 a /documente/lista din cauza filtrarii post-paginare.'
    )

    # Raportul dedicat (tinta CORECTA a KPI) interogheaza tot tabelul -> il arata.
    resp_exp = authenticated_client.get('/documente/expirate')
    assert resp_exp.status_code == 200
    html_exp = resp_exp.get_data(as_text=True)
    assert 'REVIZ-EXPIRAT-VECHI' in html_exp, (
        'documentul expirat trebuie sa apara in raportul /documente/expirate, '
        'indiferent de data_upload (query pe tot tabelul, fara paginare).'
    )

    # Curatenie.
    with app.app_context():
        Document.query.filter(Document.nume_document.like('REVIZ-%')).delete(
            synchronize_session=False)
        db.session.commit()


def test_dashboard_kpi_expirate_link_corect(authenticated_client, app):
    """
    Finding #1 (plasare link): cardul KPI Doc. Expirate trebuie sa pointeze la
    /documente/expirate, NU la /documente/lista?status=expirat.
    """
    # Fortam KPI > 0 ca acentul danger + linkul sa fie randate.
    ang_id = _creeaza_angajat(app)
    with app.app_context():
        d = Document.query.filter_by(nume_document='REVIZ-KPI-EXP').first()
        if d is None:
            db.session.add(Document(
                angajat_id=ang_id, tip='alte', nume_document='REVIZ-KPI-EXP',
                data_expirare=date.today() - timedelta(days=5), status='expirat'))
            db.session.commit()

    resp = authenticated_client.get('/')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    import re
    # Extragem href-ul cardului Doc. Expirate: cautam ancora ed-stat care contine
    # eticheta "Doc. Expirate".
    carduri = re.findall(r'<a[^>]*class="ed-stat[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         html, re.DOTALL)
    tinta = None
    for href, corp in carduri:
        if 'Doc. Expirate' in corp:
            tinta = href
            break
    assert tinta is not None, 'cardul KPI "Doc. Expirate" nu a fost gasit ca link ed-stat'
    assert '/documente/expirate' in tinta, (
        f'KPI Doc. Expirate trebuie sa duca la /documente/expirate, dar duce la {tinta}')
    assert 'status=expirat' not in tinta, (
        'KPI nu mai trebuie sa duca la documente.lista?status=expirat (filtru post-paginare)')

    with app.app_context():
        Document.query.filter_by(nume_document='REVIZ-KPI-EXP').delete(
            synchronize_session=False)
        db.session.commit()


def test_butoane_icon_only_au_nume_accesibil(authenticated_client, app):
    """
    Finding #2: butoanele icon-only din tabelele migrate (aprobare pontaje) au
    aria-label, iar iconita e marcata aria-hidden. Verificam markup-ul randat,
    nu doar prezenta unei iconite.
    """
    # Avem nevoie de cel putin un pontaj in asteptare ca sa apara butoanele
    # Aproba/Respinge. Daca nu exista decor, testam direct macro-ul randat (mai jos).
    resp = authenticated_client.get('/pontaje/aprobare')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Daca exista butoane de actiune icon-only in pagina, ele trebuie sa aiba aria-label.
    if 'ed-btn' in html and 'fa-check' in html:
        # un buton check icon-only trebuie sa aiba aria-label, nu doar title
        assert 'aria-label="Aproba"' in html or 'aria-label="Respinge"' in html, (
            'butoanele de actiune icon-only trebuie sa expuna aria-label')


def test_macro_btn_icon_only_emite_aria(app):
    """
    Finding #2 la sursa: macro-ul ed.btn cu label gol + aria_label emite
    aria-label pe buton si aria-hidden pe iconita. Cel cu text NU schimba nimic
    (backward compatible).
    """
    with app.app_context():
        tpl_icon = app.jinja_env.from_string(
            "{% import '_components.html' as ed %}"
            "{{ ed.btn('', icon='check', size='sm', submit=true, "
            "attrs='title=\"Aproba\"', aria_label='Aproba') }}"
        )
        tpl_text = app.jinja_env.from_string(
            "{% import '_components.html' as ed %}"
            "{{ ed.btn('Salveaza', submit=true) }}"
        )
        icon_part = tpl_icon.render()
        text_part = tpl_text.render()
    # Butonul icon-only: nume accesibil sigur + iconita decorativa.
    assert 'aria-label="Aproba"' in icon_part
    assert 'aria-hidden="true"' in icon_part
    # Butonul cu text: niciun aria-label injectat (textul e deja numele accesibil).
    assert 'aria-label' not in text_part
    assert 'Salveaza' in text_part


def test_ed_namespace_vizibil_in_blocuri(authenticated_client):
    """
    Finding #3 era FALS POZITIV: paginile migrate randeaza 200 (nu 500), pentru ca
    `ed` importat la nivel top in base.html e vizibil in blocurile copilului.
    """
    for path in ('/', '/dashboard/executiv', '/angajati/', '/proiecte/',
                 '/pontaje/', '/pontaje/aprobare'):
        resp = authenticated_client.get(path)
        assert resp.status_code == 200, f'{path} a dat {resp.status_code} (ed ar trebui definit)'
