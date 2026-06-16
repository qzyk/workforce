"""
Teste pentru sync 4D plan<->actuals (ARIA 3, Faza 5b).

Propaga RaportActivitate.procent_realizare -> BIMTaskSchedule.progres_pct prin
element_bim_id comun. Gate pe flag 'bim-4d-schedule'. Idempotent.
"""

from datetime import date
import pytest

from models import (db, BIMTaskSchedule, ElementBIM, Cladire, Santier,
                    Angajat, Proiect, RaportActivitate, Utilizator)
from services import bim_4d
from services import feature_flags as ff


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='4dsync_admin@test.local').first()
        if not u:
            u = Utilizator(nume='4DSync', prenume='X',
                           email='4dsync_admin@test.local', rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


@pytest.fixture
def context(app):
    """
    Santier + element + schedule + angajat + proiect (pt RaportActivitate).

    Izolare per-test: rapoartele si schedule-ul vechi se sterg la fiecare apel,
    iar proiectul/angajatul cu cod unic se reutilizeaza (DB persista intre teste)."""
    with app.app_context():
        s = Santier.query.filter_by(cod='S-4DSYNC').first()
        if not s:
            s = Santier(cod='S-4DSYNC', nume='Santier sync')
            db.session.add(s); db.session.flush()
        c = Cladire.query.filter_by(santier_id=s.id, cod='C1').first()
        if not c:
            c = Cladire(santier_id=s.id, cod='C1', nume='Cladire')
            db.session.add(c); db.session.flush()
        el = ElementBIM.query.filter_by(cladire_id=c.id, cod='W001').first()
        if not el:
            el = ElementBIM(cladire_id=c.id, cod='W001', tip_element='wall',
                            status='proiectat', nume='Perete')
            db.session.add(el); db.session.flush()
        # Curatam datele care variaza intre teste
        RaportActivitate.query.filter_by(element_bim_id=el.id).delete()
        BIMTaskSchedule.query.filter_by(element_bim_id=el.id).delete()
        db.session.flush()
        sched = BIMTaskSchedule(element_bim_id=el.id, faza='structura',
                                data_start_plan=date(2026, 6, 1),
                                data_sfarsit_plan=date(2026, 6, 30),
                                status='planificat', progres_pct=0)
        db.session.add(sched)
        ang = Angajat.query.filter_by(nume='Ion4DSync', prenume='Pop').first()
        if not ang:
            ang = Angajat(nume='Ion4DSync', prenume='Pop', functie='Muncitor',
                          data_angajare=date(2025, 1, 1))
            db.session.add(ang)
        p = Proiect.query.filter_by(cod_proiect='P-4DSYNC').first()
        if not p:
            p = Proiect(cod_proiect='P-4DSYNC', nume='Proiect sync',
                        data_start=date(2026, 1, 1))
            db.session.add(p)
        db.session.commit()
        yield {'santier_id': s.id, 'element_id': el.id, 'sched_id': sched.id,
               'angajat_id': ang.id, 'proiect_id': p.id}


def _raport(context, procent, *, status_executie='in_desfasurare'):
    r = RaportActivitate(
        angajat_id=context['angajat_id'], proiect_id=context['proiect_id'],
        element_bim_id=context['element_id'], data=date(2026, 6, 10),
        activitate_principala='Montaj perete',
        procent_realizare=procent, status_executie=status_executie)
    db.session.add(r); db.session.commit()
    return r


# ====================================================
# FLAG OFF -> nimic (zero regresie)
# ====================================================

def test_sync_flag_off_nu_face_nimic(app, context, admin):
    with app.app_context():
        ff.set_flag('bim-4d-schedule', False)
        _raport(context, 60)
        rez = bim_4d.sync_actuals_din_rapoarte(user=admin)
        assert rez['actualizate'] == 0
        sched = BIMTaskSchedule.query.get(context['sched_id'])
        assert sched.progres_pct == 0  # neschimbat


# ====================================================
# FLAG ON -> propaga procentul
# ====================================================

def test_sync_propaga_procent_60(app, context, admin):
    """Specul: o activitate cu procent_realizare 60 -> schedule-ul ajunge la 60."""
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
        try:
            _raport(context, 60)
            rez = bim_4d.sync_actuals_din_rapoarte(user=admin)
            assert rez['actualizate'] == 1
            assert rez['elemente'] == 1
            sched = BIMTaskSchedule.query.get(context['sched_id'])
            assert sched.progres_pct == 60
            assert sched.status == 'in_curs'  # auto-derivat de update_progress
        finally:
            ff.set_flag('bim-4d-schedule', False)


def test_sync_ia_maximul_pe_element(app, context, admin):
    """Mai multe rapoarte pe acelasi element -> se ia procentul maxim."""
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
        try:
            _raport(context, 30)
            _raport(context, 75)
            _raport(context, 50)
            bim_4d.sync_actuals_din_rapoarte(user=admin)
            sched = BIMTaskSchedule.query.get(context['sched_id'])
            assert sched.progres_pct == 75
        finally:
            ff.set_flag('bim-4d-schedule', False)


def test_sync_100_finalizeaza(app, context, admin):
    """procent_realizare 100 -> status 'finalizat' + data_sfarsit_real setata."""
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
        try:
            _raport(context, 100, status_executie='finalizata')
            bim_4d.sync_actuals_din_rapoarte(user=admin)
            sched = BIMTaskSchedule.query.get(context['sched_id'])
            assert sched.progres_pct == 100
            assert sched.status == 'finalizat'
            assert sched.data_sfarsit_real is not None
        finally:
            ff.set_flag('bim-4d-schedule', False)


def test_sync_idempotent(app, context, admin):
    """A doua rulare cu aceleasi date nu mai modifica nimic."""
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
        try:
            _raport(context, 40)
            r1 = bim_4d.sync_actuals_din_rapoarte(user=admin)
            assert r1['actualizate'] == 1
            r2 = bim_4d.sync_actuals_din_rapoarte(user=admin)
            assert r2['actualizate'] == 0
            assert r2['fara_schimbare'] == 1
        finally:
            ff.set_flag('bim-4d-schedule', False)


def test_sync_ignora_rapoarte_fara_procent(app, context, admin):
    """Rapoarte cu procent_realizare NULL nu suprascriu progresul cu 0."""
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
        try:
            # progres existent setat manual
            sched = BIMTaskSchedule.query.get(context['sched_id'])
            bim_4d.update_progress(sched, 35)
            # raport fara procent (None)
            r = RaportActivitate(
                angajat_id=context['angajat_id'], proiect_id=context['proiect_id'],
                element_bim_id=context['element_id'], data=date(2026, 6, 11),
                activitate_principala='Fara procent', procent_realizare=None)
            db.session.add(r); db.session.commit()
            rez = bim_4d.sync_actuals_din_rapoarte(user=admin)
            assert rez['actualizate'] == 0
            sched = BIMTaskSchedule.query.get(context['sched_id'])
            assert sched.progres_pct == 35  # pastrat
        finally:
            ff.set_flag('bim-4d-schedule', False)


def test_sync_filtrat_pe_santier(app, context, admin):
    """Restrangerea pe santier_id ignora elementele altui santier."""
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
        try:
            _raport(context, 55)
            # alt santier, fara legatura -> nu trebuie atins
            s2 = Santier.query.filter_by(cod='S-ALT-4DSYNC').first()
            if not s2:
                s2 = Santier(cod='S-ALT-4DSYNC', nume='Alt santier')
                db.session.add(s2); db.session.commit()
            rez = bim_4d.sync_actuals_din_rapoarte(santier_id=s2.id, user=admin)
            assert rez['actualizate'] == 0
            sched = BIMTaskSchedule.query.get(context['sched_id'])
            assert sched.progres_pct == 0
            # pe santierul corect -> propaga
            rez2 = bim_4d.sync_actuals_din_rapoarte(
                santier_id=context['santier_id'], user=admin)
            assert rez2['actualizate'] == 1
            sched = BIMTaskSchedule.query.get(context['sched_id'])
            assert sched.progres_pct == 55
        finally:
            ff.set_flag('bim-4d-schedule', False)


def test_sync_pentru_element_singular(app, context, admin):
    """Helper sync_actuals_pentru_element propaga corect pe un singur element."""
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
        try:
            _raport(context, 80)
            rez = bim_4d.sync_actuals_pentru_element(context['element_id'], user=admin)
            assert rez['progres'] == 80
            assert rez['actualizate'] == 1
            sched = BIMTaskSchedule.query.get(context['sched_id'])
            assert sched.progres_pct == 80
        finally:
            ff.set_flag('bim-4d-schedule', False)
