"""add verrechnungen und rechnungskorrektur (Gesamttest Debitoren)

Revision ID: a14acef69fae
Revises: ddc9a184ddb4
Create Date: 2026-10-26 09:34:30.297540

Tabelle ``verrechnungen`` (Ausgleich gegenläufiger offener Posten ohne Buchung, nur
anfügen). Hat ein Befehl des neuen Codes die Tabelle schon angelegt (``init_db`` vor der
Migration), übernimmt die Migration sie und legt nur an, was fehlt.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a14acef69fae'
down_revision: Union[str, Sequence[str], None] = 'ddc9a184ddb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDIZES = ("gegen_posten_id", "kontakt_id", "posten_id")


def _tabellen() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


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


def downgrade() -> None:
    """Downgrade schema."""
    for spalte in reversed(INDIZES):
        op.drop_index(f'ix_verrechnungen_{spalte}', table_name='verrechnungen')
    op.drop_table('verrechnungen')
