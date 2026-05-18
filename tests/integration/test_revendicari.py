"""
Integration tests pentru Faza 13 - Revendicari + Legaturi M:N:
  - CRUD revendicari
  - Workflow status
  - Legaturi M:N: Termen / Task / Cantitate
  - Stergere legatura
"""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def setup_proiect_rev(app, admin_user):
    from models import (
        db, Proiect, Contract, Revendicare, RevendicareTermen,
        RevendicareTask, RevendicareCantitate, TermenContract,
        ProgramReferinta, TaskProgram, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara,
    )
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        # Cleanup cascade
        RevendicareCantitate.query.delete()
        RevendicareTask.query.delete()
        RevendicareTermen.query.delete()
        Revendicare.query.delete()
        TermenContract.query.delete()
        CantitateExecutataLunara.query.delete()
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('REV-%')).delete()
        OfertaContract.query.delete()
        TaskProgram.query.delete()
        ProgramReferinta.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='REV-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='REV-PRJ', nume='Rev Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='REV-CTR-001',
                     data_semnare=date(2026, 1, 15), status='activ',
                     valoare_totala=Decimal('100000'))
        db.session.add(c); db.session.commit()
        # Un termen
        t = TermenContract(contract_id=c.id, proiect_id=p.id,
                           denumire='Receptie partiala',
                           tip='receptie_partiala',
                           data_scadenta=date(2026, 5, 1))
        db.session.add(t); db.session.commit()
        # Un program + task
        prog = ProgramReferinta(proiect_id=p.id, versiune=1,
                                denumire='Prog Rev', data_emitere=date(2026, 1, 1),
                                sursa_import='manual')
        db.session.add(prog); db.session.commit()
        tk = TaskProgram(program_id=prog.id, proiect_id=p.id,
                         cod_extern='RT-001', denumire='Task Rev',
                         data_start_planificat=date(2026, 4, 1),
                         data_sfarsit_planificat=date(2026, 4, 30))
        db.session.add(tk); db.session.commit()
        # Oferta + pozitie + cantitate
        o = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=1,
                           data_emitere=date(2026, 1, 20),
                           valoare_totala=Decimal('100000'),
                           sursa_import='manual', aprobata=True)
        db.session.add(o); db.session.commit()
        pz = PozitieBoQ(oferta_id=o.id, proiect_id=p.id,
                        cod_articol='REV-001', denumire='Pozitie',
                        um='mc', cantitate_oferta=Decimal('100'),
                        pret_unitar=Decimal('500'), categorie='mixt', ordine=1)
        db.session.add(pz); db.session.commit()
        cnt = CantitateExecutataLunara(
            pozitie_boq_id=pz.id, proiect_id=p.id,
            an=2026, luna=4, cantitate_executata=Decimal('30'),
            valoare_calculata=Decimal('15000'), validat=True,
        )
        db.session.add(cnt); db.session.commit()
        yield {
            'proiect_id': p.id, 'contract_id': c.id, 'termen_id': t.id,
            'task_id': tk.id, 'cantitate_id': cnt.id,
        }
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        RevendicareCantitate.query.delete()
        RevendicareTask.query.delete()
        RevendicareTermen.query.delete()
        Revendicare.query.delete()
        TermenContract.query.delete()
        CantitateExecutataLunara.query.delete()
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('REV-%')).delete()
        OfertaContract.query.delete()
        TaskProgram.query.delete()
        ProgramReferinta.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='REV-PRJ').delete()
        db.session.commit()


class TestRevendicariCRUD:
    def test_lista_ok(self, authenticated_client, setup_proiect_rev):
        r = authenticated_client.get('/contracte/revendicari')
        assert r.status_code == 200

    def test_create_post(self, app, authenticated_client, setup_proiect_rev):
        from models import Revendicare
        r = authenticated_client.post('/contracte/revendicare/nou', data={
            'proiect_id': str(setup_proiect_rev['proiect_id']),
            'contract_id': str(setup_proiect_rev['contract_id']),
            'numar_revendicare': 'REV-TEST-001',
            'data_emitere': '2026-04-15',
            'tip': 'intarziere',
            'descriere': 'Test claim',
            'valoare_solicitata': '5000',
            'zile_prelungire_solicitate': '30',
            'status': 'draft',
            'corespondenta_initiatoare_id': '0',
        }, follow_redirects=False)
        assert r.status_code in (302, 303), f'Status {r.status_code}, data: {r.data[:500]}'
        with app.app_context():
            rev = Revendicare.query.filter_by(numar_revendicare='REV-TEST-001').first()
            assert rev is not None
            assert rev.tip == 'intarziere'
            assert rev.valoare_solicitata == Decimal('5000')
            assert rev.zile_prelungire_solicitate == 30


class TestRevendicariLegaturi:
    def _create_rev(self, app, setup_proiect_rev, tip='intarziere'):
        from models import db, Revendicare
        with app.app_context():
            r = Revendicare(
                proiect_id=setup_proiect_rev['proiect_id'],
                contract_id=setup_proiect_rev['contract_id'],
                numar_revendicare=f'REV-LINK-{tip}',
                data_emitere=date(2026, 4, 15),
                tip=tip, status='draft',
                zile_prelungire_solicitate=30,
            )
            db.session.add(r); db.session.commit()
            return r.id

    def test_link_termen(self, app, authenticated_client, setup_proiect_rev):
        from models import RevendicareTermen
        rid = self._create_rev(app, setup_proiect_rev, 'intarziere')
        r = authenticated_client.post(
            f'/contracte/revendicare/{rid}/link/termen',
            data={
                'termen_contract_id': str(setup_proiect_rev['termen_id']),
                'tip_legatura': 'cauza',
                'observatii': 'test link',
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            links = RevendicareTermen.query.filter_by(revendicare_id=rid).all()
            assert len(links) == 1
            assert links[0].tip_legatura == 'cauza'

    def test_link_task(self, app, authenticated_client, setup_proiect_rev):
        from models import RevendicareTask
        rid = self._create_rev(app, setup_proiect_rev, 'intarziere')
        r = authenticated_client.post(
            f'/contracte/revendicare/{rid}/link/task',
            data={
                'task_program_id': str(setup_proiect_rev['task_id']),
                'tip_legatura': 'consecinta',
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            assert RevendicareTask.query.filter_by(revendicare_id=rid).count() == 1

    def test_link_cantitate(self, app, authenticated_client, setup_proiect_rev):
        from models import RevendicareCantitate
        rid = self._create_rev(app, setup_proiect_rev, 'schimbare_scop')
        r = authenticated_client.post(
            f'/contracte/revendicare/{rid}/link/cantitate',
            data={
                'cantitate_lunara_id': str(setup_proiect_rev['cantitate_id']),
                'observatii': 'cantitate validata afectata',
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            assert RevendicareCantitate.query.filter_by(revendicare_id=rid).count() == 1

    def test_link_unique_no_duplicate(self, app, authenticated_client, setup_proiect_rev):
        """Insert acelasi link de 2 ori -> al doilea NU se duplica."""
        from models import RevendicareTermen
        rid = self._create_rev(app, setup_proiect_rev, 'intarziere')
        for _ in range(2):
            authenticated_client.post(
                f'/contracte/revendicare/{rid}/link/termen',
                data={
                    'termen_contract_id': str(setup_proiect_rev['termen_id']),
                    'tip_legatura': 'cauza',
                },
            )
        with app.app_context():
            assert RevendicareTermen.query.filter_by(revendicare_id=rid).count() == 1

    def test_link_sterge(self, app, authenticated_client, setup_proiect_rev):
        from models import db, RevendicareTermen
        rid = self._create_rev(app, setup_proiect_rev, 'intarziere')
        with app.app_context():
            link = RevendicareTermen(revendicare_id=rid,
                                     termen_contract_id=setup_proiect_rev['termen_id'],
                                     tip_legatura='cauza')
            db.session.add(link); db.session.commit()
            link_id = link.id
        r = authenticated_client.post(
            f'/contracte/revendicare/{rid}/link/termen/{link_id}/sterge',
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with app.app_context():
            assert RevendicareTermen.query.get(link_id) is None
