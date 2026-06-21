"""
Serviciu pentru modulul Competente (skill matrix + matching).

Functii pure, fara dependente de request, usor de testat:
- normalizeaza: lowercase + fara diacritice (pentru potrivire pe continut).
- tokenizeaza: cuvinte semnificative (>= 3 litere) dintr-un text.
- scor_potrivire_angajat: cat de bine se potriveste un angajat pe o
  CategorieActivitate, pe baza competentelor lui active (potrivire pe cuvinte
  intre numele/categoria competentei si denumirea categoriei de activitate).
- angajati_pentru_categorie: lista de angajati cu scor descrescator pentru o
  CategorieActivitate (folosit la endpoint-ul de matching).

Regula de scor (simpla, deterministica, fara dependente noi):
- fiecare competenta atribuita activa care imparte cel putin un cuvant cu
  denumirea categoriei contribuie cu un scor de baza ponderat pe nivel (1-5).
- competentele expirate (data_expirare in trecut) NU contribuie la scor.
- scorul angajatului = suma contributiilor competentelor potrivite.

Modulul e gated pe feature flag 'competente' (vezi routes/competente.py);
serviciul in sine nu evalueaza flag-ul (e logica pura, apelata din rute gated).
"""

from __future__ import annotations

import unicodedata
from datetime import date
from typing import Iterable, Optional

from models import (
    db, Angajat, Competenta, AngajatCompetenta, CategorieActivitate,
)


# Cuvinte prea generice ca sa fie utile la potrivire (zgomot).
_STOPWORDS = {
    'lucrari', 'lucrare', 'activitate', 'activitati', 'general', 'generale',
    'diverse', 'alte', 'montaj', 'lucru', 'pentru', 'din', 'pe', 'cu',
    'instalatie', 'instalatii', 'tip',
}


def normalizeaza(text: Optional[str]) -> str:
    """Lowercase + elimina diacriticele (potrivire robusta pe continut)."""
    if not text:
        return ''
    # Descompune diacriticele si elimina semnele combinante.
    nfkd = unicodedata.normalize('NFKD', text)
    fara_diacritice = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return fara_diacritice.lower().strip()


def tokenizeaza(text: Optional[str]) -> set[str]:
    """Set de cuvinte semnificative (>= 3 litere, fara stopwords) dintr-un text."""
    norm = normalizeaza(text)
    cuvinte = set()
    bucata = []
    for ch in norm:
        if ch.isalnum():
            bucata.append(ch)
        else:
            if bucata:
                cuvinte.add(''.join(bucata))
                bucata = []
    if bucata:
        cuvinte.add(''.join(bucata))
    return {c for c in cuvinte if len(c) >= 3 and c not in _STOPWORDS}


def _competenta_potriveste(tokens_categorie: set[str], comp: Competenta) -> bool:
    """True daca numele sau categoria competentei imparte un cuvant cu categoria."""
    tokens_comp = tokenizeaza(comp.nume) | tokenizeaza(comp.categorie)
    return bool(tokens_comp & tokens_categorie)


def _atribuire_activa(ac: AngajatCompetenta, la_data: date) -> bool:
    """O atribuire contribuie daca nu e expirata la data data (referinta)."""
    if ac.data_expirare is not None and ac.data_expirare < la_data:
        return False
    return True


def scor_potrivire_angajat(
    angajat_id: int,
    categorie: CategorieActivitate,
    *,
    la_data: Optional[date] = None,
) -> dict:
    """
    Calculeaza scorul de potrivire al unui angajat pe o categorie de activitate.

    Returneaza un dict cu:
      - 'scor' (int): suma contributiilor competentelor potrivite (0 = niciuna).
      - 'competente' (list[AngajatCompetenta]): atribuirile care au contat.
      - 'expirate' (list[AngajatCompetenta]): competente potrivite dar expirate
        (utile in UI ca avertisment: angajatul ar fi potrivit, dar trebuie reinnoit).
    """
    if la_data is None:
        la_data = date.today()

    tokens_categorie = tokenizeaza(categorie.denumire) if categorie else set()

    rezultat = {'scor': 0, 'competente': [], 'expirate': []}
    if not tokens_categorie:
        return rezultat

    atribuiri = (
        AngajatCompetenta.query
        .filter(AngajatCompetenta.angajat_id == angajat_id)
        .join(Competenta, AngajatCompetenta.competenta_id == Competenta.id)
        .filter(Competenta.activ.is_(True))
        .all()
    )

    for ac in atribuiri:
        if not _competenta_potriveste(tokens_categorie, ac.competenta):
            continue
        if not _atribuire_activa(ac, la_data):
            rezultat['expirate'].append(ac)
            continue
        nivel = ac.nivel if ac.nivel else 3
        rezultat['scor'] += int(nivel)
        rezultat['competente'].append(ac)

    return rezultat


def angajati_pentru_categorie(
    categorie: CategorieActivitate,
    *,
    angajati: Optional[Iterable[Angajat]] = None,
    doar_cu_scor: bool = True,
    la_data: Optional[date] = None,
) -> list[dict]:
    """
    Lista angajatilor potriviti pentru o categorie, ordonata descrescator dupa scor.

    Fiecare element: {'angajat': Angajat, 'scor': int, 'competente': [...],
    'expirate': [...]}. Daca `doar_cu_scor` e True, exclude angajatii cu scor 0.
    """
    if angajati is None:
        angajati = (
            Angajat.query.filter_by(status='activ')
            .order_by(Angajat.nume, Angajat.prenume)
            .all()
        )

    rezultate = []
    for ang in angajati:
        info = scor_potrivire_angajat(ang.id, categorie, la_data=la_data)
        if doar_cu_scor and info['scor'] <= 0 and not info['expirate']:
            continue
        rezultate.append({
            'angajat': ang,
            'scor': info['scor'],
            'competente': info['competente'],
            'expirate': info['expirate'],
        })

    rezultate.sort(key=lambda r: (r['scor'], r['angajat'].nume), reverse=True)
    return rezultate
