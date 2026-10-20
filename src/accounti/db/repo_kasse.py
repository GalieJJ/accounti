"""Repository des Kassenbuchs (Baustein 12)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from accounti.db.tabellen_kasse import KassenvorgangRow
from accounti.models.kasse import Kassenart, Kassenvorgang


def _row_zu_vorgang(r: KassenvorgangRow) -> Kassenvorgang:
    return Kassenvorgang(
        id=UUID(r.id),
        nr=r.nr,
        datum=r.datum,
        betrag=Decimal(str(r.betrag)),
        art=Kassenart(r.art),
        text=r.text,
        belegnummer=r.belegnummer,
        gegenkonto=r.gegenkonto,
        steuersatz=Decimal(str(r.steuersatz)) if r.steuersatz is not None else None,
        transaktion_id=UUID(r.transaktion_id) if r.transaktion_id else None,
        buchung_id=UUID(r.buchung_id) if r.buchung_id else None,
        storno_von=r.storno_von,
        erfasst_am=r.erfasst_am,
        erfasst_von=r.erfasst_von,
    )


def naechste_kassennummer(session: Session) -> int:
    return int(session.query(func.max(KassenvorgangRow.nr)).scalar() or 0) + 1


def speichere_kassenvorgang(session: Session, v: Kassenvorgang) -> None:
    session.add(
        KassenvorgangRow(
            id=str(v.id),
            nr=v.nr,
            datum=v.datum,
            betrag=v.betrag,
            art=v.art.value,
            text=v.text[:200],
            belegnummer=v.belegnummer[:60] if v.belegnummer else None,
            gegenkonto=v.gegenkonto,
            steuersatz=v.steuersatz,
            transaktion_id=str(v.transaktion_id) if v.transaktion_id else None,
            buchung_id=str(v.buchung_id) if v.buchung_id else None,
            storno_von=v.storno_von,
            erfasst_am=v.erfasst_am,
            erfasst_von=v.erfasst_von[:50] if v.erfasst_von else None,
        )
    )
    session.flush()


def lade_kassenbuch(session: Session) -> list[Kassenvorgang]:
    rows = session.query(KassenvorgangRow).order_by(KassenvorgangRow.nr).all()
    return [_row_zu_vorgang(r) for r in rows]
