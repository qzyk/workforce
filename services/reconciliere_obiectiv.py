"""
Reconciliere pe 3 niveluri a unui obiectiv de investitie: F3 -> F2 -> F1.

Primeste un folder cu fisierele unui obiectiv (F1 + F2-uri + F3-uri) si verifica:
  - Nivel F3->F2: totalul fiecarui F3 (suma articolelor) == valoarea lui declarata
    in F2 (linia sub-obiectului).
  - Nivel F2->F1: suma sub-obiectelor unui F2 == valoarea obiectului in F1
    (informativ; capitolele Montaj/Procurare pot fi separate in F1).
  - Sumar: ce obiecte/sub-obiecte lipsesc sau au abateri > toleranta.

Nu scrie nimic in DB - e un raport de QA pe devizele primite. Strict aditiv.
Totalurile F3 sunt calculate cu motorul existent `gantt.import_engine`.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal
from typing import Optional

from services.parsers import centralizator_f1f2 as cf


TOLERANTA = Decimal('1.00')   # lei - rotunjire acceptata


def _total_f3(path: str) -> tuple[Decimal, int]:
    """Suma articolelor unui F3 (coloana TOTAL) + nr articole. (0,0) la eroare.

    Foloseste extractorul direct (cf.total_f3_file), nu gantt/import_engine:
    formatul cu antet 'Capitol de lucrari' nu e recunoscut de motorul de articole,
    iar pentru reconciliere ne trebuie doar TOTALUL, nu articolele individuale."""
    try:
        return cf.total_f3_file(path)
    except Exception:
        return Decimal('0'), 0


def clasifica_fisiere(director: str) -> dict:
    """Imparte fisierele din folder pe tip: F1, F2 (pe cod obiect), F3 (pe obiect+sub)."""
    f1 = None
    f2: dict[str, str] = {}
    f3: dict[tuple[str, str], str] = {}
    for root, _dirs, files in os.walk(director):
        for f in files:
            if not f.lower().endswith(('.xls', '.xlsx')):
                continue
            p = os.path.join(root, f)
            low = f.lower()
            if 'f1' in low and 'obiectiv' in low:
                f1 = p
            elif 'f2' in low or 'centralizator_pe_obiect' in low:
                m = re.match(r'^(\d{3})', f)
                if m:
                    f2[m.group(1)] = p
            elif 'f3' in low or 'lista_cantitati' in low:
                m = re.match(r'^(\d{3})[_\-](\d{3})', f)
                if m:
                    f3[(m.group(1), m.group(2))] = p
    return dict(f1=f1, f2=f2, f3=f3)


def reconciliaza(director: str) -> dict:
    """Construieste raportul de reconciliere pe 3 niveluri pentru un obiectiv."""
    fisiere = clasifica_fisiere(director)
    f1p, f2map, f3map = fisiere['f1'], fisiere['f2'], fisiere['f3']

    f1 = cf.parse_f1_file(f1p) if f1p else None
    f2parsed = {cod: cf.parse_f2_file(p) for cod, p in f2map.items()}

    # --- Nivel F3 -> F2 ---
    linii_f3 = []
    for (ob, sub), p in sorted(f3map.items()):
        total_f3, n_art = _total_f3(p)
        declarat = None
        if ob in f2parsed:
            for s in f2parsed[ob]['sub_obiecte']:
                if s['cod'] == sub:
                    declarat = s['valoare']
                    break
        abatere = (total_f3 - declarat) if declarat is not None else None
        ok = declarat is not None and abs(abatere) <= TOLERANTA
        linii_f3.append(dict(
            obiect=ob, sub=sub, fisier=os.path.basename(p), articole=n_art,
            total_f3=total_f3, declarat_f2=declarat, abatere=abatere, ok=ok,
        ))

    # --- Nivel F2 -> F1 ---
    # F1 listeaza acelasi cod de obiect sub mai multe capitole (4.1 Constructii,
    # 4.2 Montaj, 4.3-4.5 Echipamente). Pastram PRIMA aparitie = linia de
    # Constructii (4.1). Δ intre suma F2 (care include montaj) si linia 4.1 din F1
    # reprezinta partea de montaj/echipamente a obiectului - asteptat, nu eroare.
    obiecte_f1: dict[str, dict] = {}
    for o in (f1['obiecte'] if f1 else []):
        obiecte_f1.setdefault(o['cod'], o)
    linii_f2 = []
    for cod, parsed in sorted(f2parsed.items()):
        suma_sub = sum((s['valoare'] for s in parsed['sub_obiecte']), Decimal('0'))
        val_f1 = obiecte_f1.get(cod, {}).get('valoare')
        abatere = (suma_sub - val_f1) if val_f1 is not None else None
        ok = val_f1 is not None and abs(abatere) <= TOLERANTA
        linii_f2.append(dict(
            obiect=cod, nume=obiecte_f1.get(cod, {}).get('nume'),
            sub_obiecte=len(parsed['sub_obiecte']),
            suma_sub_obiecte=suma_sub, valoare_f1_constructii=val_f1,
            abatere=abatere, ok=ok,
        ))

    # --- Sumar ---
    n_f3_ok = sum(1 for l in linii_f3 if l['ok'])
    n_f3_abateri = sum(1 for l in linii_f3 if l['abatere'] is not None and not l['ok'])
    n_f3_neimperecheat = sum(1 for l in linii_f3 if l['declarat_f2'] is None)
    return dict(
        director=director,
        are_f1=f1 is not None,
        nr_f2=len(f2parsed),
        nr_f3=len(f3map),
        obiecte_f1=[dict(cod=o['cod'], nume=o['nume'], valoare=o['valoare'])
                    for o in (f1['obiecte'] if f1 else [])],
        total_f1=(f1.get('total_4_1') or f1.get('total')) if f1 else None,
        linii_f3=linii_f3,
        linii_f2=linii_f2,
        sumar=dict(
            f3_ok=n_f3_ok, f3_abateri=n_f3_abateri,
            f3_neimperecheat=n_f3_neimperecheat, f3_total=len(linii_f3),
        ),
    )


def format_text(raport: dict) -> str:
    """Raport lizibil pentru consola / CLI."""
    def lei(v):
        return f'{float(v):,.2f}'.replace(',', '@').replace('.', ',').replace('@', '.') if v is not None else '—'

    L = []
    L.append(f"Obiectiv: {os.path.basename(raport['director'].rstrip('/'))}")
    L.append(f"  F1={'da' if raport['are_f1'] else 'NU'}  F2={raport['nr_f2']}  F3={raport['nr_f3']}")
    s = raport['sumar']
    L.append(f"  F3->F2: {s['f3_ok']} ok / {s['f3_abateri']} abateri / "
             f"{s['f3_neimperecheat']} neimperecheate (din {s['f3_total']})")
    L.append("")
    L.append("  Nivel F3 -> F2 (total lista vs valoare declarata in F2):")
    for l in raport['linii_f3']:
        marca = 'OK ' if l['ok'] else ('?? ' if l['declarat_f2'] is None else 'XX ')
        L.append(f"   {marca}{l['obiect']}_{l['sub']}  art={l['articole']:>4}  "
                 f"F3={lei(l['total_f3']):>16}  F2={lei(l['declarat_f2']):>16}  "
                 f"Δ={lei(l['abatere']):>12}")
    L.append("")
    L.append("  Nivel F2 -> F1 (suma sub-obiecte F2 vs linia Constructii 4.1 din F1;")
    L.append("                  Δ != 0 = partea de montaj/echipamente a obiectului):")
    for l in raport['linii_f2']:
        marca = 'OK ' if l['ok'] else '~~ '
        L.append(f"   {marca}obiect {l['obiect']}  ΣF2={lei(l['suma_sub_obiecte']):>16}  "
                 f"F1(4.1)={lei(l['valoare_f1_constructii']):>16}  Δ={lei(l['abatere']):>12}")
    return '\n'.join(L)
