"""
Serviciu pentru gestionarea TermenUrmarit (Faza 13).

Functii publice:
  - creeaza_termen_din_corespondenta(corespondenta) -> TermenUrmarit | None
    Daca corespondenta are genereaza_termen=True + subtip valid,
    creeaza un TermenUrmarit cu regula 30-zile (sau actualizeaza unul existent).

  - sterge_termen_din_corespondenta(corespondenta) -> bool
    Sterge TermenUrmarit asociat unei corespondente (folosit la unset
    genereaza_termen sau la stergerea corespondentei).

  - creeaza_termen_program_referinta(contract, user_id=None) -> TermenUrmarit | None
    La setarea contract.data_inceput_executie, auto-creeaza termen
    'emitere_program_30_zile' (regula HG907/2016).

Idempotent: nu duplica termene pentru aceeasi sursa.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from models import db, Corespondenta, Contract, TermenUrmarit


# Regula: 30 zile pentru raspuns la notificare beneficiar
ZILE_GRACE_NOTIFICARE = 30
ZILE_ANTICIPARE_DEFAULT = 7


def creeaza_termen_din_corespondenta(
    corespondenta: Corespondenta,
    user_id: Optional[int] = None,
) -> Optional[TermenUrmarit]:
    """
    Creeaza sau actualizeaza un TermenUrmarit asociat unei Corespondente.

    Reguli:
      - Daca corespondenta.genereaza_termen este False -> NU face nimic.
      - Daca exista deja un TermenUrmarit cu (entitate_sursa='corespondenta',
        id_entitate_sursa=corespondenta.id), il actualizeaza
        (data_scadenta = data_inregistrare + 30 zile).
      - Altfel, creeaza un termen nou cu tip_regula='raspuns_30_zile'.

    Returneaza TermenUrmarit creat/actualizat sau None daca nu se aplica.
    """
    if not corespondenta or not corespondenta.genereaza_termen:
        return None
    if not corespondenta.data_inregistrare:
        return None

    data_start = corespondenta.data_inregistrare
    data_scadenta = data_start + timedelta(days=ZILE_GRACE_NOTIFICARE)

    existing = TermenUrmarit.query.filter_by(
        entitate_sursa='corespondenta',
        id_entitate_sursa=corespondenta.id,
    ).first()

    if existing is not None:
        # Update: doar daca status='activ' (nu re-deschidem termene indeplinite)
        if existing.status == 'activ':
            existing.data_start = data_start
            existing.data_scadenta = data_scadenta
            existing.zile_grace = ZILE_GRACE_NOTIFICARE
            existing.proiect_id = corespondenta.proiect_id
        return existing

    termen = TermenUrmarit(
        proiect_id=corespondenta.proiect_id,
        entitate_sursa='corespondenta',
        id_entitate_sursa=corespondenta.id,
        tip_regula='raspuns_30_zile',
        data_start=data_start,
        data_scadenta=data_scadenta,
        zile_grace=ZILE_GRACE_NOTIFICARE,
        zile_anticipare=ZILE_ANTICIPARE_DEFAULT,
        status='activ',
        note=(f'Termen auto-generat din corespondenta '
              f'"{corespondenta.numar_inregistrare}" '
              f'({corespondenta.subtip or corespondenta.tip}).'),
    )
    db.session.add(termen)
    db.session.flush()
    return termen


def sterge_termen_din_corespondenta(
    corespondenta: Corespondenta,
) -> bool:
    """
    Sterge TermenUrmarit asociat unei Corespondente (daca exista).
    Returneaza True daca a sters ceva, False altfel.
    """
    if not corespondenta:
        return False
    deleted = TermenUrmarit.query.filter_by(
        entitate_sursa='corespondenta',
        id_entitate_sursa=corespondenta.id,
    ).delete()
    return deleted > 0


def creeaza_termen_program_referinta(
    contract: Contract,
    user_id: Optional[int] = None,
) -> Optional[TermenUrmarit]:
    """
    Auto-creeaza termen 'emitere_program_30_zile' la setarea NTP executie.

    Conform conventiei HG907/2016: programul de referinta trebuie emis in
    30 zile de la data NTP executie. Asta e un termen "watcher" pe care il
    folosim ca alerta in faza 14 (job APScheduler).

    Idempotent: daca exista deja un termen pentru acest contract, NU duplica.
    """
    if not contract or not contract.data_inceput_executie:
        return None

    existing = TermenUrmarit.query.filter_by(
        entitate_sursa='contract',
        id_entitate_sursa=contract.id,
        tip_regula='emitere_program_30_zile',
    ).first()
    if existing is not None:
        # Update doar data_scadenta daca data_inceput_executie a fost schimbata
        new_scadenta = contract.data_inceput_executie + timedelta(days=30)
        if existing.status == 'activ' and existing.data_scadenta != new_scadenta:
            existing.data_start = contract.data_inceput_executie
            existing.data_scadenta = new_scadenta
        return existing

    termen = TermenUrmarit(
        proiect_id=contract.proiect_id,
        entitate_sursa='contract',
        id_entitate_sursa=contract.id,
        tip_regula='emitere_program_30_zile',
        data_start=contract.data_inceput_executie,
        data_scadenta=contract.data_inceput_executie + timedelta(days=30),
        zile_grace=30,
        zile_anticipare=ZILE_ANTICIPARE_DEFAULT,
        status='activ',
        note=(f'Termen auto-generat: emitere program de referinta la 30 zile '
              f'de la NTP executie contract {contract.nr_contract}.'),
    )
    db.session.add(termen)
    db.session.flush()
    return termen
