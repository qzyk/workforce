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
        # U2: parcursul ghidat + pasul urmator (proiect nou -> primul pas e "urmatorul")
        assert b'Parcurs proiect' in r.data and b'urmatorul' in r.data
    finally:
        with app.app_context():
            p = db.session.get(Proiect, pid)
            if p:
                db.session.delete(p)
                db.session.commit()


def test_leaga_dezleaga_santier(authenticated_client, app):
    from models import db, Proiect, Santier, ProiectSantier
    with app.app_context():
        p = Proiect(cod_proiect='PS-T', nume='PS test', data_start=date.today())
        s = Santier(cod='SAN-1', nume='Santier 1')
        db.session.add_all([p, s])
        db.session.commit()
        pid, sid = p.id, s.id
    try:
        r = authenticated_client.post(f'/proiecte/{pid}/leaga-santier', data={'santier_id': sid})
        assert r.status_code == 302
        with app.app_context():
            assert ProiectSantier.query.filter_by(proiect_id=pid, santier_id=sid).count() == 1
        rh = authenticated_client.get(f'/proiecte/{pid}/hub')
        assert rh.status_code == 200 and b'SAN-1' in rh.data and b'Santiere BIM legate' in rh.data
        rd = authenticated_client.post(f'/proiecte/{pid}/dezleaga-santier/{sid}')
        assert rd.status_code == 302
        with app.app_context():
            assert ProiectSantier.query.filter_by(proiect_id=pid).count() == 0
    finally:
        with app.app_context():
            for x in ProiectSantier.query.filter_by(proiect_id=pid).all():
                db.session.delete(x)
            for x in Santier.query.filter_by(cod='SAN-1').all():
                db.session.delete(x)
            pr = db.session.get(Proiect, pid)
            if pr:
                db.session.delete(pr)
            db.session.commit()
