"""
Integrare wf-4: pontaj de echipa pe teren (bulk) + GPS optional, gated pe
flag-ul 'teren-pontaj-bulk'.

Verifica VALORI, nu doar existenta:
- Flag OFF (default): ruta /teren/pontaj-echipa raspunde 404 si cardul nu apare
  in /teren/ (modulul Teren ramane neschimbat - doar pontaj individual).
- Flag ON: GET arata formularul; POST creeaza cate un pontaj per angajat selectat,
  cu orele calculate corect (reutilizeaza creeaza_pontaje_bulk din pontaje).
- GPS optional: coordonatele valide se persista (lat/long/sursa_gps='gps');
  fara GPS sau cu coordonate invalide, raman NULL si NU blocheaza pontajul.
- Anti-duplicat / anti-suprapunere: un angajat care are deja pontaj in ziua aleasa
  e omis (count_skip), restul echipei se salveaza.
"""

from datetime import date

import pytest

from services import feature_flags as ff


def _post_echipa(client, proiect_id, angajat_ids, data_str, **extra):
    data = {
        'proiect_id': str(proiect_id),
        'data': data_str,
        'actiune': 'draft',
        'angajat_ids': [str(a) for a in angajat_ids],
        'ora_start': '08:00',
        'ora_sfarsit': '16:00',
    }
    data.update(extra)
    return client.post('/teren/pontaj-echipa', data=data, follow_redirects=False)


@pytest.fixture
def echipa(app):
    """1 proiect + 3 angajati activi, returneaza dict cu ID-uri."""
    from models import db, Proiect, Angajat
    from tests.fixtures.data import make_proiect, make_angajat
    with app.app_context():
        Proiect.query.filter_by(cod_proiect='PRJ-ECH-001').delete()
        for cnp in ('1900101010201', '1900101010202', '1900101010203'):
            Angajat.query.filter_by(cnp=cnp).delete()
        db.session.commit()
        p = make_proiect(db, Proiect, cod='PRJ-ECH-001')
        a1 = make_angajat(db, Angajat, cnp='1900101010201', nume='Echipa', prenume='Unu')
        a2 = make_angajat(db, Angajat, cnp='1900101010202', nume='Echipa', prenume='Doi')
        a3 = make_angajat(db, Angajat, cnp='1900101010203', nume='Echipa', prenume='Trei')
        yield {'proiect_id': p.id, 'angajat_ids': [a1.id, a2.id, a3.id]}
        Proiect.query.filter_by(cod_proiect='PRJ-ECH-001').delete()
        for cnp in ('1900101010201', '1900101010202', '1900101010203'):
            Angajat.query.filter_by(cnp=cnp).delete()
        db.session.commit()


class TestTerenPontajBulkFlag:
    def test_flag_off_ruta_404(self, app, authenticated_client):
        """Cu flag OFF, ruta de echipa nu exista (404)."""
        with app.app_context():
            ff.set_flag('teren-pontaj-bulk', False)
        r = authenticated_client.get('/teren/pontaj-echipa')
        assert r.status_code == 404

    def test_flag_off_card_lipseste(self, app, authenticated_client):
        """Cu flag OFF, indexul Teren NU arata cardul de echipa (neschimbat)."""
        with app.app_context():
            ff.set_flag('teren-pontaj-bulk', False)
        r = authenticated_client.get('/teren/')
        assert r.status_code == 200
        assert b'Pontaj echipa' not in r.data
        # pontajul individual ramane disponibil (comportament istoric)
        assert b'Pontaj rapid' in r.data

    def test_flag_on_card_si_form(self, app, authenticated_client):
        """Cu flag ON, cardul apare in index si formularul se incarca."""
        with app.app_context():
            ff.set_flag('teren-pontaj-bulk', True)
        try:
            idx = authenticated_client.get('/teren/')
            assert idx.status_code == 200 and b'Pontaj echipa' in idx.data
            frm = authenticated_client.get('/teren/pontaj-echipa')
            assert frm.status_code == 200 and b'Pontaj echipa' in frm.data
        finally:
            with app.app_context():
                ff.set_flag('teren-pontaj-bulk', False)


class TestTerenPontajBulkValori:
    def test_creeaza_pentru_toata_echipa_cu_gps(self, app, authenticated_client, echipa):
        """Flag ON + GPS valid: cate un pontaj per angajat, cu coordonate salvate."""
        from models import db, Pontaj
        ziua = date(2025, 10, 6)
        with app.app_context():
            ff.set_flag('teren-pontaj-bulk', True)
            for aid in echipa['angajat_ids']:
                Pontaj.query.filter_by(angajat_id=aid, data=ziua).delete()
            db.session.commit()
        try:
            r = _post_echipa(
                authenticated_client, echipa['proiect_id'], echipa['angajat_ids'],
                ziua.isoformat(), latitudine='44.426800', longitudine='26.104400',
            )
            assert r.status_code in (302, 200)
            with app.app_context():
                pontaje = Pontaj.query.filter_by(data=ziua).filter(
                    Pontaj.angajat_id.in_(echipa['angajat_ids'])
                ).all()
                assert len(pontaje) == 3
                for p in pontaje:
                    assert p.proiect_id == echipa['proiect_id']
                    assert p.status == 'draft'
                    # 08:00-16:00 = 8h brut; calcul ore aplicat (pauza scazuta)
                    assert float(p.ore_lucrate) == 7.5
                    # GPS persistat corect
                    assert p.sursa_gps == 'gps'
                    assert abs(p.latitudine - 44.4268) < 1e-4
                    assert abs(p.longitudine - 26.1044) < 1e-4
                for p in pontaje:
                    db.session.delete(p)
                db.session.commit()
        finally:
            with app.app_context():
                ff.set_flag('teren-pontaj-bulk', False)

    def test_fara_gps_nu_blocheaza(self, app, authenticated_client, echipa):
        """Fara coordonate, pontajele se salveaza oricum (lat/long/sursa NULL)."""
        from models import db, Pontaj
        ziua = date(2025, 10, 7)
        with app.app_context():
            ff.set_flag('teren-pontaj-bulk', True)
            for aid in echipa['angajat_ids']:
                Pontaj.query.filter_by(angajat_id=aid, data=ziua).delete()
            db.session.commit()
        try:
            r = _post_echipa(
                authenticated_client, echipa['proiect_id'],
                echipa['angajat_ids'][:2], ziua.isoformat(),
            )
            assert r.status_code in (302, 200)
            with app.app_context():
                pontaje = Pontaj.query.filter_by(data=ziua).filter(
                    Pontaj.angajat_id.in_(echipa['angajat_ids'])
                ).all()
                assert len(pontaje) == 2
                for p in pontaje:
                    assert p.latitudine is None
                    assert p.longitudine is None
                    assert p.sursa_gps is None
                    db.session.delete(p)
                db.session.commit()
        finally:
            with app.app_context():
                ff.set_flag('teren-pontaj-bulk', False)

    def test_gps_invalid_ignorat(self, app, authenticated_client, echipa):
        """Coordonate in afara domeniului -> ignorate (NULL), pontajul tot trece."""
        from models import db, Pontaj
        ziua = date(2025, 10, 8)
        with app.app_context():
            ff.set_flag('teren-pontaj-bulk', True)
            for aid in echipa['angajat_ids']:
                Pontaj.query.filter_by(angajat_id=aid, data=ziua).delete()
            db.session.commit()
        try:
            r = _post_echipa(
                authenticated_client, echipa['proiect_id'],
                echipa['angajat_ids'][:1], ziua.isoformat(),
                latitudine='999', longitudine='abc',
            )
            assert r.status_code in (302, 200)
            with app.app_context():
                p = Pontaj.query.filter_by(
                    angajat_id=echipa['angajat_ids'][0], data=ziua,
                ).first()
                assert p is not None
                assert p.latitudine is None and p.sursa_gps is None
                db.session.delete(p)
                db.session.commit()
        finally:
            with app.app_context():
                ff.set_flag('teren-pontaj-bulk', False)

    def test_duplicat_omis_restul_trece(self, app, authenticated_client, echipa):
        """Un angajat cu pontaj existent in ziua aleasa e omis; restul se salveaza."""
        from models import db, Pontaj
        ziua = date(2025, 10, 9)
        existent_aid = echipa['angajat_ids'][0]
        with app.app_context():
            ff.set_flag('teren-pontaj-bulk', True)
            for aid in echipa['angajat_ids']:
                Pontaj.query.filter_by(angajat_id=aid, data=ziua).delete()
            db.session.add(Pontaj(angajat_id=existent_aid,
                                  proiect_id=echipa['proiect_id'],
                                  data=ziua, ore_lucrate=8, status='draft'))
            db.session.commit()
        try:
            r = _post_echipa(
                authenticated_client, echipa['proiect_id'],
                echipa['angajat_ids'], ziua.isoformat(),
            )
            assert r.status_code in (302, 200)
            with app.app_context():
                # angajatul cu duplicat ramane cu un singur pontaj (8h, neschimbat)
                dupl = Pontaj.query.filter_by(angajat_id=existent_aid, data=ziua).all()
                assert len(dupl) == 1
                assert float(dupl[0].ore_lucrate) == 8.0
                # ceilalti 2 angajati au pontaje noi
                noi = Pontaj.query.filter_by(data=ziua).filter(
                    Pontaj.angajat_id.in_(echipa['angajat_ids'][1:])
                ).all()
                assert len(noi) == 2
                for p in Pontaj.query.filter_by(data=ziua).filter(
                        Pontaj.angajat_id.in_(echipa['angajat_ids'])).all():
                    db.session.delete(p)
                db.session.commit()
        finally:
            with app.app_context():
                ff.set_flag('teren-pontaj-bulk', False)


class TestCreeazaPontajeBulkUnit:
    def test_helper_calcul_ore_si_skip(self, app, echipa):
        """creeaza_pontaje_bulk: calcul ore corect + skip pe duplicat, fara commit."""
        from models import db, Pontaj
        from routes.pontaje import creeaza_pontaje_bulk
        ziua = date(2025, 10, 10)
        aids = echipa['angajat_ids']
        with app.app_context():
            for aid in aids:
                Pontaj.query.filter_by(angajat_id=aid, data=ziua).delete()
            # pre-existent pentru primul angajat -> trebuie omis
            db.session.add(Pontaj(angajat_id=aids[0], proiect_id=echipa['proiect_id'],
                                  data=ziua, ore_lucrate=8, status='draft'))
            db.session.commit()

            randuri = [{'angajat_id': aid, 'ora_start': '08:00',
                        'ora_sfarsit': '16:00'} for aid in aids]
            ok, skip, create = creeaza_pontaje_bulk(
                echipa['proiect_id'], ziua, randuri, actiune='trimite',
            )
            assert ok == 2 and skip == 1
            assert len(create) == 2
            for p in create:
                assert p.status == 'trimis'
                assert float(p.ore_lucrate) == 7.5
            db.session.rollback()
            # dupa rollback, doar pontajul pre-existent ramane
            for aid in aids:
                Pontaj.query.filter_by(angajat_id=aid, data=ziua).delete()
            db.session.commit()
