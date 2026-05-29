"""
Normalizare text pentru import si clasificare:
- elimina diacriticele romanesti (a-caciula, a-circumflex, i-circumflex, s/t-virgula)
- colapseaza spatiile, trim
- lowercase optional

Folosit atat la import (curatarea articolelor) cat si la clasificare (potrivirea cheilor).
"""
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
