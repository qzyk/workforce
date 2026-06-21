"""
Migrare optionala, idempotenta si NEDISTRUCTIVA: specializari text -> competente.

Pentru fiecare angajat cu camp `specializari` (text CSV liber), creeaza:
- cate o Competenta in nomenclator pentru fiecare specializare distincta (daca
  nu exista deja una cu acelasi nume, comparat case-insensitive);
- cate o legatura AngajatCompetenta intre angajat si competenta (daca nu exista
  deja - respecta index-ul unic (angajat_id, competenta_id)).

Campul text `specializari` NU este modificat sau sters (sursa istorica ramane).
Scriptul poate fi rulat de mai multe ori fara efecte secundare (idempotent):
la a doua rulare nu se mai creeaza nimic.

Folosire (local):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
        scripts/migrare_specializari_competente.py

Pe PythonAnywhere (in venv):
    python scripts/migrare_specializari_competente.py

Nota: scriptul NU activeaza flag-ul 'competente'. Datele se populeaza, dar UI-ul
ramane ascuns pana cand flag-ul e pornit explicit.
"""

import os
import sys

# Asigura ca repo root e in sys.path (scriptul poate fi rulat din orice director).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def parseaza_specializari(text):
    """Imparte un text CSV in specializari curate, distincte, pastrand ordinea.

    Returneaza lista de string-uri (fara duplicate, comparat case-insensitive).
    """
    if not text:
        return []
    rezultat = []
    vazute = set()
    for bucata in text.split(','):
        nume = bucata.strip()
        if not nume:
            continue
        cheie = nume.lower()
        if cheie in vazute:
            continue
        vazute.add(cheie)
        rezultat.append(nume)
    return rezultat


def migreaza(app=None):
    """Ruleaza migrarea in contextul aplicatiei. Returneaza un dict cu statistici."""
    if app is None:
        from app import create_app
        app = create_app('default')

    from models import db, Angajat, Competenta, AngajatCompetenta

    stats = {
        'angajati_procesati': 0,
        'competente_create': 0,
        'atribuiri_create': 0,
        'atribuiri_existente': 0,
    }

    with app.app_context():
        # Cache nume_competenta(lower) -> Competenta (1 query, nu N).
        cache_competente = {}
        for c in Competenta.query.all():
            cache_competente[c.nume.strip().lower()] = c

        angajati = Angajat.query.all()
        for ang in angajati:
            specializari = parseaza_specializari(ang.specializari)
            if not specializari:
                continue
            stats['angajati_procesati'] += 1

            for nume in specializari:
                cheie = nume.lower()
                comp = cache_competente.get(cheie)
                if comp is None:
                    comp = Competenta(
                        nume=nume,
                        categorie='import specializari',
                        descriere='Generata automat din campul text specializari.',
                        activ=True,
                    )
                    db.session.add(comp)
                    db.session.flush()  # obtine comp.id pentru legatura
                    cache_competente[cheie] = comp
                    stats['competente_create'] += 1

                # Legatura idempotenta (respecta index-ul unic).
                existent = AngajatCompetenta.query.filter_by(
                    angajat_id=ang.id, competenta_id=comp.id
                ).first()
                if existent is not None:
                    stats['atribuiri_existente'] += 1
                    continue
                db.session.add(AngajatCompetenta(
                    angajat_id=ang.id,
                    competenta_id=comp.id,
                    nivel=3,  # nivel implicit (necunoscut din textul liber)
                ))
                stats['atribuiri_create'] += 1

        db.session.commit()

    return stats


if __name__ == '__main__':
    rezultat = migreaza()
    print('[OK] Migrare specializari -> competente (nedistructiva, idempotenta):')
    print(f"  Angajati cu specializari procesati : {rezultat['angajati_procesati']}")
    print(f"  Competente noi create              : {rezultat['competente_create']}")
    print(f"  Atribuiri noi create               : {rezultat['atribuiri_create']}")
    print(f"  Atribuiri deja existente (sarite)  : {rezultat['atribuiri_existente']}")
    print('  Campul text specializari a ramas neschimbat.')
