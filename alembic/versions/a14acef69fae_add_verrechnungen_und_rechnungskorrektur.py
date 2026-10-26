"""add verrechnungen und rechnungskorrektur (Gesamttest Debitoren)

Revision ID: a14acef69fae
Revises: 2f7c7043043e
Create Date: 2026-10-26 09:34:30.297540

Tabelle ``verrechnungen`` (Ausgleich gegenläufiger offener Posten ohne Buchung, nur
anfügen); ``ausgangsrechnungen.rechnungstyp``/``korrektur_zu`` (Gutschrift 381,
Rechnungskorrektur 384 mit Bezug BT-25); ``ausgangspositionen.elektronisch`` (§ 3a Abs. 5
UStG). Hat ein Befehl des neuen Codes die Tabelle schon angelegt (``init_db`` vor der
Migration), übernimmt die Migration sie und legt nur an, was fehlt. Auf SQLite sperren
Trigger ``verrechnungen_kein_update``/``_delete`` auch rohes SQL (nur anfügen).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a14acef69fae'
down_revision: Union[str, Sequence[str], None] = '2f7c7043043e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDIZES = ("gegen_posten_id", "kontakt_id", "posten_id")
# nur anfügen — SQLite sperrt auch rohes SQL (wie after_create in db/tabellen.py)
TRIGGER_TEXT = "Verrechnungen sind unveränderbar"


def _tabellen() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _spalten(tabelle: str) -> set[str]:
    return {s["name"] for s in sa.inspect(op.get_bind()).get_columns(tabelle)}


def _indizes(tabelle: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(tabelle)}


def upgrade() -> None:
    """Upgrade schema."""
    if 'verrechnungen' not in _tabellen():
        op.create_table('verrechnungen',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('kontakt_id', sa.String(length=36), nullable=False),
        sa.Column('posten_id', sa.String(length=36), nullable=False),
        sa.Column('gegen_posten_id', sa.String(length=36), nullable=False),
        sa.Column('betrag', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('datum', sa.Date(), nullable=False),
        sa.Column('person', sa.String(length=100), nullable=True),
        sa.Column('grund', sa.String(length=500), nullable=True),
        sa.Column('erstellt_am', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['gegen_posten_id'], ['offene_posten.id'], ),
        sa.ForeignKeyConstraint(['kontakt_id'], ['kontakte.id'], ),
        sa.ForeignKeyConstraint(['posten_id'], ['offene_posten.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    vorhanden = _indizes('verrechnungen')
    for spalte in INDIZES:
        name = f'ix_verrechnungen_{spalte}'
        if name not in vorhanden:
            op.create_index(name, 'verrechnungen', [spalte], unique=False)
    rechnungen = _spalten('ausgangsrechnungen')
    with op.batch_alter_table('ausgangsrechnungen') as batch_op:
        if 'rechnungstyp' not in rechnungen:
            batch_op.add_column(
                sa.Column('rechnungstyp', sa.String(length=3), nullable=True)
            )
        if 'korrektur_zu' not in rechnungen:
            batch_op.add_column(
                sa.Column('korrektur_zu', sa.String(length=40), nullable=True)
            )
    if op.get_bind().dialect.name == "sqlite":
        for aktion in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS verrechnungen_kein_{aktion.lower()} "
                f"BEFORE {aktion} ON verrechnungen BEGIN "
                f"SELECT RAISE(ABORT, '{TRIGGER_TEXT}'); END"
            )
    if 'elektronisch' not in _spalten('ausgangspositionen'):
        with op.batch_alter_table('ausgangspositionen') as batch_op:
            batch_op.add_column(
                sa.Column(
                    'elektronisch',
                    sa.Boolean(),
                    server_default=sa.false(),
                    nullable=False,
                )
            )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ausgangspositionen') as batch_op:
        batch_op.drop_column('elektronisch')
    with op.batch_alter_table('ausgangsrechnungen') as batch_op:
        batch_op.drop_column('korrektur_zu')
        batch_op.drop_column('rechnungstyp')
    if op.get_bind().dialect.name == "sqlite":
        for aktion in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS verrechnungen_kein_{aktion}")
    for spalte in reversed(INDIZES):
        op.drop_index(f'ix_verrechnungen_{spalte}', table_name='verrechnungen')
    op.drop_table('verrechnungen')
