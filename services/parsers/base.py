"""
Interfata abstracta pentru parsere de import (Faza 11).

Design principles:
  - Parserele sunt PURE: citesc un fisier si intorc structuri Python.
    NU fac DB writes - call-site-ul (routes) e responsabil pentru
    crearea entitatilor SQLAlchemy + transaction management.
  - Warnings vs Errors: warning-urile NU opresc parsarea (ex: camp lipsa
    pe un articol -> default applied + warning). Errors opresc parsarea
    si invalideaza intreg fisierul.
  - Toate parserele tin stats (linii citite, entitati extrase, durata).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ParseError(Exception):
    """Eroare fatala de parsare. Continutul fisierului e invalidat."""
    pass


@dataclass
class ParseResult:
    """
    Rezultatul parsarii unui fisier.

    Atribute:
      entities: lista de dict-uri ready-to-build entitati ORM.
                Ex: pentru MSProject -> [{'cod_extern': 'UID-1', 'denumire': '...', ...}, ...]
      warnings: lista de mesaje informative (camp lipsa, valoare default
                aplicata, etc). Nu opresc importul.
      errors:   lista de mesaje critice. Daca non-vida, importul TREBUIE
                respins (call-site-ul verifica `result.errors`).
      stats:    dict liber pentru info de debug/audit
                (entities_count, warnings_count, format_version, etc).
      sursa:    string cu identificatorul tipului de parser folosit
                (de ex. 'msproject_xml', 'edevize_xml', 'excel_xlsx').
                Folosit pentru a popula `sursa_import` pe entitatea parinte.
    """
    entities: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    sursa: str = ''

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def is_empty(self) -> bool:
        return not self.entities

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)


class Parser(ABC):
    """
    Interfata abstracta pentru parsere de fisier.

    Subclasele trebuie sa implementeze `parse(file_path) -> ParseResult`.
    """
    #: Identificator format parser - se foloseste in `sursa_import` pe DB.
    SURSA_COD: str = ''

    @abstractmethod
    def parse(self, file_path: str) -> ParseResult:
        """
        Citeste fisierul de la `file_path` si returneaza ParseResult.

        NU arunca exceptii pentru continut invalid - le adauga in
        `result.errors`. ParseError se arunca DOAR daca fisierul e
        complet ilizibil (XML malformat, XLSX corupt, etc) si parsing-ul
        nu poate continua.
        """
        ...
