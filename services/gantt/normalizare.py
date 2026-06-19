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


def cheie_stabila(cod: str, denumire: str, obiect: str = '', tronson: str = '') -> str:
    """Cheie stabila de activitate (Faza 2 tracking).

    Hash determinist (sha1, primii 16 hexa) din componentele normalizate ale
    activitatii: cod articol + denumire + obiect + tronson. NU depinde de
    ordinea randurilor din F3, deci ramane stabila la re-import (atata timp cat
    aceste 4 atribute nu se schimba). Folosita pentru a lega baseline-ul,
    progresul fizic si elementele 4D de o activitate, independent de id-ul
    secvential A000001 (volatil).
    """
    parti = '|'.join([
        normalizeaza_cheie(cod),
        normalizeaza(denumire),
        normalizeaza(obiect),
        normalizeaza(tronson),
    ])
    return hashlib.sha1(parti.encode('utf-8')).hexdigest()[:16]
