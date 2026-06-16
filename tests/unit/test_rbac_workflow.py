"""
Teste pentru integrarea RBAC fin in CDE workflow (ARIA 1, Faza 5b).

Verifica enforcement-ul permisiunilor pe disciplina in can_user_transition,
gated pe flag-ul 'bim-rbac-fine':
- flag OFF  -> comportament istoric (rol elevat admin/manager). ZERO regresie.
- flag ON   -> permisiune RBAC fina pe disciplina versiunii; un rol global elevat
               raman privilegiat (fallback), dar un user oarecare e refuzat daca
               nu are permisiunea fina; admin tenant bypaseaza mereu.
"""

import pytest

from models import db, BIMModelVersion, ModelBIM, Santier, Utilizator
from services import bim_workflow, rbac
from services import feature_flags as ff


@pytest.fixture
def santier(app):
    with app.app_context():
        s = Santier.query.filter_by(cod='S-RBACWF').first()
        if not s:
            s = Santier(cod='S-RBACWF', nume='Santier RBAC WF')
            db.session.add(s); db.session.commit()
        yield s.id


@pytest.fixture
def model_arh(app, santier):
    """Model BIM pe disciplina ARH, legat de un santier (pentru scope RBAC)."""
    with app.app_context():
        m = ModelBIM(nume='Model ARH', tip='ifc', versiune='draft',
                     santier_id=santier)
        db.session.add(m); db.session.commit()
        yield m.id


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='rbacwf_admin@test.local').first()
        if not u:
            u = Utilizator(nume='RBACWF', prenume='Admin',
                           email='rbacwf_admin@test.local', rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u.id


@pytest.fixture
def manager(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='rbacwf_mgr@test.local').first()
        if not u:
            u = Utilizator(nume='RBACWF', prenume='Mgr',
                           email='rbacwf_mgr@test.local', rol='manager', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u.id


@pytest.fixture
def operator(app):
    """User cu rol global NEelevat (operator) - depinde 100% de RBAC fin."""
    with app.app_context():
        u = Utilizator.query.filter_by(email='rbacwf_op@test.local').first()
        if not u:
            u = Utilizator(nume='RBACWF', prenume='Op',
                           email='rbacwf_op@test.local', rol='operator', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u.id


def _versiune_shared(model_id, autor, disciplina='ARH'):
    """Creeaza o versiune si o duce in 'shared' (autorul poate face share)."""
    m = ModelBIM.query.get(model_id)
    v = bim_workflow.create_new_version(m, f'v-{autor.id}-{disciplina}', autor,
                                        disciplina=disciplina)
    bim_workflow.transition(v, 'shared', autor)
    return v


# ====================================================
# FLAG OFF -> comportament istoric (ZERO regresie)
# ====================================================

def test_flag_off_operator_cu_permisiune_disciplina_tot_refuzat(app, model_arh, admin, operator):
    """
    Regresie: cu flag OFF, chiar daca operatorul are rol RBAC lead_designer pe ARH,
    NU poate publica (se aplica doar regula veche admin/manager).
    """
    with app.app_context():
        ff.set_flag('bim-rbac-fine', False)
        try:
            adm = Utilizator.query.get(admin)
            op = Utilizator.query.get(operator)
            rbac.assign_role(op.id, 'lead_designer', scope_type='disciplina',
                             scope_disciplina='ARH', created_by=adm)
            v = _versiune_shared(model_arh, adm, 'ARH')
            allowed, motiv = bim_workflow.can_user_transition(op, v, 'published')
            assert allowed is False
            assert 'manageri' in motiv.lower() or 'administr' in motiv.lower()
        finally:
            ff.set_flag('bim-rbac-fine', False)


def test_flag_off_manager_poate_publica(app, model_arh, admin, manager):
    """Regresie: cu flag OFF, managerul global publica (ca azi)."""
    with app.app_context():
        ff.set_flag('bim-rbac-fine', False)
        adm = Utilizator.query.get(admin)
        mgr = Utilizator.query.get(manager)
        v = _versiune_shared(model_arh, adm, 'ARH')
        allowed, _ = bim_workflow.can_user_transition(mgr, v, 'published')
        assert allowed is True


# ====================================================
# FLAG ON -> enforcement fin pe disciplina
# ====================================================

def test_flag_on_operator_fara_permisiune_refuzat(app, model_arh, admin, operator):
    """Cu flag ON, operatorul fara niciun rol RBAC NU poate publica."""
    with app.app_context():
        ff.set_flag('bim-rbac-fine', True)
        try:
            adm = Utilizator.query.get(admin)
            op = Utilizator.query.get(operator)
            v = _versiune_shared(model_arh, adm, 'ARH')
            allowed, motiv = bim_workflow.can_user_transition(op, v, 'published')
            assert allowed is False
            assert 'rbac' in motiv.lower() or 'permisiune' in motiv.lower()
        finally:
            ff.set_flag('bim-rbac-fine', False)


def test_flag_on_permisiune_pe_disciplina_corecta_permite(app, model_arh, admin, operator):
    """Cu flag ON + rol lead_designer pe ARH -> poate publica versiunea ARH."""
    with app.app_context():
        ff.set_flag('bim-rbac-fine', True)
        try:
            adm = Utilizator.query.get(admin)
            op = Utilizator.query.get(operator)
            rbac.assign_role(op.id, 'lead_designer', scope_type='disciplina',
                             scope_disciplina='ARH', created_by=adm)
            v = _versiune_shared(model_arh, adm, 'ARH')
            allowed, motiv = bim_workflow.can_user_transition(op, v, 'published')
            assert allowed is True, motiv
        finally:
            ff.set_flag('bim-rbac-fine', False)


def test_flag_on_permisiune_pe_alta_disciplina_refuzat(app, model_arh, admin, operator):
    """
    Cu flag ON, rolul pe STR NU autorizeaza publish pe o versiune ARH.
    Acesta e bug-ul pe care fazele anterioare nu il prindeau (testele slabe)."""
    with app.app_context():
        ff.set_flag('bim-rbac-fine', True)
        try:
            adm = Utilizator.query.get(admin)
            op = Utilizator.query.get(operator)
            rbac.assign_role(op.id, 'lead_designer', scope_type='disciplina',
                             scope_disciplina='STR', created_by=adm)
            v = _versiune_shared(model_arh, adm, 'ARH')
            allowed, _ = bim_workflow.can_user_transition(op, v, 'published')
            assert allowed is False
        finally:
            ff.set_flag('bim-rbac-fine', False)


def test_flag_on_admin_bypaseaza(app, model_arh, admin):
    """Admin tenant bypaseaza RBAC fin (has_permission ramane True)."""
    with app.app_context():
        ff.set_flag('bim-rbac-fine', True)
        try:
            adm = Utilizator.query.get(admin)
            v = _versiune_shared(model_arh, adm, 'ARH')
            allowed, _ = bim_workflow.can_user_transition(adm, v, 'published')
            assert allowed is True
        finally:
            ff.set_flag('bim-rbac-fine', False)


def test_flag_on_manager_fallback_pe_rol_global(app, model_arh, admin, manager):
    """
    Cu flag ON, managerul global (fara rol RBAC fin) ramane privilegiat ca fallback,
    ca sa nu blocam complet operarea cand RBAC fin nu e populat inca."""
    with app.app_context():
        ff.set_flag('bim-rbac-fine', True)
        try:
            adm = Utilizator.query.get(admin)
            mgr = Utilizator.query.get(manager)
            v = _versiune_shared(model_arh, adm, 'ARH')
            allowed, _ = bim_workflow.can_user_transition(mgr, v, 'published')
            assert allowed is True
        finally:
            ff.set_flag('bim-rbac-fine', False)


def test_flag_on_share_permis_cu_permisiune_share(app, model_arh, admin, operator):
    """
    wip->shared nu e privilegiat (oricine autenticat il face), deci ramane permis;
    dar shared->wic rollback pentru un user non-creator cere 'version:share' fin."""
    with app.app_context():
        ff.set_flag('bim-rbac-fine', True)
        try:
            adm = Utilizator.query.get(admin)
            op = Utilizator.query.get(operator)
            # task_team_manager are 'version:share' pe ARH
            rbac.assign_role(op.id, 'task_team_manager', scope_type='disciplina',
                             scope_disciplina='ARH', created_by=adm)
            v = _versiune_shared(model_arh, adm, 'ARH')  # autor = admin
            # operatorul NU e autorul, dar are share fin pe ARH -> poate retrage
            allowed, motiv = bim_workflow.can_user_transition(op, v, 'wip')
            assert allowed is True, motiv
        finally:
            ff.set_flag('bim-rbac-fine', False)
