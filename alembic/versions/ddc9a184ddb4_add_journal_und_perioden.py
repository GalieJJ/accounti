"""add journal und perioden (Baustein 7: Journal, Buchungskorrekturen, Monatsabschlüsse, Storno-Spalten)

Revision ID: ddc9a184ddb4
Revises: a684d10751de
Create Date: 2026-10-21 17:30:51.469236

Nach dem Upgrade einer Datenbank mit Bestand einmal ``accounti journal uebernehmen`` —
sonst meldet ``journal pruefen`` ältere Buchungen, Belege und Sperren ohne Eintrag.

Hat ein Befehl des neuen Codes die Tabellen schon angelegt (``init_db`` vor der
Migration, oder eine Sicherung wurde in eine mit ``init_db`` angelegte Datenbank
zurückgespielt), übernimmt die Migration sie und legt nur an, was fehlt.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ddc9a184ddb4'
down_revision: Union[str, Sequence[str], None] = 'a684d10751de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# nur anfügen — SQLite sperrt auch rohes SQL (wie after_create in tabellen_pruefung.py)
TRIGGER = {
    "journal": "Journal ist unveränderbar",
    "buchungskorrekturen": "Buchungskorrekturen sind unveränderbar",
}


def _tabellen() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _spalten(tabelle: str) -> set[str]:
    return {s["name"] for s in sa.inspect(op.get_bind()).get_columns(tabelle)}


def _indizes(tabelle: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(tabelle)}


def upgrade() -> None:
    """Upgrade schema."""
    vorhanden = _tabellen()
    if 'buchungskorrekturen' not in vorhanden:
        op.create_table('buchungskorrekturen',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('original_id', sa.String(length=36), nullable=False),
        sa.Column('storno_id', sa.String(length=36), nullable=False),
        sa.Column('neubuchung_id', sa.String(length=36), nullable=True),
        sa.Column('datum', sa.Date(), nullable=False),
        sa.Column('grund', sa.String(length=500), nullable=False),
        sa.Column('person', sa.String(length=100), nullable=False),
        sa.Column('zeitpunkt', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('original_id'),
        sa.UniqueConstraint('storno_id')
        )
    if 'journal' not in vorhanden:
        op.create_table('journal',
        sa.Column('nr', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('zeitpunkt', sa.DateTime(), nullable=False),
        sa.Column('person', sa.String(length=100), nullable=False),
        sa.Column('vorgang', sa.String(length=40), nullable=False),
        sa.Column('objekt_typ', sa.String(length=30), nullable=False),
        sa.Column('objekt_id', sa.String(length=64), nullable=False),
        sa.Column('vorher', sa.Text(), nullable=True),
        sa.Column('nachher', sa.Text(), nullable=True),
        sa.Column('grund', sa.String(length=500), nullable=True),
        sa.Column('bezug', sa.String(length=100), nullable=True),
        sa.Column('vorgaenger_hash', sa.String(length=64), nullable=False),
        sa.Column('hash', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('nr'),
        sa.UniqueConstraint('hash')
        )
    journal_indizes = _indizes('journal')
    if 'ix_journal_objekt' not in journal_indizes:
        op.create_index('ix_journal_objekt', 'journal', ['objekt_typ', 'objekt_id'], unique=False)
    if 'ix_journal_vorgang' not in journal_indizes:
        op.create_index(op.f('ix_journal_vorgang'), 'journal', ['vorgang'], unique=False)
    if 'periodenabschluesse' not in vorhanden:
        op.create_table('periodenabschluesse',
        sa.Column('monat', sa.String(length=7), nullable=False),
        sa.Column('gesperrt', sa.Boolean(), nullable=False),
        sa.Column('geschlossen_am', sa.DateTime(), nullable=False),
        sa.Column('geschlossen_von', sa.String(length=100), nullable=False),
        sa.Column('geoeffnet_am', sa.DateTime(), nullable=True),
        sa.Column('geoeffnet_von', sa.String(length=100), nullable=True),
        sa.Column('grund', sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint('monat')
        )
    # Storno statt Änderung: eindeutig je Richtung — als benannte Unique-Indizes (eine
    # unbenannte Unique-Constraint lässt sich im Batch-Modus von SQLite nicht anlegen)
    spalten = _spalten('buchungssaetze')
    indizes = _indizes('buchungssaetze')
    with op.batch_alter_table('buchungssaetze') as batch_op:
        for spalte in ('storniert_durch', 'storno_von'):
            if spalte not in spalten:
                batch_op.add_column(sa.Column(spalte, sa.String(length=36), nullable=True))
        for spalte in ('storniert_durch', 'storno_von'):
            name = f'ix_buchungssaetze_{spalte}'
            if name not in indizes:
                batch_op.create_index(batch_op.f(name), [spalte], unique=True)
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
    with op.batch_alter_table('buchungssaetze') as batch_op:
        batch_op.drop_index(batch_op.f('ix_buchungssaetze_storno_von'))
        batch_op.drop_index(batch_op.f('ix_buchungssaetze_storniert_durch'))
        batch_op.drop_column('storno_von')
        batch_op.drop_column('storniert_durch')
    op.drop_table('periodenabschluesse')
    op.drop_index(op.f('ix_journal_vorgang'), table_name='journal')
    op.drop_index('ix_journal_objekt', table_name='journal')
    op.drop_table('journal')
    op.drop_table('buchungskorrekturen')
