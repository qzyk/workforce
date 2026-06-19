"""
Normalizare text pentru import si clasificare:
- elimina diacriticele romanesti (a-caciula, a-circumflex, i-circumflex, s/t-virgula)
- colapseaza spatiile, trim
- lowercase optional

Folosit atat la import (curatarea articolelor) cat si la clasificare (potrivirea cheilor).
"""
import hashlib
import re
import unicodedata

_RE_SPATII = re.compile(r'\s+')


def fara_diacritice(text: str) -> str:
    """Elimina diacriticele prin descompunere NFKD + eliminarea semnelor combinate.
    'sapatura' din 'sapatura', 'tronson' din 'tronson' etc."""
    if not text:
        return ''
    nfkd = unicodedata.normalize('NFKD', str(text))
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def normalizeaza(text: str, lower: bool = True) -> str:
    """Normalizare completa: fara diacritice, fara spatii multiple, trim, lowercase."""
    t = fara_diacritice(text or '')
    t = _RE_SPATII.sub(' ', t).strip()
    return t.lower() if lower else t


def normalizeaza_cheie(text: str) -> str:
    """Cheie de comparatie pentru deduplicare (cod articol normalizat agresiv)."""
    return re.sub(r'[^a-z0-9]', '', normalizeaza(text))


def cheie_stabila(cod: str, denumire: str, obiect: str = '', tronson: str = '',
                  ordinal: int = 1) -> str:
    """Cheie stabila de activitate (Faza 2 tracking).

    Hash determinist (sha1, primii 16 hexa) din componentele normalizate ale
    activitatii: cod articol + denumire + obiect + tronson. NU depinde de
    ordinea randurilor din F3, deci ramane stabila la re-import (atata timp cat
    aceste 4 atribute nu se schimba). Folosita pentru a lega baseline-ul,
    progresul fizic si elementele 4D de o activitate, independent de id-ul
    secvential A000001 (volatil).

    `ordinal` dezambiguizeaza duplicatele: in devize reale acelasi cod+denumire
    poate aparea repetat in ACELASI obiect/tronson (ex. mai multe randuri de
    "Sapatura" sub acelasi capitol), iar cele 4 componente nu mai sunt unice.
    Pentru a NU genera chei identice (ce ar corupe tracking-ul - baseline cu mai
    putine activitati, progres aplicat tuturor duplicatelor, input-uri de form cu
    acelasi name), pipeline-ul numara aparitiile per tuple si trece un ordinal
    1, 2, 3... pe ordinea de aparitie. `ordinal <= 1` (implicit) pastreaza cheia
    istorica neschimbata (backward compat: prima aparitie = exact ca inainte);
    `ordinal >= 2` amesteca un sufix determinist '#<n>' in hash.
    """
    parti = [
        normalizeaza_cheie(cod),
        normalizeaza(denumire),
        normalizeaza(obiect),
        normalizeaza(tronson),
    ]
    if ordinal and ordinal > 1:
        # sufix determinist doar pentru duplicate (2+); prima aparitie ramane
        # identica cu cheia istorica de dinainte de fix.
        parti.append('#%d' % int(ordinal))
    return hashlib.sha1('|'.join(parti).encode('utf-8')).hexdigest()[:16]
