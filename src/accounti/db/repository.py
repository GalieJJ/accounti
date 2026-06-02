"""Mapping zwischen Domänen- (Pydantic) und Persistenz- (ORM) Modellen."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.tabellen import TransaktionRow
from accounti.models import Transaktion, TransaktionQuelle


def speichere_transaktion(session: Session, tx: Transaktion) -> None:
    session.add(
        TransaktionRow(
            id=str(tx.id),
            datum=tx.datum,
            betrag=tx.betrag,
            waehrung=tx.waehrung,
            verwendungszweck=tx.verwendungszweck,
            gegenkonto_name=tx.gegenkonto_name,
            gegenkonto_iban=tx.gegenkonto_iban,
            quelle=tx.quelle.value,
            rohtext=tx.rohtext,
        )
    )


def lade_transaktionen(session: Session) -> list[Transaktion]:
    rows = session.query(TransaktionRow).all()
    return [
        Transaktion(
            id=UUID(r.id),
            datum=r.datum,
            betrag=Decimal(str(r.betrag)),
            waehrung=r.waehrung,
            verwendungszweck=r.verwendungszweck,
            gegenkonto_name=r.gegenkonto_name,
            gegenkonto_iban=r.gegenkonto_iban,
            quelle=TransaktionQuelle(r.quelle),
            rohtext=r.rohtext,
        )
        for r in rows
    ]
