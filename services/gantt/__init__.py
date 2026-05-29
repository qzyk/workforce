"""
Modul GANTT F3 -> structura de planificare (WBS + activitati + dependente).

Genereaza automat o structura Gantt din articole de deviz / liste de cantitati (F3):
import -> clasificare tehnologica -> WBS -> durate -> dependente -> validare -> export
(CSV / MS Project XML / Primavera P6 XML / JSON).

Proiectat pentru proiecte mari (10.000-100.000+ activitati), fara dependinte
externe grele: pur Python + openpyxl. pandas / networkx sunt acceleratoare optionale.

Punct de intrare principal: services.gantt.pipeline.MotorPlanificare
"""

from .modele import (
    ArticolF3, Activitate, Dependenta, NodWBS, Problema,
    RaportValidare, RezultatPlanificare, TIPURI_RELATIE,
)
from .pipeline import MotorPlanificare

__all__ = [
    'ArticolF3', 'Activitate', 'Dependenta', 'NodWBS', 'Problema',
    'RaportValidare', 'RezultatPlanificare', 'TIPURI_RELATIE',
    'MotorPlanificare',
]
