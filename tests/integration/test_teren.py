"""Teste pentru captura rapida din teren (mobil): pontaj rapid + raportare problema."""
from datetime import date


def _cleanup(app, pid=None, aid=None, iss_titlu=None):
    from models import db, Proiect, Angajat, Pontaj, IssueBIM
    with app.app_context():
        if aid:
            for x in Pontaj.query.filter_by(angajat_id=aid).all():
                db.session.delete(x)
        if iss_titlu:
            for x in IssueBIM.query.filter_by(titlu=iss_titlu).all():
                db.session.delete(x)
        if aid:
            a = db.session.get(Angajat, aid)
            if a:
                db.session.delete(a)
        if pid:
            p = db.session.get(Proiect, pid)
            if p:
                db.session.delete(p)
        db.session.commit()


def test_teren_pagini_se_incarca(authenticated_client):
    for url in ('/teren/', '/teren/pontaj', '/teren/problema'):
        r = authenticated_client.get(url)
        assert r.status_code == 200, url
    assert b'Pontaj rapid' in authenticated_client.get('/teren/').data


def test_pontaj_rapid_creeaza_draft(authenticated_client, app):
    from models import db, Proiect, Angajat, Pontaj
    with app.app_context():
        p = Proiect(cod_proiect='TR-1', nume='Teren proiect', data_start=date.today(),
                    status='activ')
        a = Angajat(nume='Ion', prenume='Teren', data_angajare=date.today())
        db.session.add_all([p, a]); db.session.commit()
        pid, aid = p.id, a.id
    try:
        r = authenticated_client.post('/teren/pontaj', data={
            'proiect_id': pid, 'angajat_id': aid, 'ore': '10', 'data': date.today().isoformat(),
            'observatii': 'turnare beton',
        }, follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            pj = Pontaj.query.filter_by(angajat_id=aid, proiect_id=pid).first()
            assert pj is not None
            assert pj.status == 'draft' and abs((pj.ore_lucrate or 0) - 10) < 0.01
            assert pj.data == date.today()
    finally:
        _cleanup(app, pid=pid, aid=aid)


def test_pontaj_rapid_refuza_duplicat(authenticated_client, app):
    from models import db, Proiect, Angajat, Pontaj
    with app.app_context():
        p = Proiect(cod_proiect='TR-2', nume='P2', data_start=date.today(), status='activ')
        a = Angajat(nume='Vasile', prenume='Dup', data_angajare=date.today())
        db.session.add_all([p, a]); db.session.flush()
        db.session.add(Pontaj(angajat_id=a.id, proiect_id=p.id, data=date.today(),
                              ore_lucrate=8, status='draft'))
        db.session.commit()
        pid, aid = p.id, a.id
    try:
        authenticated_client.post('/teren/pontaj', data={
            'proiect_id': pid, 'angajat_id': aid, 'ore': '8',
        }, follow_redirects=True)
        with app.app_context():
            # ramane un singur pontaj pe ziua respectiva (nu s-a dublat)
            n = Pontaj.query.filter_by(angajat_id=aid, data=date.today()).count()
            assert n == 1
    finally:
        _cleanup(app, pid=pid, aid=aid)


def test_pontaj_rapid_campuri_lipsa(authenticated_client, app):
    from models import Pontaj
    r = authenticated_client.post('/teren/pontaj', data={'ore': '8'},
                                  follow_redirects=True)
    assert r.status_code == 200  # redirect inapoi la formular, fara crash


def test_problema_creeaza_issue(authenticated_client, app):
    from models import db, IssueBIM
    titlu = 'TEREN fisura grinda ax B'
    try:
        r = authenticated_client.post('/teren/problema', data={
            'titlu': titlu, 'severitate': 'mare', 'descriere': 'vizibila pe fata inferioara',
        }, follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            iss = IssueBIM.query.filter_by(titlu=titlu).first()
            assert iss is not None
            assert iss.tip == 'observatie' and iss.severitate == 'mare'
            assert iss.status == 'deschis'
    finally:
        _cleanup(app, iss_titlu=titlu)


def test_angajat_curent_dupa_email(authenticated_client, app):
    """Daca exista un Angajat cu acelasi email ca userul logat, e preselectat."""
    from models import db, Angajat, Utilizator
    with app.app_context():
        u = Utilizator.query.filter_by(email='admin_test@test.local').first()
        a = Angajat(nume='Admin', prenume='Legat', data_angajare=date.today(),
                    email=u.email)
        db.session.add(a); db.session.commit()
        aid = a.id
    try:
        r = authenticated_client.get('/teren/')
        assert r.status_code == 200 and b'Admin Legat' in r.data
    finally:
        _cleanup(app, aid=aid)
