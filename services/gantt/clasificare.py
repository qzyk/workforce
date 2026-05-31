"""
Motor de clasificare tehnologica (rule-based, configurabil).

Strategie (in ordine, oprire la prima potrivire):
  1. Potrivire EXACTA pe cuvinte-cheie (regex cu limite de cuvant) -> scor 1.0  (rapid, majoritar)
  2. Potrivire FUZZY (difflib) pentru greseli de scriere -> scor = raportul de similaritate
     (ruleaza DOAR pe articolele neclasificate la pasul 1, deci ramane rapid pe 100k randuri)

Diacriticele sunt eliminate inainte de potrivire (vezi normalizare). Sinonimele se aplica
inainte de clasificare. Rezultatul are scor de incredere (0..1).

Performanta: cache pe denumirea normalizata (F3 are multe denumiri repetate) -> O(1) pe duplicate.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional, Tuple

from .normalizare import normalizeaza


def _norm_cod(c) -> str:
    """Normalizeaza un cod/prefix de articol: fara diacritice, doar litere+cifre, lowercase.
    'TSA01B01>' -> 'tsa01b01' ; '1.0' -> '10'."""
    if not c:
        return ''
    return re.sub(r'[^a-z0-9]', '', normalizeaza(str(c)))


class Clasificator:
    def __init__(self, dictionar: dict, sinonime: Optional[dict] = None,
                 prag_fuzzy: float = 0.84, reguli_prefix: Optional[list] = None):
        """
        Args:
            dictionar: {CATEGORIE: [cuvinte-cheie / expresii]}.
            sinonime: {termen: inlocuire} aplicate inainte de clasificare.
            prag_fuzzy: scor minim pentru a accepta o potrivire fuzzy.
            reguli_prefix: [(prefix_cod, CATEGORIE, prioritate)] - clasificare pe
                prefixul codului de articol (indicativ eDevize), incercata PRIMA.
        """
        self.prag_fuzzy = prag_fuzzy
        self.sinonime = [(re.compile(r'\b' + re.escape(normalizeaza(k)) + r'\b'), normalizeaza(v))
                         for k, v in (sinonime or {}).items()]
        # prefixe normalizate (fara spatii/punctuatie), cele mai lungi primele
        self.reguli_prefix = sorted(
            [(_norm_cod(p), cat) for p, cat, _pr in (reguli_prefix or []) if _norm_cod(p)],
            key=lambda t: -len(t[0]))
        self.categorii: dict[str, list[str]] = {}
        self._patterns: dict[str, list] = {}
        for cat, chei in dictionar.items():
            chei_n = sorted({normalizeaza(c) for c in chei if c}, key=len, reverse=True)
            self.categorii[cat] = chei_n
            # cheile mai lungi (mai specifice) sunt incercate prima
            self._patterns[cat] = [re.compile(r'\b' + re.escape(c) + r'\b') for c in chei_n]
        self._cache: dict[str, Tuple[Optional[str], float]] = {}

    def _aplica_sinonime(self, t: str) -> str:
        for rx, repl in self.sinonime:
            t = rx.sub(repl, t)
        return t

    def _din_prefix(self, cod: str) -> Optional[str]:
        """Categoria dupa prefixul codului de articol (sau None)."""
        cn = _norm_cod(cod)
        if not cn:
            return None
        for prefix, cat in self.reguli_prefix:
            if cn.startswith(prefix):
                return cat
        return None

    def clasifica(self, denumire: str, cod: Optional[str] = None) -> Tuple[Optional[str], float]:
        """Intoarce (categorie | None, scor_incredere 0..1).
        Daca `cod` are un prefix cunoscut, are prioritate (incredere 1.0)."""
        # 0. prefix de cod (indicativ) - cea mai sigura sursa
        cat_prefix = self._din_prefix(cod) if cod else None
        if cat_prefix:
            return (cat_prefix, 1.0)

        t0 = normalizeaza(denumire)
        if not t0:
            return (None, 0.0)
        if t0 in self._cache:
            return self._cache[t0]

        t = self._aplica_sinonime(t0)

        # 1. potrivire exacta pe cheie
        for cat, pats in self._patterns.items():
            for p in pats:
                if p.search(t):
                    rez = (cat, 1.0)
                    self._cache[t0] = rez
                    return rez

        # 2. fuzzy (doar daca nu s-a potrivit nimic exact)
        rez = self._fuzzy(t)
        self._cache[t0] = rez
        return rez

    def _fuzzy(self, t: str) -> Tuple[Optional[str], float]:
        tokens = t.split()
        cel_mai_bun, scor_max = None, 0.0
        for cat, chei in self.categorii.items():
            for cheie in chei:
                # similaritate pe sirul intreg
                s = SequenceMatcher(None, cheie, t).ratio()
                if s > scor_max:
                    cel_mai_bun, scor_max = cat, s
                # similaritate token-cu-token (prinde greseli izolate)
                for ct in cheie.split():
                    for tok in tokens:
                        st = SequenceMatcher(None, ct, tok).ratio()
                        if st > scor_max:
                            cel_mai_bun, scor_max = cat, st
        if scor_max >= self.prag_fuzzy:
            return (cel_mai_bun, round(scor_max, 3))
        return (None, round(scor_max, 3))

    def clasifica_lot(self, denumiri) -> list:
        """Clasifica o lista de denumiri (foloseste cache-ul intern)."""
        return [self.clasifica(d) for d in denumiri]
