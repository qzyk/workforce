"""
Modele de date (dataclasses) pentru motorul de planificare Gantt.

Folosim dataclasses din stdlib (nu pydantic - nu e instalat si nu vrem dep noua).
Tot ce e expus prin API are si un `to_dict` / `from_dict` pentru serializare JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# Tipuri de relatie suportate (ca in Primavera / MS Project)
#   FS = Finish-to-Start, SS = Start-to-Start, FF = Finish-to-Finish, SF = Start-to-Finish
TIPURI_RELATIE = ('FS', 'SS', 'FF', 'SF')

# Severitati pentru problemele de validare
SEVERITATI = ('eroare', 'avertisment', 'info')


@dataclass
class ArticolF3:
    """Un rand brut dintr-un fisier F3 (deviz / lista de cantitati), dupa normalizare."""
    cod_articol: str
    denumire: str
    um: str = ''
    cantitate: float = 0.0
    obiect: str = ''
    tronson: str = ''
    categorie: str = ''          # categoria din F3 (input optional, ex: "Terasamente")
    rand_sursa: int = 0          # nr. randului in fisier (pentru raportarea erorilor)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'ArticolF3':
        return cls(
            cod_articol=str(d.get('cod_articol', '')).strip(),
            denumire=str(d.get('denumire', '')).strip(),
            um=str(d.get('um', '')).strip(),
            cantitate=_to_float(d.get('cantitate', 0)),
            obiect=str(d.get('obiect', '')).strip(),
            tronson=str(d.get('tronson', '')).strip(),
            categorie=str(d.get('categorie', '')).strip(),
            rand_sursa=int(d.get('rand_sursa', 0) or 0),
        )


@dataclass
class Dependenta:
    """O relatie de precedenta intre doua activitati."""
    predecesor_id: str
    tip: str = 'FS'              # unul din TIPURI_RELATIE
    decalaj: int = 0            # lag in zile (poate fi negativ)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Dependenta':
        return cls(
            predecesor_id=str(d.get('predecesor_id', '')),
            tip=str(d.get('tip', 'FS')).upper(),
            decalaj=int(d.get('decalaj', 0) or 0),
        )


@dataclass
class Activitate:
    """O activitate de planificare (frunza in WBS), generata dintr-un articol F3."""
    id: str
    cod: str
    nume: str
    categorie_tehnologica: Optional[str]      # ex: SAPATURA, POZARE_CONDUCTA (None = neclasificat)
    obiect: str = ''
    tronson: str = ''
    um: str = ''
    cantitate: float = 0.0
    durata: int = 1                            # zile lucratoare
    wbs_id: str = ''                           # ex: 1.1.2.3
    nivel: int = 4
    increder_clasificare: float = 0.0          # scor 0..1
    predecesori: list = field(default_factory=list)   # list[Dependenta]

    def to_dict(self) -> dict:
        d = asdict(self)
        d['predecesori'] = [p.to_dict() if isinstance(p, Dependenta) else p
                            for p in self.predecesori]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Activitate':
        a = cls(
            id=str(d.get('id', '')),
            cod=str(d.get('cod', '')),
            nume=str(d.get('nume', '')),
            categorie_tehnologica=(d.get('categorie_tehnologica') or None),
            obiect=str(d.get('obiect', '')),
            tronson=str(d.get('tronson', '')),
            um=str(d.get('um', '')),
            cantitate=_to_float(d.get('cantitate', 0)),
            durata=int(d.get('durata', 1) or 1),
            wbs_id=str(d.get('wbs_id', '')),
            nivel=int(d.get('nivel', 4) or 4),
            increder_clasificare=_to_float(d.get('increder_clasificare', 0)),
        )
        a.predecesori = [Dependenta.from_dict(p) for p in (d.get('predecesori') or [])]
        return a


@dataclass
class NodWBS:
    """Un nod in arborele WBS (obiect / tronson / categorie / activitate)."""
    wbs_id: str                 # ex: 1.1.2
    nume: str
    nivel: int                  # 1=obiect, 2=tronson, 3=categorie, 4=activitate
    parinte_id: Optional[str]
    tip: str                    # 'obiect' | 'tronson' | 'categorie' | 'activitate'
    activitate_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Problema:
    """O problema detectata de motorul de validare."""
    cod: str                    # ex: 'ciclu', 'orfan', 'predecesor_lipsa'
    mesaj: str
    severitate: str = 'avertisment'   # 'eroare' | 'avertisment' | 'info'

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RaportValidare:
    """Rezultatul validarii structurii de planificare."""
    probleme: list = field(default_factory=list)     # list[Problema]
    nr_activitati: int = 0

    @property
    def erori(self) -> list:
        return [p for p in self.probleme if p.severitate == 'eroare']

    @property
    def avertismente(self) -> list:
        return [p for p in self.probleme if p.severitate == 'avertisment']

    @property
    def valid(self) -> bool:
        return len(self.erori) == 0

    def to_dict(self) -> dict:
        return {
            'valid': self.valid,
            'nr_activitati': self.nr_activitati,
            'nr_erori': len(self.erori),
            'nr_avertismente': len(self.avertismente),
            'probleme': [p.to_dict() for p in self.probleme],
        }


@dataclass
class RezultatPlanificare:
    """Rezultatul complet al pipeline-ului: activitati + WBS + validare + statistici."""
    activitati: list = field(default_factory=list)    # list[Activitate]
    noduri_wbs: list = field(default_factory=list)     # list[NodWBS]
    raport: Optional[RaportValidare] = None
    statistici: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'statistici': self.statistici,
            'raport': self.raport.to_dict() if self.raport else None,
            'noduri_wbs': [n.to_dict() for n in self.noduri_wbs],
            'activitati': [a.to_dict() for a in self.activitati],
        }


def _to_float(v) -> float:
    """Parseaza un numar tolerant (virgula zecimala, separatori de mii, spatii)."""
    if v is None or v == '':
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(' ', '').replace(' ', '')
    # 1.234,56 -> 1234.56 ; 1234,56 -> 1234.56
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0
