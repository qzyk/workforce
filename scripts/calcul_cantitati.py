"""
Calcul cantitati OFFLINE pentru un model BIM (pentru modele mari, evita
timeout-ul web). Ruleaza dupa importul IFC.

Pe PA:
    cd ~/workforce
    ~/.virtualenvs/workforce-env/bin/python scripts/calcul_cantitati.py <model_id>
    # --toate = recalculeaza inclusiv elementele care au deja cantitate
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from services import cantitati_bim  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print('Utilizare: python scripts/calcul_cantitati.py <model_id> [--toate]')
        sys.exit(1)
    model_id = int(sys.argv[1])
    doar_lipsa = '--toate' not in sys.argv
    app = create_app('default')
    with app.app_context():
        t0 = time.time()
        res = cantitati_bim.extrage_cantitati(model_id, doar_lipsa=doar_lipsa)
        print(f"{res['status']} | {res['mesaj']} | {time.time() - t0:.1f}s")


if __name__ == '__main__':
    main()
