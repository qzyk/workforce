"""
Orchestratorul pipeline-ului de planificare.

    articole F3 -> clasificare -> durate -> WBS -> dependente -> validare -> RezultatPlanificare

MotorPlanificare incarca configuratiile o singura data (clasificare, dependente, setari)
si poate procesa multiple seturi de articole reutilizand acelasi clasificator (cu cache).
"""
from __future__ import annotations

import time
from typing import Optional

from .modele import Activitate, RezultatPlanificare
from .clasificare import Clasificator
from .wbs import genereaza_wbs
from .dependinte import genereaza_dependinte
from .durate import estimeaza_durata
from .validare import valideaza
from . import import_engine
from . import config_loader as cfg


class MotorPlanificare:
    """Punct de intrare de nivel inalt pentru generarea structurii Gantt."""

    def __init__(self, clasificare: Optional[dict] = None,
                 dependinte: Optional[dict] = None,
                 setari: Optional[dict] = None):
        self.dict_clasificare = clasificare or cfg.incarca('clasificare', cfg.CLASIFICARE_IMPLICITA)
        self.dependinte = dependinte or cfg.incarca('dependinte', cfg.DEPENDINTE_IMPLICITE)
        self.setari = setari or cfg.incarca('setari', cfg.SETARI_IMPLICITE)
        self.clasificator = Clasificator(self.dict_clasificare, self.setari.get('sinonime'))

    # -- pas cu pas (mapeaza endpoint-urile API) --
    def clasifica_articole(self, articole) -> list:
        """Transforma articole F3 -> activitati clasificate (cu durata estimata)."""
        activitati = []
        for i, art in enumerate(articole, start=1):
            cat, scor = self.clasificator.clasifica(art.denumire)
            durata = estimeaza_durata(art.cantitate, cat, self.setari)
            activitati.append(Activitate(
                id=f'A{i:06d}',
                cod=art.cod_articol,
                nume=art.denumire,
                categorie_tehnologica=cat,
                obiect=art.obiect,
                tronson=art.tronson,
                um=art.um,
                cantitate=art.cantitate,
                durata=durata,
                increder_clasificare=scor,
            ))
        return activitati

    def proceseaza(self, articole) -> RezultatPlanificare:
        """Ruleaza pipeline-ul complet pe o lista de ArticolF3."""
        t0 = time.perf_counter()

        activitati = self.clasifica_articole(articole)
        noduri = genereaza_wbs(activitati, self.dependinte.get('ordine_categorii', []))
        nr_dep = genereaza_dependinte(
            activitati,
            self.dependinte.get('relatii', []),
            self.dependinte.get('intra_categorie', 'secvential'),
            self.dependinte.get('ordine_categorii', []),
        )
        raport = valideaza(activitati)

        durata_s = round(time.perf_counter() - t0, 3)
        statistici = self._statistici(activitati, noduri, nr_dep, durata_s)
        return RezultatPlanificare(activitati=activitati, noduri_wbs=noduri,
                                   raport=raport, statistici=statistici)

    def genereaza_din_fisier(self, continut: bytes, extensie: str):
        """Import + pipeline complet. Intoarce (RezultatPlanificare, raport_import)."""
        articole, raport_import = import_engine.importa(continut, extensie, self.setari)
        rezultat = self.proceseaza(articole)
        rezultat.statistici['import'] = raport_import
        return rezultat, raport_import

    # -- statistici --
    def _statistici(self, activitati, noduri, nr_dep, durata_s) -> dict:
        neclasificate = sum(1 for a in activitati if not a.categorie_tehnologica)
        obiecte = {a.obiect for a in activitati}
        tronsoane = {(a.obiect, a.tronson) for a in activitati}
        per_categorie: dict = {}
        for a in activitati:
            k = a.categorie_tehnologica or 'NECLASIFICAT'
            per_categorie[k] = per_categorie.get(k, 0) + 1
        return {
            'nr_activitati': len(activitati),
            'nr_dependente': nr_dep,
            'nr_noduri_wbs': len(noduri),
            'nr_obiecte': len(obiecte),
            'nr_tronsoane': len(tronsoane),
            'nr_neclasificate': neclasificate,
            'procent_clasificat': (round(100 * (len(activitati) - neclasificate) / len(activitati), 1)
                                   if activitati else 0.0),
            'activitati_per_categorie': per_categorie,
            'durata_procesare_s': durata_s,
        }
