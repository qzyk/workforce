"""
INNOVA WORKFORCE - Configurare aplicatie
"""

import os
import secrets

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Securitate
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'innova-workforce-dev-key-2024-do-not-use-in-production'
    WTF_CSRF_ENABLED = True

    # Baza de date
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'database', 'workforce.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload fisiere
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    EXPORT_FOLDER = os.path.join(basedir, 'exports')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

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


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
