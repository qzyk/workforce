"""
Integration tests pentru Faza 12 - RaportLucrariProiect (aggregator).

Verifica:
  - Generare raport agregheaza Pontaj (ore) + RaportActivitate (descriere)
    + TaskProgram (taskuri overlap luna)
  - Reutilizeaza raport existent pentru (proiect, an, luna)
  - Detalii view
"""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def setup_pentru_raport(app, admin_user):
    """Setup proiect cu Pontaj + Activitati + Program + Taskuri."""
    from models import (
        db, Proiect, Angajat, Pontaj, ProgramReferinta, TaskProgram,
        RaportLucrariProiect,
    )
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        # Cleanup
        RaportLucrariProiect.query.delete()
        TaskProgram.query.delete()
        ProgramReferinta.query.delete()
        Pontaj.query.delete()
        Angajat.query.filter_by(cnp='1234567890123').delete()
        Proiect.query.filter_by(cod_proiect='RAP-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='RAP-PRJ', nume='Rap Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        a = Angajat(cnp='1234567890123', nume='RapTest', prenume='Worker',
                    email='rap@test.local',
                    functie='Muncitor', tip_contract='nedeterminat',
                    salariu_baza=3000, data_angajare=date(2026, 1, 1),
                    status='activ')
        db.session.add(a); db.session.commit()
        # 3 pontaje in luna 3/2026, 2 aprobate + 1 draft
        pj1 = Pontaj(angajat_id=a.id, proiect_id=p.id, data=date(2026, 3, 5),
                     ore_lucrate=Decimal('8'), status='aprobat',
                     tip_zi='lucratoare')
        pj2 = Pontaj(angajat_id=a.id, proiect_id=p.id, data=date(2026, 3, 10),
                     ore_lucrate=Decimal('8'), status='aprobat',
                     tip_zi='lucratoare')
        pj3 = Pontaj(angajat_id=a.id, proiect_id=p.id, data=date(2026, 3, 15),
                     ore_lucrate=Decimal('6'), status='draft',
                     tip_zi='lucratoare')
        db.session.add_all([pj1, pj2, pj3]); db.session.commit()

        # Program referinta + 2 taskuri overlap luna 3
        prog = ProgramReferinta(
            proiect_id=p.id, versiune=1, denumire='Test Prog',
            data_emitere=date(2026, 1, 1), sursa_import='manual',
        )
        db.session.add(prog); db.session.commit()
        t1 = TaskProgram(program_id=prog.id, proiect_id=p.id,
                         cod_extern='T-001', denumire='Faza 1',
                         data_start_planificat=date(2026, 2, 15),
                         data_sfarsit_planificat=date(2026, 3, 20))
        t2 = TaskProgram(program_id=prog.id, proiect_id=p.id,
                         cod_extern='T-002', denumire='Faza 2',
                         data_start_planificat=date(2026, 3, 10),
                         data_sfarsit_planificat=date(2026, 4, 30))
        # Task care NU se intersecteaza cu luna 3
        t3 = TaskProgram(program_id=prog.id, proiect_id=p.id,
                         cod_extern='T-003', denumire='Faza 3',
                         data_start_planificat=date(2026, 5, 1),
                         data_sfarsit_planificat=date(2026, 6, 30))
        db.session.add_all([t1, t2, t3]); db.session.commit()
        yield {'proiect_id': p.id, 'angajat_id': a.id}
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        RaportLucrariProiect.query.delete()
        TaskProgram.query.delete()
        ProgramReferinta.query.delete()
        Pontaj.query.delete()
        Angajat.query.filter_by(cnp='1234567890123').delete()
        Proiect.query.filter_by(cod_proiect='RAP-PRJ').delete()
        db.session.commit()


class TestRapoarteLucrari:
    def test_lista_ok(self, authenticated_client, setup_pentru_raport):
        r = authenticated_client.get(
            f'/contracte/proiect/{setup_pentru_raport["proiect_id"]}/rapoarte-lucrari'
        )
        assert r.status_code == 200

    def test_genereaza_agreaga_pontaj_aprobat(
        self, app, authenticated_client, setup_pentru_raport
    ):
        """Ore aprobate prioritare: 8+8=16 (ignora draft-ul de 6)."""
        from models import RaportLucrariProiect
        r = authenticated_client.post(
            f'/contracte/proiect/{setup_pentru_raport["proiect_id"]}/raport-lucrari/genereaza',
            data={'an': '2026', 'luna': '3'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            raport = RaportLucrariProiect.query.filter_by(
                proiect_id=setup_pentru_raport['proiect_id'], an=2026, luna=3
            ).first()
            assert raport is not None
            # Doar pontajele aprobate
            assert raport.ore_totale_manopera == Decimal('16')

    def test_genereaza_capteaza_taskuri_overlap(
        self, app, authenticated_client, setup_pentru_raport
    ):
        """Doar T-001 si T-002 se intersecteaza cu luna 3, NU T-003."""
        from models import RaportLucrariProiect
        authenticated_client.post(
            f'/contracte/proiect/{setup_pentru_raport["proiect_id"]}/raport-lucrari/genereaza',
            data={'an': '2026', 'luna': '3'},
        )
        with app.app_context():
            raport = RaportLucrariProiect.query.filter_by(
                proiect_id=setup_pentru_raport['proiect_id'], an=2026, luna=3
            ).first()
            taskuri = raport.taskuri_acoperite
            assert 'T-001' in taskuri
            assert 'T-002' in taskuri
            assert 'T-003' not in taskuri

    def test_regenereaza_reutilizeaza_existing(
        self, app, authenticated_client, setup_pentru_raport
    ):
        """A doua generare actualizeaza, nu duplica."""
        from models import RaportLucrariProiect
        # Genereaza de 2 ori
        for _ in range(2):
            authenticated_client.post(
                f'/contracte/proiect/{setup_pentru_raport["proiect_id"]}/raport-lucrari/genereaza',
                data={'an': '2026', 'luna': '3'},
            )
        with app.app_context():
            rapoarte = RaportLucrariProiect.query.filter_by(
                proiect_id=setup_pentru_raport['proiect_id'], an=2026, luna=3
            ).all()
            assert len(rapoarte) == 1  # NU duplicat

    def test_detalii_view(self, app, authenticated_client, setup_pentru_raport):
        from models import db, RaportLucrariProiect
        with app.app_context():
            r = RaportLucrariProiect(
                proiect_id=setup_pentru_raport['proiect_id'],
                an=2026, luna=3,
                ore_totale_manopera=Decimal('16'),
                progres_descriere='Test progres',
            )
            r.taskuri_acoperite = ['T-001', 'T-002']
            db.session.add(r); db.session.commit()
            rid = r.id
        resp = authenticated_client.get(f'/contracte/raport-lucrari/{rid}')
        assert resp.status_code == 200
        assert b'16' in resp.data  # ore manopera
        assert b'T-001' in resp.data
