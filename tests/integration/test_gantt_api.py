"""
Teste de integrare pentru blueprint-ul Gantt (UI + REST API).
Foloseste fixture-urile app / authenticated_client din conftest.
"""
import io

SAMPLE = (
    "cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    "ART001;Trasare traseu;m;800;Retea apa;Strada A;Terasamente\n"
    "ART002;Sapatura mecanizata;mc;1200;Retea apa;Strada A;Terasamente\n"
    "ART003;Pozare conducta PEHD;m;800;Retea apa;Strada A;Conducte\n"
    "ART004;Umplutura compactare;mc;900;Retea apa;Strada A;Terasamente\n"
    "ART005;Refacere asfalt carosabil;mp;640;Retea apa;Strada A;Drumuri\n"
).encode('utf-8')


def _fisier():
    return {'fisier': (io.BytesIO(SAMPLE), 'f3.csv')}


def test_gantt_index_pagina(authenticated_client):
    r = authenticated_client.get('/gantt/')
    assert r.status_code == 200
    assert b'Planificare Gantt' in r.data


def test_gantt_api_pipeline(authenticated_client):
    r = authenticated_client.post('/gantt/api/pipeline', data=_fisier(),
                                  content_type='multipart/form-data')
    assert r.status_code == 200
    j = r.get_json()
    assert j['statistici']['nr_activitati'] == 5
    assert j['statistici']['nr_dependente'] >= 4
    assert j['raport']['valid'] is True
    # fiecare activitate are wbs_id + categorie
    cats = {a['categorie_tehnologica'] for a in j['activitati']}
    assert 'SAPATURA' in cats and 'POZARE_CONDUCTA' in cats


def test_gantt_api_import_apoi_classify(authenticated_client):
    r = authenticated_client.post('/gantt/api/import', data=_fisier(),
                                  content_type='multipart/form-data')
    assert r.status_code == 200
    articole = r.get_json()['articole']
    assert len(articole) == 5

    r2 = authenticated_client.post('/gantt/api/classify', json={'articole': articole})
    assert r2.status_code == 200
    acts = r2.get_json()['activitati']
    assert all('categorie_tehnologica' in a for a in acts)


def test_gantt_api_validate_detecteaza_ciclu(authenticated_client):
    activitati = [
        {'id': 'A1', 'cod': 'c1', 'nume': 'A', 'categorie_tehnologica': 'SAPATURA',
         'predecesori': [{'predecesor_id': 'A2', 'tip': 'FS', 'decalaj': 0}]},
        {'id': 'A2', 'cod': 'c2', 'nume': 'B', 'categorie_tehnologica': 'POZARE_CONDUCTA',
         'predecesori': [{'predecesor_id': 'A1', 'tip': 'FS', 'decalaj': 0}]},
    ]
    r = authenticated_client.post('/gantt/api/validate', json={'activitati': activitati})
    assert r.status_code == 200
    j = r.get_json()
    assert j['valid'] is False
    assert any(p['cod'] == 'ciclu' for p in j['probleme'])


def test_gantt_ui_genereaza_si_export(authenticated_client):
    r = authenticated_client.post('/gantt/genereaza', data=_fisier(),
                                  content_type='multipart/form-data')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Planificare generata' in html
    import re
    m = re.search(r'/gantt/export/([0-9a-f]{32})/csv', html)
    assert m, 'token de export lipseste din preview'
    token = m.group(1)
    for fmt, semn in (('csv', b'Activity Name'), ('msproject', b'<Task'),
                      ('primavera', b'Activity'), ('json', b'statistici')):
        rr = authenticated_client.get(f'/gantt/export/{token}/{fmt}')
        assert rr.status_code == 200, fmt
        assert semn in rr.data, fmt


def test_gantt_api_export_csv(authenticated_client):
    activitati = [
        {'id': 'A1', 'cod': 'ART1', 'nume': 'Sapatura', 'categorie_tehnologica': 'SAPATURA',
         'obiect': 'O', 'tronson': 'T', 'durata': 3, 'predecesori': []},
        {'id': 'A2', 'cod': 'ART2', 'nume': 'Pozare', 'categorie_tehnologica': 'POZARE_CONDUCTA',
         'obiect': 'O', 'tronson': 'T', 'durata': 2,
         'predecesori': [{'predecesor_id': 'A1', 'tip': 'FS', 'decalaj': 0}]},
    ]
    r = authenticated_client.post('/gantt/api/export',
                                  json={'activitati': activitati, 'format': 'csv'})
    assert r.status_code == 200
    assert b'Activity Name' in r.data
