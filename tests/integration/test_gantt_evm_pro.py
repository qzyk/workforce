"""
Teste de integrare pentru EVM pe plan din tracking (Gantt Faza 3) - calea cu DB.

Completeaza tests/unit/test_gantt_evm_pro.py (functii pure peste dict-uri) cu partea
REALA, end-to-end: plan salvat + baseline activ (snapshot inghetat) + jurnal
GanttProgres la date diferite + pontaje pentru AC. Verifica VALORI EVM concrete:
  - EV ponderat pe valoarea inghetata a activitatilor, la o data de stare, luand
    ultima masuratoare <= data de stare pe cheie (functie-treapta in timp).
  - AC din pontaje+utilaj (sursa 'pontaje+utilaj'); fallback pe SituatieLunara
    cand nu exista pontaje/consum (sursa 'situatie').
  - SPI = EV/PV si CPI = EV/AC numerice; status (ok/atentie/critic).
  - ramurile None: flag 'gantt-evm-pro' OFF, plan fara baseline, plan fara progres.
  - ruta /gantt/plan/<id>/evm: 404 cu flag OFF, JSON cu flag ON, ?data_stare invalid
    -> azi (nu arunca).
  - cache pe instanta de plan: al doilea apel pe acelasi (plan, data_stare) NU
    re-interogheaza (nu reruleaza agregarea EV).

Cheile activitatilor sunt cheile stabile produse de pipeline (cheie_stabila), citite
inapoi din snapshot-ul de baseline ca sa nu depindem de pretul exact al motorului.
"""
import io
from datetime import date
from unittest import mock

import pytest

from services.gantt import evm_pro, tracking_db


# F3 minimal: 2 articole -> 2 activitati cu VALORI explicite (pret unitar x cantitate),
# ca BAC-ul sa nu fie 0 (fara deviz pretuit). valoare(ART001)=100*6=600, (ART002)=100*4=400.
SAMPLE = (
    b"cod_articol;denumire;um;cantitate;pret unitar;obiect;tronson\n"
    b"ART001;Sapatura mecanizata;mc;100;6;Retea;Strada A\n"
    b"ART002;Pozare conducta PEHD;m;100;4;Retea;Strada A\n"
)

# Date de stare folosite (start plan = luni 2026-06-01, doar Lu-Vi fara calendar).
DATA_START = date(2026, 6, 1)
DS_PARTIAL = date(2026, 6, 9)    # ART001 inca la 40%, ART002 la 50%
DS_FINAL = date(2026, 6, 15)     # ART001 la 100%, ART002 la 50% (dupa toata curba PV)


@pytest.fixture(autouse=True)
def _curata(app):
    """Sterge datele de test (plan/baseline/progres/pontaje/proiect/flags) dupa fiecare."""
    yield
    from models import (db, GanttPlan, GanttBaseline, GanttProgres,
                        Pontaj, AngajatProiect, Angajat, Proiect,
                        SituatieLunara, Contract)
    from services.feature_flags import FeatureFlag
    with app.app_context():
        try:
            for m in (GanttProgres, GanttBaseline):
                for row in m.query.all():
                    db.session.delete(row)
            # rupem legatura baseline_activ_id inainte sa stergem planul
            for p in GanttPlan.query.all():
                p.baseline_activ_id = None
            db.session.flush()
            for m in (GanttPlan, Pontaj, AngajatProiect, SituatieLunara,
                      Contract, Angajat):
                for row in m.query.all():
                    db.session.delete(row)
            for pr in Proiect.query.filter(
                    Proiect.cod_proiect.like('EVMPRO-%')).all():
                db.session.delete(pr)
            for ff in FeatureFlag.query.filter(
                    FeatureFlag.key.in_(('gantt-tracking', 'gantt-evm-pro'))).all():
                db.session.delete(ff)
            db.session.commit()
        except Exception:
            db.session.rollback()


def _activeaza(app, tracking=True, evm=True):
    from services.feature_flags import set_flag
    with app.app_context():
        if tracking:
            set_flag('gantt-tracking', True)
        if evm:
            set_flag('gantt-evm-pro', True)


def _salveaza_plan(client, app, proiect_id=None, nume='Plan EVM'):
    """Genereaza + salveaza un plan din SAMPLE; seteaza data_start fixa. Intoarce id."""
    client.post('/gantt/genereaza',
                data={'fisier': (io.BytesIO(SAMPLE), 'plan.csv')},
                content_type='multipart/form-data')
    data = {'nume': nume}
    if proiect_id:
        data['proiect_id'] = str(proiect_id)
    client.post('/gantt/salveaza', data=data)
    from models import db, GanttPlan
    with app.app_context():
        p = GanttPlan.query.filter_by(nume=nume).first()
        p.data_start = DATA_START
        db.session.commit()
        return p.id


def _inghet_baseline(client, pid):
    r = client.post(f'/gantt/plan/{pid}/baseline', data={'nume': 'BL EVM'})
    assert r.status_code == 302


def _chei_valori(app, pid):
    """(cheieA, valA, cheieB, valB, bac) din snapshot-ul baseline-ului activ."""
    from models import db, GanttPlan
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        snap = tracking_db.baseline_activ(p, None)
    assert snap, 'baseline activ trebuie sa existe cu flag tracking ON'
    valori = evm_pro._valori_din_baseline(snap)
    # ordonam dupa cod ca sa avem ART001 (A) inaintea ART002 (B)
    items = sorted(snap['activitati'].items(), key=lambda kv: kv[1].get('cod', ''))
    (cheieA, _), (cheieB, _) = items[0], items[1]
    bac = float((snap.get('meta') or {}).get('bac') or 0)
    return cheieA, valori[cheieA], cheieB, valori[cheieB], bac


def _progres(client, pid, cheie, procent, data_zi):
    r = client.post(f'/gantt/plan/{pid}/progres',
                    json={'data_stare': data_zi.isoformat(),
                          'progrese': [{'cheie': cheie, 'procent': procent,
                                        'data': data_zi.isoformat()}]})
    assert r.status_code == 200


def _proiect_cu_pontaj(app, ore=10.0, tarif=50.0, data_zi=date(2026, 6, 4)):
    """Proiect + angajat alocat (tarif) + 1 pontaj. AC asteptat = tarif*ore."""
    from models import db, Proiect, Angajat, AngajatProiect, Pontaj
    with app.app_context():
        pr = Proiect(cod_proiect='EVMPRO-001', nume='Proiect EVM',
                     data_start=DATA_START, beneficiar='B', status='activ')
        db.session.add(pr)
        db.session.flush()
        a = Angajat(nume='EVM', prenume='Test', cnp='2980101010102',
                    functie='Muncitor', tip_contract='nedeterminat',
                    salariu_baza=5000, data_angajare=date(2024, 1, 1), status='activ')
        db.session.add(a)
        db.session.flush()
        db.session.add(AngajatProiect(angajat_id=a.id, proiect_id=pr.id,
                                      data_start=DATA_START, tarif_negociat=tarif))
        db.session.add(Pontaj(angajat_id=a.id, proiect_id=pr.id, data=data_zi,
                              ore_lucrate=ore, ore_normale=8, status='aprobat'))
        db.session.commit()
        return pr.id


# ============================================================ valori concrete
def test_evm_valori_concrete_end_to_end(authenticated_client, app):
    """Plan real + baseline + progres + pontaj -> EV/PV/SPI/CPI numerice.

    ART001 -> 40% (06-05) apoi 100% (06-12); ART002 -> 50% (06-08).
    La DS_PARTIAL (06-09): ART001=40% (masuratoarea de 06-12 e dupa data), ART002=50%.
    EV = 0.40*valA + 0.50*valB; PV<100% (curba inca neterminata); AC=500 (10h*50);
    SPI = EV/PV, CPI = EV/AC, status critic/atentie dupa praguri.
    """
    proiect_id = _proiect_cu_pontaj(app)
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app, proiect_id=proiect_id)
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)
    assert bac > 0 and valA > 0 and valB > 0

    _progres(authenticated_client, pid, cheieA, 40, date(2026, 6, 5))
    _progres(authenticated_client, pid, cheieA, 100, date(2026, 6, 12))
    _progres(authenticated_client, pid, cheieB, 50, date(2026, 6, 8))

    from models import db, GanttPlan
    from services.evm import _pv_la_data
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        rez = evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL)
        snap = tracking_db.baseline_activ(p, None)

    assert rez is not None
    # EV concret: ultima masuratoare <= 06-09 -> A la 40%, B la 50%
    ev_asteptat = round(0.40 * valA + 0.50 * valB, 2)
    assert rez['ev_val'] == round(ev_asteptat, 0)
    assert rez['nr_activitati_cu_progres'] == 2
    # PV concret din curba baseline-ului, mapata pe date (procent la 06-09)
    pv_pts, bac_snap, _ = evm_pro._pv_din_baseline_gantt(snap, DATA_START)
    pv_pct = _pv_la_data(pv_pts, DS_PARTIAL)
    pv_val = round(pv_pct / 100.0 * bac_snap, 0)
    assert rez['pv_val'] == pv_val
    # AC concret: 10h * 50 lei = 500, din pontaje
    assert rez['ac'] == 500.0 and rez['ac_sursa'] == 'pontaje+utilaj'
    # SPI / CPI numerice (= EV/PV, EV/AC), nu None
    assert rez['spi'] == round(ev_asteptat / pv_val, 2)
    assert rez['cpi'] == round(ev_asteptat / 500.0, 2)
    # forecast reutilizat din services.evm._prognoza (EAC pe CPI cand AC>0)
    assert rez['prognoza']['eac_varianta'] == 'cpi'
    assert rez['prognoza']['eac'] == round(bac_snap / rez['cpi'], 0)
    # status derivat din praguri (CPI/SPI < 0.9 -> critic; < 1.0 -> atentie)
    if rez['cpi'] < 0.9 or rez['spi'] < 0.9:
        assert rez['status'] == 'critic'
    elif rez['cpi'] < 1.0 or rez['spi'] < 1.0:
        assert rez['status'] == 'atentie'
    else:
        assert rez['status'] == 'ok'


def test_ev_avanseaza_in_timp_la_data_finala(authenticated_client, app):
    """A doua masuratoare (100% la 06-12) e luata abia la o data de stare ulterioara.

    La DS_FINAL (06-15, dupa toata curba): ART001=100%, ART002=50% -> EV creste;
    PV = 100% (data >= ultimul punct al curbei) -> pv_val == BAC."""
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app)
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)

    _progres(authenticated_client, pid, cheieA, 40, date(2026, 6, 5))
    _progres(authenticated_client, pid, cheieA, 100, date(2026, 6, 12))
    _progres(authenticated_client, pid, cheieB, 50, date(2026, 6, 8))

    from models import db, GanttPlan
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        rez_partial = evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL)
        # instanta noua ca sa nu lovim cache-ul de la apelul anterior
        p2 = db.session.get(GanttPlan, pid)
        rez_final = evm_pro.evm_pe_plan(p2, None, data_stare=DS_FINAL)

    ev_partial = round(0.40 * valA + 0.50 * valB, 0)
    ev_final = round(1.00 * valA + 0.50 * valB, 0)
    assert rez_partial['ev_val'] == ev_partial
    assert rez_final['ev_val'] == ev_final
    assert ev_final > ev_partial            # progresul a avansat in timp
    # PV la final = 100% din BAC (data de stare dupa ultimul punct al curbei)
    assert rez_final['pv_val'] == round(bac, 0)
    assert rez_final['pv_pct'] == 100.0


def test_ac_fallback_situatie_lunara(authenticated_client, app):
    """Fara pontaje/consum dar cu SituatieLunara -> AC din valoarea cumulata, sursa 'situatie'."""
    from models import db, Proiect, Contract, SituatieLunara
    with app.app_context():
        pr = Proiect(cod_proiect='EVMPRO-002', nume='Proiect EVM sit',
                     data_start=DATA_START, beneficiar='B', status='activ')
        db.session.add(pr)
        db.session.flush()
        ct = Contract(proiect_id=pr.id, nr_contract='C-EVM-1',
                      data_semnare=DATA_START, valoare_totala=10000)
        db.session.add(ct)
        db.session.flush()
        db.session.add(SituatieLunara(
            proiect_id=pr.id, contract_id=ct.id, luna=6, an=2026,
            data_emitere=date(2026, 6, 5), valoare_cumulat_la_zi=1234.0,
            status='emisa'))
        db.session.commit()
        proiect_id = pr.id

    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app, proiect_id=proiect_id)
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)
    _progres(authenticated_client, pid, cheieA, 50, date(2026, 6, 6))

    from models import db, GanttPlan
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        rez = evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL)

    assert rez['ac'] == 1234.0 and rez['ac_sursa'] == 'situatie'
    # CPI = EV / 1234 (numeric)
    ev = round(0.50 * valA, 2)
    assert rez['cpi'] == round(ev / 1234.0, 2)


def test_ac_zero_fara_proiect(authenticated_client, app):
    """Plan fara proiect -> AC=0, sursa 'fara', CPI None (diviziune cu 0), EAC atipica."""
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app)   # fara proiect_id
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)
    _progres(authenticated_client, pid, cheieA, 50, date(2026, 6, 6))

    from models import db, GanttPlan
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        rez = evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL)

    assert rez['ac'] == 0.0 and rez['ac_sursa'] == 'fara'
    assert rez['cpi'] is None                       # EV/0 -> None
    assert rez['prognoza']['eac_varianta'] == 'atipica'


# ============================================================ ramuri None
def test_none_cu_flag_off(authenticated_client, app):
    """Flag 'gantt-evm-pro' OFF -> evm_pe_plan None (chiar cu baseline + progres)."""
    # activam doar tracking (ca sa putem ingheta baseline), NU evm-pro
    _activeaza(app, tracking=True, evm=False)
    pid = _salveaza_plan(authenticated_client, app)
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)
    _progres(authenticated_client, pid, cheieA, 50, date(2026, 6, 6))

    from models import db, GanttPlan
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        assert evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL) is None


def test_none_fara_baseline(authenticated_client, app):
    """Flag ON dar plan FARA baseline activ -> None (nu avem referinta PV)."""
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app)
    # NU inghetam baseline
    from models import db, GanttPlan
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        assert p.baseline_activ_id is None
        assert evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL) is None


def test_none_fara_progres(authenticated_client, app):
    """Flag ON + baseline activ dar FARA nicio masuratoare de progres -> None."""
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app)
    _inghet_baseline(authenticated_client, pid)
    # niciun progres adaugat
    from models import db, GanttPlan, GanttProgres
    with app.app_context():
        assert GanttProgres.query.filter_by(plan_id=pid).count() == 0
        p = db.session.get(GanttPlan, pid)
        assert evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL) is None


def test_none_progres_doar_dupa_data_stare(authenticated_client, app):
    """Progres exista, dar toate masuratorile sunt DUPA data de stare -> None."""
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app)
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)
    _progres(authenticated_client, pid, cheieA, 50, date(2026, 6, 20))  # dupa DS_PARTIAL

    from models import db, GanttPlan
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        assert evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL) is None


# ============================================================ ruta /evm
def test_ruta_evm_404_cu_flag_off(authenticated_client, app):
    """Ruta /gantt/plan/<id>/evm -> 404 cu flag 'gantt-evm-pro' OFF (comportament neschimbat)."""
    _activeaza(app, tracking=True, evm=False)
    pid = _salveaza_plan(authenticated_client, app)
    _inghet_baseline(authenticated_client, pid)
    _progres_off_safe(authenticated_client, pid)
    r = authenticated_client.get(f'/gantt/plan/{pid}/evm')
    assert r.status_code == 404


def _progres_off_safe(client, pid):
    """Adauga progres daca ruta de progres e deschisa (depinde de gantt-tracking)."""
    client.post(f'/gantt/plan/{pid}/progres',
                json={'progrese': [{'cheie': 'x', 'procent': 10}]})


def test_ruta_evm_json_cu_flag_on(authenticated_client, app):
    """Ruta /evm cu flag ON + baseline + progres -> 200 JSON cu valori EVM."""
    proiect_id = _proiect_cu_pontaj(app)
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app, proiect_id=proiect_id)
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)
    _progres(authenticated_client, pid, cheieA, 100, date(2026, 6, 5))
    _progres(authenticated_client, pid, cheieB, 50, date(2026, 6, 8))

    r = authenticated_client.get(
        f'/gantt/plan/{pid}/evm?data_stare={DS_PARTIAL.isoformat()}')
    assert r.status_code == 200
    js = r.get_json()
    assert js['plan_id'] == pid
    assert js['data_stare'] == DS_PARTIAL.isoformat()
    # EV concret prin ruta: A la 100%, B la 50%
    assert js['ev_val'] == round(1.00 * valA + 0.50 * valB, 0)
    assert js['ac'] == 500.0 and js['ac_sursa'] == 'pontaje+utilaj'
    assert js['cpi'] is not None and js['spi'] is not None


def test_ruta_evm_data_stare_invalida_cade_pe_azi(authenticated_client, app):
    """?data_stare invalid -> ruta foloseste azi (nu arunca 400/500)."""
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app)
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)
    # progres cu data veche (<= azi) ca rezultatul sa nu fie None pe data azi
    _progres(authenticated_client, pid, cheieA, 60, date(2026, 1, 10))

    r = authenticated_client.get(f'/gantt/plan/{pid}/evm?data_stare=nu-e-data')
    assert r.status_code == 200
    assert r.get_json()['data_stare'] == date.today().isoformat()


def test_ruta_evm_404_fara_baseline(authenticated_client, app):
    """Ruta /evm cu flag ON dar plan fara baseline -> 404 (rez None)."""
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app)
    assert authenticated_client.get(f'/gantt/plan/{pid}/evm').status_code == 404


# ============================================================ cache pe instanta
def test_cache_pe_plan_nu_reinterogheaza(authenticated_client, app):
    """Al doilea apel pe acelasi (plan, data_stare) foloseste cache-ul: agregarea
    EV (_ev_la_data) ruleaza O SINGURA DATA pentru aceeasi cheie."""
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app)
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)
    _progres(authenticated_client, pid, cheieA, 50, date(2026, 6, 6))

    from models import db, GanttPlan
    real_ev = evm_pro._ev_la_data
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        with mock.patch('services.gantt.evm_pro._ev_la_data',
                        side_effect=real_ev) as spion:
            r1 = evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL)
            r2 = evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL)   # din cache
            assert spion.call_count == 1          # a doua oara: cache, fara agregare
    assert r1 is r2                                # exact acelasi obiect din cache


def test_cache_distinct_pe_data_stare(authenticated_client, app):
    """Cache pe cheie = data de stare: date diferite -> agregari separate (2 apeluri)."""
    _activeaza(app)
    pid = _salveaza_plan(authenticated_client, app)
    _inghet_baseline(authenticated_client, pid)
    cheieA, valA, cheieB, valB, bac = _chei_valori(app, pid)
    _progres(authenticated_client, pid, cheieA, 50, date(2026, 6, 6))

    from models import db, GanttPlan
    real_ev = evm_pro._ev_la_data
    with app.app_context():
        p = db.session.get(GanttPlan, pid)
        with mock.patch('services.gantt.evm_pro._ev_la_data',
                        side_effect=real_ev) as spion:
            evm_pro.evm_pe_plan(p, None, data_stare=DS_PARTIAL)
            evm_pro.evm_pe_plan(p, None, data_stare=DS_FINAL)    # alta cheie de cache
            assert spion.call_count == 2
