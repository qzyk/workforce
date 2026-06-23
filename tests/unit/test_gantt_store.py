"""
Teste pentru overlay-ul de configurare Gantt (services/gantt/store.py).

Verifica contractul Faza 2:
- fara DB / fara context -> store cade pe JSON (zero regresie);
- cu DB seed-uit (ca migratia 0012) -> store reproduce EXACT regulile din JSON,
  iar MotorPlanificare produce acelasi rezultat ca pe JSON pur.
"""
import io

from services.gantt import store, config_loader as cfg
from services.gantt import import_engine
from services.gantt.pipeline import MotorPlanificare


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


# ----------------------------------------------------- fallback JSON (fara DB)
def test_store_fallback_json_fara_context():
    # in afara unui app context -> store intoarce exact JSON-ul
    assert store.clasificare() == cfg.incarca('clasificare', cfg.CLASIFICARE_IMPLICITA)
    assert store.dependinte() == cfg.incarca('dependinte', cfg.DEPENDINTE_IMPLICITE)
    col_json = cfg.incarca('setari', cfg.SETARI_IMPLICITE)['coloane']
    assert store.coloane() == col_json


def test_semnatura_antet_stabila():
    a = ['Nr.', 'Denumire', 'U.M.', 'Cantitate']
    b = ['cantitate', 'u.m.', 'denumire', 'nr.']   # alta ordine + alt case
    assert store.semnatura_antet(a) == store.semnatura_antet(b)
    assert store.semnatura_antet([]) == ''


# ----------------------------------------------------- overlay din DB (seed)
def _seed_din_json(db, models):
    """Mirror al seed-ului din migratia 0012 (din config/gantt/*.json)."""
    setari = cfg.incarca('setari', cfg.SETARI_IMPLICITE)
    for camp, syns in setari['coloane'].items():
        for s in syns:
            db.session.add(models['sin'](camp=camp, sinonim=s, activ=True))
    clas = cfg.incarca('clasificare', cfg.CLASIFICARE_IMPLICITA)
    for cat, words in clas.items():
        for w in words:
            db.session.add(models['cls'](categorie=cat, tip_regula='cuvant',
                                         valoare=w, prioritate=100, activ=True))
    dep = cfg.incarca('dependinte', cfg.DEPENDINTE_IMPLICITE)
    rang = {c: i for i, c in enumerate(dep['ordine_categorii'])}
    for r in dep['relatii']:
        db.session.add(models['rel'](categorie_din=r['from'], categorie_in=r['to'],
                                     tip=r['tip'], decalaj=r['decalaj'],
                                     rang_din=rang.get(r['from']), activ=True))
    db.session.flush()
    return setari, clas, dep


def test_store_overlay_db_reproduce_json(app):
    from models import (db, GanttSinonimColoana, GanttClasificareRegula,
                        GanttRelatieTemplate)
    models = {'sin': GanttSinonimColoana, 'cls': GanttClasificareRegula,
              'rel': GanttRelatieTemplate}
    with app.app_context():
        try:
            setari, clas, dep = _seed_din_json(db, models)

            # coloane: acelasi set de sinonime per camp
            col = store.coloane()
            for camp, syns in setari['coloane'].items():
                assert set(col[camp]) == set(syns), camp

            # clasificare: acelasi set de cuvinte per categorie
            cl = store.clasificare()
            assert set(cl.keys()) == set(clas.keys())
            for cat, words in clas.items():
                assert set(cl[cat]) == set(words), cat

            # dependinte: ordine_categorii reconstruit EXACT + aceleasi relatii
            d = store.dependinte()
            assert d['ordine_categorii'] == dep['ordine_categorii']
            norm = lambda L: {(x['from'], x['to'], x['tip'], x['decalaj']) for x in L}
            assert norm(d['relatii']) == norm(dep['relatii'])
        finally:
            db.session.rollback()


def test_motor_db_vs_json_acelasi_rezultat(app):
    """MotorPlanificare cu DB seed-uit == MotorPlanificare pe JSON pur."""
    from models import (db, GanttSinonimColoana, GanttClasificareRegula,
                        GanttRelatieTemplate)
    models = {'sin': GanttSinonimColoana, 'cls': GanttClasificareRegula,
              'rel': GanttRelatieTemplate}
    articole, _ = import_engine.importa(SAMPLE_CSV, '.csv')
    with app.app_context():
        try:
            setari, clas, dep = _seed_din_json(db, models)
            rez_db = MotorPlanificare().proceseaza(articole)            # din DB (overlay)
            rez_json = MotorPlanificare(clasificare=clas, dependinte=dep,
                                        setari=setari).proceseaza(articole)  # JSON explicit
            assert (rez_db.statistici['activitati_per_categorie']
                    == rez_json.statistici['activitati_per_categorie'])
            assert rez_db.statistici['nr_dependente'] == rez_json.statistici['nr_dependente']
            assert rez_db.statistici['procent_clasificat'] == rez_json.statistici['procent_clasificat']
        finally:
            db.session.rollback()


# ------------------------------------------- capacitati nivelare (Gantt Faza 4)
def _sterge_capacitati(db):
    """seteaza_capacitate face commit intern, deci rollback nu ajunge -> stergem
    explicit randurile de capacitate (curatenie intre teste)."""
    from models import TarifCategorie
    for r in TarifCategorie.query.filter_by(disciplina='gantt-capacitate').all():
        db.session.delete(r)
    db.session.commit()


def test_capacitati_fara_context_gol():
    """Fara context aplicatie -> dict gol (nivelarea nu va misca nimic)."""
    assert store.capacitati_gantt() == {}


def test_seteaza_si_citeste_capacitate(app):
    """Roundtrip: seteaza_capacitate -> capacitati_gantt intoarce valoarea (UPPER)."""
    from models import db
    with app.app_context():
        try:
            row, err = store.seteaza_capacitate('beton', 3)
            assert err is None and row is not None
            cap = store.capacitati_gantt()
            assert cap.get('BETON') == 3          # normalizat UPPER
            # upsert (update) pe aceeasi categorie
            store.seteaza_capacitate('BETON', 5)
            assert store.capacitati_gantt().get('BETON') == 5
            # lista admin
            lst = store.lista_capacitati()
            assert {'categorie': 'BETON', 'capacitate': 5} in lst
        finally:
            _sterge_capacitati(db)


def test_capacitate_zero_sterge(app):
    """capacitate=0 sterge randul -> categoria devine nelimitata (absenta din dict)."""
    from models import db
    with app.app_context():
        try:
            store.seteaza_capacitate('zid', 2)
            assert store.capacitati_gantt().get('ZID') == 2
            _row, err = store.seteaza_capacitate('zid', 0)
            assert err is None
            assert 'ZID' not in store.capacitati_gantt()
        finally:
            _sterge_capacitati(db)


def test_capacitate_invalida(app):
    """Capacitate ne-numerica / negativa -> eroare, nimic salvat."""
    from models import db
    with app.app_context():
        try:
            _row, err = store.seteaza_capacitate('terasamente', 'abc')
            assert err is not None
            _row2, err2 = store.seteaza_capacitate('terasamente', -1)
            assert err2 is not None
            assert 'TERASAMENTE' not in store.capacitati_gantt()
        finally:
            _sterge_capacitati(db)
