"""
Configurare pytest comuna - fixtures pentru aplicatie + DB temporara.
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
