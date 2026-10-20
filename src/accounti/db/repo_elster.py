"""Repository der Steuermeldungen: Freigaben und Übermittlungsprotokoll."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.tabellen import BelegRow
from accounti.db.tabellen_elster import (
    SteuermeldungFreigabeRow,
    SteuermeldungProtokollRow,
)
from accounti.models.elster import Freigabe, Meldeart, Modus, Uebermittlung


def speichere_freigabe(session: Session, f: Freigabe) -> None:
    werte = f.model_dump()
    werte.update(id=str(f.id), art=f.art.value)
    session.add(SteuermeldungFreigabeRow(**werte))
    session.flush()


def lade_freigaben(
    session: Session, art: Meldeart | None = None, zeitraum: str | None = None
) -> list[Freigabe]:
    query = session.query(SteuermeldungFreigabeRow).order_by(
        SteuermeldungFreigabeRow.zeitpunkt
    )
    if art is not None:
        query = query.filter(SteuermeldungFreigabeRow.art == art.value)
    if zeitraum is not None:
        query = query.filter(SteuermeldungFreigabeRow.zeitraum == zeitraum)
    return [
        Freigabe.model_validate({f: getattr(r, f) for f in Freigabe.model_fields})
        for r in query.all()
    ]


def _row_zu_uebermittlung(r: SteuermeldungProtokollRow) -> Uebermittlung:
    return Uebermittlung.model_validate(
        {feld: getattr(r, feld) for feld in Uebermittlung.model_fields}
    )


def speichere_uebermittlung(session: Session, u: Uebermittlung) -> None:
    werte = u.model_dump()
    werte.update(
        id=str(u.id),
        art=u.art.value,
        modus=u.modus.value,
        freigabe_id=str(u.freigabe_id) if u.freigabe_id else None,
    )
    session.add(SteuermeldungProtokollRow(**werte))
    session.flush()


def lade_uebermittlungen(
    session: Session,
    art: Meldeart | None = None,
    zeitraum: str | None = None,
    modus: Modus | None = None,
) -> list[Uebermittlung]:
    query = session.query(SteuermeldungProtokollRow).order_by(
        SteuermeldungProtokollRow.nr
    )
    if art is not None:
        query = query.filter(SteuermeldungProtokollRow.art == art.value)
    if zeitraum is not None:
        query = query.filter(SteuermeldungProtokollRow.zeitraum == zeitraum)
    if modus is not None:
        query = query.filter(SteuermeldungProtokollRow.modus == modus.value)
    return [_row_zu_uebermittlung(r) for r in query.all()]


def letzte_uebermittlung(session: Session) -> Uebermittlung | None:
    r = (
        session.query(SteuermeldungProtokollRow)
        .order_by(SteuermeldungProtokollRow.nr.desc())
        .first()
    )
    return _row_zu_uebermittlung(r) if r is not None else None


def lade_beleg_kontakte(session: Session) -> dict[UUID, UUID]:
    """Beleg → Kontakt für alle Belege mit Kontakt (ohne Positionen zu laden)."""
    rows = (
        session.query(BelegRow.id, BelegRow.kontakt_id)
        .filter(BelegRow.kontakt_id.is_not(None))
        .all()
    )
    return {UUID(beleg): UUID(kontakt) for beleg, kontakt in rows}
