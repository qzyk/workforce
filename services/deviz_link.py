"""
Legatura Gantt <-> deviz pretuit (5D real).

Extrage preturile reale din pozitiile BoQ ale ofertelor unui proiect, indexate
pe cod articol (precis) si pe denumire normalizata (fallback). Folosit de
motorul Gantt ca sa coste activitatile cu preturile reale din deviz, nu cu
tarifele plate orientative (cand exista o oferta pretuita pe acelasi F3).
"""
from __future__ import annotations


def preturi_proiect(proiect_id: int, tenant_id=None) -> dict:
    """{'cod': {cheie_cod: rec}, 'den': {denumire_norm: rec}} unde
    rec = {'pu': pret_unitar, 'mat': material_unitar, 'man': manopera_unitar}."""
    from models import OfertaContract, PozitieBoQ
    from services.gantt.normalizare import normalizeaza, normalizeaza_cheie

    of_ids = [o.id for o in OfertaContract.query.filter_by(proiect_id=proiect_id).all()]
    pe_cod, pe_den = {}, {}
    if not of_ids:
        return {'cod': pe_cod, 'den': pe_den}
    for poz in PozitieBoQ.query.filter(PozitieBoQ.oferta_id.in_(of_ids)).all():
        pu = float(poz.pret_unitar or 0)
        if pu <= 0:
            continue
        rec = {'pu': pu,
               'mat': float(poz.valoare_materiale_unitar or 0),
               'man': float(poz.valoare_manopera_unitar or 0)}
        if poz.cod_articol:
            pe_cod.setdefault(normalizeaza_cheie(poz.cod_articol), rec)
        if poz.denumire:
            pe_den.setdefault(normalizeaza(poz.denumire), rec)
    return {'cod': pe_cod, 'den': pe_den}


def are_preturi(preturi_boq) -> bool:
    return bool(preturi_boq and (preturi_boq.get('cod') or preturi_boq.get('den')))
