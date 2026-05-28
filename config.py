"""
EDIFICO WORKFORCE - Configurare aplicatie
"""

import os
import secrets

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Securitate
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'edifico-workforce-dev-key-2024-do-not-use-in-production'
    WTF_CSRF_ENABLED = True

    # Baza de date
    # Suporta:
    # - SQLite (default): sqlite:///<path>/workforce.db
    # - MySQL: mysql+pymysql://user:pass@host/dbname
    # - MySQL (legacy short): mysql://... (auto-converted la mysql+pymysql://)
    _db_url = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'database', 'workforce.db')
    # Auto-prefer pymysql daca user-ul a scris doar mysql:// (ex: PythonAnywhere docs)
    if _db_url.startswith('mysql://') and not _db_url.startswith('mysql+'):
        _db_url = _db_url.replace('mysql://', 'mysql+pymysql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Engine options - pool tuning pentru MySQL pe PythonAnywhere
    # (PA inchide conexiuni MySQL idle dupa ~5 min)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,    # detecteaza conexiuni stale
        'pool_recycle': 280,      # recicleaza la 280s (sub limita PA de 300s)
    } if 'mysql' in _db_url else {}

    @staticmethod
    def is_mysql():
        return 'mysql' in Config.SQLALCHEMY_DATABASE_URI

    @staticmethod
    def is_sqlite():
        return Config.SQLALCHEMY_DATABASE_URI.startswith('sqlite:///')

    # Upload fisiere
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    EXPORT_FOLDER = os.path.join(basedir, 'exports')
    MAX_CONTENT_LENGTH = 250 * 1024 * 1024  # 250MB (modele IFC mari, ex. 58MB+)

    # Extensii permise
    ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'docx', 'xlsx'}

    # Extensii permise pentru documente proiect (include DWG, DXF, ZIP)
    ALLOWED_EXTENSIONS_PROIECT = {'pdf', 'dwg', 'dxf', 'docx', 'xlsx', 'jpg', 'jpeg', 'png', 'zip'}

    # Fus orar
    TIMEZONE = 'Europe/Bucharest'

    # Paginare
    ITEMS_PER_PAGE = 25

    # Sesiune
    PERMANENT_SESSION_LIFETIME = 28800  # 8 ore in secunde

    # Multi-tenant: 'off' | 'optional' | 'strict'
    MULTI_TENANT_MODE = os.environ.get('MULTI_TENANT_MODE', 'off')
    TENANT_FROM_SUBDOMAIN = os.environ.get('TENANT_FROM_SUBDOMAIN', 'false').lower() == 'true'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
