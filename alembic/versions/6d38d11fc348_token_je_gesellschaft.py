"""token je gesellschaft (Gesamttest Betrieb B9: Token-Name eindeutig je Gesellschaft)

Revision ID: 6d38d11fc348
Revises: ddc9a184ddb4
Create Date: 2026-10-26 09:48:21.415779

Der Index ``uq_api_token_aktiv`` (nur aktive Token) lag auf ``name`` allein — ein Token
„erp“ in a verhinderte eines in b. Jetzt auf ``(gesellschaft, name)``.

Hat ``init_db`` des neuen Codes ``api_tokens`` schon angelegt (Datenbank ohne
Benutzertabellen vor der Migration), steht der neue Index bereits — dann nichts tun.
Das Downgrade scheitert, wenn zwei Gesellschaften aktive Token gleichen Namens haben:
erst eines widerrufen. Es prüft das vor dem Löschen des Index — SQLite führt DDL hier
ohne Transaktion aus, ein Abbruch danach ließe die Tabelle ohne Index zurück
(Nachprüfung N3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d38d11fc348'
down_revision: Union[str, Sequence[str], None] = 'ddc9a184ddb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = 'uq_api_token_aktiv'
NUR_AKTIVE = {
    'sqlite_where': sa.text('widerrufen_am IS NULL'),
    'postgresql_where': sa.text('widerrufen_am IS NULL'),
}


def _spalten() -> list[str] | None:
    for index in sa.inspect(op.get_bind()).get_indexes('api_tokens'):
        if index['name'] == INDEX:
            return [str(s) for s in index['column_names']]
    return None


def _neu_anlegen(spalten: list[str]) -> None:
    if _spalten() == spalten:
        return
    if _spalten() is not None:
        op.drop_index(INDEX, table_name='api_tokens')
    op.create_index(INDEX, 'api_tokens', spalten, unique=True, **NUR_AKTIVE)


def upgrade() -> None:
    """Upgrade schema."""
    _neu_anlegen(['gesellschaft', 'name'])


def downgrade() -> None:
    """Downgrade schema."""
    doppelt = [
        str(name)
        for (name,) in op.get_bind().execute(
            sa.text(
                'SELECT name FROM api_tokens WHERE widerrufen_am IS NULL '
                'GROUP BY name HAVING COUNT(*) > 1 ORDER BY name'
            )
        )
    ]
    if doppelt:
        raise RuntimeError(
            'Downgrade abgebrochen: aktive Token gleichen Namens in mehreren '
            f'Gesellschaften ({", ".join(doppelt)}) — erst widerrufen, bis jeder '
            'Name nur einmal aktiv ist; nichts geändert'
        )
    _neu_anlegen(['name'])
