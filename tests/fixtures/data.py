"""
Factory de date pentru teste - hard-coded, fara dependinte externe.
Fiecare functie creeaza obiectul + il salveaza in DB + intoarce instanta.
"""

from datetime import date, datetime
import json


def make_proiect(db, Proiect, cod='PRJ-TEST-001', **kwargs):
    """Creeaza un proiect de test."""
    defaults = {
        'cod_proiect': cod,
        'nume': f'Proiect Test {cod}',
        'data_start': date(2025, 1, 1),
        'data_sfarsit_planificat': date(2025, 12, 31),
        'beneficiar': 'Beneficiar Test SRL',
        'locatie': 'Bucuresti',
        'status': 'activ',
    }
    defaults.update(kwargs)
    p = Proiect(**defaults)
    db.session.add(p)
    db.session.commit()
    return p


def make_angajat(db, Angajat, cnp='1900101010101', nume='Test', prenume='Angajat',
                 functie='Inginer', **kwargs):
    """Creeaza un angajat de test."""
    defaults = {
        'cnp': cnp,
        'nume': nume,
        'prenume': prenume,
        'email': f'{prenume.lower()}.{nume.lower()}@test.local',
        'functie': functie,
        'tip_contract': 'nedeterminat',
        'salariu_baza': 5000,
        'data_angajare': date(2024, 1, 1),
        'status': 'activ',
    }
    defaults.update(kwargs)
    a = Angajat(**defaults)
    db.session.add(a)
    db.session.commit()
    return a


def make_pontaj(db, Pontaj, angajat_id, proiect_id, data_zi=None,
                ora_start='08:00', ora_sfarsit='17:00', tip_zi='lucratoare', **kwargs):
    """Creeaza un pontaj de test si calculeaza orele."""
    defaults = {
        'angajat_id': angajat_id,
        'proiect_id': proiect_id,
        'data': data_zi or date(2025, 9, 1),
        'ora_start': ora_start,
        'ora_sfarsit': ora_sfarsit,
        'tip_zi': tip_zi,
        'status': 'draft',
    }
    defaults.update(kwargs)
    p = Pontaj(**defaults)
    p.calculeaza_ore()
    db.session.add(p)
    db.session.commit()
    return p


def make_raport_activitate(db, RaportActivitate, angajat_id, proiect_id,
                           tip='zilnica', titlu='Test activitate',
                           data_zi=None, **kwargs):
    """Creeaza o activitate (raport) de test."""
    defaults = {
        'angajat_id': angajat_id,
        'proiect_id': proiect_id,
        'data': data_zi or date(2025, 9, 1),
        'tip_activitate': tip,
        'activitate_principala': titlu,
        'status': 'draft',
        'status_executie': 'planificata',
    }
    defaults.update(kwargs)
    a = RaportActivitate(**defaults)
    if hasattr(a, 'calculeaza_perioada'):
        a.calculeaza_perioada()
    db.session.add(a)
    db.session.commit()
    return a


def make_santier(db, Santier, cod='S-TEST', **kwargs):
    """Creeaza un santier de test."""
    defaults = {
        'cod': cod,
        'nume': f'Santier Test {cod}',
        'oras': 'Bucuresti',
        'judet': 'Bucuresti',
        'status': 'activ',
    }
    defaults.update(kwargs)
    s = Santier(**defaults)
    db.session.add(s)
    db.session.commit()
    return s


def make_cladire(db, Cladire, santier_id, cod='B-TEST', **kwargs):
    """Creeaza o cladire de test."""
    defaults = {
        'santier_id': santier_id,
        'cod': cod,
        'nume': f'Cladire {cod}',
        'tip_constructie': 'rezidential',
        'nr_niveluri': 3,
    }
    defaults.update(kwargs)
    c = Cladire(**defaults)
    db.session.add(c)
    db.session.commit()
    return c


def make_nivel(db, Nivel, cladire_id, cod='N00', nume='Parter', ordine=0, **kwargs):
    """Creeaza un nivel."""
    defaults = {
        'cladire_id': cladire_id,
        'cod': cod,
        'nume': nume,
        'ordine': ordine,
        'elevatie_m': 0.0,
    }
    defaults.update(kwargs)
    n = Nivel(**defaults)
    db.session.add(n)
    db.session.commit()
    return n


def make_spatiu(db, Spatiu, nivel_id, cod='SP-001', nume='Birou test', **kwargs):
    """Creeaza un spatiu."""
    defaults = {
        'nivel_id': nivel_id,
        'cod': cod,
        'nume': nume,
        'tip_spatiu': 'birou',
        'suprafata_mp': 25.0,
    }
    defaults.update(kwargs)
    sp = Spatiu(**defaults)
    db.session.add(sp)
    db.session.commit()
    return sp


def make_element_bim(db, ElementBIM, cod='AHU-T1', tip='AHU',
                     spatiu_id=None, nivel_id=None, cladire_id=None, **kwargs):
    """Creeaza un element BIM."""
    defaults = {
        'cod': cod,
        'nume': f'Element {cod}',
        'tip_element': tip,
        'status': 'proiectat',
        'spatiu_id': spatiu_id,
        'nivel_id': nivel_id,
        'cladire_id': cladire_id,
    }
    defaults.update(kwargs)
    e = ElementBIM(**defaults)
    db.session.add(e)
    db.session.commit()
    return e


def setup_full_bim_hierarchy(db, Santier, Cladire, Nivel, Spatiu, ElementBIM,
                              santier_cod='S-FULL'):
    """
    Helper compus: creeaza ierarhie BIM completa pentru teste.
    Returneaza dict cu obiectele create.
    """
    s = make_santier(db, Santier, cod=santier_cod, nume='Santier Full Test')
    c = make_cladire(db, Cladire, santier_id=s.id, cod=f'{santier_cod}-B1')
    n_subsol = make_nivel(db, Nivel, cladire_id=c.id, cod='B01', nume='Subsol', ordine=-1)
    n_parter = make_nivel(db, Nivel, cladire_id=c.id, cod='N00', nume='Parter', ordine=0)
    n_etaj = make_nivel(db, Nivel, cladire_id=c.id, cod='N01', nume='Etaj 1', ordine=1)
    sp_lobby = make_spatiu(db, Spatiu, nivel_id=n_parter.id, cod='SP-LOBBY', nume='Lobby')
    sp_birou = make_spatiu(db, Spatiu, nivel_id=n_etaj.id, cod='SP-OFFICE', nume='Birou')
    e_ahu = make_element_bim(db, ElementBIM, cod='AHU-01',
                              tip='AHU', spatiu_id=sp_lobby.id,
                              nivel_id=n_parter.id, cladire_id=c.id)
    e_door = make_element_bim(db, ElementBIM, cod='DOOR-01',
                               tip='door', spatiu_id=sp_birou.id,
                               nivel_id=n_etaj.id, cladire_id=c.id)
    return {
        'santier': s, 'cladire': c,
        'nivel_subsol': n_subsol, 'nivel_parter': n_parter, 'nivel_etaj': n_etaj,
        'spatiu_lobby': sp_lobby, 'spatiu_birou': sp_birou,
        'element_ahu': e_ahu, 'element_door': e_door,
    }
