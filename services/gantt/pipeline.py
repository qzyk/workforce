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
from .cost import calculeaza_cost
from .program import programeaza, curba_s, drum_critic
from .validare import valideaza
from . import import_engine
from . import store


class MotorPlanificare:
    """Punct de intrare de nivel inalt pentru generarea structurii Gantt.

    Configurarea vine din overlay-ul `store` (DB suprascrie JSON; fallback la JSON
    daca nu exista randuri / context / tabel). `tenant_id` selecteaza regulile
    per-organizatie (None = globale).
    """

    def __init__(self, clasificare: Optional[dict] = None,
                 dependinte: Optional[dict] = None,
                 setari: Optional[dict] = None,
                 tenant_id: Optional[int] = None,
                 preturi_boq: Optional[dict] = None):
        self.tenant_id = tenant_id
        self.preturi_boq = preturi_boq   # preturi reale din deviz (5D), optional
        self.dict_clasificare = clasificare or store.clasificare(tenant_id)
        self.dependinte = dependinte or store.dependinte(tenant_id)
        self.setari = setari or store.setari(tenant_id)
        self.tarife = store.tarife_gantt(tenant_id)
        self.clasificator = Clasificator(self.dict_clasificare, self.setari.get('sinonime'),
                                         reguli_prefix=store.reguli_prefix_cod(tenant_id))

    # -- pas cu pas (mapeaza endpoint-urile API) --
    def clasifica_articole(self, articole) -> list:
        """Transforma articole F3 -> activitati clasificate (cu durata estimata)."""
        activitati = []
        for i, art in enumerate(articole, start=1):
            cat, scor = self.clasificator.clasifica(art.denumire, art.cod_articol)
            durata = estimeaza_durata(art.cantitate, cat, self.setari)
            val, vmat, vman, estimat = calculeaza_cost(art, cat, self.tarife, self.preturi_boq)
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
                valoare=val,
                valoare_material=vmat,
                valoare_manopera=vman,
                cost_estimat=estimat,
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
        durata_totala = programeaza(activitati)   # forward pass -> start/finish per activitate
        nr_critice = drum_critic(activitati, durata_totala)  # backward pass -> marja + critic
        raport = valideaza(activitati)

        durata_s = round(time.perf_counter() - t0, 3)
        statistici = self._statistici(activitati, noduri, nr_dep, durata_s)
        statistici['durata_totala_zile'] = durata_totala
        statistici['nr_activitati_critice'] = nr_critice
        statistici['curba_s'] = curba_s(activitati, durata_totala)
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
        cost_categorie: dict = {}
        cost_obiect: dict = {}
        cost_total = cost_material = cost_manopera = 0.0
        nr_estimate = 0
        for a in activitati:
            k = a.categorie_tehnologica or 'NECLASIFICAT'
            per_categorie[k] = per_categorie.get(k, 0) + 1
            cost_categorie[k] = round(cost_categorie.get(k, 0.0) + (a.valoare or 0), 2)
            cost_obiect[a.obiect] = round(cost_obiect.get(a.obiect, 0.0) + (a.valoare or 0), 2)
            cost_total += a.valoare or 0
            cost_material += a.valoare_material or 0
            cost_manopera += a.valoare_manopera or 0
            if a.cost_estimat:
                nr_estimate += 1
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
            'cost_total': round(cost_total, 2),
            'cost_material': round(cost_material, 2),
            'cost_manopera': round(cost_manopera, 2),
            'cost_per_categorie': cost_categorie,
            'cost_per_obiect': cost_obiect,
            'nr_cost_estimat': nr_estimate,
            'durata_procesare_s': durata_s,
        }
