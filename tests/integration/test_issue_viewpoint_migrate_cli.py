"""
Test CLI 'flask migrate-bim' pentru Faza 4: pe o schema veche (bim_issues FARA
viewpoint_json) comanda trebuie sa adauge coloana cu ALTER idempotent.

Pattern teardown ca la test_clash_migrate_cli / test_gantt_calendar_db: la final
recreem schema curenta din modele (db.create_all) ca sa NU poluam sesiunea
(DB-ul e session-scoped, partajat cu restul testelor).
"""
from datetime import datetime

import pytest
from sqlalchemy import inspect, text


# DDL bim_issues FARA viewpoint_json - schema dinainte de Faza 4 (minimal, dar
# cu coloanele atinse de query-urile uzuale + cele adaugate de migrate-bim).
_DDL_ISSUES_VECHI = """
CREATE TABLE bim_issues (
    id INTEGER NOT NULL,
    tenant_id INTEGER,
    element_bim_id INTEGER,
    spatiu_id INTEGER,
    nivel_id INTEGER,
    cladire_id INTEGER,
    cod VARCHAR(50),
    titlu VARCHAR(300) NOT NULL,
    descriere TEXT,
    tip VARCHAR(50),
    severitate VARCHAR(20),
    status VARCHAR(30),
    raportat_de_id INTEGER,
    asignat_id INTEGER,
    data_raportare DATE,
    data_termen DATE,
    data_rezolvare DATE,
    bcf_topic_guid VARCHAR(100),
    extern_id VARCHAR(100),
    source_system VARCHAR(30),
    data_creare DATETIME,
    data_actualizare DATETIME,
    PRIMARY KEY (id)
)
"""


def test_migrate_bim_adauga_viewpoint_json_pe_schema_veche(app):
    from models import db, IssueBIM

    with app.app_context():
        # 1. Schema prod veche: bim_issues fara viewpoint_json
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS bim_issues'))
            conn.execute(text(_DDL_ISSUES_VECHI))
            conn.execute(text(
                "INSERT INTO bim_issues (titlu, tip, severitate, status, data_creare) "
                "VALUES ('Vechi', 'defect', 'medie', 'deschis', :acum)"),
                {'acum': datetime.utcnow()})
        db.session.remove()

        insp = inspect(db.engine)
        cols = {c['name'] for c in insp.get_columns('bim_issues')}
        assert 'viewpoint_json' not in cols

    # 2. Ruleaza CLI-ul de deploy
    runner = app.test_cli_runner()
    r1 = runner.invoke(args=['migrate-bim'])
    assert r1.exit_code == 0

    with app.app_context():
        insp = inspect(db.engine)
        cols = {c['name'] for c in insp.get_columns('bim_issues')}
        assert 'viewpoint_json' in cols  # ALTER aplicat

        # Query-ul pe model nu mai crapa, datele vechi raman
        iss = IssueBIM.query.first()
        assert iss is not None and iss.viewpoint_json is None

    # 3. Idempotent: a doua rulare nu crapa
    r2 = runner.invoke(args=['migrate-bim'])
    assert r2.exit_code == 0

    # 4. Teardown ROBUST: recreem schema curenta din modele
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS bim_issues'))
        db.session.remove()
        db.create_all()
