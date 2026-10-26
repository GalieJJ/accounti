"""add kontierung (Baustein 10b: Herkunft je Buchung, gelernte Kontierungsregeln)

Revision ID: d5a849692843
Revises: a14acef69fae
Create Date: 2026-10-21 22:55:11.190053

``kontierungsgruende`` ist nur anfügbar (unter SQLite zusätzlich per Trigger, wie
``journal``); ``kontierungsregeln`` hält die gelernten Regeln der Gesellschaft (vorher
als ``gelernt_*`` in der Regeldatei — ``accounti regeln uebernehmen`` holt sie).

Hat ein Befehl des neuen Codes die Tabellen schon angelegt (``init_db`` vor der
Migration), übernimmt die Migration sie und legt nur an, was fehlt.

Hängt seit dem Zusammenführen mit main hinter ``a14acef69fae`` (Verrechnungen,
Gesamttest Debitoren) — vorher hinter ``ddc9a184ddb4``; die Reihenfolge der beiden
Migrationen von Baustein 10b bleibt.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5a849692843'
down_revision: Union[str, Sequence[str], None] = 'a14acef69fae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# nur anfügen — SQLite sperrt auch rohes SQL (wie after_create in tabellen_kontierung.py)
TRIGGER = {"kontierungsgruende": "Kontierungsgründe sind unveränderbar"}


def _tabellen() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indizes(tabelle: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(tabelle)}


def upgrade() -> None:
    """Upgrade schema."""
    vorhanden = _tabellen()
    if 'kontierungsgruende' not in vorhanden:
        op.create_table('kontierungsgruende',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('buchung_id', sa.String(length=36), nullable=False),
        sa.Column('quelle', sa.String(length=20), nullable=False),
        sa.Column('regel', sa.String(length=100), nullable=True),
        sa.Column('modell', sa.String(length=100), nullable=True),
        sa.Column('begruendung', sa.String(length=500), nullable=False),
        sa.Column('erstellt_am', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
    indizes = _indizes('kontierungsgruende')
    if 'ix_kontierungsgruende_buchung_id' not in indizes:
        op.create_index(op.f('ix_kontierungsgruende_buchung_id'), 'kontierungsgruende', ['buchung_id'], unique=False)
    if 'ix_kontierungsgruende_regel' not in indizes:
        op.create_index(op.f('ix_kontierungsgruende_regel'), 'kontierungsgruende', ['regel'], unique=False)
    if 'kontierungsregeln' not in vorhanden:
        op.create_table('kontierungsregeln',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('muster', sa.String(length=200), nullable=False),
        sa.Column('ist_text', sa.Boolean(), nullable=False),
        sa.Column('feld', sa.String(length=20), nullable=False),
        sa.Column('richtung', sa.String(length=10), nullable=True),
        sa.Column('soll_konto', sa.String(length=10), nullable=False),
        sa.Column('haben_konto', sa.String(length=10), nullable=False),
        sa.Column('steuer_schluessel', sa.Integer(), nullable=True),
        sa.Column('buchungstext', sa.String(length=60), nullable=True),
        sa.Column('quelle_buchung_id', sa.String(length=36), nullable=True),
        sa.Column('herkunft', sa.String(length=20), nullable=False),
        sa.Column('angelegt_von', sa.String(length=100), nullable=False),
        sa.Column('angelegt_am', sa.DateTime(), nullable=False),
        sa.Column('aktiv', sa.Boolean(), nullable=False),
        sa.Column('deaktiviert_von', sa.String(length=100), nullable=True),
        sa.Column('deaktiviert_am', sa.DateTime(), nullable=True),
        sa.Column('deaktiviert_grund', sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
        )
    if 'ix_kontierungsregeln_aktiv' not in _indizes('kontierungsregeln'):
        op.create_index(op.f('ix_kontierungsregeln_aktiv'), 'kontierungsregeln', ['aktiv'], unique=False)
    if op.get_bind().dialect.name == "sqlite":
        for tabelle, text in TRIGGER.items():
            for aktion in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {tabelle}_kein_{aktion.lower()} "
                    f"BEFORE {aktion} ON {tabelle} BEGIN "
                    f"SELECT RAISE(ABORT, '{text}'); END"
                )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name == "sqlite":
        for tabelle in TRIGGER:
            for aktion in ("update", "delete"):
                op.execute(f"DROP TRIGGER IF EXISTS {tabelle}_kein_{aktion}")
    op.drop_index(op.f('ix_kontierungsregeln_aktiv'), table_name='kontierungsregeln')
    op.drop_table('kontierungsregeln')
    op.drop_index(op.f('ix_kontierungsgruende_regel'), table_name='kontierungsgruende')
    op.drop_index(op.f('ix_kontierungsgruende_buchung_id'), table_name='kontierungsgruende')
    op.drop_table('kontierungsgruende')
