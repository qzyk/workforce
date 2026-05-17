"""
Teste unit pentru modelele Faza 9 - Contract & Project Controls.

Acopera:
  - Defaults (status, moneda, citita, validat etc.)
  - Self-FK (Contract.acte_aditionale, TaskProgram.copii,
    PozitieBoQ.subpozitii, Corespondenta.raspunsuri)
  - Backref-uri pe Proiect / Contract / OfertaContract / ProgramReferinta
  - JSON properties (predecesori, participanti, taskuri_acoperite,
    email_destinatari)
  - Unique constraints (nr_contract, versiune, an+luna, M:N pairs)
  - Legaturi M:N: Revendicare <-> {TermenContract, TaskProgram,
    CantitateExecutataLunara}
  - __repr__ pe toate cele 19 modele (smoke test)
"""
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def proiect_test(app):
    """Proiect minimal pentru testele Faza 9. Cleanup automat."""
    from models import db, Proiect
    with app.app_context():
        Proiect.query.filter(Proiect.cod_proiect.like('F9-PRJ-%')).delete()
        db.session.commit()
        p = Proiect(
            cod_proiect='F9-PRJ-001',
            nume='Proiect Faza9 Test',
            data_start=date(2025, 1, 1),
            data_sfarsit_planificat=date(2026, 12, 31),
            beneficiar='Beneficiar F9 SRL',
            status='activ',
        )
        db.session.add(p)
        db.session.commit()
        yield p.id
        # Cleanup cascade-light: stergem entitatile Faza 9 + proiect
        from models import (
            Contract, TermenContract, TermenUrmarit, ProgramReferinta,
            TaskProgram, OfertaContract, PozitieBoQ, CantitateExecutataLunara,
            SituatieLunara, RaportLucrariProiect, Corespondenta, Revendicare,
            RevendicareTermen, RevendicareTask, RevendicareCantitate,
            ProcesVerbal, Anexa, ReguliNotificareProiect,
        )
        for cls in (RevendicareCantitate, RevendicareTask, RevendicareTermen,
                    Revendicare, Corespondenta, CantitateExecutataLunara,
                    PozitieBoQ, OfertaContract, TaskProgram, ProgramReferinta,
                    SituatieLunara, RaportLucrariProiect, ProcesVerbal,
                    ReguliNotificareProiect, TermenUrmarit, TermenContract,
                    Contract, Anexa):
            try:
                cls.query.filter_by(proiect_id=p.id).delete()
            except Exception:
                pass
        Proiect.query.filter_by(id=p.id).delete()
        db.session.commit()


# ============================================================
# A. CONTRACT + TERMENE
# ============================================================

class TestContract:
    def test_creation_defaults(self, app, proiect_test):
        from models import db, Contract
        with app.app_context():
            c = Contract(
                proiect_id=proiect_test,
                nr_contract='F9-CTR-001',
                data_semnare=date(2025, 1, 15),
            )
            db.session.add(c)
            db.session.commit()
            assert c.status == 'activ'
            assert c.moneda == 'RON'
            assert c.data_creare is not None
            assert isinstance(c.data_creare, datetime)

    def test_self_fk_acte_aditionale(self, app, proiect_test):
        from models import db, Contract
        with app.app_context():
            principal = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-P',
                                 data_semnare=date(2025, 1, 15))
            db.session.add(principal)
            db.session.commit()
            act1 = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-A1',
                            data_semnare=date(2025, 6, 1),
                            parinte_contract_id=principal.id)
            db.session.add(act1)
            db.session.commit()
            assert act1.parinte_contract.id == principal.id
            assert act1 in principal.acte_aditionale.all()

    def test_unique_nr_contract_per_tenant(self, app, proiect_test):
        """UniqueConstraint(tenant_id, nr_contract) - SQLite trateaza NULL ca
        distinct in unique, deci testam cu un tenant_id explicit."""
        from models import db, Contract, Tenant
        with app.app_context():
            t = Tenant.query.filter_by(cod='F9-TST-TENANT').first()
            if not t:
                t = Tenant(cod='F9-TST-TENANT', nume='F9 Test Tenant', activ=True)
                db.session.add(t); db.session.commit()
            try:
                c1 = Contract(tenant_id=t.id, proiect_id=proiect_test,
                              nr_contract='F9-CTR-DUP',
                              data_semnare=date(2025, 1, 1))
                db.session.add(c1)
                db.session.commit()
                c2 = Contract(tenant_id=t.id, proiect_id=proiect_test,
                              nr_contract='F9-CTR-DUP',
                              data_semnare=date(2025, 2, 1))
                db.session.add(c2)
                with pytest.raises(IntegrityError):
                    db.session.commit()
                db.session.rollback()
            finally:
                Contract.query.filter_by(tenant_id=t.id).delete()
                Tenant.query.filter_by(id=t.id).delete()
                db.session.commit()

    def test_proiect_backref_contracte(self, app, proiect_test):
        from models import db, Proiect, Contract
        with app.app_context():
            c = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-BR',
                         data_semnare=date(2025, 1, 1))
            db.session.add(c)
            db.session.commit()
            p = Proiect.query.get(proiect_test)
            assert c in p.contracte.all()


class TestTermenContract:
    def test_creation_and_backrefs(self, app, proiect_test):
        from models import db, Contract, TermenContract
        with app.app_context():
            c = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-T1',
                         data_semnare=date(2025, 1, 1))
            db.session.add(c)
            db.session.commit()
            t = TermenContract(
                contract_id=c.id, proiect_id=proiect_test,
                denumire='Predare amplasament',
                tip='predare_amplasament',
                data_scadenta=date(2025, 2, 15),
            )
            db.session.add(t)
            db.session.commit()
            assert t.status == 'planificat'  # default
            assert t.zile_alerta_inainte == 7  # default
            assert t in c.termeni.all()


class TestTermenUrmarit:
    def test_polymorphic_source(self, app, proiect_test):
        from models import db, TermenUrmarit
        with app.app_context():
            tu = TermenUrmarit(
                proiect_id=proiect_test,
                entitate_sursa='corespondenta',
                id_entitate_sursa=12345,
                tip_regula='raspuns_30_zile',
                data_start=date(2025, 5, 1),
                data_scadenta=date(2025, 5, 31),
            )
            db.session.add(tu)
            db.session.commit()
            assert tu.status == 'activ'
            assert tu.zile_grace == 30
            assert tu.zile_anticipare == 7


# ============================================================
# B. PROGRAM REFERINTA + TASKURI
# ============================================================

class TestProgramReferinta:
    def test_versionare_unique(self, app, proiect_test):
        from models import db, ProgramReferinta
        with app.app_context():
            p1 = ProgramReferinta(proiect_id=proiect_test, versiune=1,
                                  denumire='Programul initial',
                                  data_emitere=date(2025, 1, 20))
            db.session.add(p1)
            db.session.commit()
            p2 = ProgramReferinta(proiect_id=proiect_test, versiune=1,
                                  denumire='Programul duplicat',
                                  data_emitere=date(2025, 2, 1))
            db.session.add(p2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


class TestTaskProgram:
    def test_hierarchy_and_predecesori_json(self, app, proiect_test):
        from models import db, ProgramReferinta, TaskProgram
        with app.app_context():
            prog = ProgramReferinta(proiect_id=proiect_test, versiune=1,
                                    denumire='P1', data_emitere=date(2025, 1, 1))
            db.session.add(prog); db.session.commit()

            summary = TaskProgram(
                program_id=prog.id, proiect_id=proiect_test,
                cod_extern='UID-100', denumire='Faza proiectare',
                nivel_ierarhie=1, tip_task='summary',
                data_start_planificat=date(2025, 2, 1),
                data_sfarsit_planificat=date(2025, 3, 31),
            )
            db.session.add(summary); db.session.commit()

            child = TaskProgram(
                program_id=prog.id, proiect_id=proiect_test,
                cod_extern='UID-101', denumire='Releveu',
                nivel_ierarhie=2, tip_task='task',
                parinte_task_id=summary.id,
                data_start_planificat=date(2025, 2, 1),
                data_sfarsit_planificat=date(2025, 2, 15),
            )
            child.predecesori = [
                {'uid_extern': 'UID-099', 'tip': 'FS', 'lag_zile': 0},
            ]
            db.session.add(child); db.session.commit()

            # Verific JSON property
            assert child.predecesori[0]['tip'] == 'FS'
            assert child.predecesori[0]['lag_zile'] == 0
            # Self-FK
            assert child.parinte.id == summary.id
            assert child in summary.copii.all()


# ============================================================
# C. TEHNICO-ECONOMIC
# ============================================================

class TestOfertaContract:
    def test_versionare_unique_per_contract(self, app, proiect_test):
        from models import db, Contract, OfertaContract
        with app.app_context():
            c = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-O',
                         data_semnare=date(2025, 1, 1))
            db.session.add(c); db.session.commit()
            o1 = OfertaContract(contract_id=c.id, proiect_id=proiect_test,
                                versiune=1, data_emitere=date(2025, 1, 5))
            db.session.add(o1); db.session.commit()
            o2 = OfertaContract(contract_id=c.id, proiect_id=proiect_test,
                                versiune=1, data_emitere=date(2025, 2, 1))
            db.session.add(o2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


class TestPozitieBoQ:
    def test_subpozitii_hierarchy(self, app, proiect_test):
        from models import db, Contract, OfertaContract, PozitieBoQ
        with app.app_context():
            c = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-BQ',
                         data_semnare=date(2025, 1, 1))
            db.session.add(c); db.session.commit()
            o = OfertaContract(contract_id=c.id, proiect_id=proiect_test,
                               versiune=1, data_emitere=date(2025, 1, 5))
            db.session.add(o); db.session.commit()

            cap = PozitieBoQ(oferta_id=o.id, proiect_id=proiect_test,
                             cod_articol='CAP-01', denumire='Terasamente',
                             um='mc', categorie='mixt', ordine=1)
            db.session.add(cap); db.session.commit()

            art = PozitieBoQ(oferta_id=o.id, proiect_id=proiect_test,
                             cod_articol='CA01A1',
                             denumire='Sapatura manuala',
                             um='mc', cantitate_oferta=Decimal('150.0000'),
                             pret_unitar=Decimal('45.5000'),
                             categorie='manopera', ordine=2,
                             parinte_pozitie_id=cap.id)
            db.session.add(art); db.session.commit()

            assert art.parinte_pozitie.id == cap.id
            assert art in cap.subpozitii.all()


class TestCantitateExecutataLunara:
    def test_unique_pozitie_anluna(self, app, proiect_test):
        from models import db, Contract, OfertaContract, PozitieBoQ, CantitateExecutataLunara
        with app.app_context():
            c = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-C',
                         data_semnare=date(2025, 1, 1))
            db.session.add(c); db.session.commit()
            o = OfertaContract(contract_id=c.id, proiect_id=proiect_test,
                               versiune=1, data_emitere=date(2025, 1, 5))
            db.session.add(o); db.session.commit()
            pz = PozitieBoQ(oferta_id=o.id, proiect_id=proiect_test,
                            cod_articol='CA02', denumire='Beton', um='mc',
                            cantitate_oferta=Decimal('100'), pret_unitar=Decimal('500'))
            db.session.add(pz); db.session.commit()

            ce1 = CantitateExecutataLunara(
                pozitie_boq_id=pz.id, proiect_id=proiect_test,
                an=2025, luna=3, cantitate_executata=Decimal('20.0000'))
            db.session.add(ce1); db.session.commit()
            ce2 = CantitateExecutataLunara(
                pozitie_boq_id=pz.id, proiect_id=proiect_test,
                an=2025, luna=3, cantitate_executata=Decimal('5.0000'))
            db.session.add(ce2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


class TestSituatieLunara:
    def test_unique_proiect_anluna(self, app, proiect_test):
        from models import db, Contract, SituatieLunara
        with app.app_context():
            c = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-S',
                         data_semnare=date(2025, 1, 1))
            db.session.add(c); db.session.commit()

            s1 = SituatieLunara(proiect_id=proiect_test, contract_id=c.id,
                                an=2025, luna=4)
            db.session.add(s1); db.session.commit()
            assert s1.status == 'draft'
            assert s1.data_emitere == date.today()  # default

            s2 = SituatieLunara(proiect_id=proiect_test, contract_id=c.id,
                                an=2025, luna=4)
            db.session.add(s2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


class TestRaportLucrariProiect:
    def test_taskuri_acoperite_json(self, app, proiect_test):
        from models import db, RaportLucrariProiect
        with app.app_context():
            r = RaportLucrariProiect(proiect_id=proiect_test, an=2025, luna=5)
            r.taskuri_acoperite = ['UID-100', 'UID-101', 'UID-102']
            db.session.add(r); db.session.commit()
            assert r.taskuri_acoperite == ['UID-100', 'UID-101', 'UID-102']
            assert '"UID-100"' in r.task_program_acoperite_json


# ============================================================
# D. CORESPONDENTA + REVENDICARI
# ============================================================

class TestCorespondenta:
    def test_self_fk_raspunsuri(self, app, proiect_test):
        from models import db, Corespondenta
        with app.app_context():
            orig = Corespondenta(
                proiect_id=proiect_test, numar_inregistrare='F9-COR-001',
                data_inregistrare=date(2025, 5, 1),
                tip='notificare', subtip='notificare_cerinte_beneficiar',
                directie='primita', genereaza_termen=True,
            )
            db.session.add(orig); db.session.commit()
            replica = Corespondenta(
                proiect_id=proiect_test, numar_inregistrare='F9-COR-002',
                data_inregistrare=date(2025, 5, 10),
                tip='raspuns', directie='emisa',
                raspuns_la_id=orig.id,
            )
            db.session.add(replica); db.session.commit()
            assert replica.raspuns_la.id == orig.id
            assert replica in orig.raspunsuri.all()


class TestRevendicareM2M:
    def test_legatura_termen(self, app, proiect_test):
        from models import (db, Contract, TermenContract, Revendicare,
                            RevendicareTermen)
        with app.app_context():
            c = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-R1',
                         data_semnare=date(2025, 1, 1))
            db.session.add(c); db.session.commit()
            t = TermenContract(contract_id=c.id, proiect_id=proiect_test,
                               denumire='Receptie partiala',
                               tip='receptie_partiala',
                               data_scadenta=date(2025, 6, 1))
            db.session.add(t); db.session.commit()
            rv = Revendicare(proiect_id=proiect_test, contract_id=c.id,
                             numar_revendicare='F9-REV-001',
                             data_emitere=date(2025, 5, 15),
                             tip='intarziere', zile_prelungire_solicitate=15)
            db.session.add(rv); db.session.commit()
            assert rv.status == 'draft'

            link = RevendicareTermen(revendicare_id=rv.id,
                                     termen_contract_id=t.id,
                                     tip_legatura='cauza')
            db.session.add(link); db.session.commit()
            assert link in rv.legaturi_termeni.all()
            assert link in t.legaturi_revendicari.all()

    def test_legatura_task_unique(self, app, proiect_test):
        from models import (db, Contract, Revendicare, ProgramReferinta,
                            TaskProgram, RevendicareTask)
        with app.app_context():
            c = Contract(proiect_id=proiect_test, nr_contract='F9-CTR-R2',
                         data_semnare=date(2025, 1, 1))
            db.session.add(c); db.session.commit()
            prog = ProgramReferinta(proiect_id=proiect_test, versiune=1,
                                    denumire='P-R2', data_emitere=date(2025, 1, 1))
            db.session.add(prog); db.session.commit()
            tk = TaskProgram(program_id=prog.id, proiect_id=proiect_test,
                             denumire='Faza X',
                             data_start_planificat=date(2025, 3, 1),
                             data_sfarsit_planificat=date(2025, 4, 1))
            db.session.add(tk); db.session.commit()
            rv = Revendicare(proiect_id=proiect_test, contract_id=c.id,
                             numar_revendicare='F9-REV-002',
                             data_emitere=date(2025, 4, 5), tip='perturbare')
            db.session.add(rv); db.session.commit()

            rt1 = RevendicareTask(revendicare_id=rv.id, task_program_id=tk.id)
            db.session.add(rt1); db.session.commit()
            rt2 = RevendicareTask(revendicare_id=rv.id, task_program_id=tk.id)
            db.session.add(rt2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


# ============================================================
# E. PV + ANEXE + NOTIFICARI
# ============================================================

class TestProcesVerbal:
    def test_participanti_json(self, app, proiect_test):
        from models import db, ProcesVerbal
        with app.app_context():
            pv = ProcesVerbal(proiect_id=proiect_test,
                              tip='predare_amplasament',
                              data_emitere=date(2025, 2, 1))
            pv.participanti = [
                {'nume': 'Ion Popescu', 'functie': 'Diriginte santier',
                 'organizatie': 'Beneficiar SRL'},
                {'nume': 'Maria Ionescu', 'functie': 'Sef proiect',
                 'organizatie': 'Antreprenor SA'},
            ]
            db.session.add(pv); db.session.commit()
            assert len(pv.participanti) == 2
            assert pv.participanti[0]['nume'] == 'Ion Popescu'
            assert pv.semnat is False  # default


class TestAnexa:
    def test_polymorphic_target_no_fk(self, app):
        """Anexa nu are FK strict pe entitate_tinta — doar index."""
        from models import db, Anexa
        with app.app_context():
            a = Anexa(entitate_tinta='revendicare', id_entitate_tinta=99999,
                      tip_fisier='foto', fisier_path='/uploads/test.jpg',
                      nume_original='foto1.jpg', dimensiune_bytes=12345)
            db.session.add(a); db.session.commit()
            assert a.id is not None
            db.session.delete(a)
            db.session.commit()


class TestNotificareApp:
    def test_defaults(self, app, admin_user):
        from models import db, NotificareApp, Utilizator
        with app.app_context():
            # Re-query admin user pentru a-l atasa la session-ul curent
            u = Utilizator.query.filter_by(email='admin_test@test.local').first()
            n = NotificareApp(utilizator_id=u.id,
                              tip='termen_apropiat',
                              titlu='Termen aproape')
            db.session.add(n); db.session.commit()
            assert n.citita is False
            assert n.data_creare is not None
            db.session.delete(n); db.session.commit()


class TestReguliNotificareProiect:
    def test_email_destinatari_json_and_unique(self, app, proiect_test):
        from models import db, ReguliNotificareProiect
        with app.app_context():
            r = ReguliNotificareProiect(proiect_id=proiect_test,
                                        tip_eveniment='termen_apropiat')
            r.email_destinatari = ['manager@edifico.test', 'sef@edifico.test']
            db.session.add(r); db.session.commit()
            assert r.email_destinatari == ['manager@edifico.test', 'sef@edifico.test']
            assert r.in_app_activ is True  # default
            assert r.email_activ is False  # default

            r2 = ReguliNotificareProiect(proiect_id=proiect_test,
                                         tip_eveniment='termen_apropiat')
            db.session.add(r2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


# ============================================================
# SMOKE: __repr__ pe toate cele 19 modele
# ============================================================

def test_repr_all_19_models_no_crash(app, proiect_test, admin_user):
    """Smoke test: instantiez fiecare model (minimal) si apelez __repr__."""
    from datetime import date
    from models import (
        db, Contract, TermenContract, TermenUrmarit, ProgramReferinta,
        TaskProgram, OfertaContract, PozitieBoQ, CantitateExecutataLunara,
        SituatieLunara, RaportLucrariProiect, Corespondenta, Revendicare,
        RevendicareTermen, RevendicareTask, RevendicareCantitate,
        ProcesVerbal, Anexa, NotificareApp, ReguliNotificareProiect,
        Utilizator,
    )
    with app.app_context():
        admin_id = Utilizator.query.filter_by(email='admin_test@test.local').first().id
        # Lant minim de obiecte
        c = Contract(proiect_id=proiect_test, nr_contract='F9-REPR-001',
                     data_semnare=date(2025, 1, 1))
        db.session.add(c); db.session.commit()
        prog = ProgramReferinta(proiect_id=proiect_test, versiune=1,
                                denumire='Pr-repr', data_emitere=date(2025, 1, 1))
        db.session.add(prog); db.session.commit()
        tk = TaskProgram(program_id=prog.id, proiect_id=proiect_test,
                         denumire='T1',
                         data_start_planificat=date(2025, 2, 1),
                         data_sfarsit_planificat=date(2025, 3, 1))
        db.session.add(tk); db.session.commit()
        of = OfertaContract(contract_id=c.id, proiect_id=proiect_test,
                            versiune=1, data_emitere=date(2025, 1, 5))
        db.session.add(of); db.session.commit()
        pz = PozitieBoQ(oferta_id=of.id, proiect_id=proiect_test,
                        cod_articol='AR1', denumire='Articol', um='mc')
        db.session.add(pz); db.session.commit()
        ce = CantitateExecutataLunara(pozitie_boq_id=pz.id,
                                      proiect_id=proiect_test, an=2025, luna=2)
        db.session.add(ce); db.session.commit()
        tc = TermenContract(contract_id=c.id, proiect_id=proiect_test,
                            denumire='T', tip='executie',
                            data_scadenta=date(2025, 5, 1))
        db.session.add(tc); db.session.commit()
        co = Corespondenta(proiect_id=proiect_test,
                           numar_inregistrare='F9-REPR-CO',
                           data_inregistrare=date(2025, 1, 10),
                           tip='scrisoare')
        db.session.add(co); db.session.commit()
        rv = Revendicare(proiect_id=proiect_test, contract_id=c.id,
                         numar_revendicare='F9-REPR-RV',
                         data_emitere=date(2025, 3, 1), tip='intarziere')
        db.session.add(rv); db.session.commit()

        objs = [
            c, tc,
            TermenUrmarit(proiect_id=proiect_test, entitate_sursa='contract',
                          id_entitate_sursa=c.id, tip_regula='custom',
                          data_start=date(2025, 1, 1),
                          data_scadenta=date(2025, 2, 1)),
            prog, tk, of, pz, ce,
            SituatieLunara(proiect_id=proiect_test, contract_id=c.id,
                           an=2025, luna=8),
            RaportLucrariProiect(proiect_id=proiect_test, an=2025, luna=8),
            co, rv,
            RevendicareTermen(revendicare_id=rv.id, termen_contract_id=tc.id),
            RevendicareTask(revendicare_id=rv.id, task_program_id=tk.id),
            RevendicareCantitate(revendicare_id=rv.id, cantitate_lunara_id=ce.id),
            ProcesVerbal(proiect_id=proiect_test, tip='altul',
                         data_emitere=date(2025, 1, 1)),
            Anexa(entitate_tinta='corespondenta', id_entitate_tinta=co.id,
                  tip_fisier='pdf', fisier_path='/x.pdf'),
            NotificareApp(utilizator_id=admin_id, tip='generic',
                          titlu='Test'),
            ReguliNotificareProiect(proiect_id=proiect_test,
                                    tip_eveniment='generic'),
        ]
        for o in objs:
            s = repr(o)
            assert isinstance(s, str) and len(s) > 0
