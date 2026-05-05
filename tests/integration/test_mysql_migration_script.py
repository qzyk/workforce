"""
End-to-end test pentru scripts/migrate_sqlite_to_mysql.py.

Workflow:
1. Creez un fisier SQLite temporar cu schema completa + 50+ randuri de test
2. Rulez migrate(sqlite_path, mysql_url)
3. Verific:
   - Toate tabelele migrate
   - Row count se potriveste
   - Sample data identica
   - AUTO_INCREMENT setat corect
   - Idempotenta: rerun nu duplica

Pentru rulare:
    docker compose -f docker-compose.test.yml up -d
    export MYSQL_TEST_URL='mysql+pymysql://workforce:workforce_pass@127.0.0.1:3307/workforce_test'
    pytest tests/integration/test_mysql_migration_script.py -v
"""

import os
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal

import pytest

pytestmark = pytest.mark.mysql


@pytest.fixture
def populated_sqlite():
    """Creeaza un SQLite cu 50+ randuri reprezentative pentru test migrare."""
    fd, path = tempfile.mkstemp(suffix='.db', prefix='workforce_migr_test_')
    os.close(fd)

    sqlite_url = f'sqlite:///{path}'
    os.environ['DATABASE_URL'] = sqlite_url

    from app import create_app
    from models import db, Tenant, Utilizator, Angajat, Proiect, RaportActivitate
    from models import Santier, Cladire, Nivel, Spatiu, ElementBIM
    app = create_app('default')
    with app.app_context():
        db.create_all()

        # Tenants
        t = Tenant(cod='migr-test', nume='Migration Test Tenant', activ=True)
        db.session.add(t); db.session.commit()

        # Utilizatori
        u_admin = Utilizator(nume='Admin', prenume='Migr',
                              email='admin.migr@test.local', rol='admin', activ=True)
        u_admin.set_password('p')
        db.session.add(u_admin); db.session.commit()

        # 5 angajati cu CNP unic
        angajati_ids = []
        for i in range(5):
            a = Angajat(
                cnp=f'18001010100{i:02d}', nume=f'Angajat{i}', prenume='Test',
                email=f'a{i}@test.local',
                functie=['Inginer', 'Sef_santier', 'Director', 'Manager_calitate', 'Muncitor'][i % 5],
                tip_contract='nedeterminat',
                salariu_baza=Decimal('5040.50') + Decimal(str(i * 100)),
                data_angajare=date(2024, 1, 1),
                status='activ',
            )
            db.session.add(a)
        db.session.commit()
        angajati = Angajat.query.filter(Angajat.cnp.like('1800101%')).all()
        angajati_ids = [a.id for a in angajati]

        # 3 proiecte
        proiecte_ids = []
        for i in range(3):
            p = Proiect(
                cod_proiect=f'PRJ-MIGR-{i:02d}',
                nume=f'Proiect Migrare {i}',
                data_start=date(2025, 1, 1),
                data_sfarsit_planificat=date(2026, 6, 30),
                buget_total=Decimal('100000.00'),
                buget_manopera=Decimal('30000.00'),
                status='activ',
                beneficiar='Beneficiar Test',
            )
            db.session.add(p)
        db.session.commit()
        proiecte_ids = [p.id for p in Proiect.query.filter(Proiect.cod_proiect.like('PRJ-MIGR-%')).all()]

        # 30 rapoarte activitate
        for i in range(30):
            r = RaportActivitate(
                angajat_id=angajati_ids[i % len(angajati_ids)],
                proiect_id=proiecte_ids[i % len(proiecte_ids)],
                data=date(2025, 9, 1 + (i % 28)),
                tip_activitate=['zilnica', 'saptamanala', 'lunara'][i % 3],
                activitate_principala=f'Activitate test {i} - cu Șț',
                activitate_detaliata=f'Detalii: pasul {i} pe Câmpul Băneasa 🏗️',
                status='draft',
                status_executie='in_desfasurare',
                ore_lucrate=Decimal('8.0'),
                necesita_aprobare_tehnica=(i % 2 == 0),
            )
            db.session.add(r)
        db.session.commit()

        # BIM ierarhie
        s = Santier(cod='MIGR-S1', nume='Santier Migrare', oras='București')
        db.session.add(s); db.session.commit()
        c = Cladire(santier_id=s.id, cod='B1', nume='Cladire 1', nr_niveluri=3)
        db.session.add(c); db.session.commit()
        n = Nivel(cladire_id=c.id, cod='N00', nume='Parter', ordine=0)
        db.session.add(n); db.session.commit()
        sp = Spatiu(nivel_id=n.id, cod='SP1', nume='Birou')
        db.session.add(sp); db.session.commit()
        # 10 elemente BIM
        for i in range(10):
            db.session.add(ElementBIM(
                cladire_id=c.id, nivel_id=n.id, spatiu_id=sp.id,
                cod=f'EL-{i:03d}', tip_element=['wall', 'door', 'AHU'][i % 3],
                ifc_global_id=f'GUID-{i:08d}',
                source_system='ifc',
                status='proiectat',
            ))
        db.session.commit()

    yield path

    # Cleanup
    try:
        os.unlink(path)
    except OSError:
        pass


def _wipe_mysql_db(mysql_url):
    """Sterge toate tabelele din MySQL test ca sa porneasca curat."""
    from sqlalchemy import create_engine, text, MetaData
    engine = create_engine(mysql_url)
    meta = MetaData()
    meta.reflect(bind=engine)
    with engine.begin() as conn:
        conn.execute(text('SET FOREIGN_KEY_CHECKS=0'))
        for tbl in reversed(meta.sorted_tables):
            conn.execute(text(f'DROP TABLE IF EXISTS {tbl.name}'))
        conn.execute(text('SET FOREIGN_KEY_CHECKS=1'))


class TestMigrationE2E:
    def test_migration_full_pipeline(self, populated_sqlite):
        """Migrare completa SQLite -> MySQL + verificare row counts."""
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        assert mysql_url, 'MYSQL_TEST_URL needed'

        _wipe_mysql_db(mysql_url)

        from scripts.migrate_sqlite_to_mysql import migrate
        stats = migrate(populated_sqlite, mysql_url, dry_run=False, verbose=False)

        # Asertez ca tabelele cheie au date
        assert stats['tenants']['migrated'] >= 1
        assert stats['utilizatori']['migrated'] >= 1
        assert stats['angajati']['migrated'] == 5
        assert stats['proiecte']['migrated'] == 3
        assert stats['rapoarte_activitati']['migrated'] == 30
        assert stats['bim_santiere']['migrated'] == 1
        assert stats['bim_cladiri']['migrated'] == 1
        assert stats['bim_niveluri']['migrated'] == 1
        assert stats['bim_spatii']['migrated'] == 1
        assert stats['bim_elemente']['migrated'] == 10

    def test_migration_preserves_data(self, populated_sqlite):
        """Sample row check: dupa migrare, datele sunt identice."""
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        _wipe_mysql_db(mysql_url)

        from scripts.migrate_sqlite_to_mysql import migrate
        migrate(populated_sqlite, mysql_url, dry_run=False, verbose=False)

        # Conectez la MySQL si verific
        os.environ['DATABASE_URL'] = mysql_url
        from app import create_app
        from models import db, Angajat, RaportActivitate, ElementBIM
        app = create_app('default')
        with app.app_context():
            # Numar exact
            assert Angajat.query.filter(Angajat.cnp.like('1800101%')).count() == 5
            assert RaportActivitate.query.filter(
                RaportActivitate.activitate_principala.like('Activitate test%')
            ).count() == 30
            assert ElementBIM.query.filter(ElementBIM.cod.like('EL-%')).count() == 10

            # Verifica diacritice + emoji
            r = RaportActivitate.query.filter(
                RaportActivitate.activitate_principala.like('Activitate test 0%')
            ).first()
            assert r is not None
            assert 'Șț' in r.activitate_principala
            assert '🏗️' in r.activitate_detaliata

            # Verifica boolean preserved
            true_count = RaportActivitate.query.filter(
                RaportActivitate.activitate_principala.like('Activitate test%'),
                RaportActivitate.necesita_aprobare_tehnica == True
            ).count()
            assert true_count > 0

            # Verifica decimal preserved
            a = Angajat.query.filter_by(cnp='180010101000').first()
            assert a.salariu_baza == Decimal('5040.50')

    def test_migration_idempotent(self, populated_sqlite):
        """Re-rularea migrarii nu duplica date."""
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        _wipe_mysql_db(mysql_url)

        from scripts.migrate_sqlite_to_mysql import migrate
        migrate(populated_sqlite, mysql_url, dry_run=False, verbose=False)
        stats2 = migrate(populated_sqlite, mysql_url, dry_run=False, verbose=False)

        # A doua rulare: toate tabelele cu skipped=True
        for tname, s in stats2.items():
            if s.get('migrated', 0) > 0:
                pytest.fail(f'Re-rulare a inserat in {tname} {s["migrated"]} randuri (nu trebuia)')

    def test_auto_increment_after_migration(self, populated_sqlite):
        """Dupa migrare, AUTO_INCREMENT trebuie setat la max(id)+1."""
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        _wipe_mysql_db(mysql_url)

        from scripts.migrate_sqlite_to_mysql import migrate
        migrate(populated_sqlite, mysql_url, dry_run=False, verbose=False)

        os.environ['DATABASE_URL'] = mysql_url
        from app import create_app
        from models import db, Tenant
        app = create_app('default')
        with app.app_context():
            existing_max = db.session.execute(
                db.text('SELECT MAX(id) FROM tenants')
            ).scalar() or 0
            new_t = Tenant(cod='migr-after', nume='New After')
            db.session.add(new_t); db.session.commit()
            assert new_t.id > existing_max
            db.session.delete(new_t); db.session.commit()


class TestDryRunMode:
    def test_dry_run_doesnt_insert(self, populated_sqlite):
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        _wipe_mysql_db(mysql_url)

        # Trebuie sa creez schema-ul intai, ca dry_run nu o face
        from sqlalchemy import create_engine
        os.environ['DATABASE_URL'] = mysql_url
        from app import create_app
        from models import db
        app = create_app('default')
        with app.app_context():
            db.create_all()

        from scripts.migrate_sqlite_to_mysql import migrate
        stats = migrate(populated_sqlite, mysql_url, dry_run=True, verbose=False)

        # Toate tabelele non-empty trebuie sa fie 'dry_run': True
        for tname, s in stats.items():
            if s.get('sqlite', 0) > 0:
                assert s.get('dry_run') is True
                assert s.get('migrated', 0) == 0
