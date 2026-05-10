"""
Teste unit pentru services.bim_workflow (CDE workflow + versioning).
"""

import pytest

from models import db, BIMModelVersion, ModelBIM, Utilizator
from services import bim_workflow


# ====================================================
# FIXTURES
# ====================================================

@pytest.fixture
def model(app):
    with app.app_context():
        m = ModelBIM(nume='Test Model', tip='ifc', versiune='draft')
        db.session.add(m)
        db.session.commit()
        yield m.id


@pytest.fixture
def user_admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='wf_admin@test.local').first()
        if not u:
            u = Utilizator(nume='WF', prenume='Admin', email='wf_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x')
            db.session.add(u)
            db.session.commit()
        yield u.id


@pytest.fixture
def user_operator(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='wf_op@test.local').first()
        if not u:
            u = Utilizator(nume='WF', prenume='Op', email='wf_op@test.local',
                           rol='operator', activ=True)
            u.set_password('x')
            db.session.add(u)
            db.session.commit()
        yield u.id


# ====================================================
# CREATE NEW VERSION
# ====================================================

def test_create_new_version_default_status_is_wip(app, model, user_admin):
    with app.app_context():
        m = ModelBIM.query.get(model)
        u = Utilizator.query.get(user_admin)
        v = bim_workflow.create_new_version(m, 'v1.0', u, disciplina='ARH')
        assert v.status == 'wip'
        assert v.versiune == 'v1.0'
        assert v.disciplina == 'ARH'
        assert v.creat_de_id == u.id


def test_create_duplicate_version_raises(app, model, user_admin):
    with app.app_context():
        m = ModelBIM.query.get(model)
        u = Utilizator.query.get(user_admin)
        bim_workflow.create_new_version(m, 'v1.0', u)
        with pytest.raises(bim_workflow.WorkflowError):
            bim_workflow.create_new_version(m, 'v1.0', u)


def test_create_empty_version_label_raises(app, model, user_admin):
    with app.app_context():
        m = ModelBIM.query.get(model)
        u = Utilizator.query.get(user_admin)
        with pytest.raises(bim_workflow.WorkflowError):
            bim_workflow.create_new_version(m, '   ', u)


# ====================================================
# TRANSITION RULES
# ====================================================

def test_wip_to_shared_allowed_for_anyone(app, model, user_operator):
    with app.app_context():
        m = ModelBIM.query.get(model)
        u = Utilizator.query.get(user_operator)
        v = bim_workflow.create_new_version(m, 'v1.0', u)
        bim_workflow.transition(v, 'shared', u)
        assert v.status == 'shared'
        assert v.data_share is not None


def test_shared_to_published_requires_admin_or_manager(app, model, user_admin, user_operator):
    with app.app_context():
        m = ModelBIM.query.get(model)
        admin = Utilizator.query.get(user_admin)
        op = Utilizator.query.get(user_operator)
        v = bim_workflow.create_new_version(m, 'v1.0', op)
        bim_workflow.transition(v, 'shared', op)
        # Operatorul NU poate publica
        with pytest.raises(bim_workflow.WorkflowError):
            bim_workflow.transition(v, 'published', op)
        # Admin DA
        bim_workflow.transition(v, 'published', admin)
        assert v.status == 'published'
        assert v.aprobat_de_id == admin.id
        assert v.data_publicare is not None


def test_invalid_transition_raises(app, model, user_admin):
    with app.app_context():
        m = ModelBIM.query.get(model)
        u = Utilizator.query.get(user_admin)
        v = bim_workflow.create_new_version(m, 'v1.0', u)
        # wip -> published direct nu e permis
        with pytest.raises(bim_workflow.WorkflowError):
            bim_workflow.transition(v, 'published', u)


def test_archived_is_terminal(app, model, user_admin):
    with app.app_context():
        m = ModelBIM.query.get(model)
        u = Utilizator.query.get(user_admin)
        v = bim_workflow.create_new_version(m, 'v1.0', u)
        bim_workflow.transition(v, 'archived', u)
        assert v.is_terminal
        # Din archived nu se mai poate face nicio tranzitie
        for new_status in ('wip', 'shared', 'published', 'rejected'):
            with pytest.raises(bim_workflow.WorkflowError):
                bim_workflow.transition(v, new_status, u)


def test_rejected_with_comentariu(app, model, user_admin, user_operator):
    with app.app_context():
        m = ModelBIM.query.get(model)
        admin = Utilizator.query.get(user_admin)
        op = Utilizator.query.get(user_operator)
        v = bim_workflow.create_new_version(m, 'v1.0', op)
        bim_workflow.transition(v, 'shared', op)
        bim_workflow.transition(v, 'rejected', admin, comentariu='Lipsa cote pe etajul 3')
        assert v.status == 'rejected'
        assert v.comentariu_aprobare == 'Lipsa cote pe etajul 3'
        assert v.aprobat_de_id == admin.id


def test_shared_to_wip_by_creator(app, model, user_operator):
    with app.app_context():
        m = ModelBIM.query.get(model)
        op = Utilizator.query.get(user_operator)
        v = bim_workflow.create_new_version(m, 'v1.0', op)
        bim_workflow.transition(v, 'shared', op)
        # Creatorul poate trage inapoi in WIP
        bim_workflow.transition(v, 'wip', op)
        assert v.status == 'wip'


def test_shared_to_wip_blocked_for_non_creator_non_manager(app, model, user_operator):
    with app.app_context():
        m = ModelBIM.query.get(model)
        op = Utilizator.query.get(user_operator)
        v = bim_workflow.create_new_version(m, 'v1.0', op)
        bim_workflow.transition(v, 'shared', op)

        # Alt user operator (nu creatorul)
        alt = Utilizator(nume='Alt', prenume='Op', email='alt_op@test.local',
                         rol='operator', activ=True)
        alt.set_password('x')
        db.session.add(alt)
        db.session.commit()

        with pytest.raises(bim_workflow.WorkflowError):
            bim_workflow.transition(v, 'wip', alt)


# ====================================================
# QUERIES
# ====================================================

def test_get_published_versions_for_santier(app, user_admin):
    from models import Santier
    with app.app_context():
        admin = Utilizator.query.get(user_admin)
        s = Santier(cod='S-FED-01', nume='Santier Federation Test')
        db.session.add(s)
        db.session.commit()

        m1 = ModelBIM(nume='ARH', tip='ifc', santier_id=s.id)
        m2 = ModelBIM(nume='STR', tip='ifc', santier_id=s.id)
        db.session.add_all([m1, m2])
        db.session.commit()

        v1 = bim_workflow.create_new_version(m1, 'v1.0', admin, disciplina='ARH')
        v2 = bim_workflow.create_new_version(m2, 'v1.0', admin, disciplina='STR')
        v_wip = bim_workflow.create_new_version(m1, 'v2.0', admin, disciplina='ARH')

        bim_workflow.transition(v1, 'shared', admin)
        bim_workflow.transition(v1, 'published', admin)
        bim_workflow.transition(v2, 'shared', admin)
        bim_workflow.transition(v2, 'published', admin)
        # v_wip ramane in WIP

        published = bim_workflow.get_published_versions_for_santier(s.id)
        assert len(published) == 2
        # Toate sunt published
        for v in published:
            assert v.status == 'published'


def test_get_latest_version_filtered_by_status(app, model, user_admin):
    with app.app_context():
        m = ModelBIM.query.get(model)
        u = Utilizator.query.get(user_admin)
        v1 = bim_workflow.create_new_version(m, 'v1.0', u)
        v2 = bim_workflow.create_new_version(m, 'v2.0', u)
        bim_workflow.transition(v1, 'shared', u)
        bim_workflow.transition(v1, 'published', u)
        # v2 ramane WIP

        latest_any = bim_workflow.get_latest_version(m.id)
        latest_published = bim_workflow.get_latest_version(m.id, status='published')

        assert latest_any.versiune == 'v2.0'  # cea mai recenta indiferent de status
        assert latest_published.versiune == 'v1.0'
