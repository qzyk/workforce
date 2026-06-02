"""Teste: toggle clasificare (cu/fara) + fix export MSP/P6 cu <Name> gol/invalid."""
import xml.etree.ElementTree as ET
from io import BytesIO

MSP_NS = '{http://schemas.microsoft.com/project}'

SAMPLE = (
    b"cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    b"TS01;Sapatura mecanizata pamant;mc;100;O1;T1;Terasamente\n"
    b"X02;Articol oarecare;buc;5;O1;T1;CategDinFisier\n"
)


def _arts():
    from services.gantt.modele import ArticolF3
    return [
        ArticolF3(cod_articol='TS01', denumire='Sapatura mecanizata pamant', um='mc',
                  cantitate=100, obiect='O1', tronson='T1', categorie='Terasamente'),
        ArticolF3(cod_articol='X02', denumire='', um='buc', cantitate=5,
                  obiect='O1', tronson='T1', categorie=''),   # nume GOL
    ]


def test_clasificare_on_vs_off(app):
    """clasifica=True foloseste dictionarul; False pastreaza categoria din fisier."""
    from services.gantt.pipeline import MotorPlanificare
    with app.app_context():
        motor = MotorPlanificare()
        a_on = motor.proceseaza(_arts(), clasifica=True).activitati
        a_off = motor.proceseaza(_arts(), clasifica=False).activitati
    # cu clasificare: TS01 -> categorie din dictionar (SAPATURA)
    assert a_on[0].categorie_tehnologica == 'SAPATURA'
    # fara clasificare: categoria ramane cea din fisier, ca atare
    assert a_off[0].categorie_tehnologica == 'Terasamente'
    assert a_off[0].increder_clasificare == 1.0


def test_export_msp_nume_gol_devine_valid(app):
    """Nod cu nume gol -> <Name> non-gol in MSP XML (fix-ul erorii UID=78)."""
    from services.gantt.pipeline import MotorPlanificare
    from services.gantt import export
    with app.app_context():
        r = MotorPlanificare().proceseaza(_arts(), clasifica=False)
        xml = export.export_msproject_xml(r.activitati, r.noduri_wbs, nume_proiect='T')
    root = ET.fromstring(xml)   # parseaza => XML valid (fara control chars)
    nume_goale = [t.find(f'{MSP_NS}Name').text for t in root.iter(f'{MSP_NS}Task')
                  if not (t.find(f'{MSP_NS}Name').text or '').strip()]
    assert nume_goale == []     # niciun <Name> gol


def test_export_curata_control_chars(app):
    """Caractere de control invalide XML sunt curatate (nu strica importul)."""
    from services.gantt import export
    from services.gantt.modele import Activitate, NodWBS
    acts = [Activitate(id='A1', cod='C1', nume='Beton\x07 turnat\x1f', categorie_tehnologica='X',
                       obiect='O', tronson='T', um='mc', cantitate=1, durata=1)]
    noduri = [NodWBS(wbs_id='1', nume='Grup\x0brau', nivel=1, tip='grup', parinte_id=None,
                     activitate_id=None),
              NodWBS(wbs_id='1.1', nume='Beton\x07 turnat\x1f', nivel=2, tip='activitate',
                     parinte_id='1', activitate_id='A1')]
    xml = export.export_msproject_xml(acts, noduri, nume_proiect='P')
    root = ET.fromstring(xml)   # nu arunca => fara caractere invalide
    nume = [t.find(f'{MSP_NS}Name').text for t in root.iter(f'{MSP_NS}Task')]
    assert all('\x07' not in (n or '') and '\x1f' not in (n or '') for n in nume)
    assert 'Beton turnat' in nume   # control chars scoase, restul pastrat


def test_ruta_genereaza_fara_clasificare(authenticated_client):
    """POST fara checkbox 'clasifica' -> sesiunea retine alegerea (False)."""
    r = authenticated_client.post('/gantt/genereaza', data={
        'fisier': (BytesIO(SAMPLE), 'test.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    with authenticated_client.session_transaction() as sess:
        assert sess.get('gantt_clasifica') is False


def test_ruta_genereaza_cu_clasificare(authenticated_client):
    """POST cu checkbox 'clasifica' bifat -> sesiunea retine True."""
    r = authenticated_client.post('/gantt/genereaza', data={
        'fisier': (BytesIO(SAMPLE), 'test.csv'), 'clasifica': 'on',
    }, content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    with authenticated_client.session_transaction() as sess:
        assert sess.get('gantt_clasifica') is True
