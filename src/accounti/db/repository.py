"""Mapping zwischen Domänen- (Pydantic) und Persistenz- (ORM) Modellen."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.tabellen import BuchungssatzRow, TransaktionRow
from accounti.models import (
    Buchungssatz,
    BuchungStatus,
    Transaktion,
    TransaktionQuelle,
)


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


def speichere_buchung(session: Session, b: Buchungssatz) -> None:
    session.add(
        BuchungssatzRow(
            id=str(b.id),
            transaktion_id=str(b.transaktion_id),
            datum=b.datum,
            soll_konto=b.soll_konto,
            haben_konto=b.haben_konto,
            betrag_netto=b.betrag_netto,
            steuer_schluessel=b.steuer_schluessel,
            steuer_betrag=b.steuer_betrag,
            buchungstext=b.buchungstext,
            status=b.status.value,
            confidence=b.confidence,
        )
    )


def lade_buchungen(session: Session) -> list[Buchungssatz]:
    rows = session.query(BuchungssatzRow).all()
    return [
        Buchungssatz(
            id=UUID(r.id),
            transaktion_id=UUID(r.transaktion_id),
            datum=r.datum,
            soll_konto=r.soll_konto,
            haben_konto=r.haben_konto,
            betrag_netto=Decimal(str(r.betrag_netto)),
            steuer_schluessel=r.steuer_schluessel,
            steuer_betrag=(
                Decimal(str(r.steuer_betrag)) if r.steuer_betrag is not None else None
            ),
            buchungstext=r.buchungstext,
            status=BuchungStatus(r.status),
            confidence=r.confidence,
        )
        for r in rows
    ]
