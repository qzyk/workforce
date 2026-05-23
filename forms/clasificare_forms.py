"""
Helper pentru clasificarea manuala bulk a pozitiilor BoQ (override categorie).

Nu folosim FieldList (prea greoi pentru zeci de randuri). Route-ul parseaza
direct request.form cu chei "categorie_<pozitie_id>".
"""

from __future__ import annotations


def parse_bulk_categorii(form_data, prefix: str = 'categorie_') -> dict[int, str]:
    """
    Extrage din request.form maparea {pozitie_id: categorie_lucrare}.

    Cauta chei de forma "categorie_<pozitie_id>". Ignora valorile goale.
    Returneaza dict {int pozitie_id: str categorie}.
    """
    result: dict[int, str] = {}
    for key, val in form_data.items():
        if not key.startswith(prefix):
            continue
        raw = (val or '').strip()
        if not raw:
            continue
        try:
            pid = int(key[len(prefix):])
        except (ValueError, TypeError):
            continue
        result[pid] = raw[:60]
    return result
