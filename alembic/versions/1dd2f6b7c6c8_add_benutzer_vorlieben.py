"""add benutzer vorlieben (Baustein 10c P1: Anzeige-Vorlieben je Benutzer)

Revision ID: 1dd2f6b7c6c8
Revises: e7153706b43a
Create Date: 2026-11-03 21:30:00.000000

``auth_benutzer`` bekommt Darstellung (``auto``/``hell``/``dunkel``), Fachansicht,
„Beträge verbergen“ und Tastenkürzel — jede Spalte ``NOT NULL`` mit Server-Standard,
damit bestehende Benutzer gültig sind (automatisch, aus, aus, an). ``auth_benutzer``
liegt wegen der gemeinsamen Metadaten in jeder Datenbank (System- und
Gesellschaftsdatenbank); die Migration läuft gegen jede, die Systemdatenbank zuerst
(ohne die Spalten startet ``accounti serve`` nicht). Spalten, die es schon gibt (etwa
von einem Vorabstand), bleiben.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1dd2f6b7c6c8'
down_revision: Union[str, Sequence[str], None] = 'e7153706b43a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAMEN = ('darstellung', 'fachansicht', 'betraege_verbergen', 'tastenkuerzel')


def _neue_spalten() -> list[sa.Column]:
    return [
        sa.Column(
            'darstellung', sa.String(length=6), nullable=False, server_default='auto'
        ),
        sa.Column('fachansicht', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            'betraege_verbergen', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column('tastenkuerzel', sa.Boolean(), nullable=False, server_default=sa.true()),
    ]


def _spalten(tabelle: str) -> set[str]:
    return {s["name"] for s in sa.inspect(op.get_bind()).get_columns(tabelle)}


def upgrade() -> None:
    """Upgrade schema."""
    vorhanden = _spalten('auth_benutzer')
    fehlt = [s for s in _neue_spalten() if s.name not in vorhanden]
    if fehlt:
        with op.batch_alter_table('auth_benutzer') as batch_op:
            for spalte in fehlt:
                batch_op.add_column(spalte)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('auth_benutzer') as batch_op:
        for name in reversed(NAMEN):
            batch_op.drop_column(name)
