"""0012 gantt import db

Revision ID: 0012_gantt_import_db
Revises: 0011_deviz_pricing
Create Date: 2026-05-31 13:45:00.000000

Tabele pentru importul F3 configurabil din DB (overlay peste config/gantt/*.json):
- gantt_profil_mapare      profiluri de mapare invatate din wizard
- gantt_sinonim_coloana    sinonime de antet (overlay setari.json -> coloane)
- gantt_clasificare_regula dictionar de clasificare (overlay clasificare.json)
- gantt_relatie_template   relatii tehnologice (overlay dependinte.json)

Strict aditiv. Seed best-effort din JSON-urile curente -> daca seed-ul reuseste,
DB reflecta exact regulile de azi; daca tabelele raman goale, motorul cade pe JSON
(zero regresie in ambele cazuri).
"""
from typing import Sequence, Union
import json
import os
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012_gantt_import_db'
down_revision: Union[str, Sequence[str], None] = '0011_deviz_pricing'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# config/gantt/ relativ la radacina repo-ului (migrations/versions/.. -> ../../config/gantt)
_DIR_CFG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'config', 'gantt')


def _json(nume: str, implicit):
    try:
        with open(os.path.join(_DIR_CFG, nume), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return implicit


def upgrade() -> None:
    """Upgrade schema + seed din JSON."""
    # -- gantt_profil_mapare --
    op.create_table(
        'gantt_profil_mapare',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('nume', sa.String(length=120), nullable=False),
        sa.Column('semnatura', sa.String(length=255), nullable=False),
        sa.Column('mapare_json', sa.Text(), nullable=False),
        sa.Column('sursa', sa.String(length=20), nullable=False),
        sa.Column('nr_utilizari', sa.Integer(), nullable=False),
        sa.Column('activ', sa.Boolean(), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=True),
        sa.Column('data_actualizare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'semnatura', name='uix_gantt_profil_semnatura'),
    )
    with op.batch_alter_table('gantt_profil_mapare', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gantt_profil_mapare_semnatura'),
                              ['semnatura'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_profil_mapare_tenant_id'),
                              ['tenant_id'], unique=False)

    # -- gantt_sinonim_coloana --
    op.create_table(
        'gantt_sinonim_coloana',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('camp', sa.String(length=30), nullable=False),
        sa.Column('sinonim', sa.String(length=120), nullable=False),
        sa.Column('activ', sa.Boolean(), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'camp', 'sinonim', name='uix_gantt_sinonim'),
    )
    with op.batch_alter_table('gantt_sinonim_coloana', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gantt_sinonim_coloana_camp'),
                              ['camp'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_sinonim_coloana_tenant_id'),
                              ['tenant_id'], unique=False)

    # -- gantt_clasificare_regula --
    op.create_table(
        'gantt_clasificare_regula',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('categorie', sa.String(length=40), nullable=False),
        sa.Column('tip_regula', sa.String(length=16), nullable=False),
        sa.Column('valoare', sa.String(length=120), nullable=False),
        sa.Column('prioritate', sa.Integer(), nullable=False),
        sa.Column('activ', sa.Boolean(), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'categorie', 'tip_regula', 'valoare',
                            name='uix_gantt_clasif'),
    )
    with op.batch_alter_table('gantt_clasificare_regula', schema=None) as batch_op:
        batch_op.create_index('ix_gantt_clasif_tip_prio',
                              ['tip_regula', 'prioritate'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_clasificare_regula_categorie'),
                              ['categorie'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_clasificare_regula_tenant_id'),
                              ['tenant_id'], unique=False)

    # -- gantt_relatie_template --
    op.create_table(
        'gantt_relatie_template',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('categorie_din', sa.String(length=40), nullable=False),
        sa.Column('categorie_in', sa.String(length=40), nullable=False),
        sa.Column('tip', sa.String(length=2), nullable=False),
        sa.Column('decalaj', sa.Integer(), nullable=False),
        sa.Column('rang_din', sa.Integer(), nullable=True),
        sa.Column('activ', sa.Boolean(), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'categorie_din', 'categorie_in',
                            name='uix_gantt_relatie'),
    )
    with op.batch_alter_table('gantt_relatie_template', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gantt_relatie_template_tenant_id'),
                              ['tenant_id'], unique=False)

    _seed()


def _seed() -> None:
    """Populeaza tabelele din config/gantt/*.json (best-effort, idempotent la prima rulare)."""
    now = datetime.utcnow()

    t_sinonim = sa.table(
        'gantt_sinonim_coloana',
        sa.column('tenant_id', sa.Integer), sa.column('camp', sa.String),
        sa.column('sinonim', sa.String), sa.column('activ', sa.Boolean),
        sa.column('creat_de_id', sa.Integer), sa.column('data_creare', sa.DateTime),
    )
    t_clasif = sa.table(
        'gantt_clasificare_regula',
        sa.column('tenant_id', sa.Integer), sa.column('categorie', sa.String),
        sa.column('tip_regula', sa.String), sa.column('valoare', sa.String),
        sa.column('prioritate', sa.Integer), sa.column('activ', sa.Boolean),
        sa.column('creat_de_id', sa.Integer), sa.column('data_creare', sa.DateTime),
    )
    t_relatie = sa.table(
        'gantt_relatie_template',
        sa.column('tenant_id', sa.Integer), sa.column('categorie_din', sa.String),
        sa.column('categorie_in', sa.String), sa.column('tip', sa.String),
        sa.column('decalaj', sa.Integer), sa.column('rang_din', sa.Integer),
        sa.column('activ', sa.Boolean), sa.column('creat_de_id', sa.Integer),
        sa.column('data_creare', sa.DateTime),
    )

    # sinonime de coloana <- setari.json -> coloane
    coloane = (_json('setari.json', {}) or {}).get('coloane', {}) or {}
    randuri_sin = [
        {'tenant_id': None, 'camp': camp, 'sinonim': s, 'activ': True,
         'creat_de_id': None, 'data_creare': now}
        for camp, sinonime in coloane.items() for s in sinonime
    ]
    if randuri_sin:
        op.bulk_insert(t_sinonim, randuri_sin)

    # reguli de clasificare <- clasificare.json (cuvinte-cheie)
    clasif = _json('clasificare.json', {}) or {}
    randuri_cl = [
        {'tenant_id': None, 'categorie': categorie, 'tip_regula': 'cuvant',
         'valoare': w, 'prioritate': 100, 'activ': True,
         'creat_de_id': None, 'data_creare': now}
        for categorie, cuvinte in clasif.items() for w in cuvinte
    ]
    if randuri_cl:
        op.bulk_insert(t_clasif, randuri_cl)

    # relatii tehnologice <- dependinte.json (rang_din = pozitia 'from' in ordine_categorii)
    dep = _json('dependinte.json', {}) or {}
    rang = {c: i for i, c in enumerate(dep.get('ordine_categorii', []) or [])}
    randuri_rel = []
    for r in (dep.get('relatii', []) or []):
        din = r.get('from')
        randuri_rel.append({
            'tenant_id': None, 'categorie_din': din, 'categorie_in': r.get('to'),
            'tip': str(r.get('tip', 'FS')).upper(), 'decalaj': int(r.get('decalaj', 0) or 0),
            'rang_din': rang.get(din), 'activ': True,
            'creat_de_id': None, 'data_creare': now,
        })
    if randuri_rel:
        op.bulk_insert(t_relatie, randuri_rel)


def downgrade() -> None:
    """Downgrade schema (drop cele 4 tabele; SQLite scoate si indexurile asociate)."""
    op.drop_table('gantt_relatie_template')
    op.drop_table('gantt_clasificare_regula')
    op.drop_table('gantt_sinonim_coloana')
    op.drop_table('gantt_profil_mapare')
