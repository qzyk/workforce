"""
Teste unitare pentru stratul de urmarire Gantt (Faza 2 tracking) - functii PURE:
- cheie stabila de activitate (rezista la re-import / reordonare randuri)
- snapshot_baseline + compara_baseline (chei disparute / noi raportate)
- aplica_progres (retained logic: durata ramasa = durata * (1 - pct/100))
- diagrama.sarcini_gantt cu progres real + overlay baseline

Nu necesita Flask/DB - testeaza direct functiile pure peste dataclasses.
"""
from datetime import date

from services.gantt.normalizare import cheie_stabila
from services.gantt.modele import ArticolF3, Activitate
from services.gantt.pipeline import MotorPlanificare
from services.gantt import diagrama, tracking


# ------------------------------------------------------------- cheie stabila
def test_cheie_stabila_determinista():
    c1 = cheie_stabila('ART001', 'Sapatura mecanizata', 'Retea', 'Strada A')
    c2 = cheie_stabila('ART001', 'Sapatura mecanizata', 'Retea', 'Strada A')
    assert c1 == c2 and len(c1) == 16


def test_cheie_stabila_ignora_diacritice_si_spatii():
    # acelasi continut, scris cu diacritice / spatii multiple -> aceeasi cheie
    a = cheie_stabila('ART001', 'Sapatura mecanizata', 'Retea', 'Strada A')
    b = cheie_stabila(' ART001 ', 'Săpătură   mecanizată', 'Rețea', 'Strada A')
    assert a == b


def test_cheie_stabila_diferentiaza_pe_componente():
    baza = cheie_stabila('ART001', 'Sapatura', 'O1', 'T1')
    assert baza != cheie_stabila('ART002', 'Sapatura', 'O1', 'T1')   # cod
    assert baza != cheie_stabila('ART001', 'Sapatura', 'O2', 'T1')   # obiect
    assert baza != cheie_stabila('ART001', 'Sapatura', 'O1', 'T2')   # tronson


def _articole():
    return [
        ArticolF3(cod_articol='ART001', denumire='Sapatura mecanizata', um='mc',
                  cantitate=100, obiect='Retea', tronson='Strada A', categorie='Terasamente'),
        ArticolF3(cod_articol='ART002', denumire='Pozare conducta PEHD', um='m',
                  cantitate=200, obiect='Retea', tronson='Strada A', categorie='Conducte'),
    ]


def test_cheie_stabila_la_reimport_cu_ordine_schimbata():
    """Aceeasi cheie pe activitate, indiferent de ordinea randurilor in F3
    (id-ul A000001 se schimba, cheia stabila NU)."""
    m = MotorPlanificare()
    arts = _articole()
    r1 = m.proceseaza(arts, clasifica=False)
    r2 = m.proceseaza(list(reversed(arts)), clasifica=False)

    chei1 = {a.cod: a.cheie for a in r1.activitati}
    chei2 = {a.cod: a.cheie for a in r2.activitati}
    assert chei1 == chei2
    # id-urile insa difera (volatile pe ordine)
    id1 = {a.cod: a.id for a in r1.activitati}
    id2 = {a.cod: a.id for a in r2.activitati}
    assert id1 != id2


# ------------------------------------------------------------- duplicate (coliziune cheie)
def _articole_duplicate():
    """Trei articole, dintre care DOUA identice pe (cod+denumire+obiect+tronson).
    Caz real: acelasi cod de resursa repetat in acelasi capitol/obiect."""
    return [
        ArticolF3(cod_articol='ART001', denumire='Sapatura mecanizata', um='mc',
                  cantitate=100, obiect='Retea', tronson='Strada A', categorie='Terasamente'),
        ArticolF3(cod_articol='ART001', denumire='Sapatura mecanizata', um='mc',
                  cantitate=80, obiect='Retea', tronson='Strada A', categorie='Terasamente'),
        ArticolF3(cod_articol='ART002', denumire='Pozare conducta PEHD', um='m',
                  cantitate=200, obiect='Retea', tronson='Strada A', categorie='Conducte'),
    ]


def test_duplicate_primesc_chei_distincte():
    """Articole identice pe cele 4 componente -> chei stabile DIFERITE (ordinal),
    deci nu se suprascriu tacit in baseline / progres / form."""
    m = MotorPlanificare()
    acts = list(m.proceseaza(_articole_duplicate(), clasifica=False).activitati)
    chei = [a.cheie for a in acts]
    assert len(set(chei)) == len(chei) == 3   # toate distincte
    # prima aparitie pastreaza cheia istorica (backward compat) = hash fara ordinal
    assert acts[0].cheie == cheie_stabila('ART001', 'Sapatura mecanizata', 'Retea', 'Strada A')
    assert acts[1].cheie != acts[0].cheie


def test_snapshot_nu_pierde_duplicate():
    """Coliziunea de cheie corupea baseline-ul: snapshot pastra tacit doar ultima
    activitate, dar meta.nr_activitati le numara pe toate. Cu chei distincte cele
    doua cifre coincid si nicio activitate nu e raportata fals ca disparuta."""
    m = MotorPlanificare()
    rez = m.proceseaza(_articole_duplicate(), clasifica=False)
    snap = tracking.snapshot_baseline(rez)
    # nr activitati in snapshot == meta.nr_activitati (nu se mai pierde nimic)
    assert len(snap['activitati']) == snap['meta']['nr_activitati'] == 3

    cmp = tracking.compara_baseline(rez, snap)
    assert cmp['nr_disparute'] == 0 and cmp['nr_noi'] == 0   # nicio cheie pierduta
    assert len(cmp['randuri']) == 3


def test_progres_aplicat_independent_pe_duplicate():
    """Progresul tastat pe al doilea duplicat NU mai afecteaza primul (chei distincte)
    si name-urile de input din form (pct_<cheie>) sunt distincte."""
    m = MotorPlanificare()
    acts = list(m.proceseaza(_articole_duplicate(), clasifica=False).activitati)
    c0, c1 = acts[0].cheie, acts[1].cheie
    # name-urile de form sunt distincte -> Werkzeug nu mai colapseaza valorile
    assert ('pct_%s' % c0) != ('pct_%s' % c1)

    tracking.aplica_progres(acts, {c1: {'procent': 100}}, data_stare=date(2026, 6, 1))
    assert acts[0].progres_pct == 0.0      # primul duplicat ramane neatins
    assert acts[1].progres_pct == 100.0    # progresul merge doar pe al doilea


# ------------------------------------------------------------- baseline
def test_snapshot_si_compara_identic():
    m = MotorPlanificare()
    rez = m.proceseaza(_articole(), clasifica=False)
    snap = tracking.snapshot_baseline(rez)
    assert snap['activitati'] and snap['meta']['nr_activitati'] == 2

    cmp = tracking.compara_baseline(rez, snap)
    # acelasi plan vs propriul baseline -> zero delta, fara chei noi/disparute
    assert cmp['nr_disparute'] == 0 and cmp['nr_noi'] == 0
    assert all(r['delta_finish'] == 0 and r['delta_start'] == 0 for r in cmp['randuri'])
    assert cmp['delta_durata_zile'] == 0


def test_compara_raporteaza_chei_disparute_si_noi():
    """F3 modificat intre baseline si curent -> chei disparute/noi raportate, NU eroare."""
    m = MotorPlanificare()
    snap = tracking.snapshot_baseline(m.proceseaza(_articole(), clasifica=False))

    arts_mod = _articole()
    arts_mod[1] = ArticolF3(cod_articol='ART999', denumire='Camin de vizitare', um='buc',
                            cantitate=5, obiect='Retea', tronson='Strada A', categorie='Conducte')
    rez_mod = m.proceseaza(arts_mod, clasifica=False)

    cmp = tracking.compara_baseline(rez_mod, snap)
    assert cmp['nr_disparute'] == 1   # ART002 a disparut din baseline
    assert cmp['nr_noi'] == 1         # ART999 e nou
    # activitatea comuna (ART001) ramane comparabila
    assert any(r['cod'] == 'ART001' for r in cmp['randuri'])


# ------------------------------------------------------------- progres
def test_aplica_progres_retained_logic():
    m = MotorPlanificare()
    rez = m.proceseaza(_articole(), clasifica=False)
    acts = list(rez.activitati)
    cheie_prima = acts[0].cheie

    sumar = tracking.aplica_progres(
        acts, {cheie_prima: {'procent': 50}}, data_stare=date(2026, 6, 1))

    # progres atasat, durata ramasa = durata * (1 - 0.5)
    assert acts[0].progres_pct == 50.0
    assert abs(acts[0].durata_ramasa - acts[0].durata * 0.5) < 1e-9
    # cealalta activitate ramane 0% -> durata ramasa integrala
    assert acts[1].progres_pct == 0.0
    assert abs(acts[1].durata_ramasa - acts[1].durata) < 1e-9
    # plan fara preturi (clasifica=False, fara BoQ) -> valoare 0; EV ponderat pe
    # valoare e 0, dar procent_mediu cade pe media simpla a procentelor (50% / 2 = 25%)
    assert sumar['nr_in_curs'] == 1 and sumar['procent_mediu'] == 25.0


def test_aplica_progres_clamp_si_100():
    m = MotorPlanificare()
    acts = list(m.proceseaza(_articole(), clasifica=False).activitati)
    c0, c1 = acts[0].cheie, acts[1].cheie
    sumar = tracking.aplica_progres(
        acts, {c0: {'procent': 150}, c1: {'procent': 100}})
    assert acts[0].progres_pct == 100.0          # clamp la 100
    assert acts[1].durata_ramasa == 0.0          # 100% -> nimic ramas
    assert sumar['nr_gata'] == 2


def test_progres_curent_din_jurnal_pastreaza_ultima_masuratoare():
    class _P:
        def __init__(self, cheie, data, data_creare, pct):
            self.cheie_activitate = cheie
            self.data = data
            self.data_creare = data_creare
            self.procent_fizic = pct
            self.data_start_real = None
            self.data_finish_real = None

    rows = [
        _P('abc', date(2026, 6, 1), date(2026, 6, 1), 20),
        _P('abc', date(2026, 6, 8), date(2026, 6, 8), 60),   # mai recenta
        _P('xyz', date(2026, 6, 5), date(2026, 6, 5), 10),
    ]
    curent = tracking.progres_curent_din_jurnal(rows)
    assert curent['abc']['procent'] == 60
    assert curent['xyz']['procent'] == 10


# ------------------------------------------------------------- diagrama
def test_diagrama_progres_zero_fara_tracking():
    """Fara progrese (flag OFF) -> bare cu progress 0 (comportament istoric)."""
    m = MotorPlanificare()
    rez = m.proceseaza(_articole(), clasifica=False)
    d = diagrama.sarcini_gantt(rez, date(2026, 6, 1))
    assert all(s['progress'] == 0 for s in d['sarcini'])
    assert d['baseline'] == []


def test_diagrama_progres_real_si_overlay_baseline():
    m = MotorPlanificare()
    rez = m.proceseaza(_articole(), clasifica=False)
    snap = tracking.snapshot_baseline(rez)
    cheie0 = rez.activitati[0].cheie

    d = diagrama.sarcini_gantt(rez, date(2026, 6, 1),
                               progrese={cheie0: 40}, baseline=snap)
    progrese_bare = {s['id']: s['progress'] for s in d['sarcini']}
    assert progrese_bare[rez.activitati[0].id] == 40
    # overlay baseline: cate o bara-fantoma per activitate prezenta in baseline
    assert len(d['baseline']) == len(rez.activitati)
    assert all(b['id'].startswith('bl_') for b in d['baseline'])
