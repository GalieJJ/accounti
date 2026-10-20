"""Repository des Jahresabschlusses (Baustein 12)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.tabellen_abschluss import KontoauszugssaldoRow
from accounti.models.abschluss import Kontoauszugssaldo


def speichere_kontoauszugssaldo(session: Session, k: Kontoauszugssaldo) -> None:
    session.add(
        KontoauszugssaldoRow(
            id=str(k.id),
            bankkonto_id=str(k.bankkonto_id),
            stichtag=k.stichtag,
            saldo=k.saldo,
            erfasst_am=k.erfasst_am,
            erfasst_von=k.erfasst_von,
        )
    )
    session.flush()


def kontoauszugssaldo(
    session: Session, bankkonto_id: UUID, stichtag: date
) -> Kontoauszugssaldo | None:
    """Der zuletzt erfasste Saldo des Kontos zum Stichtag."""
    row = (
        session.query(KontoauszugssaldoRow)
        .filter_by(bankkonto_id=str(bankkonto_id), stichtag=stichtag)
        .order_by(KontoauszugssaldoRow.erfasst_am.desc())
        .first()
    )
    if row is None:
        return None
    return Kontoauszugssaldo(
        id=UUID(row.id),
        bankkonto_id=UUID(row.bankkonto_id),
        stichtag=row.stichtag,
        saldo=Decimal(str(row.saldo)),
        erfasst_am=row.erfasst_am,
        erfasst_von=row.erfasst_von,
    )
