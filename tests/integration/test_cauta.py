"""Test U1b: cautare globala (header autocomplete) - /cauta."""
from datetime import date


def test_cauta_globala(authenticated_client, app):
    from models import db, Proiect
    with app.app_context():
        p = Proiect(cod_proiect='ZQX-CAUTA', nume='Proiect cautabil', data_start=date.today())
        db.session.add(p); db.session.commit()
        pid = p.id
    try:
        r = authenticated_client.get('/cauta?q=ZQX-CAUTA')
        assert r.status_code == 200
        data = r.get_json()
        assert any(it['tip'] == 'proiect' and 'ZQX-CAUTA' in it['label'] for it in data)
        assert any('/proiecte/' in it['url'] for it in data)
        # interogare prea scurta -> gol
        assert authenticated_client.get('/cauta?q=a').get_json() == []
    finally:
        with app.app_context():
            pr = db.session.get(Proiect, pid)
            if pr:
                db.session.delete(pr)
                db.session.commit()


def test_cauta_necesita_login(client):
    r = client.get('/cauta?q=test')
    assert r.status_code in (302, 401)   # redirect la login
