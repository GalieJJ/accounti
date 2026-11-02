"""add steuerkennzeichen to belege (Gesamttest Paket C: Steuerfall ohne Steuerausweis)

Revision ID: 46371a6681c2
Revises: a14acef69fae
Create Date: 2026-10-23 10:56:12.325030

``belege.steuerkennzeichen`` hält den Steuerfall einer Rechnung ohne Steuerausweis
(UNTDID 5305: AE § 13b UStG, K ig. Lieferung, E steuerfrei bzw. Kleinunternehmer) — aus
dem Hinweistext des Belegs, der E-Rechnung oder ``accounti belege freigeben --steuer``.

Hat ein Befehl des neuen Codes die Spalte schon angelegt (``init_db`` vor der
Migration), übernimmt die Migration sie. Sie berührt nur diese eine Spalte und setzt
nichts von Nachbar-Revisionen voraus — ihre Stelle in der Kette darf sich ändern.
Ohne Versionsvermerk erkennt ``accounti db upgrade`` den Stand davor an der fehlenden
Spalte (``init_db`` ergänzt keine Spalten an alten Tabellen).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46371a6681c2'
down_revision: Union[str, Sequence[str], None] = 'a14acef69fae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _spalten(tabelle: str) -> set[str]:
    return {s["name"] for s in sa.inspect(op.get_bind()).get_columns(tabelle)}


def upgrade() -> None:
    """Upgrade schema."""
    if 'steuerkennzeichen' not in _spalten('belege'):
        op.add_column(
            'belege',
            sa.Column('steuerkennzeichen', sa.String(length=10), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('belege') as tabelle:
        tabelle.drop_column('steuerkennzeichen')
