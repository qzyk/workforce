"""
Auto-pricing pentru liste de cantitati (devize) - metoda validata.

Distribuie un TOTAL GLOBAL fara TVA pe pozitiile unei oferte, ponderat
cu: pondere = cantitate x tarif_categorie x factor_aleator.
Suma preturilor pozitiilor == totalul global (exact, cu reconciliere rounding).

Bazat pe playbook-ul "Liste cantitati & deviz pricing" (Hala Campina):
  - Tarife pe CATEGORIE DE LUCRARE (nu pe U.M.) - excavatie != beton desi ambele mc.
  - Clasificare pe keywords din DENUMIRE, ordine SPECIFIC -> GENERIC.
  - idem carry-forward: randurile "idem" mostenesc categoria randului real anterior.
  - Split material/manopera pe % editabil (default 65/35).
  - TVA adaugat la final (NU pe pozitii) - aici lucram doar fara TVA.

Functii publice:
  - deduce_disciplina(cod_capitol) -> disciplina
  - clasifica_pozitie(denumire, cod, disciplina) -> categorie_lucrare
  - clasifica_oferta(oferta) -> atribuie categorie_lucrare + idem carry-forward
  - dry_run_clasificare(oferta) -> distributie + lista 'Diverse'
  - total_sugerat(oferta, tarife) -> round(sum(cant*tarif*factor))
  - aplica_pricing(oferta, total, tarife, procent_material, seed) -> set preturi
  - seed_tarife_default() -> populeaza tarife globale
  - get_tarife_efective(proiect_id) -> dict {(disciplina, categorie): tarif}
"""

from __future__ import annotations

import random
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from models import db, OfertaContract, PozitieBoQ, TarifCategorie


# Disciplinele cunoscute (oglindesc TarifCategorie.DISCIPLINE)
DISCIPLINE = [
    'structural', 'arhitectura', 'electrice', 'hvac',
    'sanitare', 'drumuri', 'organizare', 'general',
]

# Procent material default (restul = manopera)
PROCENT_MATERIAL_DEFAULT = Decimal('0.65')

# Factor aleator: interval [min, max] pentru variatie realista intre pozitii
FACTOR_MIN = 0.90
FACTOR_MAX = 1.10


# ============================================================
# Mapare cod_capitol (eDevize) -> disciplina
# ============================================================

_DISCIPLINA_KEYWORDS = {
    'structural':  ['rezistenta', 'structura', 'structural', 'fundatii'],
    'arhitectura': ['arhitectura', 'arhitect', 'finisaje'],
    'electrice':   ['electric', 'curenti', 'iluminat', 'electrice ct', 'electrice cs'],
    'hvac':        ['termic', 'ventilat', 'hvac', 'climatizare', 'incalzire',
                    'desfumare', 'termoventilare'],
    'sanitare':    ['sanitar', 'apa', 'canalizare'],
    'drumuri':     ['drum', 'rutier', 'platforme', 'sistematizare'],
    'organizare':  ['organizare', 'santier'],
}


def deduce_disciplina(cod_capitol: Optional[str]) -> str:
    """Deduce disciplina din cod_capitol (ex 'eDevize: 1 REZISTENTA' -> structural)."""
    if not cod_capitol:
        return 'general'
    text = cod_capitol.lower()
    for disc, kws in _DISCIPLINA_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                return disc
    return 'general'


# ============================================================
# CLASIFICATOR pe categorii de lucrare, per disciplina.
# Ordine IMPORTANTA: specific inainte de generic (vezi playbook gotchas).
# Fiecare entry: (categorie_lucrare, [keywords])
# ============================================================

_CLASIFICATOR: dict[str, list[tuple[str, list[str]]]] = {
    'structural': [
        ('probe_incercari',   ['incercare', 'incercari', 'proba', 'probe', 'verificare']),
        ('armatura',          ['armatura', 'armaturi', 'plase sudate', 'plasa sudata',
                               'bst500', 'pc52', 'otel beton', 'otel-beton', 's500c']),
        ('cofraje',           ['cofraj', 'cofrare']),
        ('beton',             ['beton', 'turnare', 'c8/10', 'c12/15', 'c16/20',
                               'c20/25', 'c25/30', 'c30/37', 'c35/45', 'sapa beton']),
        ('zidarie',           ['zidarie', 'caramida', 'bca', 'blocuri ceramice']),
        ('confectii_metalice',['confectii metalice', 'confectie metalica', 'profil metalic',
                               's355', 's235', 'grinda metalica', 'stalp metalic',
                               'gratar', 'gratare', 'ancora', 'ancore', 'ancorare',
                               'scara metalica', 'platforma metalica']),
        ('izolatii_structura',['hidroizol', 'membrana', 'bariera vapori', 'banda perimetrala',
                               'folie pe', 'folie antivant']),
        ('terasamente',       ['sapatura', 'umplutura', 'compactare', 'pamant',
                               'sprijiniri', 'sprijinire', 'berlineza', 'dulapi',
                               'epuisment', 'perna', 'rupere capilaritate',
                               'decapare', 'transport pamant', 'pietris', 'strat pietris',
                               'nisip', 'balast']),
    ],
    'arhitectura': [
        ('placaje',           ['faianta', 'gresie', 'placaj', 'placare', 'klinker',
                               'granit', 'marmura', 'travertin', 'piatra naturala']),
        ('termosistem',       ['termosistem', 'polistiren', 'vata minerala', 'vata bazaltica',
                               'izolatie termica', 'eps', 'xps']),
        ('tamplarie',         ['tamplarie', 'usa', 'usi', 'fereastra', 'ferestre', 'geam',
                               'glaf', 'pervaz', 'hpl', 'sticla securizata', 'ancadrament']),
        ('compartimentari',   ['gipscarton', 'gips-carton', 'rigips', 'gips carton',
                               'perete gips']),
        ('tavane',            ['plafon', 'tavan', 'casetat']),
        ('invelitori',        ['invelitoare', 'acoperis', 'tigla', 'tabla cutata', 'jgheab',
                               'burlan']),
        ('pardoseli',         ['pardoseala', 'pardoseli', 'sapa', 'sape', 'parchet',
                               'covor pvc', 'deck', 'lvt', 'plinta', 'mocheta',
                               'profil antiderapant', 'profil de trecere']),
        ('finisaje_pereti',   ['tencuiala', 'tencuieli', 'glet', 'gleturi', 'zugraveala',
                               'vopsitorie', 'vopsitorii', 'lavabila', 'amorsa', 'driscuit',
                               'tapet']),
        ('balustrade',        ['balustrada', 'mana curenta', 'parapet']),
    ],
    'electrice': [
        # SPECIFIC inainte de generic (gotchas din playbook)
        ('probe_verificari',  ['incercare', 'incercari', 'verificari si probe', 'masuratori',
                               'verificare priza', 'buclatura']),
        ('corpuri_iluminat',  ['corp de iluminat', 'corp iluminat', 'corpuri de iluminat',
                               'aplica', 'proiector led']),
        ('prize_pamant',      ['priza de pamant', 'priza de impamantare', 'platbanda',
                               'impamantare', 'paratrasnet', 'electrod', 'pda',
                               'conductor de coborare', 'coborare', 'coboare',
                               'tija de sustinere', 'bara de egalizare',
                               'egalizare potential', 'bep']),
        ('tablouri',          ['tablou electric', 'tablou de', 'tablouri electrice', 'tablou']),
        # CS (curenti slabi) - echipamente IT/securitate/audio. INAINTE de aparataj
        # ca sa prinda 'pdu cu prize' inainte de keyword 'prize'.
        ('echipamente_cs',    ['camera', 'detector', 'centrala', 'senzor', 'sirena',
                               'monitor led', 'interfon', 'control acces', 'switch', 'rack',
                               'patch', 'nvr', 'ups', 'pdu', 'amplificator', 'boxa',
                               'media player', 'media', 'modul', 'acumulator',
                               'sursa de alimentare', 'sursa alimentare', 'contact magnetic',
                               'cititor', 'organizator', 'distribuitor fibra', 'fibra optica',
                               'conector', 'siguranta fuzibil', 'siguranta', 'sigurante',
                               'contor de apa', 'smart', 'licenta', 'licente', 'tastatura',
                               'comunicator', 'software', 'programare', 'punere in functiune',
                               'hdd', 'interfata', 'transmitere semnale', 'supraveghere video',
                               'player', 'dispozitiv de alarmare', 'unitate', 'separatie',
                               'instalatie completa', 'piesa de separatie']),
        ('aparataj',          ['intrerupator', 'comutator', 'priza', 'doza', 'doze', 'buton']),
        ('tuburi_jgheaburi',  ['tub de protectie', 'tub izolant', 'jgheab', 'pat de cabluri',
                               'pat cablu', 'copex', 'tub pvc', 'tuburi']),
        ('cabluri',           ['cablu', 'conductor', 'myf', 'cyy', 'cyab', 'fy', 'n2xh',
                               'nhxh', 'e90', 'fe180', 'folie avertizoare', 'folie semnaliz']),
        ('accesorii_electrice',['accesorii si material marunt', 'material marunt',
                               'etansari treceri', 'etansare treceri', 'accesorii',
                               'diblu', 'holzurub', 'brida prindere', 'bride prindere']),
    ],
    'hvac': [
        ('probe_hvac',        ['proba', 'probe', 'incercare', 'incercari', 'verificare',
                               'spalarea si darea', 'spalarea hidraulica', 'spalare',
                               'grunduire', 'grunduirea']),
        ('instrumente',       ['termostat', 'manometru', 'termometru', 'traductor',
                               'regulator', 'senzor temperatura']),
        ('izolatii_hvac',     ['izolarea termica', 'izolare termica', 'izolarea', 'izolare',
                               'izolatie', 'cochilie', 'armaflex', 'cauciuc sintetic',
                               'impotriva condensului']),
        ('echipamente_termice',['cazan', 'centrala termica', 'boiler', 'pompa de caldura',
                               'pompa', 'radiator', 'calorifer', 'ventiloconvector',
                               'schimbator', 'vas de expansiune', 'vas expansiune']),
        ('ventilatie',        ['tubulatura', 'ventilator', 'grila', 'anemostat', 'cta',
                               'clapeta', 'gura de', 'recuperator', 'valva',
                               'racord antivibrant', 'cutie filtranta', 'filtru carbon']),
        ('armaturi_hvac',     ['robinet', 'vana', 'ventil', 'distribuitor']),
        ('conducte_hvac',     ['teava', 'conducta', 'fiting', 'cot', 'reductie', 'mufa']),
    ],
    'sanitare': [
        ('probe_sanitare',    ['proba', 'probe', 'incercare', 'incercari', 'verificare',
                               'spalarea si darea', 'spalarea conductelor', 'spalare',
                               'dispozitiv testare', 'dispozitiv de testare']),
        ('obiecte_sanitare',  ['lavoar', 'vas wc', 'wc', 'cada', 'dus', 'cabina dus',
                               'chiuveta', 'pisoar', 'obiect sanitar', 'spalator', 'bideu',
                               'ploscar', 'receptor de terasa', 'uscator de maini', 'uscator',
                               'dispenser', 'accesorii pentru baie', 'accesorii baie']),
        ('echipamente_sanitare',['hidrofor', 'pompa', 'boiler', 'rezervor', 'statie',
                               'contor de apa', 'vas de expansiune', 'separator', 'vas tampon',
                               'convector', 'hidrant', 'racord storz', 'storz', 'racord psi',
                               'racord psi', 'antigel']),
        ('armaturi_sanitare', ['baterie', 'robinet', 'ventil', 'sifon', 'filtru y', 'filtru',
                               'clapet', 'clapeta de sens', 'clapet de sens']),
        ('canalizare',        ['canalizare', 'racord canalizare', 'tub pvc canal', 'camin',
                               'receptor', 'piesa de curatire', 'piesa de trecere',
                               'piesa de legatura', 'colier antifoc', 'colierer antifoc',
                               'protejare la foc', 'banda avertizare']),
        ('conducte_sanitare', ['teava', 'tub', 'conducta', 'fiting', 'cot', 'mufa',
                               'cupru', 'pexal', 'ppr', 'adaptor', 'pehd', 'flansa']),
    ],
    'drumuri': [
        # Indicatoare rutiere (au "Fig." + denumiri specifice) INAINTE de generic
        ('marcaje_semnalizare',['marcaj', 'indicator', 'semnalizare', 'parapet metalic',
                               'fig.', 'circulatie in ambele', 'oprire', 'acces interzis',
                               'limitare de viteza', 'la dreapta', 'la stanga', 'ocolire',
                               'trecere pentru pietoni', 'sens unic', 'parcare', 'handicapati',
                               'terminarea benzii', 'bariera', 'bariere', 'stalp indicator']),
        ('geosintetice',      ['geocompozit', 'geotextil', 'geogrila', 'geomembrana',
                               'antifisura', 'geosintetic']),
        ('asfalt',            ['asfalt', 'mixtura asfaltica', 'binder', 'uzura', 'beton asfaltic',
                               'emulsie bituminoasa', 'amorsare', 'frezare', 'frezarea']),
        ('borduri',           ['bordura', 'borduri', 'rigola']),
        ('fundatii_drum',     ['balast', 'piatra sparta', 'strat de fundatie', 'strat fundatie',
                               'agregate']),
        ('terasamente_drum',  ['sapatura', 'umplutura', 'decapare', 'strat de forma',
                               'strat forma', 'compactare', 'nivelare']),
    ],
    'organizare': [
        ('organizare_santier',['organizare', 'baraca', 'imprejmuire', 'gard', 'utilitati',
                               'racord provizoriu', 'panou', 'wc ecologic',
                               'container metalic', 'container', 'schela', 'schele',
                               'bazin vidanjabil', 'vidanjabil']),
    ],
    # Reguli cross-disciplina (verificate ca fallback): montaj, amenajare teren, folii.
    'general': [
        ('amenajare_teren',   ['amenajare teren', 'amenajari pentru protectia', 'spatii verzi',
                               'peisager', 'plantare', 'aducerea terenului']),
        ('transport',         ['transportul rutier', 'transport rutier', 'transport']),
        ('montaj_echipamente',['montaj', 'montare', 'consola pat', 'consola']),
        ('etansari',          ['etansare', 'etanseizare']),
        ('izolatii_diverse',  ['folie']),
    ],
}

# Marker idem (carry-forward categoria randului anterior)
_IDEM_RE = re.compile(r'^\s*idem\b', re.IGNORECASE)


def clasifica_pozitie(denumire: str, cod: Optional[str] = None,
                      disciplina: str = 'general', um: Optional[str] = None) -> str:
    """
    Clasifica o pozitie -> categorie_lucrare pe baza keyword-urilor din denumire.

    Ordine: cauta in clasificatorul disciplinei (specific->generic), apoi
    fallback in 'general', apoi fallback pe UM ('diverse_<um>').
    NU trateaza 'idem' aici (e gestionat in clasifica_oferta cu carry-forward).
    """
    text = (denumire or '').lower()

    def _match(rules):
        for categorie, keywords in rules:
            for kw in keywords:
                if kw in text:
                    return categorie
        return None

    # 1. Clasificator disciplina
    cat = _match(_CLASIFICATOR.get(disciplina, []))
    if cat:
        return cat
    # 2. Fallback: incearca toate disciplinele (poate cod_capitol e gresit)
    for disc, rules in _CLASIFICATOR.items():
        if disc == disciplina:
            continue
        cat = _match(rules)
        if cat:
            return cat
    # 3. Fallback pe UM (asigura ca VLOOKUP nu esueaza niciodata)
    if um:
        return f'diverse_{um.strip().lower()}'
    return 'diverse'


def clasifica_oferta(oferta: OfertaContract, commit: bool = True,
                     doar_neclasificate: bool = False) -> dict:
    """
    Atribuie categorie_lucrare la toate pozitiile ofertei.

    Implementeaza idem carry-forward: randurile 'idem' mostenesc categoria
    ultimului rand real (non-idem). Returneaza stats {categorie: count}.

    Args:
        doar_neclasificate: daca True, NU re-clasifica pozitiile care au
            deja o categorie_lucrare setata (protejeaza editarile manuale +
            clasificarile anterioare). Carry-forward 'idem' tine cont de
            categoria existenta a randului real precedent.
    """
    pozitii = oferta.pozitii.order_by(PozitieBoQ.ordine).all()
    ultima_categorie = None
    stats: dict[str, int] = {}

    for p in pozitii:
        existenta = (p.categorie_lucrare or '').strip()
        if doar_neclasificate and existenta:
            # Pastram categoria existenta (manual sau auto anterioara)
            ultima_categorie = existenta
            stats[existenta] = stats.get(existenta, 0) + 1
            continue
        disc = deduce_disciplina(p.cod_capitol)
        if _IDEM_RE.match(p.denumire or '') and ultima_categorie:
            # idem -> carry-forward
            categorie = ultima_categorie
        else:
            categorie = clasifica_pozitie(p.denumire, p.cod_articol, disc, p.um)
            ultima_categorie = categorie
        p.categorie_lucrare = categorie
        stats[categorie] = stats.get(categorie, 0) + 1

    if commit:
        db.session.commit()
    return stats


def dry_run_clasificare(oferta: OfertaContract) -> dict:
    """
    Ruleaza clasificarea FARA persist (rollback). Returneaza:
      {distributie: {cat: count}, diverse: [poz_info], total_pozitii: N}
    Pentru validare inainte de pricing (playbook: don't ship blind).
    """
    pozitii = oferta.pozitii.order_by(PozitieBoQ.ordine).all()
    ultima = None
    distributie: dict[str, int] = {}
    diverse = []
    for p in pozitii:
        disc = deduce_disciplina(p.cod_capitol)
        if _IDEM_RE.match(p.denumire or '') and ultima:
            categorie = ultima
        else:
            categorie = clasifica_pozitie(p.denumire, p.cod_articol, disc, p.um)
            ultima = categorie
        distributie[categorie] = distributie.get(categorie, 0) + 1
        if categorie.startswith('diverse'):
            diverse.append({
                'cod': p.cod_articol, 'denumire': p.denumire[:60],
                'um': p.um, 'categorie': categorie,
            })
    return {
        'distributie': dict(sorted(distributie.items(), key=lambda x: -x[1])),
        'diverse': diverse,
        'total_pozitii': len(pozitii),
        'procent_diverse': round(len(diverse) / len(pozitii) * 100, 1) if pozitii else 0,
    }


# ============================================================
# Tarife
# ============================================================

# Tarife default per (disciplina, categorie_lucrare) - lei/UM orientativ.
# Editabile din UI; acestea sunt doar seed-ul initial.
_TARIFE_DEFAULT = {
    'structural': {
        'terasamente': 30, 'beton': 550, 'armatura': 6, 'cofraje': 60,
        'zidarie': 180, 'confectii_metalice': 12, 'izolatii_structura': 45,
        'probe_incercari': 100, 'diverse': 100,
    },
    'arhitectura': {
        'finisaje_pereti': 35, 'pardoseli': 90, 'tamplarie': 450,
        'termosistem': 55, 'compartimentari': 75, 'tavane': 80,
        'invelitori': 70, 'placaje': 85, 'balustrade': 120, 'diverse': 100,
    },
    'electrice': {
        'cabluri': 18, 'aparataj': 40, 'corpuri_iluminat': 200, 'tablouri': 1500,
        'tuburi_jgheaburi': 25, 'echipamente_cs': 350, 'prize_pamant': 22,
        'probe_verificari': 80, 'diverse': 100,
    },
    'hvac': {
        'conducte_hvac': 60, 'echipamente_termice': 2500, 'ventilatie': 90,
        'armaturi_hvac': 120, 'izolatii_hvac': 30, 'instrumente': 250,
        'probe_hvac': 100, 'diverse': 100,
    },
    'sanitare': {
        'conducte_sanitare': 45, 'obiecte_sanitare': 400, 'armaturi_sanitare': 150,
        'canalizare': 55, 'echipamente_sanitare': 1800, 'probe_sanitare': 80,
        'diverse': 100,
    },
    'drumuri': {
        'terasamente_drum': 25, 'fundatii_drum': 70, 'asfalt': 350,
        'borduri': 60, 'marcaje_semnalizare': 40, 'diverse': 100,
    },
    'organizare': {'organizare_santier': 500, 'diverse': 100},
    'general': {
        'amenajare_teren': 40, 'transport': 15, 'montaj_echipamente': 300,
        'etansari': 50, 'izolatii_diverse': 30, 'diverse': 100,
    },
}


def seed_tarife_default(force: bool = False) -> int:
    """
    Populeaza TarifCategorie cu tarifele globale (proiect_id=None).
    Idempotent: nu duplica daca exista deja (decat daca force=True).
    Returneaza numarul de tarife create.
    """
    created = 0
    for disc, cats in _TARIFE_DEFAULT.items():
        for cat, tarif in cats.items():
            existing = TarifCategorie.query.filter_by(
                proiect_id=None, disciplina=disc, categorie_lucrare=cat
            ).first()
            if existing and not force:
                continue
            if existing and force:
                existing.tarif_baza = Decimal(str(tarif))
                continue
            t = TarifCategorie(
                proiect_id=None, disciplina=disc, categorie_lucrare=cat,
                tarif_baza=Decimal(str(tarif)),
            )
            db.session.add(t)
            created += 1
    db.session.commit()
    return created


def get_tarife_efective(proiect_id: Optional[int] = None) -> dict:
    """
    Returneaza dict {(disciplina, categorie_lucrare): Decimal(tarif)}.
    Override per proiect peste global default.
    """
    tarife: dict[tuple, Decimal] = {}
    # 1. Global default
    for t in TarifCategorie.query.filter_by(proiect_id=None).all():
        tarife[(t.disciplina, t.categorie_lucrare)] = t.tarif_baza or Decimal('0')
    # 2. Override proiect
    if proiect_id:
        for t in TarifCategorie.query.filter_by(proiect_id=proiect_id).all():
            tarife[(t.disciplina, t.categorie_lucrare)] = t.tarif_baza or Decimal('0')
    return tarife


def _tarif_pentru(pozitie: PozitieBoQ, tarife: dict) -> Decimal:
    """Tariful pentru o pozitie pe baza disciplinei + categoriei de lucrare."""
    disc = deduce_disciplina(pozitie.cod_capitol)
    cat = pozitie.categorie_lucrare or 'diverse'
    # Cauta exact, apoi fallback la 'diverse' al disciplinei, apoi global diverse
    return (tarife.get((disc, cat))
            or tarife.get((disc, 'diverse'))
            or tarife.get(('general', 'diverse'))
            or Decimal('100'))


# ============================================================
# Pricing
# ============================================================

def total_sugerat(oferta: OfertaContract, tarife: Optional[dict] = None,
                  seed: int = 42) -> Decimal:
    """
    Total global sugerat = round(sum(cantitate x tarif x factor)).
    Folosit ca valoare default in formularul de pricing.
    """
    if tarife is None:
        tarife = get_tarife_efective(oferta.proiect_id)
    rng = random.Random(seed)
    total = Decimal('0')
    for p in oferta.pozitii.all():
        cant = p.cantitate_oferta or Decimal('0')
        if cant <= 0:
            continue
        tarif = _tarif_pentru(p, tarife)
        factor = Decimal(str(rng.uniform(FACTOR_MIN, FACTOR_MAX)))
        total += cant * tarif * factor
    return total.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def aplica_pricing(
    oferta: OfertaContract,
    total_global: Decimal,
    tarife: Optional[dict] = None,
    procent_material: Decimal = PROCENT_MATERIAL_DEFAULT,
    seed: int = 42,
    clasifica_intai: bool = True,
    commit: bool = True,
) -> dict:
    """
    Distribuie total_global pe pozitiile ofertei (metoda pondere).

    Algoritm:
      1. (optional) clasifica_oferta() pentru categorie_lucrare + idem.
      2. pondere[i] = cantitate[i] x tarif[i] x factor_aleator[i]
      3. pret_total[i] = total_global x pondere[i] / sum(pondere)
      4. pret_unitar[i] = pret_total[i] / cantitate[i]  (guard cant>0)
      5. valoare_materiale_unitar = pret_unitar x procent_material
         valoare_manopera_unitar  = pret_unitar x (1 - procent_material)
      6. Reconciliere rounding: ultima pozitie absoarbe diferenta ca
         sum(pret_total) == total_global exact.

    Returneaza dict cu verificare: {total_aplicat, total_tinta, diferenta,
    pozitii_pretuite, pozitii_zero_cant}.
    """
    if tarife is None:
        tarife = get_tarife_efective(oferta.proiect_id)
    total_global = Decimal(str(total_global))
    procent_material = Decimal(str(procent_material))

    if clasifica_intai:
        clasifica_oferta(oferta, commit=False)

    pozitii = oferta.pozitii.order_by(PozitieBoQ.ordine).all()
    rng = random.Random(seed)

    # Pas 1: ponderi
    ponderi = []
    suma_pondere = Decimal('0')
    pozitii_valide = []
    pozitii_zero = 0
    for p in pozitii:
        cant = p.cantitate_oferta or Decimal('0')
        if cant <= 0:
            p.factor_aleator = None
            pozitii_zero += 1
            continue
        tarif = _tarif_pentru(p, tarife)
        factor = Decimal(str(rng.uniform(FACTOR_MIN, FACTOR_MAX))).quantize(Decimal('0.0001'))
        p.factor_aleator = factor
        pondere = cant * tarif * factor
        ponderi.append(pondere)
        suma_pondere += pondere
        pozitii_valide.append(p)

    if suma_pondere <= 0:
        return {'eroare': 'Suma ponderilor e 0 - verifica tarife si cantitati.',
                'pozitii_pretuite': 0}

    # Pas 2: distributie. Reconciliere pe VALOAREA REALA (pret_unitar x cant),
    # nu pe pret_total intermediar - astfel Σ(pret_unitar x cant) == total
    # cat mai exact posibil (reziduul ramas e doar rotunjirea ultimei pozitii).
    q4 = Decimal('0.0001')
    q2 = Decimal('0.01')
    total_aplicat = Decimal('0')  # acumuleaza VALOAREA REALA (pret_unitar x cant)
    n = len(pozitii_valide)
    for i, p in enumerate(pozitii_valide):
        cant = p.cantitate_oferta
        if i == n - 1:
            # Ultima pozitie: valoarea ei = ce ramane din total (compenseaza
            # tot drift-ul de rotunjire acumulat din pozitiile anterioare).
            valoare_pozitie = total_global - total_aplicat
        else:
            pret_total_ideal = total_global * ponderi[i] / suma_pondere
            valoare_pozitie = pret_total_ideal.quantize(q2, rounding=ROUND_HALF_UP)

        pret_unitar = (valoare_pozitie / cant).quantize(q4, rounding=ROUND_HALF_UP)
        p.pret_unitar = pret_unitar
        p.valoare_materiale_unitar = (pret_unitar * procent_material).quantize(q4, rounding=ROUND_HALF_UP)
        p.valoare_manopera_unitar = (pret_unitar - p.valoare_materiale_unitar).quantize(q4, rounding=ROUND_HALF_UP)
        p.categorie = 'mixt'  # are si material si manopera

        # Acumulez valoarea REALA stocata (pret_unitar x cant), nu valoarea ideala
        total_aplicat += (pret_unitar * cant).quantize(q2, rounding=ROUND_HALF_UP)

    # Actualizez valoarea totala oferta
    oferta.valoare_totala = total_global

    if commit:
        db.session.commit()

    diferenta = (total_aplicat - total_global).quantize(q2)
    return {
        'total_tinta': total_global,
        'total_aplicat': total_aplicat,
        'diferenta': diferenta,
        'pozitii_pretuite': len(pozitii_valide),
        'pozitii_zero_cant': pozitii_zero,
        'suma_pondere': suma_pondere,
    }


def categorii_cunoscute() -> dict[str, list[str]]:
    """
    Returneaza {disciplina: [categorii_lucrare]} pentru dropdown-uri UI
    (clasificare manuala). Include 'diverse' ca optiune generica.
    """
    out: dict[str, list[str]] = {}
    for disc, reguli in _CLASIFICATOR.items():
        cats = [cat for cat, _kw in reguli]
        cats.append('diverse')
        out[disc] = cats
    # Asigur ca toate disciplinele din DISCIPLINE au cel putin 'diverse'
    for disc in DISCIPLINE:
        out.setdefault(disc, ['diverse'])
    return out


def toate_categoriile_flat() -> list[str]:
    """Lista plata, unica si sortata, a tuturor categoriilor de lucrare."""
    s: set[str] = {'diverse'}
    for reguli in _CLASIFICATOR.values():
        for cat, _kw in reguli:
            s.add(cat)
    return sorted(s)
