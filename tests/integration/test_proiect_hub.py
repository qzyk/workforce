"""Test pentru pagina Proiect 360 (hub cross-modul)."""
from datetime import date


def test_hub_se_incarca(authenticated_client, app):
    from models import db, Proiect
    with app.app_context():
        p = Proiect(cod_proiect='HUB-T1', nume='Proiect hub test', data_start=date.today())
        db.session.add(p)
        db.session.commit()
        pid = p.id
    try:
        r = authenticated_client.get(f'/proiecte/{pid}/hub')
        assert r.status_code == 200
        assert b'Proiect hub test' in r.data
        assert b'Contracte' in r.data and b'Planuri Gantt' in r.data
    finally:
        with app.app_context():
            p = db.session.get(Proiect, pid)
            if p:
                db.session.delete(p)
                db.session.commit()
