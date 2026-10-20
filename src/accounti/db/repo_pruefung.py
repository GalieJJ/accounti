"""Repository der Belegvollständigkeit & Ordnungsmäßigkeit (Baustein 7)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from accounti.db.tabellen import BuchungssatzRow
from accounti.db.tabellen_pruefung import BuchungskorrekturRow
from accounti.models.pruefung import Buchungskorrektur


def setze_storniert_durch(session: Session, buchung_id: UUID, storno_id: UUID) -> None:
    """Der Stornovermerk am Original — die einzige Änderung, die es noch annimmt."""
    zeile = session.get(BuchungssatzRow, str(buchung_id))
    if zeile is None:
        raise ValueError(f"Buchung {buchung_id} nicht gefunden")
    zeile.storniert_durch = str(storno_id)
    session.flush()


def speichere_korrektur(session: Session, k: Buchungskorrektur) -> None:
    session.add(
        BuchungskorrekturRow(
            id=str(k.id),
            original_id=str(k.original_id),
            storno_id=str(k.storno_id),
            neubuchung_id=str(k.neubuchung_id) if k.neubuchung_id else None,
            datum=k.datum,
            grund=k.grund[:500],
            person=k.person[:100],
            zeitpunkt=k.zeitpunkt,
        )
    )
    session.flush()


def _korrektur(r: BuchungskorrekturRow) -> Buchungskorrektur:
    return Buchungskorrektur(
        id=UUID(r.id),
        original_id=UUID(r.original_id),
        storno_id=UUID(r.storno_id),
        neubuchung_id=UUID(r.neubuchung_id) if r.neubuchung_id else None,
        datum=r.datum,
        grund=r.grund,
        person=r.person,
        zeitpunkt=r.zeitpunkt,
    )


def lade_korrekturen(session: Session) -> list[Buchungskorrektur]:
    rows = session.query(BuchungskorrekturRow).order_by(BuchungskorrekturRow.zeitpunkt)
    return [_korrektur(r) for r in rows.all()]


def korrektur_zu(session: Session, buchung_id: UUID) -> Buchungskorrektur | None:
    """Korrektur, an der die Buchung beteiligt ist (Original, Storno, Neubuchung)."""
    ident = str(buchung_id)
    r = (
        session.query(BuchungskorrekturRow)
        .filter(
            or_(
                BuchungskorrekturRow.original_id == ident,
                BuchungskorrekturRow.storno_id == ident,
                BuchungskorrekturRow.neubuchung_id == ident,
            )
        )
        .first()
    )
    return _korrektur(r) if r is not None else None
