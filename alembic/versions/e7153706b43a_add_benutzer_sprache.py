"""add benutzer sprache (Baustein 10b: Sprache der Oberfläche je Benutzer)

Revision ID: e7153706b43a
Revises: d5a849692843
Create Date: 2026-10-21 23:58:11.000000

``auth_benutzer`` liegt wegen der gemeinsamen Metadaten in jeder Datenbank (System-
und Gesellschaftsdatenbank) — die Migration läuft gegen jede. ``NULL`` heißt
„automatisch“ (Sprache des Browsers). Ohne die Spalte startet ``accounti serve`` nicht
(Schemaprüfung der Systemdatenbank). Ist die Spalte schon da, bleibt sie.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7153706b43a'
down_revision: Union[str, Sequence[str], None] = 'd5a849692843'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _spalten(tabelle: str) -> set[str]:
    return {s["name"] for s in sa.inspect(op.get_bind()).get_columns(tabelle)}


def upgrade() -> None:
    """Upgrade schema."""
    if 'sprache' not in _spalten('auth_benutzer'):
        with op.batch_alter_table('auth_benutzer') as batch_op:
            batch_op.add_column(sa.Column('sprache', sa.String(length=5), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('auth_benutzer') as batch_op:
        batch_op.drop_column('sprache')
