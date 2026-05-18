"""
Serviciu agregator pentru RaportLucrariProiect (Faza 12).

Citește Pontaj + RaportActivitate + TaskProgram pentru o luna data,
sintetizeaza intr-un snapshot RaportLucrariProiect. NU modifica datele
sursa - doar le agregheaza.

Folosit pentru:
  - Status raport intern pe proiect (ore totale, progres, taskuri acoperite)
  - Input pentru SituatieLunara (manopera consumata) si negocieri claim
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from models import (
    db, Proiect, Pontaj, RaportActivitate, ProgramReferinta, TaskProgram,
    RaportLucrariProiect,
)


def genereaza_raport_lucrari(proiect_id: int, an: int, luna: int,
                              user_id: Optional[int] = None) -> RaportLucrariProiect:
    """
    Genereaza (sau regenereaza) un RaportLucrariProiect.

    Agreaga:
      - ore_totale_manopera = sum(Pontaj.ore_lucrate) pentru pontajele cu
        proiect_id si data in interval luna (status='aprobat' preferat).
      - progres_descriere = concatenarea descrierilor lunare din
        RaportActivitate.activitate_principala (tip 'lunara').
      - task_program_acoperite = lista cod_extern al TaskProgram-urilor a
        caror durata se intersecteaza cu luna data, din programul cel mai
        recent al proiectului (auto-detected).

    Reutilizeaza un raport existent daca (proiect, an, luna) match,
    actualizeaza valorile. Returneaza raportul commit-uit.
    """
    proiect = Proiect.query.get(proiect_id)
    if proiect is None:
        raise ValueError(f'Proiect id={proiect_id} nu exista.')

    raport = RaportLucrariProiect.query.filter_by(
        proiect_id=proiect_id, an=an, luna=luna,
    ).first()
    if raport is None:
        raport = RaportLucrariProiect(
            proiect_id=proiect_id, an=an, luna=luna,
            data_intocmire=date.today(),
            intocmit_de_id=user_id,
        )
        db.session.add(raport)
        db.session.flush()

    # 1. Ore manopera din Pontaj (status='aprobat' preferential; fallback toate)
    luna_start = date(an, luna, 1)
    if luna == 12:
        luna_end = date(an + 1, 1, 1)
    else:
        luna_end = date(an, luna + 1, 1)

    q_pontaj_base = db.session.query(
        db.func.sum(Pontaj.ore_lucrate)
    ).filter(
        Pontaj.proiect_id == proiect_id,
        Pontaj.data >= luna_start,
        Pontaj.data < luna_end,
    )
    ore_aprobate = q_pontaj_base.filter(Pontaj.status == 'aprobat').scalar() or Decimal('0')
    ore_totale = db.session.query(db.func.sum(Pontaj.ore_lucrate)).filter(
        Pontaj.proiect_id == proiect_id,
        Pontaj.data >= luna_start,
        Pontaj.data < luna_end,
    ).scalar() or Decimal('0')
    raport.ore_totale_manopera = ore_aprobate if ore_aprobate else ore_totale

    # 2. Progres descriere din RaportActivitate (tip lunara/saptamanala)
    activitati = RaportActivitate.query.filter(
        RaportActivitate.proiect_id == proiect_id,
        RaportActivitate.data >= luna_start,
        RaportActivitate.data < luna_end,
        RaportActivitate.tip_activitate.in_(['lunara', 'saptamanala']),
    ).order_by(RaportActivitate.data).all()
    if activitati:
        bullets = []
        for a in activitati:
            text = (a.activitate_principala or '').strip()
            if text:
                prefix = f'[{a.data}]' if a.data else ''
                bullets.append(f'{prefix} {text}')
        raport.progres_descriere = '\n'.join(bullets) if bullets else None

    # 3. Taskuri acoperite din TaskProgram (program cel mai recent al proiectului)
    program = ProgramReferinta.query.filter_by(
        proiect_id=proiect_id
    ).order_by(ProgramReferinta.versiune.desc()).first()
    if program is not None:
        taskuri_overlap = TaskProgram.query.filter(
            TaskProgram.program_id == program.id,
            TaskProgram.data_start_planificat < luna_end,
            TaskProgram.data_sfarsit_planificat >= luna_start,
        ).all()
        # Salvam doar codul_extern (sau ID daca lipseste)
        coduri = []
        for t in taskuri_overlap:
            coduri.append(t.cod_extern or f'task_id_{t.id}')
        raport.taskuri_acoperite = coduri

    db.session.commit()
    return raport
