"""
Incarcarea configuratiilor externe (reguli de clasificare, template-uri de dependente,
setari WBS/durate). Suporta JSON (stdlib, mereu disponibil) si YAML (daca pyyaml e instalat).

Toate regulile de business sunt externalizate in config/gantt/*.json.
Daca un fisier lipseste, se foloseste valoarea implicita din cod (zero-config out of the box).
"""
import json
import os

try:
    import yaml  # optional
    _ARE_YAML = True
except Exception:  # pragma: no cover
    _ARE_YAML = False

# config/gantt/ relativ la radacina repo-ului (services/gantt/config_loader.py -> ../../config/gantt)
_RADACINA = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR_CONFIG = os.path.join(_RADACINA, 'config', 'gantt')


def incarca(nume: str, implicit=None):
    """Incarca config/gantt/<nume>.(json|yaml|yml). Fallback la `implicit`.

    Cauta in ordine: .json, .yaml, .yml. Daca nimic nu exista, intoarce `implicit`.
    """
    candidati = [(nume + '.json', 'json')]
    if _ARE_YAML:
        candidati += [(nume + '.yaml', 'yaml'), (nume + '.yml', 'yaml')]
    for fisier, tip in candidati:
        cale = os.path.join(DIR_CONFIG, fisier)
        if os.path.exists(cale):
            with open(cale, encoding='utf-8') as f:
                if tip == 'json':
                    return json.load(f)
                return yaml.safe_load(f)
    return implicit if implicit is not None else {}


# ---- Valori implicite (folosite daca fisierele de config lipsesc) ----

CLASIFICARE_IMPLICITA = {
    'TRASARE': ['trasare', 'trasari', 'pichetare', 'pichetaj'],
    'SAPATURA': ['sapatura', 'sapaturi', 'excavare', 'excavatie', 'decopertare', 'sapare'],
    'POZARE_CONDUCTA': ['pozare conducta', 'montaj teava', 'montaj conducta', 'pozare tub',
                        'pozare tuburi', 'montare conducta'],
    'UMPLUTURA': ['umplutura', 'umpluturi', 'compactare', 'strat de balast', 'umplere',
                  'reumplere'],
    'REFACERE': ['asfalt', 'refacere carosabil', 'refacere imbracaminte', 'covor asfaltic',
                 'refacere', 'refacere sistem rutier'],
}

DEPENDINTE_IMPLICITE = {
    'ordine_categorii': ['TRASARE', 'SAPATURA', 'POZARE_CONDUCTA', 'UMPLUTURA', 'REFACERE'],
    'intra_categorie': 'secvential',
    'relatii': [
        {'from': 'TRASARE', 'to': 'SAPATURA', 'tip': 'FS', 'decalaj': 0},
        {'from': 'SAPATURA', 'to': 'POZARE_CONDUCTA', 'tip': 'FS', 'decalaj': 0},
        {'from': 'POZARE_CONDUCTA', 'to': 'UMPLUTURA', 'tip': 'FS', 'decalaj': 0},
        {'from': 'UMPLUTURA', 'to': 'REFACERE', 'tip': 'FS', 'decalaj': 2},
    ],
}

SETARI_IMPLICITE = {
    'ore_pe_zi': 8,
    'durata_implicita_zile': 1,
    # Plafon de sanitate: o activitate nu depaseste N zile (in realitate se
    # suplimenteaza echipa) - un articol patologic nu deformeaza programul.
    'durata_max_zile': 240,
    # ATENTIE: tinut in sincron cu config/gantt/setari.json -> "randamente"
    # (acelasi tip de bug ca la 'coloane', reparat in 053b18c: fluxurile fara
    # fisier de config cad pe acest fallback, nu pe JSON). Valori orientative
    # de productivitate pe echipa/zi - de calibrat cu un inginer de santier.
    'randamente': {
        # retele edilitare
        'TRASARE': {'randament_zi': 500, 'um': 'm'},
        'SAPATURA': {'randament_zi': 200, 'um': 'mc'},
        'SPRIJINIRI': {'randament_zi': 300, 'um': 'mp'},
        'POZARE_CONDUCTA': {'randament_zi': 120, 'um': 'm'},
        'CAMINE': {'randament_zi': 1, 'um': 'buc'},
        'UMPLUTURA': {'randament_zi': 250, 'um': 'mc'},
        'REFACERE': {'randament_zi': 150, 'um': 'mp'},
        'PROBE': {'randament_zi': 300, 'um': 'm'},
        'DEMONTARI': {'randament_zi': 100, 'um': 'm'},
        'TRANSPORT': {'randament_zi': 50, 'um': 'to'},
        'ARMATURI': {'randament_zi': 8, 'um': 'buc'},
        'OBIECTE_SANITARE': {'randament_zi': 3, 'um': 'buc'},
        'IZOLATII': {'randament_zi': 50, 'um': 'mp'},
        'APARATURA_AMC': {'randament_zi': 5, 'um': 'buc'},
        # cladiri / structura / fatada
        'BETON': {'randament_zi': 30, 'um': 'mc'},
        'COFRAJE': {'randament_zi': 80, 'um': 'mp'},
        'ARMATURA_BETON': {'randament_zi': 1500, 'um': 'kg'},
        'ZIDARIE': {'randament_zi': 15, 'um': 'mc'},
        'TERMOSISTEM': {'randament_zi': 60, 'um': 'mp'},
        'PLACAJE': {'randament_zi': 25, 'um': 'mp'},
        'PARDOSELI': {'randament_zi': 60, 'um': 'mp'},
        'FINISAJE': {'randament_zi': 80, 'um': 'mp'},
        'TAMPLARIE': {'randament_zi': 10, 'um': 'buc'},
        'INVELITORI': {'randament_zi': 40, 'um': 'mp'},
        'CONFECTII_METALICE': {'randament_zi': 250, 'um': 'kg'},
    },
    'coloane': {
        'cod_articol': ['cod_articol', 'cod', 'articol', 'nr', 'nr crt', 'pozitie'],
        # 'capitol de lucrari' = coloana de DENUMIRE in F3-urile unor proiectanti
        # (ex. Academia de Politie); sinonimul mai lung bate 'capitol' (categorie).
        'denumire': ['denumire', 'descriere', 'denumirea lucrarii', 'lucrare',
                     'denumire articol', 'capitol de lucrari', 'capitolul de lucrari',
                     'capitol lucrari', 'capitole de lucrari'],
        'um': ['um', 'u.m.', 'unitate', 'unitate de masura', 'unitatea de masura'],
        'cantitate': ['cantitate', 'cant', 'cant.', 'qty', 'cantitati'],
        'obiect': ['obiect', 'obiectiv', 'obiect deviz'],
        'tronson': ['tronson', 'strada', 'sector', 'zona'],
        'categorie': ['categorie', 'capitol', 'categoria de lucrari'],
        'pret_unitar': ['pret unitar', 'pretul unitar', 'pretul', 'pret/um', 'p.u.',
                        'pret u', 'pret unit', 'pret pe um'],
        'pret_material': ['pret material', 'pret materiale', 'valoare material'],
        'pret_manopera': ['pret manopera', 'valoare manopera', 'pret munca'],
        'pret_utilaj': ['pret utilaj', 'pret utilaje', 'valoare utilaj', 'valoare utilaje'],
        'pret_total': ['pret total', 'totalul', 'total fara tva', 'valoare totala',
                       'total general', 'valoare lucrare'],
    },
    'sinonime': {
        'teava': 'conducta',
        'tevi': 'conducta',
        'excavatie': 'sapatura',
        'excavare': 'sapatura',
    },
}
