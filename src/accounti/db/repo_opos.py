"""Persistenz rund um offene Posten: Suche nach Belegnummer, Verrechnungen."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repository import lade_einen_posten
from accounti.db.tabellen import OffenerPostenRow, VerrechnungRow
from accounti.models import OffenerPosten, Verrechnung


def finde_posten(session: Session, schluessel: str) -> OffenerPosten:
    """Posten über die Belegnummer oder den Anfang seiner ID — eindeutig oder Fehler."""
    zeilen = (
        session.query(OffenerPostenRow.id)
        .filter(OffenerPostenRow.belegnummer == schluessel)
        .all()
    ) or (
        session.query(OffenerPostenRow.id)
        .filter(OffenerPostenRow.id.like(f"{schluessel}%"))
        .all()
    )
    if not zeilen:
        msg = f"Kein offener Posten mit Belegnummer oder ID '{schluessel}'."
        raise ValueError(msg)
    if len(zeilen) > 1:
        msg = (
            f"'{schluessel}' ist mehrdeutig ({len(zeilen)} Posten) — die ID des "
            "Postens angeben (accounti opos liste)"
        )
        raise ValueError(msg)
    return lade_einen_posten(session, UUID(zeilen[0][0]))


def _row_zu_verrechnung(r: VerrechnungRow) -> Verrechnung:
    return Verrechnung(
        id=UUID(r.id),
        kontakt_id=UUID(r.kontakt_id),
        posten_id=UUID(r.posten_id),
        gegen_posten_id=UUID(r.gegen_posten_id),
        betrag=Decimal(str(r.betrag)),
        datum=r.datum,
        person=r.person,
        grund=r.grund,
        erstellt_am=r.erstellt_am,
    )


def speichere_verrechnung(session: Session, v: Verrechnung) -> None:
    session.add(
        VerrechnungRow(
            id=str(v.id),
            kontakt_id=str(v.kontakt_id),
            posten_id=str(v.posten_id),
            gegen_posten_id=str(v.gegen_posten_id),
            betrag=v.betrag,
            datum=v.datum,
            person=v.person[:100] if v.person else None,
            grund=v.grund[:500] if v.grund else None,
            erstellt_am=v.erstellt_am,
        )
    )
    session.flush()


def lade_verrechnungen(session: Session) -> list[Verrechnung]:
    zeilen = session.query(VerrechnungRow).order_by(
        VerrechnungRow.datum, VerrechnungRow.erstellt_am
    )
    return [_row_zu_verrechnung(r) for r in zeilen.all()]
