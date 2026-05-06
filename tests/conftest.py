"""
Configurare pytest comuna - fixtures pentru aplicatie + DB temporara.

Strategia DB:
- `app` (scope=session): un singur Flask app + DB SQLite in tmpfile.
- `clean_bim` (scope=function): sterge intre teste datele BIM tipice de test
  ca sa nu existe contaminare intre runs.
"""

import os
import sys
import tempfile
import pytest

# Asigura ca repo root e in sys.path
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


@pytest.fixture(scope='session')
def app():
    """Instanta Flask app cu DB SQLite in tmpfile (clean per sesiune test)."""
    fd, db_path = tempfile.mkstemp(suffix='.db', prefix='workforce_test_')
    os.close(fd)

    os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'
    os.environ['SECRET_KEY'] = 'test-key-not-for-prod'
    os.environ['WTF_CSRF_ENABLED'] = '0'

    from app import create_app
    from models import db

    application = create_app('default')
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    application.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

    with application.app_context():
        db.create_all()

    yield application

    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def cleanup_test_data(app):
    """
    Auto-cleanup intre teste: WIPE complet la toate tabele BIM + activitati de test
    (folosim DB de test, ok sa fim agresivi).

    Ordine: copiii inainte de parinti pentru ca cascade SQLAlchemy
    nu ruleaza pe bulk delete in SQLite fara FK enforcement.
    """
    yield
    from models import (
        db, Santier, Cladire, Nivel, Zona, Spatiu, ElementBIM, Asset,
        IssueBIM, ModelBIM, ExternalMapping, RaportActivitate, Tenant,
        AuditLog, FeatureFlag,
    )
    with app.app_context():
        try:
            # WIPE total tabele BIM (le recreem la nevoie in fixture-uri specifice)
            for cls in (AuditLog, FeatureFlag, ExternalMapping, Asset, IssueBIM,
                        ElementBIM, Spatiu, Zona, Nivel, Cladire, Santier, ModelBIM):
                for obj in cls.query.all():
                    db.session.delete(obj)
            # Curat activitatile + tenant-urile de test
            for a in RaportActivitate.query.filter(
                RaportActivitate.activitate_principala.like('__%')
                | RaportActivitate.activitate_principala.like('TEST_%')
                | RaportActivitate.activitate_principala.like('SMOKE_%')
            ).all():
                db.session.delete(a)
            for t in Tenant.query.filter(
                Tenant.cod.like('test-%') | Tenant.cod.like('TEST-%')
            ).all():
                db.session.delete(t)
            db.session.commit()
        except Exception:
            db.session.rollback()


@pytest.fixture
def client(app):
    """Test client Flask."""
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Sesiune DB curata (rollback dupa fiecare test)."""
    from models import db
    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture
def admin_user(app):
    """Creeaza un admin de test si returneaza obiectul."""
    from models import db, Utilizator
    with app.app_context():
        u = Utilizator.query.filter_by(email='admin_test@test.local').first()
        if not u:
            u = Utilizator(
                nume='Admin', prenume='Test',
                email='admin_test@test.local',
                rol='admin', activ=True,
            )
            u.set_password('test_pass_123')
            db.session.add(u)
            db.session.commit()
        return u


@pytest.fixture
def authenticated_client(app, admin_user):
    """Test client deja autentificat ca admin."""
    client = app.test_client()
    client.post('/auth/login', data={
        'email': 'admin_test@test.local',
        'parola': 'test_pass_123',
    }, follow_redirects=False)
    return client


@pytest.fixture
def operator_user(app):
    """Creeaza un operator de test."""
    from models import db, Utilizator
    with app.app_context():
        u = Utilizator.query.filter_by(email='operator_test@test.local').first()
        if not u:
            u = Utilizator(nume='Op', prenume='Test',
                           email='operator_test@test.local',
                           rol='operator', activ=True)
            u.set_password('op_pass_123')
            db.session.add(u)
            db.session.commit()
        return u


@pytest.fixture
def operator_client(app, operator_user):
    """Test client autentificat ca operator."""
    client = app.test_client()
    client.post('/auth/login', data={
        'email': 'operator_test@test.local',
        'parola': 'op_pass_123',
    }, follow_redirects=False)
    return client


@pytest.fixture
def full_bim_hierarchy(app):
    """Ierarhie BIM completa: santier > cladire > 3 niveluri > 2 spatii > 2 elemente."""
    from models import db, Santier, Cladire, Nivel, Spatiu, ElementBIM
    from tests.fixtures.data import setup_full_bim_hierarchy
    with app.app_context():
        result = setup_full_bim_hierarchy(db, Santier, Cladire, Nivel, Spatiu, ElementBIM)
        # Yield ID-urile pentru a evita detached instance issues
        yield {k: v.id for k, v in result.items()}


@pytest.fixture
def workforce_basic(app):
    """Set minimal: 1 proiect + 1 angajat, returneaza dict cu ID-uri."""
    from models import db, Proiect, Angajat
    from tests.fixtures.data import make_proiect, make_angajat
    with app.app_context():
        # Curat orice rest
        Proiect.query.filter_by(cod_proiect='PRJ-WB-001').delete()
        Angajat.query.filter_by(cnp='1900101010101').delete()
        db.session.commit()
        p = make_proiect(db, Proiect, cod='PRJ-WB-001')
        a = make_angajat(db, Angajat, cnp='1900101010101',
                         nume='WBTest', prenume='Inginer')
        yield {'proiect_id': p.id, 'angajat_id': a.id}
        # Cleanup
        Proiect.query.filter_by(cod_proiect='PRJ-WB-001').delete()
        Angajat.query.filter_by(cnp='1900101010101').delete()
        db.session.commit()


@pytest.fixture
def minimal_ifc_path():
    """Path catre fisier IFC minimal de test (~1.8KB)."""
    return os.path.join(os.path.dirname(__file__), 'fixtures', 'ifc', 'minimal.ifc')


# ============================================================
# MySQL TEST FIXTURES (opt-in via MYSQL_TEST_URL)
# ============================================================
# Pentru a rula testele pe MySQL, seteaza:
#     export MYSQL_TEST_URL='mysql+pymysql://user:pass@host:port/dbname'
# Fara aceasta env var, testele cu @pytest.mark.mysql skip elegant.
#
# Pentru dev local rapid: foloseste docker-compose.test.yml (vezi README testing).
# ============================================================

def _mysql_test_url():
    """Returneaza URL-ul MySQL de test sau None."""
    return os.environ.get('MYSQL_TEST_URL', '').strip() or None


def _mysql_available():
    """True daca avem MYSQL_TEST_URL si conexiunea functioneaza."""
    url = _mysql_test_url()
    if not url:
        return False
    try:
        from sqlalchemy import create_engine, text
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as c:
            c.execute(text('SELECT 1'))
        return True
    except Exception:
        return False


# Marker pentru a sari testele MySQL daca MYSQL_TEST_URL nu e setat sau MySQL nu raspunde.
# Folosire:
#   @pytest.mark.mysql
#   def test_ceva_mysql(mysql_app):
#       ...
def pytest_collection_modifyitems(config, items):
    """Skip teste @pytest.mark.mysql daca MYSQL_TEST_URL lipseste."""
    if _mysql_available():
        return
    skip_mysql = pytest.mark.skip(
        reason='MYSQL_TEST_URL nu e setat sau MySQL inaccesibil. '
               'Pentru a rula: export MYSQL_TEST_URL=mysql+pymysql://...'
    )
    for item in items:
        if 'mysql' in item.keywords:
            item.add_marker(skip_mysql)


@pytest.fixture(scope='session')
def mysql_app():
    """
    Instanta Flask app conectata la MySQL test (DROP+CREATE schema la inceput).

    Ruleaza doar daca MYSQL_TEST_URL e setat. Marker @pytest.mark.mysql
    skip-uieste testele care depind de aceasta fixture.
    """
    url = _mysql_test_url()
    if not url:
        pytest.skip('MYSQL_TEST_URL nu e setat')

    os.environ['DATABASE_URL'] = url
    os.environ['SECRET_KEY'] = 'mysql-test-key'
    os.environ['WTF_CSRF_ENABLED'] = '0'

    from app import create_app
    from models import db

    application = create_app('default')
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    application.config['SQLALCHEMY_DATABASE_URI'] = url

    with application.app_context():
        # Schema fresh pentru sesiunea de test
        db.drop_all()
        db.create_all()

    yield application

    # Cleanup: drop schema la finalul sesiunii
    with application.app_context():
        try:
            db.drop_all()
        except Exception:
            pass


@pytest.fixture
def mysql_client(mysql_app):
    """Test client pentru mysql_app."""
    return mysql_app.test_client()


@pytest.fixture
def mysql_admin_user(mysql_app):
    """Admin de test in MySQL."""
    from models import db, Utilizator
    with mysql_app.app_context():
        u = Utilizator.query.filter_by(email='admin_my@test.local').first()
        if not u:
            u = Utilizator(nume='AdminMy', prenume='Test',
                           email='admin_my@test.local',
                           rol='admin', activ=True)
            u.set_password('mysql_pass_123')
            db.session.add(u)
            db.session.commit()
        return u


@pytest.fixture
def mysql_authenticated_client(mysql_app, mysql_admin_user):
    """Test client autentificat ca admin pe MySQL."""
    client = mysql_app.test_client()
    client.post('/auth/login', data={
        'email': 'admin_my@test.local',
        'parola': 'mysql_pass_123',
    }, follow_redirects=False)
    return client
