"""Teste pentru baseline EVM materializat (PMB) - Deviz Faza 2.

Acopera: snapshot baseline + evm citeste din baseline; fallback live cand flag OFF
sau fara snapshot (zero regresie); BAC consistent intre baseline si recalcul live;
endpoint POST flag-guard; divergenta BAC vs Contract documentata in meta.
"""
from datetime import date

from services.feature_flags import set_flag

SAMPLE = (
    b"cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    b"A1;Sapatura mecanizata;mc;100;O;T;Terasamente\n"
    b"A2;Pozare conducta PEHD;m;200;O;T;Conducte\n"
)


def _seed(db, Proiect, GanttPlan, cost=50000):
    p = Proiect(cod_proiect='EVM-BL', nume='Baseline test', data_start=date(2026, 1, 1))
    db.session.add(p); db.session.flush()
    db.session.add(GanttPlan(nume='Plan BL', continut=SAMPLE, ext='.csv', nr_activitati=2,
                             durata_zile=10, cost_total=cost, proiect_id=p.id,
                             data_start=date(2026, 1, 1)))
    db.session.commit()
    return p.id


def _cleanup(db, pid, Proiect, GanttPlan):
    from models import EvmBaseline
    # rupem pointerul inainte de a sterge baseline-urile (FK proiecte.baseline_evm_activ_id)
    pr = db.session.get(Proiect, pid)
    if pr:
        pr.baseline_evm_activ_id = None
        db.session.flush()
    for x in EvmBaseline.query.filter_by(proiect_id=pid).all():
        db.session.delete(x)
    for x in GanttPlan.query.filter_by(proiect_id=pid).all():
        db.session.delete(x)
    if pr:
        db.session.delete(pr)
    db.session.commit()


def test_snapshot_creeaza_baseline_activ(app):
    """snapshot_baseline creeaza un EvmBaseline activ si seteaza pointerul pe proiect."""
    from models import db, Proiect, GanttPlan, EvmBaseline
    from services.evm_baseline import snapshot_baseline
    with app.app_context():
        pid = _seed(db, Proiect, GanttPlan)
        bl = snapshot_baseline(pid)
        assert bl is not None and bl.activ is True and float(bl.bac) > 0
        pr = db.session.get(Proiect, pid)
        assert pr.baseline_evm_activ_id == bl.id
        snap = bl  # snapshot are PV inghetat + meta
        import json
        cj = json.loads(snap.continut_json)
        assert cj['pv_curba']                     # curba PV inghetata exista
        assert cj['meta']['plan_id'] is not None
        _cleanup(db, pid, Proiect, GanttPlan)


def test_snapshot_reinghetare_dezactiveaza_vechiul(app):
    """A doua inghetare dezactiveaza baseline-ul vechi (un singur activ pe proiect)."""
    from models import db, Proiect, GanttPlan, EvmBaseline
    from services.evm_baseline import snapshot_baseline
    with app.app_context():
        pid = _seed(db, Proiect, GanttPlan)
        bl1 = snapshot_baseline(pid)
        bl2 = snapshot_baseline(pid)
        assert bl1.id != bl2.id
        db.session.refresh(bl1)
        assert bl1.activ is False and bl2.activ is True
        active = EvmBaseline.query.filter_by(proiect_id=pid, activ=True).count()
        assert active == 1
        pr = db.session.get(Proiect, pid)
        assert pr.baseline_evm_activ_id == bl2.id
        _cleanup(db, pid, Proiect, GanttPlan)


def test_snapshot_fara_plan_intoarce_none(app):
    """Fara plan Gantt nu inghetam nimic (None, nu baseline gol)."""
    from models import db, Proiect
    from services.evm_baseline import snapshot_baseline
    with app.app_context():
        p = Proiect(cod_proiect='EVM-BL0', nume='Fara plan', data_start=date(2026, 1, 1))
        db.session.add(p); db.session.commit()
        pid = p.id
        assert snapshot_baseline(pid) is None
        db.session.delete(db.session.get(Proiect, pid)); db.session.commit()


def test_evm_citeste_din_baseline_flag_on(app):
    """Flag ON + baseline: evm_proiect foloseste PV/BAC din baseline (pv_sursa='baseline')."""
    from models import db, Proiect, GanttPlan
    from services.evm import evm_proiect
    from services.evm_baseline import snapshot_baseline
    with app.app_context():
        set_flag('evm-baseline', True)
        pid = _seed(db, Proiect, GanttPlan)
        bl = snapshot_baseline(pid)
        data = evm_proiect(pid)
        assert data['pv_sursa'] == 'baseline'
        assert data['pv_curba']                   # curba vine din baseline
        # BAC din baseline (rotunjit la 0 in evm) == bac-ul inghetat (rotunjit)
        assert round(data['bac']) == round(float(bl.bac))
        set_flag('evm-baseline', False)
        _cleanup(db, pid, Proiect, GanttPlan)


def test_evm_fallback_live_flag_off(app):
    """Flag OFF: evm_proiect recalculeaza LIVE chiar daca exista snapshot (zero regresie)."""
    from models import db, Proiect, GanttPlan
    from services.evm import evm_proiect
    from services.evm_baseline import snapshot_baseline
    with app.app_context():
        set_flag('evm-baseline', True)
        pid = _seed(db, Proiect, GanttPlan)
        snapshot_baseline(pid)                    # exista un baseline
        set_flag('evm-baseline', False)           # dar flag-ul e OFF
        data = evm_proiect(pid)
        assert data['pv_sursa'] == 'live'         # recalcul live, ignora baseline
        assert data['bac'] > 0
        _cleanup(db, pid, Proiect, GanttPlan)


def test_evm_fallback_live_fara_baseline_flag_on(app):
    """Flag ON dar fara snapshot: evm_proiect cade pe recalcul live (zero regresie)."""
    from models import db, Proiect, GanttPlan
    from services.evm import evm_proiect
    with app.app_context():
        set_flag('evm-baseline', True)
        pid = _seed(db, Proiect, GanttPlan)       # niciun snapshot inghetat
        data = evm_proiect(pid)
        assert data['pv_sursa'] == 'live'
        assert data['bac'] > 0 and data['pv_curba']
        set_flag('evm-baseline', False)
        _cleanup(db, pid, Proiect, GanttPlan)


def test_bac_baseline_consistent_cu_recalcul_live(app):
    """BAC-ul inghetat == BAC-ul recalculat live in momentul inghetarii (aceeasi sursa)."""
    from models import db, Proiect, GanttPlan
    from services.evm import evm_proiect
    from services.evm_baseline import snapshot_baseline
    with app.app_context():
        set_flag('evm-baseline', False)           # masuram live intai
        pid = _seed(db, Proiect, GanttPlan)
        data_live = evm_proiect(pid)
        bac_live = data_live['bac']
        bl = snapshot_baseline(pid)               # inghetam
        # BAC-ul inghetat coincide cu cel live (sursa identica: _pv_calendar)
        assert round(float(bl.bac)) == round(bac_live)
        _cleanup(db, pid, Proiect, GanttPlan)


def test_meta_divergenta_contract_documentata(app):
    """Meta-ul snapshot-ului contine bac_contract + divergenta fata de Contract.valoare_totala."""
    import json
    from models import db, Proiect, GanttPlan, Contract
    from services.evm_baseline import snapshot_baseline
    with app.app_context():
        pid = _seed(db, Proiect, GanttPlan)
        c = Contract(proiect_id=pid, nr_contract='C-BL', data_semnare=date(2026, 1, 1),
                     valoare_totala=40000)
        db.session.add(c); db.session.commit()
        bl = snapshot_baseline(pid)
        meta = json.loads(bl.continut_json)['meta']
        assert meta['bac_contract'] == 40000.0
        # divergenta = (bac_plan - 40000) / 40000 * 100, prezenta (poate fi 0 sau != 0)
        assert 'divergenta_contract_pct' in meta and meta['divergenta_contract_pct'] is not None
        for x in Contract.query.filter_by(proiect_id=pid).all():
            db.session.delete(x)
        db.session.commit()
        _cleanup(db, pid, Proiect, GanttPlan)


def test_get_baseline_activ_flag_off_intoarce_none(app):
    """get_baseline_activ intoarce None cu flag OFF (chiar daca exista snapshot)."""
    from models import db, Proiect, GanttPlan
    from services.evm_baseline import snapshot_baseline, get_baseline_activ
    with app.app_context():
        set_flag('evm-baseline', True)
        pid = _seed(db, Proiect, GanttPlan)
        snapshot_baseline(pid)
        set_flag('evm-baseline', False)
        assert get_baseline_activ(pid) is None
        _cleanup(db, pid, Proiect, GanttPlan)


# ----------------------------------------------------- Endpoint POST baseline

def test_endpoint_baseline_flag_off_404(authenticated_client, app):
    """POST /evm/baseline cu flag OFF -> 404 (endpoint gatuit de flag)."""
    from models import db, Proiect, GanttPlan
    with app.app_context():
        set_flag('evm-baseline', False)
        pid = _seed(db, Proiect, GanttPlan)
    try:
        r = authenticated_client.post(f'/proiecte/{pid}/evm/baseline')
        assert r.status_code == 404
    finally:
        with app.app_context():
            _cleanup(db, pid, Proiect, GanttPlan)


def test_endpoint_baseline_flag_on_creeaza(authenticated_client, app):
    """POST /evm/baseline cu flag ON -> inghetat + redirect; evm-ul citeste din baseline."""
    from models import db, Proiect, GanttPlan, EvmBaseline
    from services.evm import evm_proiect
    with app.app_context():
        set_flag('evm-baseline', True)
        pid = _seed(db, Proiect, GanttPlan)
    try:
        r = authenticated_client.post(f'/proiecte/{pid}/evm/baseline',
                                      follow_redirects=False)
        assert r.status_code == 302
        with app.app_context():
            assert EvmBaseline.query.filter_by(proiect_id=pid, activ=True).count() == 1
            assert evm_proiect(pid)['pv_sursa'] == 'baseline'
    finally:
        with app.app_context():
            set_flag('evm-baseline', False)
            _cleanup(db, pid, Proiect, GanttPlan)


def test_pagina_evm_buton_baseline_flag_gated(authenticated_client, app):
    """Butonul de baseline apare in /evm DOAR cu flag ON (ascuns cu OFF). Pagina ramane OK."""
    from models import db, Proiect, GanttPlan
    with app.app_context():
        pid = _seed(db, Proiect, GanttPlan)
    try:
        with app.app_context():
            set_flag('evm-baseline', False)
        r = authenticated_client.get(f'/proiecte/{pid}/evm')
        assert r.status_code == 200 and b'Earned Value' in r.data
        assert b'Baseline EVM' not in r.data        # ascuns cu flag OFF
        with app.app_context():
            set_flag('evm-baseline', True)
        r = authenticated_client.get(f'/proiecte/{pid}/evm')
        assert r.status_code == 200
        assert b'Baseline EVM' in r.data            # vizibil cu flag ON
        assert b'Ingheata baseline EVM' in r.data
    finally:
        with app.app_context():
            set_flag('evm-baseline', False)
            _cleanup(db, pid, Proiect, GanttPlan)
