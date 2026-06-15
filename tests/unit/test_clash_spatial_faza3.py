"""
Teste Faza 3 BIM: clash detection scalabil (spatial grid) + soft clash
(min_clearance) + deduplicare clash intre rulari + integrare bbox Faza 2.

Acopera:
- echivalenta spatial grid vs O(n^2) brute force (corectitudine, nu pierde perechi)
- performanta pe ~1500 elemente (grid, nu explozie O(n^2))
- min_clearance: sub prag -> violare; >= prag -> ok; fara bbox -> neevaluat
- dedup intre rulari (ClashGroup): a doua rulare nu dubleaza grupuri
- integrare bbox Faza 2: _get_bbox citeste element.bbox (bbox_json)
- regresie toleranta default: rezultat neschimbat fata de azi
"""
import json
import random

import pytest

from models import (db, ClashRun, ClashResult, ClashGroup, ElementBIM,
                    Cladire, Santier, Utilizator)
from services import clash_detection
from services import bim_rules


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='clash3_admin@test.local').first()
        if not u:
            u = Utilizator(nume='CA3', prenume='X', email='clash3_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


def _el_bbox_col(cladire_id, cod, tip, mn, mx, **kw):
    """Element cu bbox in coloana bbox_json (formatul Faza 2, coordonate world)."""
    el = ElementBIM(
        cladire_id=cladire_id, cod=cod, tip_element=tip, status='proiectat', nume=cod,
        bbox_json=json.dumps({'min': mn, 'max': mx}), bbox_sursa='ifc_geom', **kw,
    )
    db.session.add(el); db.session.flush()
    return el


def _el_bbox_props(cladire_id, cod, tip, mn, mx):
    """Element cu bbox in proprietati_json (formatul VECHI, fallback)."""
    el = ElementBIM(
        cladire_id=cladire_id, cod=cod, tip_element=tip, status='proiectat', nume=cod,
        proprietati_json=json.dumps({'bbox': {'min': mn, 'max': mx}}),
    )
    db.session.add(el); db.session.flush()
    return el


# ====================================================
# (5) Integrare bbox Faza 2: _get_bbox citeste element.bbox
# ====================================================

def test_get_bbox_citeste_bbox_json_faza2(app, admin):
    with app.app_context():
        s = Santier(cod='S-BB2', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = _el_bbox_col(c.id, 'W001', 'wall', [0, 0, 0], [2, 3, 0.2])
        bb = clash_detection._get_bbox(el)
        assert bb == {'min': [0.0, 0.0, 0.0], 'max': [2.0, 3.0, 0.2]}


def test_clash_geometric_vede_bbox_json(app, admin):
    """Doua elemente cu bbox in coloana bbox_json (Faza 2) -> clash geometric."""
    with app.app_context():
        s = Santier(cod='S-G2', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _el_bbox_col(c.id, 'W001', 'wall', [0, 0, 0], [2, 3, 0.2])
        _el_bbox_col(c.id, 'D001', 'duct', [1, 1, 0.05], [3, 2, 0.15])
        result = clash_detection.run_clash_detection(
            santier_id=s.id, tip='geometric', user=admin)
        assert result['total_clashes'] == 1


def test_get_bbox_fallback_props_vechi(app, admin):
    """Element fara bbox_json dar cu bbox in proprietati_json -> fallback OK."""
    with app.app_context():
        s = Santier(cod='S-FB', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = _el_bbox_props(c.id, 'W001', 'wall', [0, 0, 0], [1, 1, 1])
        bb = clash_detection._get_bbox(el)
        assert bb == {'min': [0.0, 0.0, 0.0], 'max': [1.0, 1.0, 1.0]}


# ====================================================
# (1) Echivalenta spatial grid vs O(n^2)
# ====================================================

def _set_perechi(clashes):
    """Set de perechi normalizate (a,b) cu a<b din lista de clash-uri."""
    return {tuple(sorted((c['element_a_id'], c['element_b_id']))) for c in clashes}


def test_grid_echivalent_cu_n2_model_mic(app, admin):
    """Set-ul de perechi din spatial grid == set-ul din O(n^2) brute force."""
    with app.app_context():
        s = Santier(cod='S-EQ', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Model mic determinist cu suprapuneri si elemente disjuncte
        _el_bbox_col(c.id, 'E1', 'wall', [0, 0, 0], [2, 2, 2])
        _el_bbox_col(c.id, 'E2', 'duct', [1, 1, 1], [3, 3, 3])    # clash cu E1
        _el_bbox_col(c.id, 'E3', 'pipe', [2.5, 2.5, 2.5], [4, 4, 4])  # clash cu E2
        _el_bbox_col(c.id, 'E4', 'beam', [10, 10, 10], [11, 11, 11])  # disjunct
        _el_bbox_col(c.id, 'E5', 'column', [0.5, 0.5, 0.5], [1.5, 1.5, 1.5])  # in E1 si E2

        elements = ElementBIM.query.filter_by(cladire_id=c.id).all()
        grid = clash_detection._detect_geometric_clashes(elements)
        brute = clash_detection._detect_geometric_clashes_bruteforce(elements)
        assert _set_perechi(grid) == _set_perechi(brute)
        assert len(grid) == len(brute)  # nicio pereche dublata


def test_grid_echivalent_cu_n2_random(app, admin):
    """Pe un model random reproductibil, grid == brute force (nu pierde perechi)."""
    with app.app_context():
        s = Santier(cod='S-RND', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        rng = random.Random(42)
        for i in range(120):
            x = rng.uniform(0, 30); y = rng.uniform(0, 30); z = rng.uniform(0, 10)
            dx = rng.uniform(0.5, 4); dy = rng.uniform(0.5, 4); dz = rng.uniform(0.5, 3)
            _el_bbox_col(c.id, f'R{i}', 'duct', [x, y, z], [x + dx, y + dy, z + dz])

        elements = ElementBIM.query.filter_by(cladire_id=c.id).all()
        grid = clash_detection._detect_geometric_clashes(elements)
        brute = clash_detection._detect_geometric_clashes_bruteforce(elements)
        assert _set_perechi(grid) == _set_perechi(brute)


def test_grid_echivalent_scale_mixte_forteaza_oversized(app, admin):
    """
    Echivalenta grid vs brute pe scale MIXTE care forteaza fallback-ul oversized.

    Anvelopa uriasa 50x50x12 + multe elemente mici (~0.1m) -> mediana extinderii
    coboara cell_size la 0.25m, deci anvelopa atinge milioane de celule si cade
    pe ramura 'oversized'. Inainte de fix, anvelopa ajungea izolata intr-o celula
    'GLOBAL' nepartajata cu celulele normale -> clash anvelopa<->stalp pierdut.
    """
    with app.app_context():
        s = Santier(cod='S-OVS', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Anvelopa care strapunge tot volumul (element 'oversized' fata de cell_size)
        anvelopa = _el_bbox_col(c.id, 'ANV', 'wall', [0, 0, 0], [50, 50, 12])
        # Stalp care intersecteaza anvelopa (clash real ce trebuie gasit)
        stalp = _el_bbox_col(c.id, 'STALP', 'column', [10, 10, 0], [10.4, 10.4, 3])
        # 80 usi mici care coboara mediana cell_size
        for i in range(80):
            x = 1.0 + i * 0.5
            _el_bbox_col(c.id, f'USA{i}', 'door', [x, 0.0, 0.0], [x + 0.1, 0.1, 0.1])

        elements = ElementBIM.query.filter_by(cladire_id=c.id).all()

        # Garantam ca testul chiar exercita ramura oversized.
        ewb = [(el, clash_detection._get_bbox(el)) for el in elements]
        ewb = [(el, bb) for el, bb in ewb if bb]
        cell_size = clash_detection._alege_cell_size([bb for _e, bb in ewb])
        oversized = [el for el, bb in ewb
                     if clash_detection._celule_atinse(bb, cell_size)
                     == [clash_detection._OVERSIZED]]
        assert oversized, 'testul trebuie sa forteze cel putin un element oversized'

        grid = clash_detection._detect_geometric_clashes(elements)
        brute = clash_detection._detect_geometric_clashes_bruteforce(elements)
        assert _set_perechi(grid) == _set_perechi(brute)
        assert len(grid) == len(brute)  # nicio pereche dublata
        # Clash-ul anvelopa<->stalp trebuie sa fie prezent (nu pierdut in GLOBAL)
        assert tuple(sorted((anvelopa.id, stalp.id))) in _set_perechi(grid)


def test_run_clash_anvelopa_stalp_nu_se_pierde(app, admin):
    """
    End-to-end: anvelopa mare + stalp care o strapunge + multe usi mici =>
    run_clash_detection trebuie sa raporteze clash-ul (nu total_clashes=0).
    """
    with app.app_context():
        s = Santier(cod='S-OVS2', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _el_bbox_col(c.id, 'ANV', 'wall', [0, 0, 0], [50, 50, 12])
        _el_bbox_col(c.id, 'STALP', 'column', [10, 10, 0], [10.4, 10.4, 3])
        for i in range(80):
            x = 1.0 + i * 0.5
            _el_bbox_col(c.id, f'USA{i}', 'door', [x, 0.0, 0.0], [x + 0.1, 0.1, 0.1])

        elements = ElementBIM.query.filter_by(cladire_id=c.id).all()
        brute = clash_detection._detect_geometric_clashes_bruteforce(elements)
        r = clash_detection.run_clash_detection(santier_id=s.id, tip='geometric', user=admin)
        # Paritate cu brute force (sursa de adevar)
        assert r['total_clashes'] == len(brute)
        assert r['total_clashes'] >= 1


# ====================================================
# (2) Performanta spatial pe ~1500 elemente
# ====================================================

def test_clash_spatial_perf(app, admin):
    """~1500 elemente in grila rara -> grid termina rapid, numar plauzibil de clash."""
    import time
    with app.app_context():
        s = Santier(cod='S-PERF', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Grila de cuburi 1m, pas 3m -> majoritatea disjuncte (putine clash-uri)
        n = 0
        for ix in range(13):
            for iy in range(13):
                for iz in range(9):
                    if n >= 1500:
                        break
                    bx = ix * 3.0; by = iy * 3.0; bz = iz * 3.0
                    _el_bbox_col(c.id, f'P{n}', 'duct', [bx, by, bz],
                                 [bx + 1.0, by + 1.0, bz + 1.0])
                    n += 1
        db.session.flush()
        elements = ElementBIM.query.filter_by(cladire_id=c.id).all()
        assert len(elements) >= 1400

        t0 = time.time()
        clashes = clash_detection._detect_geometric_clashes(elements)
        dt = time.time() - t0
        # Cuburi disjuncte la pas 3m -> 0 clash-uri; timpul trebuie sa fie mic.
        assert len(clashes) == 0
        assert dt < 10.0  # generos, dar O(n^2) ar fi mult mai lent pe perechi-test


# ====================================================
# (3) Min clearance (soft clash)
# ====================================================

def _make_rule(tip_sursa, min_distance_to, **constraint):
    from models import BIMRule
    definition = {
        'selector': {'tip_element': tip_sursa},
        'constraint': dict(min_distance_to=min_distance_to, **constraint),
    }
    rule = BIMRule(cod='R-CLR', nume='Gabarit', tip='min_clearance',
                   severitate='medie', activa=True,
                   definitie_json=json.dumps(definition))
    db.session.add(rule); db.session.flush()
    return rule, definition


def test_min_clearance_sub_prag_violare(app, admin):
    with app.app_context():
        s = Santier(cod='S-CLR1', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # duct la 0.05m de wall, prag 0.10m -> violare
        _el_bbox_col(c.id, 'DUCT1', 'duct', [0, 0, 0], [1, 0.2, 0.2])
        _el_bbox_col(c.id, 'WALL1', 'wall', [1.05, 0, 0], [2, 0.2, 0.2])
        rule, definition = _make_rule('duct', 'wall', value_m=0.10)
        viol = bim_rules._eval_min_clearance(rule, definition, {'santier_id': s.id})
        assert any(v.get('element_bim_id') and 'sub gabaritul' in v['mesaj'] for v in viol)


def test_min_clearance_peste_prag_ok(app, admin):
    with app.app_context():
        s = Santier(cod='S-CLR2', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # duct la 0.5m de wall, prag 0.10m -> OK (nicio violare)
        _el_bbox_col(c.id, 'DUCT1', 'duct', [0, 0, 0], [1, 0.2, 0.2])
        _el_bbox_col(c.id, 'WALL1', 'wall', [1.5, 0, 0], [2, 0.2, 0.2])
        rule, definition = _make_rule('duct', 'wall', value_m=0.10)
        viol = bim_rules._eval_min_clearance(rule, definition, {'santier_id': s.id})
        assert viol == []


def test_min_clearance_fara_bbox_neevaluat(app, admin):
    """Element sursa fara bbox -> 'neevaluat' onest, NU pass fals."""
    with app.app_context():
        s = Santier(cod='S-CLR3', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # duct fara bbox + wall cu bbox
        el = ElementBIM(cladire_id=c.id, cod='DUCT_NB', tip_element='duct',
                        status='proiectat', nume='DUCT_NB')
        db.session.add(el); db.session.flush()
        _el_bbox_col(c.id, 'WALL1', 'wall', [0, 0, 0], [1, 1, 1])
        rule, definition = _make_rule('duct', 'wall', distanta_mm=100)
        viol = bim_rules._eval_min_clearance(rule, definition, {'santier_id': s.id})
        assert any(v.get('detalii', {}).get('status') == 'neevaluat_lipsa_bbox' for v in viol)


def test_min_clearance_unitati_mm(app, admin):
    """distanta_mm=100 == 0.10m: duct la 0.05m de wall -> violare."""
    with app.app_context():
        s = Santier(cod='S-CLR4', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _el_bbox_col(c.id, 'DUCT1', 'duct', [0, 0, 0], [1, 0.2, 0.2])
        _el_bbox_col(c.id, 'WALL1', 'wall', [1.05, 0, 0], [2, 0.2, 0.2])
        rule, definition = _make_rule('duct', 'wall', distanta_mm=100)
        viol = bim_rules._eval_min_clearance(rule, definition, {'santier_id': s.id})
        assert any('sub gabaritul' in v.get('mesaj', '') for v in viol)


def test_min_clearance_sursa_vs_sursa_o_singura_violare(app, admin):
    """
    Mod sursa-vs-sursa (fara min_distance_to): doua duct-uri la 0.05m, prag 0.10m
    -> O SINGURA violare pe perechea A-B (nu si A->B si B->A). Inainte de fix,
    perechea ne-normalizata producea 2 violari pentru aceeasi pereche.
    """
    with app.app_context():
        s = Santier(cod='S-CLR5', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _el_bbox_col(c.id, 'DA', 'duct', [0, 0, 0], [1, 0.2, 0.2])
        _el_bbox_col(c.id, 'DB', 'duct', [1.05, 0, 0], [2, 0.2, 0.2])
        # min_distance_to=None -> sursa vs sursa
        rule, definition = _make_rule('duct', None, value_m=0.10)
        viol = bim_rules._eval_min_clearance(rule, definition, {'santier_id': s.id})
        sub = [v for v in viol if 'sub gabaritul' in v.get('mesaj', '')]
        assert len(sub) == 1


def test_min_clearance_anvelopa_oversized_gaseste_tubulatura(app, admin):
    """
    Tinta uriasa (placa/anvelopa) dilatata cu pragul cade pe ramura oversized.
    Inainte de fix, distanta fata de tubulatura mica (in celule normale) nu se
    calcula -> gabarit raportat FALS ca OK. Acum trebuie sa gaseasca violarea.
    """
    with app.app_context():
        s = Santier(cod='S-CLR6', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Placa mare la z=[0, 0.3]; tubulatura la 0.05m deasupra ei
        _el_bbox_col(c.id, 'PLACA', 'wall', [0, 0, 0], [50, 50, 0.3])
        _el_bbox_col(c.id, 'TUB', 'duct', [10, 10, 0.35], [10.1, 10.1, 0.45])
        # Multe elemente mici ca sa coboare cell_size si sa forteze oversized pe placa
        for i in range(80):
            x = 1.0 + i * 0.5
            _el_bbox_col(c.id, f'M{i}', 'pipe', [x, 0.0, 5.0], [x + 0.1, 0.1, 5.1])

        rule, definition = _make_rule('duct', 'wall', value_m=0.10)

        # Garantam ca placa dilatata cade pe oversized
        from services import clash_detection as cd
        placa = ElementBIM.query.filter_by(cod='PLACA').first()
        bb = cd._get_bbox(placa)
        bb_dil = {'min': [bb['min'][i] - 0.10 for i in range(3)],
                  'max': [bb['max'][i] + 0.10 for i in range(3)]}
        assert cd._celule_atinse(bb_dil, 0.25) == [cd._OVERSIZED]

        viol = bim_rules._eval_min_clearance(rule, definition, {'santier_id': s.id})
        assert any('sub gabaritul' in v.get('mesaj', '') for v in viol)


# ====================================================
# (4) Dedup intre rulari (ClashGroup)
# ====================================================

def test_clash_dedup_doua_rulari(app, admin):
    """A doua rulare pe acelasi model nu dubleaza grupurile, marcheaza existente."""
    with app.app_context():
        s = Santier(cod='S-DD', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _el_bbox_col(c.id, 'E1', 'wall', [0, 0, 0], [2, 2, 2])
        _el_bbox_col(c.id, 'E2', 'duct', [1, 1, 1], [3, 3, 3])

        r1 = clash_detection.run_clash_detection(santier_id=s.id, tip='geometric', user=admin)
        assert r1['total_clashes'] == 1
        assert r1['delta']['noi'] == 1
        assert ClashGroup.query.count() == 1

        r2 = clash_detection.run_clash_detection(santier_id=s.id, tip='geometric', user=admin)
        assert r2['total_clashes'] == 1
        assert r2['delta']['noi'] == 0
        assert r2['delta']['existente'] == 1
        # NU s-a creat un al doilea grup
        assert ClashGroup.query.count() == 1
        g = ClashGroup.query.first()
        assert len(g.get_run_ids()) == 2  # ambele rulari urmarite


def test_clash_dedup_disparut(app, admin):
    """Un clash care nu mai apare la a doua rulare -> numarat ca 'disparut', grup pastrat."""
    with app.app_context():
        s = Santier(cod='S-DG', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        e1 = _el_bbox_col(c.id, 'E1', 'wall', [0, 0, 0], [2, 2, 2])
        e2 = _el_bbox_col(c.id, 'E2', 'duct', [1, 1, 1], [3, 3, 3])

        r1 = clash_detection.run_clash_detection(santier_id=s.id, tip='geometric', user=admin)
        assert r1['delta']['noi'] == 1

        # Mut E2 departe -> clash-ul dispare
        e2.bbox_json = json.dumps({'min': [50, 50, 50], 'max': [52, 52, 52]})
        db.session.commit()

        r2 = clash_detection.run_clash_detection(santier_id=s.id, tip='geometric', user=admin)
        assert r2['total_clashes'] == 0
        assert r2['delta']['disparute'] == 1
        # Grupul ramane in DB (status pastrat 'activ')
        g = ClashGroup.query.first()
        assert g is not None and g.status == 'activ'


def test_clash_dedup_disparute_scopuit_pe_santier(app, admin):
    """
    Delta 'disparute' e scopuita pe santierul scanat. Doua santiere separate
    (S1: A-B, S2: C-D). Re-rularea pe S1 NU trebuie sa numere clash-ul C-D din S2
    (neatins) ca 'disparut'. Inainte de fix, interogarea pe tenant_id (NULL pe
    prod single-tenant) numara TOATE clash-urile active din alte santiere.
    """
    with app.app_context():
        s1 = Santier(cod='S-SC1', nume='X'); db.session.add(s1); db.session.flush()
        c1 = Cladire(santier_id=s1.id, cod='C1', nume='Y'); db.session.add(c1); db.session.flush()
        _el_bbox_col(c1.id, 'A', 'wall', [0, 0, 0], [2, 2, 2])
        _el_bbox_col(c1.id, 'B', 'duct', [1, 1, 1], [3, 3, 3])

        s2 = Santier(cod='S-SC2', nume='X'); db.session.add(s2); db.session.flush()
        c2 = Cladire(santier_id=s2.id, cod='C2', nume='Y'); db.session.add(c2); db.session.flush()
        _el_bbox_col(c2.id, 'C', 'wall', [0, 0, 0], [2, 2, 2])
        _el_bbox_col(c2.id, 'D', 'duct', [1, 1, 1], [3, 3, 3])

        # Prima rulare pe ambele santiere -> cate un grup activ per santier
        clash_detection.run_clash_detection(santier_id=s1.id, tip='geometric', user=admin)
        clash_detection.run_clash_detection(santier_id=s2.id, tip='geometric', user=admin)
        assert ClashGroup.query.filter_by(status='activ').count() == 2

        # Re-rulare DOAR pe S1: A-B reapare (existent), C-D din S2 nu e atins ->
        # NU trebuie numarat ca disparut.
        r = clash_detection.run_clash_detection(santier_id=s1.id, tip='geometric', user=admin)
        assert r['delta']['noi'] == 0
        assert r['delta']['existente'] == 1
        assert r['delta']['disparute'] == 0


def test_clash_dedup_status_pastrat_la_reaparitie(app, admin):
    """Daca user-ul marcheaza 'rezolvat', reaparitia la urmatoarea rulare NU reseteaza statusul."""
    with app.app_context():
        s = Santier(cod='S-ST', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _el_bbox_col(c.id, 'E1', 'wall', [0, 0, 0], [2, 2, 2])
        _el_bbox_col(c.id, 'E2', 'duct', [1, 1, 1], [3, 3, 3])

        clash_detection.run_clash_detection(santier_id=s.id, tip='geometric', user=admin)
        g = ClashGroup.query.first()
        g.status = 'rezolvat'; db.session.commit()

        clash_detection.run_clash_detection(santier_id=s.id, tip='geometric', user=admin)
        g2 = ClashGroup.query.first()
        assert g2.status == 'rezolvat'  # statusul user-ului pastrat


# ====================================================
# (7) Regresie toleranta default: rezultat neschimbat
# ====================================================

def test_toleranta_default_pastreaza_rezultatul(app, admin):
    """tolerance_mm=None -> 1mm istoric: cutii care doar se ating NU dau clash."""
    with app.app_context():
        s = Santier(cod='S-TOL', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Se ating exact la x=1 (overlap 0) -> sub toleranta 1mm -> fara clash
        _el_bbox_col(c.id, 'A', 'wall', [0, 0, 0], [1, 1, 1])
        _el_bbox_col(c.id, 'B', 'wall', [1.0, 0, 0], [2, 1, 1])
        r = clash_detection.run_clash_detection(santier_id=s.id, tip='geometric', user=admin)
        assert r['total_clashes'] == 0


def test_toleranta_run_salvata(app, admin):
    """tolerance_mm transmis se salveaza pe ClashRun."""
    with app.app_context():
        s = Santier(cod='S-TOL2', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _el_bbox_col(c.id, 'A', 'wall', [0, 0, 0], [1, 1, 1])
        r = clash_detection.run_clash_detection(
            santier_id=s.id, tip='geometric', tolerance_mm=5, user=admin)
        run = ClashRun.query.get(r['run_id'])
        assert run.tolerance_mm == 5
