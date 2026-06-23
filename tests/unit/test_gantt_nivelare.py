"""
Teste unitare pentru nivelarea de resurse (services/gantt/nivelare.py).

Verifica VALORI concrete (start/finish nivelate, durate, delte, histograma), nu doar
existenta. Pur Python, fara aplicatia Flask.
"""
import pytest

from services.gantt.modele import Activitate, Dependenta
from services.gantt import nivelare
from services.gantt.program import programeaza, drum_critic


def _act(id_, cat, durata, preds=None):
    """Activitate minimala; start/finish se completeaza prin programeaza()."""
    a = Activitate(id=id_, cod=id_, nume=id_, categorie_tehnologica=cat)
    a.categorie_lucrare = cat
    a.durata = durata
    a.cheie = id_
    if preds:
        a.predecesori = [Dependenta(predecesor_id=p) for p in preds]
    return a


def _programeaza(acts):
    """Ruleaza motorul CPM (forward + backward) pe activitati, ca in pipeline."""
    d = programeaza(acts)
    drum_critic(acts, d)
    return d


# --------------------------------------------------------------- caz de baza
def test_capacitati_goale_nu_misca_nimic():
    """Fara capacitati definite -> nivelarea = CPM (zero regresie)."""
    acts = [_act('A', 'BETON', 2), _act('B', 'BETON', 2), _act('C', 'BETON', 2)]
    _programeaza(acts)   # toate independente -> start 0, finish 2
    rez = nivelare.niveleaza(acts, {})
    assert rez['ok'] is True
    assert rez['nr_mutate'] == 0
    assert rez['durata_nivelata'] == 2 == rez['durata_cpm']
    assert rez['deltas'] == []
    # planul nivelat == CPM
    for a in acts:
        assert rez['plan'][a.id] == {'start_zi': 0, 'finish_zi': 2}


def test_serializare_capacitate_1():
    """3 activitati de aceeasi categorie, independente, capacitate 1 -> serializate."""
    acts = [_act('A', 'BETON', 2), _act('B', 'BETON', 2), _act('C', 'BETON', 2)]
    _programeaza(acts)
    rez = nivelare.niveleaza(acts, {'BETON': 1})
    assert rez['ok'] is True
    # 3 x durata 2, cap 1 => ferestre 0-2, 2-4, 4-6 => durata 6
    assert rez['durata_cpm'] == 2
    assert rez['durata_nivelata'] == 6
    assert rez['intarziere'] == 4
    assert rez['nr_mutate'] == 2
    starts = sorted(p['start_zi'] for p in rez['plan'].values())
    assert starts == [0, 2, 4]
    # nicio zi cu mai mult de 1 activitate (load <= cap)
    load = {}
    for p in rez['plan'].values():
        for z in range(p['start_zi'], p['finish_zi']):
            load[z] = load.get(z, 0) + 1
    assert max(load.values()) == 1


def test_capacitate_2_partial():
    """4 activitati, capacitate 2 -> doua perechi paralele (0-2 si 2-4)."""
    acts = [_act(c, 'ZID', 2) for c in 'ABCD']
    _programeaza(acts)
    rez = nivelare.niveleaza(acts, {'ZID': 2})
    assert rez['durata_nivelata'] == 4
    load = {}
    for p in rez['plan'].values():
        for z in range(p['start_zi'], p['finish_zi']):
            load[z] = load.get(z, 0) + 1
    assert max(load.values()) == 2     # niciodata peste capacitate
    assert rez['nr_mutate'] == 2       # 2 raman la 0, 2 se muta la 2


def test_categorii_diferite_nu_concureaza():
    """Activitati de categorii diferite nu isi consuma capacitatea reciproc."""
    acts = [_act('A', 'BETON', 3), _act('B', 'ZID', 3)]
    _programeaza(acts)
    rez = nivelare.niveleaza(acts, {'BETON': 1, 'ZID': 1})
    # ambele raman la 0 (categorii diferite, fiecare cap 1)
    assert rez['nr_mutate'] == 0
    assert rez['durata_nivelata'] == 3


def test_categorie_fara_capacitate_nelimitata():
    """O categorie fara capacitate definita nu se niveleaza (nelimitata)."""
    acts = [_act('A', 'SAPATURA', 2), _act('B', 'SAPATURA', 2),
            _act('C', 'SAPATURA', 2)]
    _programeaza(acts)
    rez = nivelare.niveleaza(acts, {'BETON': 1})   # capacitate doar pe alta categorie
    assert rez['nr_mutate'] == 0
    assert rez['durata_nivelata'] == 2


# --------------------------------------------------------------- dependente
def test_respecta_dependenta_fs():
    """B (FS dupa A) trebuie sa inceapa dupa finish-ul nivelat al lui A."""
    A = _act('A', 'BETON', 2)
    B = _act('B', 'BETON', 2, preds=['A'])
    C = _act('C', 'BETON', 2)            # concureaza pe capacitate cu A
    acts = [A, B, C]
    _programeaza(acts)
    rez = nivelare.niveleaza(acts, {'BETON': 1})
    pl = rez['plan']
    # FS: start B >= finish A (chiar dupa nivelare)
    assert pl['B']['start_zi'] >= pl['A']['finish_zi']
    # nicio zi peste capacitate 1
    load = {}
    for p in pl.values():
        for z in range(p['start_zi'], p['finish_zi']):
            load[z] = load.get(z, 0) + 1
    assert max(load.values()) == 1


def test_lag_negativ_si_ss():
    """Dependenta SS cu lag se respecta dupa nivelare (start succ >= start pred + lag)."""
    A = _act('A', 'X', 4)
    B = _act('B', 'Y', 2)
    B.predecesori = [Dependenta(predecesor_id='A', tip='SS', decalaj=1)]
    acts = [A, B]
    _programeaza(acts)
    rez = nivelare.niveleaza(acts, {'X': 1, 'Y': 1})
    pl = rez['plan']
    assert pl['B']['start_zi'] >= pl['A']['start_zi'] + 1


# --------------------------------------------------------------- histograma
def test_histograma_incarcare_varf_si_capacitate():
    acts = [_act('A', 'BETON', 2), _act('B', 'BETON', 2), _act('C', 'ZID', 2)]
    _programeaza(acts)    # toate start 0
    h = nivelare.histograma_incarcare(acts, capacitati={'BETON': 1})
    cats = {c['categorie']: c for c in h['categorii']}
    assert cats['BETON']['varf'] == 2          # 2 activitati BETON simultan
    assert cats['BETON']['capacitate'] == 1
    assert cats['ZID']['varf'] == 1
    assert cats['ZID']['capacitate'] is None   # fara capacitate => nelimitat
    # categoria suprasolicitata (BETON) apare prima
    assert h['categorii'][0]['categorie'] == 'BETON'


def test_histograma_cu_plan_nivelat_nu_depaseste():
    acts = [_act(c, 'BETON', 2) for c in 'ABC']
    _programeaza(acts)
    rez = nivelare.niveleaza(acts, {'BETON': 1})
    h = nivelare.histograma_incarcare(acts, plan=rez['plan'],
                                      capacitati={'BETON': 1})
    serie = h['categorii'][0]['serie']
    assert max(serie) <= 1     # dupa nivelare nicio zi nu depaseste capacitatea


# --------------------------------------------------------------- robustete
def test_plan_gol():
    rez = nivelare.niveleaza([], {'BETON': 2})
    assert rez['ok'] is True
    assert rez['durata_nivelata'] == 0
    assert rez['deltas'] == []


def test_plafon_activitati(monkeypatch):
    """Peste plafon -> return clar (ok=False), fara sa calculeze."""
    monkeypatch.setattr(nivelare, 'PLAFON_ACTIVITATI', 3)
    acts = [_act(str(i), 'X', 1) for i in range(5)]
    for a in acts:
        a.start_zi, a.finish_zi = 0, 1
    rez = nivelare.niveleaza(acts, {'X': 1})
    assert rez['ok'] is False
    assert 'plafon' in rez['motiv'].lower() or 'prea mare' in rez['motiv'].lower()
    assert rez['nr_mutate'] == 0


def test_capacitate_invalida_ignorata():
    """Capacitate <=0 sau ne-numerica e ignorata (categoria devine nelimitata)."""
    acts = [_act('A', 'BETON', 2), _act('B', 'BETON', 2)]
    _programeaza(acts)
    rez = nivelare.niveleaza(acts, {'BETON': 0, 'ZID': 'abc'})
    assert rez['nr_mutate'] == 0      # cap 0 ignorat -> nelimitat


def test_categorie_normalizata_upper():
    """Cheia de capacitate e case-insensitive (se compara UPPER)."""
    acts = [_act('A', 'beton', 2), _act('B', 'Beton', 2)]
    _programeaza(acts)
    rez = nivelare.niveleaza(acts, {'beton': 1})   # cheie lowercase in input
    assert rez['nr_mutate'] == 1                    # categoriile se unesc la BETON
    assert rez['durata_nivelata'] == 4
