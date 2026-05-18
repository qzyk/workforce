"""
Integration tests pentru detectia automata de conflicte (Faza 13).

Verifica services/conflict_revendicare.py:
  - detecta_conflicte() pe diverse scenarii
  - numara_conflicte() pentru badge UI
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest


@pytest.fixture
def setup_conflict(app, admin_user):
    """Setup proiect cu termene, taskuri, cantitati pentru test conflicte."""
    from models import (
        db, Proiect, Contract, TermenContract, ProgramReferinta, TaskProgram,
        OfertaContract, PozitieBoQ, CantitateExecutataLunara, SituatieLunara,
        Revendicare,
    )
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('controale-contract', True, commit=True)
        # Cleanup
        from models import (RevendicareCantitate, RevendicareTask, RevendicareTermen)
        RevendicareCantitate.query.delete()
        RevendicareTask.query.delete()
        RevendicareTermen.query.delete()
        Revendicare.query.delete()
        SituatieLunara.query.delete()
        CantitateExecutataLunara.query.delete()
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('CNF-%')).delete()
        OfertaContract.query.delete()
        TermenContract.query.delete()
        TaskProgram.query.delete()
        ProgramReferinta.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='CNF-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='CNF-PRJ', nume='Conf Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='CNF-CTR-001',
                     data_semnare=date(2026, 1, 15), status='activ',
                     valoare_totala=Decimal('100000'))
        db.session.add(c); db.session.commit()

        # 2 termene: 1 in intervalul revendicarii (15 zile + 30 = 45 zile),
        # 1 in afara (90 zile)
        t_in = TermenContract(contract_id=c.id, proiect_id=p.id,
                              denumire='Termen IN', tip='executie',
                              data_scadenta=date(2026, 5, 1),  # 16 zile dupa rev
                              status='planificat')
        t_out = TermenContract(contract_id=c.id, proiect_id=p.id,
                               denumire='Termen OUT', tip='executie',
                               data_scadenta=date(2026, 8, 1),  # mult dupa
                               status='planificat')
        db.session.add_all([t_in, t_out]); db.session.commit()

        # Program + 2 taskuri (1 in interval, 1 in afara)
        prog = ProgramReferinta(proiect_id=p.id, versiune=1,
                                denumire='P', data_emitere=date(2026, 1, 1),
                                sursa_import='manual')
        db.session.add(prog); db.session.commit()
        tk_in = TaskProgram(program_id=prog.id, proiect_id=p.id,
                            cod_extern='CT-IN', denumire='Task IN',
                            data_start_planificat=date(2026, 4, 1),
                            data_sfarsit_planificat=date(2026, 5, 10),  # in interval
                            procent_realizare=Decimal('30'))
        tk_out = TaskProgram(program_id=prog.id, proiect_id=p.id,
                             cod_extern='CT-OUT', denumire='Task OUT',
                             data_start_planificat=date(2026, 7, 1),
                             data_sfarsit_planificat=date(2026, 8, 1),
                             procent_realizare=Decimal('0'))
        db.session.add_all([tk_in, tk_out]); db.session.commit()

        # Oferta + 1 pozitie + cantitate validata
        o = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=1,
                           data_emitere=date(2026, 1, 20),
                           valoare_totala=Decimal('100000'),
                           sursa_import='manual', aprobata=True)
        db.session.add(o); db.session.commit()
        pz = PozitieBoQ(oferta_id=o.id, proiect_id=p.id,
                        cod_articol='CNF-001', denumire='Test',
                        um='mc', cantitate_oferta=Decimal('100'),
                        pret_unitar=Decimal('500'), categorie='mixt', ordine=1)
        db.session.add(pz); db.session.commit()
        cnt = CantitateExecutataLunara(
            pozitie_boq_id=pz.id, proiect_id=p.id,
            an=2026, luna=3, cantitate_executata=Decimal('20'),
            valoare_calculata=Decimal('10000'), validat=True,
        )
        db.session.add(cnt); db.session.commit()

        # Situatie aprobata pentru luna 3
        sit_apr = SituatieLunara(
            proiect_id=p.id, contract_id=c.id, an=2026, luna=3,
            status='aprobata_beneficiar',
            valoare_totala_luna=Decimal('10000'),
        )
        db.session.add(sit_apr); db.session.commit()

        yield {
            'proiect_id': p.id, 'contract_id': c.id,
            't_in_id': t_in.id, 't_out_id': t_out.id,
            'tk_in_id': tk_in.id, 'tk_out_id': tk_out.id,
            'cantitate_id': cnt.id, 'situatie_id': sit_apr.id,
        }
    with app.app_context():
        set_flag('controale-contract', False, commit=True)
        from models import (
            db, Proiect, Contract, TermenContract, ProgramReferinta, TaskProgram,
            OfertaContract, PozitieBoQ, CantitateExecutataLunara, SituatieLunara,
            Revendicare, RevendicareCantitate, RevendicareTask, RevendicareTermen,
        )
        RevendicareCantitate.query.delete()
        RevendicareTask.query.delete()
        RevendicareTermen.query.delete()
        Revendicare.query.delete()
        SituatieLunara.query.delete()
        CantitateExecutataLunara.query.delete()
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('CNF-%')).delete()
        OfertaContract.query.delete()
        TermenContract.query.delete()
        TaskProgram.query.delete()
        ProgramReferinta.query.delete()
        Contract.query.delete()
        Proiect.query.filter_by(cod_proiect='CNF-PRJ').delete()
        db.session.commit()


class TestDetectaConflicte:
    def test_intarziere_conflict_cu_termen_in_interval(self, app, setup_conflict):
        """Revendicare intarziere cu 30 zile -> conflict cu termen din interval."""
        from models import db, Revendicare
        from services.conflict_revendicare import detecta_conflicte
        with app.app_context():
            r = Revendicare(
                proiect_id=setup_conflict['proiect_id'],
                contract_id=setup_conflict['contract_id'],
                numar_revendicare='CNF-REV-001',
                data_emitere=date(2026, 4, 15),
                tip='intarziere',
                zile_prelungire_solicitate=30, status='draft',
            )
            db.session.add(r); db.session.commit()
            conflicte = detecta_conflicte(r.id)
            # Trebuie sa contina T-IN (data 5/1 in intervalul [3/16, 5/15])
            # Si NU T-OUT (data 8/1 e in afara)
            ids_termene = [c['id'] for c in conflicte if c['entitate'] == 'TermenContract']
            assert setup_conflict['t_in_id'] in ids_termene
            assert setup_conflict['t_out_id'] not in ids_termene

    def test_intarziere_conflict_cu_task_in_interval(self, app, setup_conflict):
        from models import db, Revendicare
        from services.conflict_revendicare import detecta_conflicte
        with app.app_context():
            r = Revendicare(
                proiect_id=setup_conflict['proiect_id'],
                contract_id=setup_conflict['contract_id'],
                numar_revendicare='CNF-REV-002',
                data_emitere=date(2026, 4, 15),
                tip='intarziere', zile_prelungire_solicitate=30, status='draft',
            )
            db.session.add(r); db.session.commit()
            conflicte = detecta_conflicte(r.id)
            ids_tasks = [c['id'] for c in conflicte if c['entitate'] == 'TaskProgram']
            assert setup_conflict['tk_in_id'] in ids_tasks
            assert setup_conflict['tk_out_id'] not in ids_tasks
            # Severitate: tk_in cu 30% realizare -> 'critical' (slab realizat)
            tk_conflict = next(c for c in conflicte
                               if c['entitate'] == 'TaskProgram'
                               and c['id'] == setup_conflict['tk_in_id'])
            assert tk_conflict['severitate'] == 'critical'

    def test_schimbare_scop_cu_cantitate_validata_critical(
        self, app, setup_conflict
    ):
        """schimbare_scop + link cu cantitate VALIDATA -> conflict critical."""
        from models import db, Revendicare, RevendicareCantitate
        from services.conflict_revendicare import detecta_conflicte
        with app.app_context():
            r = Revendicare(
                proiect_id=setup_conflict['proiect_id'],
                contract_id=setup_conflict['contract_id'],
                numar_revendicare='CNF-REV-003',
                data_emitere=date(2026, 4, 15),
                tip='schimbare_scop', status='draft',
            )
            db.session.add(r); db.session.commit()
            link = RevendicareCantitate(revendicare_id=r.id,
                                        cantitate_lunara_id=setup_conflict['cantitate_id'])
            db.session.add(link); db.session.commit()
            conflicte = detecta_conflicte(r.id)
            cnt_conflicte = [c for c in conflicte if c['entitate'] == 'CantitateLunara']
            assert len(cnt_conflicte) == 1
            assert cnt_conflicte[0]['severitate'] == 'critical'

    def test_schimbare_scop_fara_legaturi_info(self, app, setup_conflict):
        """schimbare_scop fara legaturi M:N -> sugestie 'info' (utilizare M:N)."""
        from models import db, Revendicare
        from services.conflict_revendicare import detecta_conflicte
        with app.app_context():
            r = Revendicare(
                proiect_id=setup_conflict['proiect_id'],
                contract_id=setup_conflict['contract_id'],
                numar_revendicare='CNF-REV-004',
                data_emitere=date(2026, 4, 15),
                tip='schimbare_scop', status='draft',
            )
            db.session.add(r); db.session.commit()
            conflicte = detecta_conflicte(r.id)
            sugestie = [c for c in conflicte
                        if c['entitate'] == 'Revendicare' and c['severitate'] == 'info']
            assert len(sugestie) >= 1

    def test_perturbare_conflict_cu_situatie_aprobata(self, app, setup_conflict):
        """perturbare/costuri_suplimentare cu data_emitere dupa situatie aprobata
        -> conflict warning."""
        from models import db, Revendicare
        from services.conflict_revendicare import detecta_conflicte
        with app.app_context():
            r = Revendicare(
                proiect_id=setup_conflict['proiect_id'],
                contract_id=setup_conflict['contract_id'],
                numar_revendicare='CNF-REV-005',
                data_emitere=date(2026, 4, 15),  # luna 4, dupa situatia aprobata luna 3
                tip='costuri_suplimentare', status='draft',
            )
            db.session.add(r); db.session.commit()
            conflicte = detecta_conflicte(r.id)
            sit_conflicte = [c for c in conflicte if c['entitate'] == 'SituatieLunara']
            assert len(sit_conflicte) == 1
            assert sit_conflicte[0]['severitate'] == 'warning'

    def test_cross_revendicari_pe_acelasi_termen(self, app, setup_conflict):
        """Doua revendicari diferite linkate la acelasi termen -> warning."""
        from models import db, Revendicare, RevendicareTermen
        from services.conflict_revendicare import detecta_conflicte
        with app.app_context():
            r1 = Revendicare(
                proiect_id=setup_conflict['proiect_id'],
                contract_id=setup_conflict['contract_id'],
                numar_revendicare='CNF-REV-CR1', data_emitere=date(2026, 3, 1),
                tip='intarziere', status='draft',
            )
            r2 = Revendicare(
                proiect_id=setup_conflict['proiect_id'],
                contract_id=setup_conflict['contract_id'],
                numar_revendicare='CNF-REV-CR2', data_emitere=date(2026, 3, 15),
                tip='intarziere', status='emisa',
            )
            db.session.add_all([r1, r2]); db.session.commit()
            db.session.add(RevendicareTermen(
                revendicare_id=r1.id, termen_contract_id=setup_conflict['t_in_id'],
                tip_legatura='cauza',
            ))
            db.session.add(RevendicareTermen(
                revendicare_id=r2.id, termen_contract_id=setup_conflict['t_in_id'],
                tip_legatura='consecinta',
            ))
            db.session.commit()
            conflicte = detecta_conflicte(r1.id)
            cross = [c for c in conflicte if c['entitate'] == 'Revendicare']
            assert any(c['id'] == r2.id for c in cross)

    def test_numara_conflicte_dict(self, app, setup_conflict):
        from models import db, Revendicare
        from services.conflict_revendicare import numara_conflicte
        with app.app_context():
            r = Revendicare(
                proiect_id=setup_conflict['proiect_id'],
                contract_id=setup_conflict['contract_id'],
                numar_revendicare='CNF-COUNT-001',
                data_emitere=date(2026, 4, 15),
                tip='intarziere', zile_prelungire_solicitate=30, status='draft',
            )
            db.session.add(r); db.session.commit()
            counts = numara_conflicte(r.id)
            assert 'critical' in counts
            assert 'warning' in counts
            assert 'info' in counts
            assert 'total' in counts
            assert counts['total'] >= 1
