"""
Test CLI 'flask migrate-bim' pentru Faza 3: pe o schema veche (bim_clash_runs
FARA tolerance_mm, FARA bim_clash_group) comanda trebuie sa adauge coloana cu
ALTER idempotent si sa creeze tabela noua via db.create_all().

Pattern teardown ca la test_gantt_calendar_db / test_ifc_pset_bbox: la final
recreem schema curenta din modele (db.create_all) ca sa NU poluam sesiunea
(DB-ul e session-scoped, partajat cu restul testelor).
"""
from datetime import datetime

import pytest
from sqlalchemy import inspect, text


# DDL bim_clash_runs FARA tolerance_mm - schema dinainte de Faza 3
_DDL_CLASH_RUNS_VECHI = """
CREATE TABLE bim_clash_runs (
    id INTEGER NOT NULL,
    tenant_id INTEGER,
    model_id INTEGER,
    santier_id INTEGER,
    tip VARCHAR(20) NOT NULL,
    nr_clash_uri INTEGER,
    nr_critica INTEGER,
    nr_mare INTEGER,
    nr_medie INTEGER,
    nr_mica INTEGER,
    status VARCHAR(20) NOT NULL,
    durata_ms INTEGER,
    log TEXT,
    data_rulare DATETIME NOT NULL,
    rulat_de_id INTEGER,
    PRIMARY KEY (id)
)
"""


def test_migrate_bim_adauga_tolerance_si_clash_group_pe_schema_veche(app):
    from models import db, ClashRun

    with app.app_context():
        # 1. Schema prod veche: clash_runs fara tolerance_mm, fara clash_group
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS bim_clash_group'))
            conn.execute(text('DROP TABLE IF EXISTS bim_clash_results'))
            conn.execute(text('DROP TABLE IF EXISTS bim_clash_runs'))
            conn.execute(text(_DDL_CLASH_RUNS_VECHI))
            # un run existent, ca pe prod
            conn.execute(text(
                "INSERT INTO bim_clash_runs (tip, status, data_rulare) "
                "VALUES ('logic', 'finalizat', :acum)"),
                {'acum': datetime.utcnow()})
        db.session.remove()

        insp = inspect(db.engine)
        cols = {c['name'] for c in insp.get_columns('bim_clash_runs')}
        assert 'tolerance_mm' not in cols
        assert 'bim_clash_group' not in insp.get_table_names()

    # 2. Ruleaza CLI-ul de deploy
    runner = app.test_cli_runner()
    r1 = runner.invoke(args=['migrate-bim'])
    assert r1.exit_code == 0

    with app.app_context():
        insp = inspect(db.engine)
        cols = {c['name'] for c in insp.get_columns('bim_clash_runs')}
        assert 'tolerance_mm' in cols                    # ALTER aplicat
        assert 'bim_clash_group' in insp.get_table_names()  # create_all a creat tabela

        # Query-ul pe model nu mai crapa, datele vechi raman
        run = ClashRun.query.first()
        assert run is not None and run.tolerance_mm is None

    # 3. Idempotent: a doua rulare nu crapa
    r2 = runner.invoke(args=['migrate-bim'])
    assert r2.exit_code == 0

    # 4. Teardown ROBUST: recreem schema curenta din modele
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS bim_clash_group'))
            conn.execute(text('DROP TABLE IF EXISTS bim_clash_results'))
            conn.execute(text('DROP TABLE IF EXISTS bim_clash_runs'))
        db.session.remove()
        db.create_all()
