"""Teste U3 (stepper Gantt) + U4 (empty states / hint pasul urmator) - randare fara erori."""


def test_gantt_stepper_si_loading(authenticated_client):
    """U3: pagina Gantt are stepperul vizibil + overlay-ul de incarcare."""
    r = authenticated_client.get('/gantt/')
    assert r.status_code == 200
    assert b'gz-stepper' in r.data and b'gzLoading' in r.data


def test_dashboard_ghid_pas_urmator(authenticated_client, app):
    """U4: dashboard randeaza + macro-ul next_hint se importa fara eroare."""
    r = authenticated_client.get('/')
    assert r.status_code == 200


def test_pontaje_empty_state_macro(authenticated_client):
    """U4: lista pontaje (empty_state macro) randeaza fara eroare."""
    r = authenticated_client.get('/pontaje/')
    assert r.status_code == 200


def test_dashboard_ghid_fara_planuri(authenticated_client, app):
    """U4: cu proiecte dar fara planuri -> hint 'creeaza primul plan'."""
    from models import db, Proiect, GanttPlan
    from datetime import date
    with app.app_context():
        GanttPlan.query.delete()                  # asiguram 0 planuri
        p = Proiect(cod_proiect='GHID-T', nume='Ghid', data_start=date.today())
        db.session.add(p); db.session.commit()
        pid = p.id
    try:
        r = authenticated_client.get('/')
        assert r.status_code == 200
        assert b'Creeaza primul plan' in r.data   # are proiect, 0 planuri
    finally:
        with app.app_context():
            pr = db.session.get(Proiect, pid)
            if pr:
                db.session.delete(pr)
                db.session.commit()
