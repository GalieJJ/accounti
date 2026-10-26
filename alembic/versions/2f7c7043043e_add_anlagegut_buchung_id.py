"""add anlagegut buchung_id (Zugangsbuchung eines Anlageguts, Gesamttest Abschluss B11)

Revision ID: 2f7c7043043e
Revises: ddc9a184ddb4
Create Date: 2026-10-23 10:54:52.168879

``anlagen anlegen --buchung`` verknüpft das Anlagegut mit seiner Zugangsbuchung (ein
Bankumsatz direkt auf das Anlagekonto hat keinen Beleg); ``anlagen vorschlaege`` nennt
verknüpfte Buchungen nicht mehr. Hat ein Befehl des neuen Codes die Spalte schon per
``init_db`` angelegt, legt die Migration nur an, was fehlt.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f7c7043043e'
down_revision: Union[str, Sequence[str], None] = 'ddc9a184ddb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = 'ix_anlagegueter_buchung_id'


def _spalten() -> set[str]:
    return {s["name"] for s in sa.inspect(op.get_bind()).get_columns('anlagegueter')}


def _indizes() -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes('anlagegueter')}


def upgrade() -> None:
    """Upgrade schema."""
    if 'buchung_id' not in _spalten():
        op.add_column(
            'anlagegueter', sa.Column('buchung_id', sa.String(length=36), nullable=True)
        )
    if INDEX not in _indizes():
        op.create_index(op.f(INDEX), 'anlagegueter', ['buchung_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('anlagegueter') as batch_op:
        batch_op.drop_index(batch_op.f(INDEX))
        batch_op.drop_column('buchung_id')
