"""Teste Faza 2: extrase resurse C6/C7/C8 - parser auto-detect + import pe proiect."""
from datetime import date
from io import BytesIO

C7 = (b"Lista cuprinzand consumurile cu mana de lucru\n"
      b"Nr;Denumirea meseriei;Consumul cu manopera;Tarif mediu;Valoarea;Procent\n"
      b"0;1;2;3;4;5\n"
      b"1;12300 - Izolator termic;208.2;30;6246;100\n"
      b"2;31000 - Zidar;651;30;19530;100\n"
      b"Ore Manopera;;859.2;TOTAL;25776;\n")

C6 = (b"Lista cuprinzand consumurile de resurse materiale\n"
      b"Nr;Denumirea resursei materiale;U.M.;Consumul cuprins in oferta;Pretul unitar;Valoarea;Furnizorul\n"
      b"0;1;2;3;4;5;6\n"
      b"1;100014449 - Surub fixare;buc;2700;2.41;6504.3;Depozit\n"
      b"TOTAL;;;;;6504.3;\n")

C8 = (b"Lista cuprinzand consumurile de ore de functionare a utilajelor\n"
      b"Nr;Denumirea utilajului;Ore de functionare;Tariful unitar;Valoarea\n"
      b"0;1;2;3;4\n"
      b"1;20000067 - Malaxor;39.36;7.51;295.59\n"
      b"TOTAL Utilaje;;;;295.59\n")


def test_parser_c6_c7_c8(app):
    from services.deviz_extras import parse_extras
    with app.app_context():
        tip, rows = parse_extras(C7, '.csv')
        assert tip == 'manopera' and len(rows) == 2          # TOTAL sarit
        assert rows[0]['cod'] == '12300' and rows[0]['um'] == 'ora'
        assert rows[0]['cantitate'] == 208.2 and rows[0]['valoare'] == 6246

        tip6, rows6 = parse_extras(C6, '.csv')
        assert tip6 == 'material' and len(rows6) == 1
        assert rows6[0]['um'] == 'buc' and rows6[0]['furnizor'] == 'Depozit'

        tip8, rows8 = parse_extras(C8, '.csv')
        assert tip8 == 'utilaj' and len(rows8) == 1 and rows8[0]['cantitate'] == 39.36


def test_ruta_upload_lista_sterge(authenticated_client, app):
    from models import db, Proiect, ExtrasResursa
    with app.app_context():
        p = Proiect(cod_proiect='RES-T', nume='Resurse test', data_start=date.today())
        db.session.add(p); db.session.commit()
        pid = p.id
    try:
        # upload C7 -> manopera
        r = authenticated_client.post(f'/proiecte/{pid}/resurse/upload',
            data={'fisier': (BytesIO(C7), 'C7.csv')},
            content_type='multipart/form-data', follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            assert ExtrasResursa.query.filter_by(proiect_id=pid, tip='manopera').count() == 2
        # pagina arata extrasul
        rl = authenticated_client.get(f'/proiecte/{pid}/resurse')
        assert rl.status_code == 200 and b'Izolator termic' in rl.data and b'C7' in rl.data
        # re-import inlocuieste (tot 2, nu 4)
        authenticated_client.post(f'/proiecte/{pid}/resurse/upload',
            data={'fisier': (BytesIO(C7), 'C7.csv')},
            content_type='multipart/form-data', follow_redirects=True)
        with app.app_context():
            assert ExtrasResursa.query.filter_by(proiect_id=pid, tip='manopera').count() == 2
        # sterge
        authenticated_client.post(f'/proiecte/{pid}/resurse/sterge/manopera',
                                  follow_redirects=True)
        with app.app_context():
            assert ExtrasResursa.query.filter_by(proiect_id=pid).count() == 0
    finally:
        with app.app_context():
            ExtrasResursa.query.filter_by(proiect_id=pid).delete()
            pr = db.session.get(Proiect, pid)
            if pr:
                db.session.delete(pr)
            db.session.commit()
