"""
Regression test pentru calibrarea clasificatorului pe devize REALE (Hala Campina).

Opt-in: ruleaza doar daca fisierele exista local (~/Downloads/PT DE Hala Campina).
Confirma ca procentul de pozitii "diverse" (neclasificate) ramane sub prag
dupa calibrare (FEEDBACK §4: Diverse near-zero).

Foloseste idem carry-forward (ca in clasifica_oferta real), nu clasificare
izolata pozitie cu pozitie.
"""

import os
import warnings

import pytest

from services.parsers import ExcelBoQParser
from services.deviz_pricing import clasifica_pozitie, _IDEM_RE


BASE = os.path.expanduser('~/Downloads/PT DE Hala Campina')

# (cale relativa, disciplina asteptata)
FISIERE = [
    ('02.Rezistenta/Parti scrise/Editabil/2404_AEN_PTh+DE_STR_PS_09_00-Liste cantitati.xls', 'structural'),
    ('03.Drumuri/Parti scrise/8.1.Liste de cantitati-09.04.2025.xlsx', 'drumuri'),
    ('04.Instalatii electrice/01_PARTI SCRISE/FORMULAR F3 - ELECTRICE CS_Liste cantitati.xlsx', 'electrice'),
    ('04.Instalatii electrice/01_PARTI SCRISE/FORMULAR F3 - ELECTRICE CT_Liste cantitati.xls', 'electrice'),
    ('05.Instalatii HVAC/01_PARTI SCRISE/2404_ADD_PTH_HV_LC_C1C2_001_00_LISTE DE CANTITATI INSTALATII DE CLIMATIZARE.xlsx', 'hvac'),
    ('05.Instalatii HVAC/01_PARTI SCRISE/2404_ADD_PTH_HV_LC_C1C2_002_00_LISTE DE CANTITATI INSTALATII DE VENTILARE.xlsx', 'hvac'),
    ('05.Instalatii HVAC/01_PARTI SCRISE/2404_ADD_PTH_HV_LC_C1C2_003_00_LISTE DE CANTITATI INSTALATII DE DESFUMARE.xlsx', 'hvac'),
    ('05.Instalatii HVAC/01_PARTI SCRISE/2404_ADD_PTH_HV_LC_C3_004_00_LISTE DE CANTITATI INSTALATII DE TERMOVENTILARE.xlsx', 'hvac'),
    ('06.Instalatii sanitare/01. PIESE SCRISE/EDITABIL/F3_ LISTA DE CANTITATI  - INSTALATII SANITARE.xls', 'sanitare'),
    ('06.Instalatii sanitare/01. PIESE SCRISE/EDITABIL/F4_ LISTA DE ECHIPAMENTE  - INSTALATII SANITARE.xlsx', 'sanitare'),
    ('07.Organizare de santier/2404_AEN_DTOE_ARH_GEN_LC_001_00-Organizare de santier.xls', 'organizare'),
]


def _clasifica_cu_idem(entities, disciplina):
    """Simuleaza clasifica_oferta (cu idem carry-forward). Returneaza lista categorii."""
    ultima = None
    cats = []
    for e in entities:
        if _IDEM_RE.match(e['denumire'] or '') and ultima:
            cat = ultima
        else:
            cat = clasifica_pozitie(e['denumire'], e['cod_articol'], disciplina, e['um'])
            ultima = cat
        cats.append(cat)
    return cats


@pytest.mark.skipif(not os.path.isdir(BASE),
                    reason='Devizele reale Hala Campina absente - test optional')
class TestClasificatorReal:

    def test_diverse_sub_prag_global(self):
        """Pe toate devizele proiectului, Diverse trebuie sa fie < 3% (calibrat)."""
        warnings.filterwarnings('ignore')
        total = 0
        diverse = 0
        for rel, disc in FISIERE:
            path = os.path.join(BASE, rel)
            if not os.path.exists(path):
                continue
            r = ExcelBoQParser().parse(path)
            cats = _clasifica_cu_idem(r.entities, disc)
            total += len(cats)
            diverse += sum(1 for c in cats if c.startswith('diverse'))
        assert total > 800, f'Prea putine pozitii parsate: {total}'
        pct = diverse / total * 100
        assert pct < 3.0, f'Diverse {pct:.1f}% peste prag (calibrat la ~0.9%)'

    def test_fiecare_disciplina_parseaza(self):
        """Fiecare fisier real trebuie sa parseze fara erori + sa aiba pozitii."""
        warnings.filterwarnings('ignore')
        for rel, disc in FISIERE:
            path = os.path.join(BASE, rel)
            if not os.path.exists(path):
                continue
            r = ExcelBoQParser().parse(path)
            assert not r.has_errors, f'{rel}: {r.errors}'
            assert len(r.entities) > 0, f'{rel}: 0 pozitii'

    def test_categorii_corecte_esantion(self):
        """Verific clasificari cheie pe esantion (structural)."""
        warnings.filterwarnings('ignore')
        path = os.path.join(BASE, FISIERE[0][0])
        if not os.path.exists(path):
            pytest.skip('fisier structural absent')
        r = ExcelBoQParser().parse(path)
        by_den = {}
        cats = _clasifica_cu_idem(r.entities, 'structural')
        for e, c in zip(r.entities, cats):
            by_den[e['denumire'].lower()] = c
        # Beton -> beton, Armatura -> armatura, Cofraj -> cofraje
        beton = [c for d, c in by_den.items() if d.startswith('beton')]
        assert beton and all(c == 'beton' for c in beton)
        armatura = [c for d, c in by_den.items() if d.startswith('armatura')]
        assert armatura and all(c == 'armatura' for c in armatura)
