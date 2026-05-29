"""
Teste unitare pentru motoarele de planificare Gantt (services/gantt/*).
Nu necesita aplicatia Flask - testeaza direct functiile pure.
"""
import io
import xml.etree.ElementTree as ET

import pytest

from services.gantt.normalizare import fara_diacritice, normalizeaza
from services.gantt import import_engine
from services.gantt.clasificare import Clasificator
from services.gantt.durate import estimeaza_durata
from services.gantt.wbs import genereaza_wbs
from services.gantt.dependinte import genereaza_dependinte
from services.gantt.validare import valideaza
from services.gantt import export as export_engine
from services.gantt.modele import ArticolF3, Activitate, Dependenta, RezultatPlanificare
from services.gantt.pipeline import MotorPlanificare
from services.gantt import config_loader as cfg


SAMPLE_CSV = (
    "cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    "ART001;Trasare traseu;m;800;Retea apa;Strada A;Terasamente\n"
    "ART002;Sapatura mecanizata;mc;1200;Retea apa;Strada A;Terasamente\n"
    "ART003;Pozare conducta PEHD;m;800;Retea apa;Strada A;Conducte\n"
    "ART004;Umplutura compactare;mc;900;Retea apa;Strada A;Terasamente\n"
    "ART005;Refacere asfalt;mp;640;Retea apa;Strada A;Drumuri\n"
    "ART006;Sapatura mecanizata;mc;1100;Retea apa;Strada B;Terasamente\n"
    "ART007;Pozare conducta;m;750;Retea apa;Strada B;Conducte\n"
).encode('utf-8')


# ------------------------------------------------------------------ normalizare
def test_fara_diacritice():
    assert fara_diacritice('săpătură') == 'sapatura'
    assert fara_diacritice('tronson și țeavă') == 'tronson si teava'
    assert normalizeaza('  Săpătură   MECANIZATĂ ') == 'sapatura mecanizata'


# ---------------------------------------------------------------------- import
def test_import_csv_mapeaza_coloane_si_dedup():
    articole, raport = import_engine.importa(SAMPLE_CSV, '.csv')
    assert raport['nr_articole'] == 7
    assert 'cod_articol' in raport['coloane_mapate']
    assert articole[0].obiect == 'Retea apa'
    assert articole[1].cantitate == 1200.0


def test_import_dedup_si_null():
    csv = (
        "cod;denumire;cantitate;obiect;tronson\n"
        "X1;Sapatura;10;O;T\n"
        "X1;Sapatura duplicat cod;20;O;T\n"      # cod duplicat -> redenumit, pastrat
        ";Fara cod dar cu denumire;5;O;T\n"      # fara cod -> cod auto
        "X2;;1;O;T\n"                             # fara denumire -> ignorat
    ).encode('utf-8')
    articole, raport = import_engine.importa(csv, '.csv')
    assert raport['nr_articole'] == 3
    assert raport['nr_duplicate_redenumite'] == 1
    assert raport['nr_randuri_ignorate'] == 1


def test_import_format_necunoscut():
    with pytest.raises(import_engine.EroareImport):
        import_engine.importa(b'x', '.pdf')


# ------------------------------------------------------------------ clasificare
def test_clasificare_exacta_si_diacritice():
    c = Clasificator(cfg.CLASIFICARE_IMPLICITA, cfg.SETARI_IMPLICITE['sinonime'])
    cat, scor = c.clasifica('Săpătură mecanizată în teren tare')
    assert cat == 'SAPATURA' and scor == 1.0
    cat, _ = c.clasifica('Pozare conducta PEHD De160')
    assert cat == 'POZARE_CONDUCTA'


def test_clasificare_sinonim():
    c = Clasificator(cfg.CLASIFICARE_IMPLICITA, cfg.SETARI_IMPLICITE['sinonime'])
    # 'montaj teava' -> sinonim teava->conducta -> 'montaj conducta' = POZARE_CONDUCTA
    cat, _ = c.clasifica('Montaj teava otel')
    assert cat == 'POZARE_CONDUCTA'


def test_clasificare_fuzzy_typo():
    c = Clasificator({'SAPATURA': ['sapatura']}, prag_fuzzy=0.8)
    cat, scor = c.clasifica('sapatraa in teren')  # greseala de scriere
    assert cat == 'SAPATURA' and 0.8 <= scor < 1.0


def test_clasificare_neclasificat():
    c = Clasificator(cfg.CLASIFICARE_IMPLICITA)
    cat, _ = c.clasifica('Articol complet aiurea zzz')
    assert cat is None


# ---------------------------------------------------------------------- durate
def test_durata_din_randament():
    setari = cfg.SETARI_IMPLICITE
    assert estimeaza_durata(1200, 'SAPATURA', setari) == 6   # 1200/200
    assert estimeaza_durata(0, 'SAPATURA', setari) == 1      # min 1
    assert estimeaza_durata(100, None, setari) == 1          # neclasificat -> implicit


# ------------------------------------------------------------------------- wbs
def test_wbs_ierarhie():
    articole, _ = import_engine.importa(SAMPLE_CSV, '.csv')
    motor = MotorPlanificare()
    acts = motor.clasifica_articole(articole)
    noduri = genereaza_wbs(acts, motor.dependinte['ordine_categorii'])
    niveluri = {n.nivel for n in noduri}
    assert niveluri == {1, 2, 3, 4}
    obiecte = [n for n in noduri if n.nivel == 1]
    assert obiecte[0].wbs_id == '1'
    # activitatile au wbs_id de forma a.b.c.d
    act = next(a for a in acts if a.tronson == 'Strada A' and a.categorie_tehnologica == 'SAPATURA')
    assert act.wbs_id.count('.') == 3


# ------------------------------------------------------------------ dependinte
def test_dependinte_lant_si_multiplicare_pe_tronson():
    articole, _ = import_engine.importa(SAMPLE_CSV, '.csv')
    motor = MotorPlanificare()
    rez = motor.proceseaza(articole)
    by_id = {a.id: a for a in rez.activitati}

    # Pozarea de pe Strada A are ca predecesor sapatura de pe Strada A (FS)
    poz_a = next(a for a in rez.activitati if a.tronson == 'Strada A' and a.categorie_tehnologica == 'POZARE_CONDUCTA')
    assert poz_a.predecesori, 'pozarea trebuie sa aiba predecesor'
    pred = by_id[poz_a.predecesori[0].predecesor_id]
    assert pred.categorie_tehnologica == 'SAPATURA' and pred.tronson == 'Strada A'

    # template multiplicat: si Strada B are lant propriu
    poz_b = next(a for a in rez.activitati if a.tronson == 'Strada B' and a.categorie_tehnologica == 'POZARE_CONDUCTA')
    pred_b = by_id[poz_b.predecesori[0].predecesor_id]
    assert pred_b.tronson == 'Strada B'

    # decalaj UMPLUTURA->REFACERE = 2 (din config implicit)
    refacere = next(a for a in rez.activitati if a.tronson == 'Strada A' and a.categorie_tehnologica == 'REFACERE')
    assert any(d.decalaj == 2 for d in refacere.predecesori)


# -------------------------------------------------------------------- validare
def test_validare_ciclu():
    a = Activitate(id='A1', cod='c1', nume='A', categorie_tehnologica='SAPATURA')
    b = Activitate(id='A2', cod='c2', nume='B', categorie_tehnologica='POZARE_CONDUCTA')
    a.predecesori.append(Dependenta('A2', 'FS', 0))
    b.predecesori.append(Dependenta('A1', 'FS', 0))   # ciclu A1<->A2
    rap = valideaza([a, b])
    assert not rap.valid
    assert any(p.cod == 'ciclu' for p in rap.erori)


def test_validare_predecesor_lipsa_si_neclasificat():
    a = Activitate(id='A1', cod='c1', nume='A', categorie_tehnologica=None)
    a.predecesori.append(Dependenta('INEXISTENT', 'FS', 0))
    rap = valideaza([a])
    coduri = {p.cod for p in rap.probleme}
    assert 'predecesor_lipsa' in coduri
    assert 'neclasificat' in coduri


def test_validare_id_duplicat():
    a1 = Activitate(id='DUP', cod='c1', nume='A', categorie_tehnologica='SAPATURA')
    a2 = Activitate(id='DUP', cod='c2', nume='B', categorie_tehnologica='SAPATURA')
    rap = valideaza([a1, a2])
    assert any(p.cod == 'id_duplicat' for p in rap.erori)


# --------------------------------------------------------------------- export
def _rezultat_demo():
    articole, _ = import_engine.importa(SAMPLE_CSV, '.csv')
    return MotorPlanificare().proceseaza(articole)


def test_export_csv_contine_predecesori():
    rez = _rezultat_demo()
    data, mime, ext = export_engine.exporta('csv', rez)
    text = data.decode('utf-8-sig')
    assert text.splitlines()[0].startswith('ID,WBS,Activity Name,Duration,Predecessors')
    assert 'FS' in text  # exista cel putin o relatie FS


def test_export_msproject_xml_valid():
    rez = _rezultat_demo()
    data, _, _ = export_engine.exporta('msproject', rez)
    root = ET.fromstring(data)               # trebuie sa fie XML valid
    ns = '{http://schemas.microsoft.com/project}'
    tasks = root.find(f'{ns}Tasks')
    assert tasks is not None and len(tasks) > 0
    # exista cel putin un PredecessorLink
    assert root.find(f'.//{ns}PredecessorLink') is not None


def test_export_primavera_xml_valid():
    rez = _rezultat_demo()
    data, _, _ = export_engine.exporta('primavera', rez)
    root = ET.fromstring(data)
    assert root.tag == 'APIBusinessObjects'
    assert root.find('.//Activity') is not None
    assert root.find('.//Relationship') is not None


def test_export_format_invalid():
    rez = _rezultat_demo()
    with pytest.raises(ValueError):
        export_engine.exporta('dxf', rez)
