"""add einstellungen (Baustein 10c P4a: Einstellungen in der Datenbank)

Revision ID: 83dfa5750c7f
Revises: 1dd2f6b7c6c8
Create Date: 2026-11-04 11:00:00.000000

Drei Tabellen: ``einstellungen`` (Versionen je Abschnitt, nur anfügen, Hash-Kette),
``einstellungsantraege`` (Anträge auf eine Lockerung, K3) und ``geheimnisse``
(Chiffrate). ``einstellungen`` lehnt Ändern und Löschen auch für rohes SQL ab — unter
SQLite per Trigger (UPDATE, DELETE und ein INSERT, das eine vorhandene Zeile ersetzen
würde: REPLACE INTO / INSERT OR REPLACE), unter PostgreSQL über die Funktion
``accounti_nur_anfuegen()`` mit Triggern für UPDATE/DELETE je Zeile und TRUNCATE
(``db/schutz.py``, dieselben Anweisungen wie ``after_create``, wiederholbar).

Hat ein Befehl des neuen Codes die Tabellen schon angelegt (``init_db`` vor der
Migration), übernimmt die Migration sie und legt nur an, was fehlt. Sie läuft gegen jede
Datenbank — System- und Gesellschaftsdatenbank teilen die Kette, die Systemdatenbank
bekommt die Tabellen leer.

Das Downgrade geht nur, solange alle drei Tabellen leer sind: Die Versionen sind
Organisationsunterlagen (§ 147 AO). Es prüft das, bevor es etwas löscht.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from accounti.db.schutz import FUNKTION, entferne_sql, nur_anfuegen_sql


# revision identifiers, used by Alembic.
revision: str = '83dfa5750c7f'
down_revision: Union[str, Sequence[str], None] = '1dd2f6b7c6c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELLEN = ('einstellungen', 'einstellungsantraege', 'geheimnisse')
# Text der Trigger (wie tabellen_einstellungen.TRIGGER_TEXT)
TRIGGER_TEXT = 'Die Einstellungsversion'
# eindeutige Schlüssel für den SQLite-Trigger gegen REPLACE (wie
# tabellen_einstellungen.EINDEUTIG)
EINDEUTIG = (('id',), ('abschnitt', 'version'), ('hash',))


def _tabellen() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indizes(tabelle: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(tabelle)}


def upgrade() -> None:
    """Upgrade schema."""
    vorhanden = _tabellen()
    if 'einstellungen' not in vorhanden:
        op.create_table('einstellungen',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('abschnitt', sa.String(length=40), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('daten', sa.Text(), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column('vollstaendig', sa.Boolean(), nullable=False),
        sa.Column('fehlend', sa.Text(), nullable=False),
        sa.Column('person', sa.String(length=100), nullable=False),
        sa.Column('grund', sa.String(length=500), nullable=False),
        sa.Column('quelle', sa.String(length=20), nullable=False),
        sa.Column('antrag_id', sa.Integer(), nullable=True),
        sa.Column('datei_hash', sa.String(length=64), nullable=True),
        sa.Column('erstellt_am', sa.DateTime(), nullable=False),
        sa.Column('hash', sa.String(length=64), nullable=False),
        sa.Column('vorgaenger_hash', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('abschnitt', 'version', name='uq_einstellungen_version'),
        sa.UniqueConstraint('hash')
        )
    if 'ix_einstellungen_abschnitt' not in _indizes('einstellungen'):
        op.create_index(op.f('ix_einstellungen_abschnitt'), 'einstellungen', ['abschnitt'], unique=False)
    if 'einstellungsantraege' not in vorhanden:
        op.create_table('einstellungsantraege',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('aenderungen', sa.Text(), nullable=False),
        sa.Column('inhalt_hash', sa.String(length=64), nullable=False),
        sa.Column('grund', sa.String(length=500), nullable=False),
        sa.Column('antragsteller', sa.String(length=100), nullable=False),
        sa.Column('erstellt_am', sa.DateTime(), nullable=False),
        sa.Column('gueltig_bis', sa.DateTime(), nullable=False),
        sa.Column('kontrolle', sa.String(length=40), nullable=False),
        sa.Column('recht', sa.String(length=40), nullable=False),
        sa.Column('felder', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('entschieden_von', sa.String(length=100), nullable=True),
        sa.Column('entschieden_am', sa.DateTime(), nullable=True),
        sa.Column('entscheidungsgrund', sa.String(length=500), nullable=True),
        sa.Column('versionen', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
    if 'ix_einstellungsantraege_status' not in _indizes('einstellungsantraege'):
        op.create_index(op.f('ix_einstellungsantraege_status'), 'einstellungsantraege', ['status'], unique=False)
    if 'geheimnisse' not in vorhanden:
        op.create_table('geheimnisse',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('chiffrat', sa.Text(), nullable=False),
        sa.Column('gesetzt_am', sa.DateTime(), nullable=False),
        sa.Column('gesetzt_von', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
        )
    for sql in nur_anfuegen_sql(
        'einstellungen', TRIGGER_TEXT, op.get_bind().dialect.name, eindeutig=EINDEUTIG
    ):
        op.execute(sql)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    mit_zeilen = [
        tabelle
        for tabelle in TABELLEN
        if bind.execute(sa.text(f'SELECT count(*) FROM {tabelle}')).scalar()
    ]
    if mit_zeilen:
        raise RuntimeError(
            'Downgrade abgebrochen: Einstellungen in der Datenbank '
            f'({", ".join(mit_zeilen)}) — Versionen, Anträge und Geheimnisse sind '
            'Organisationsunterlagen (§ 147 AO) und gingen verloren; vorher '
            'accounti sicherung erstellen, danach nur in einer leeren Datenbank '
            'zurückgehen; nichts geändert'
        )
    for sql in entferne_sql('einstellungen', bind.dialect.name):
        op.execute(sql)
    op.drop_table('geheimnisse')
    op.drop_index(op.f('ix_einstellungsantraege_status'), table_name='einstellungsantraege')
    op.drop_table('einstellungsantraege')
    op.drop_index(op.f('ix_einstellungen_abschnitt'), table_name='einstellungen')
    op.drop_table('einstellungen')
    if bind.dialect.name == 'postgresql':
        # die Funktion nur entfernen, wenn kein anderer Trigger sie nutzt
        genutzt = bind.execute(
            sa.text(
                'SELECT count(*) FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid '
                'WHERE p.proname = :name'
            ),
            {'name': FUNKTION},
        ).scalar()
        if not genutzt:
            op.execute(f'DROP FUNCTION IF EXISTS {FUNKTION}()')
