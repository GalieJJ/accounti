"""Repository für festgeschriebene Kontoauszüge (Baustein 11).

Es gibt bewusst kein Ändern und kein Löschen: Ein Auszug wird einmal geschrieben.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounti.db.tabellen_export import KontoauszugRow, KontoauszugUmsatzRow
from accounti.models.export import Kontoauszug


def speichere_kontoauszug(session: Session, a: Kontoauszug) -> None:
    nachtraege = set(a.nachtraege)
    session.add(
        KontoauszugRow(
            id=str(a.id),
            finanzkonto=a.finanzkonto,
            jahr=a.jahr,
            nummer=a.nummer,
            von=a.von,
            bis=a.bis,
            waehrung=a.waehrung,
            anfangssaldo=a.anfangssaldo,
            endsaldo=a.endsaldo,
            kontrollsaldo=a.kontrollsaldo,
            erstellt_am=a.erstellt_am,
            vorgaenger_hash=a.vorgaenger_hash,
            hash=a.hash,
        )
    )
    for position, tx_id in enumerate(a.umsaetze, start=1):
        session.add(
            KontoauszugUmsatzRow(
                auszug_id=str(a.id),
                transaktion_id=str(tx_id),
                position=position,
                nachtrag=tx_id in nachtraege,
            )
        )
    session.flush()


def _dec(wert: Decimal | None) -> Decimal | None:
    return Decimal(str(wert)) if wert is not None else None


def lade_kontoauszuege(
    session: Session, finanzkonto: str | None = None
) -> list[Kontoauszug]:
    """Auszüge nach Finanzkonto und Zeitraum sortiert, mit ihren Umsätzen."""
    abfrage = select(KontoauszugRow)
    if finanzkonto is not None:
        abfrage = abfrage.where(KontoauszugRow.finanzkonto == finanzkonto)
    zeilen = session.scalars(
        abfrage.order_by(KontoauszugRow.finanzkonto, KontoauszugRow.von)
    ).all()
    umsaetze: dict[str, list[KontoauszugUmsatzRow]] = defaultdict(list)
    if zeilen:
        for u in session.scalars(
            select(KontoauszugUmsatzRow)
            .where(KontoauszugUmsatzRow.auszug_id.in_([z.id for z in zeilen]))
            .order_by(KontoauszugUmsatzRow.position)
        ):
            umsaetze[u.auszug_id].append(u)
    return [
        Kontoauszug(
            id=UUID(z.id),
            finanzkonto=z.finanzkonto,
            jahr=z.jahr,
            nummer=z.nummer,
            von=z.von,
            bis=z.bis,
            waehrung=z.waehrung,
            anfangssaldo=Decimal(str(z.anfangssaldo)),
            endsaldo=Decimal(str(z.endsaldo)),
            umsaetze=[UUID(u.transaktion_id) for u in umsaetze[z.id]],
            nachtraege=[UUID(u.transaktion_id) for u in umsaetze[z.id] if u.nachtrag],
            kontrollsaldo=_dec(z.kontrollsaldo),
            erstellt_am=z.erstellt_am,
            vorgaenger_hash=z.vorgaenger_hash,
            hash=z.hash,
        )
        for z in zeilen
    ]


def zugeordnete_transaktion_ids(session: Session) -> set[UUID]:
    """Transaktionen, die schon in einem Kontoauszug stehen."""
    return {
        UUID(t) for t in session.scalars(select(KontoauszugUmsatzRow.transaktion_id))
    }
