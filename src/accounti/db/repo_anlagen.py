"""Repository der Anlagenbuchhaltung (Baustein 12)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from accounti.db.tabellen import BuchungssatzRow
from accounti.db.tabellen_anlagen import AfaVorgangRow, AnlagegutRow
from accounti.models.anlagen import AbgangArt, AfaArt, AfaVorgang, Anlagegut

_FELDER = (
    "bezeichnung",
    "konto",
    "afa_konto",
    "anschaffungsdatum",
    "anschaffungskosten",
    "nutzungsdauer",
    "wechsel_linear",
    "immateriell",
    "typ",
    "abgang_datum",
    "abgang_erloes",
    "notiz",
    "erstellt_am",
)


def _row_zu_anlage(r: AnlagegutRow) -> Anlagegut:
    werte: dict[str, Any] = {feld: getattr(r, feld) for feld in _FELDER}
    for feld in ("anschaffungskosten", "abgang_erloes"):
        if werte[feld] is not None:
            werte[feld] = Decimal(str(werte[feld]))
    return Anlagegut.model_validate(
        {
            **werte,
            "id": UUID(r.id),
            "nr": r.nr,
            "afa_art": AfaArt(r.afa_art),
            "beleg_id": UUID(r.beleg_id) if r.beleg_id else None,
            "buchung_id": UUID(r.buchung_id) if r.buchung_id else None,
            "abgang_art": AbgangArt(r.abgang_art) if r.abgang_art else None,
        }
    )


def _werte(a: Anlagegut) -> dict[str, object]:
    return {
        **{feld: getattr(a, feld) for feld in _FELDER},
        "afa_art": a.afa_art.value,
        "beleg_id": str(a.beleg_id) if a.beleg_id else None,
        "buchung_id": str(a.buchung_id) if a.buchung_id else None,
        "abgang_art": a.abgang_art.value if a.abgang_art else None,
    }


def speichere_anlage(session: Session, a: Anlagegut) -> Anlagegut:
    """Legt das Anlagegut an und vergibt die nächste Inventarnummer."""
    letzte = session.query(func.max(AnlagegutRow.nr)).scalar() or 0
    a = a.model_copy(update={"nr": letzte + 1})
    session.add(AnlagegutRow(id=str(a.id), nr=a.nr, **_werte(a)))
    session.flush()
    return a


def aktualisiere_anlage(session: Session, a: Anlagegut) -> None:
    row = session.get(AnlagegutRow, str(a.id))
    if row is None:
        raise ValueError(f"Anlagegut {a.nr} nicht gefunden")
    for feld, wert in _werte(a).items():
        setattr(row, feld, wert)
    session.flush()


def lade_anlagen(session: Session) -> list[Anlagegut]:
    rows = session.query(AnlagegutRow).order_by(AnlagegutRow.nr).all()
    return [_row_zu_anlage(r) for r in rows]


def lade_anlage(session: Session, schluessel: str) -> Anlagegut:
    """Anlagegut über die Inventarnummer oder den Anfang der ID."""
    treffer: list[AnlagegutRow]
    if schluessel.isdigit():
        treffer = session.query(AnlagegutRow).filter_by(nr=int(schluessel)).all()
    else:
        treffer = (
            session.query(AnlagegutRow)
            .filter(AnlagegutRow.id.like(f"{schluessel.lower()}%"))
            .all()
        )
    if len(treffer) != 1:
        grund = "nicht eindeutig" if treffer else "nicht gefunden"
        raise ValueError(f"Anlagegut '{schluessel}' {grund}")
    return _row_zu_anlage(treffer[0])


def speichere_afa_vorgang(session: Session, v: AfaVorgang) -> None:
    session.add(
        AfaVorgangRow(
            id=str(v.id),
            objekt=v.objekt,
            anlage_id=str(v.anlage_id) if v.anlage_id else None,
            jahr=v.jahr,
            bis_monat=v.bis_monat,
            betrag=v.betrag,
            buchung_id=str(v.buchung_id) if v.buchung_id else None,
            begruendung=v.begruendung[:500],
            erstellt_am=v.erstellt_am,
        )
    )


def lade_afa_vorgaenge(
    session: Session, jahr: int | None = None, objekt: str | None = None
) -> list[AfaVorgang]:
    query = session.query(AfaVorgangRow)
    if jahr is not None:
        query = query.filter(AfaVorgangRow.jahr == jahr)
    if objekt is not None:
        query = query.filter(AfaVorgangRow.objekt == objekt)
    return [
        AfaVorgang(
            id=UUID(r.id),
            objekt=r.objekt,
            anlage_id=UUID(r.anlage_id) if r.anlage_id else None,
            jahr=r.jahr,
            bis_monat=r.bis_monat,
            betrag=Decimal(str(r.betrag)),
            buchung_id=UUID(r.buchung_id) if r.buchung_id else None,
            begruendung=r.begruendung,
            erstellt_am=r.erstellt_am,
        )
        for r in query.order_by(AfaVorgangRow.erstellt_am).all()
    ]


def loesche_afa_vorgaenge(session: Session, ids: set[UUID]) -> None:
    """AfA-Vorgänge eines verworfenen AfA-Vorschlags entfernen (``anlagen aendern``,
    ``abgang --zuruecknehmen``) — sonst zählten sie als „schon gebucht“."""
    for ident in sorted(str(i) for i in ids):
        zeile = session.get(AfaVorgangRow, ident)
        if zeile is not None:
            session.delete(zeile)
    session.flush()


def verwirf_vorschlag(session: Session, buchung_id: UUID) -> None:
    """Einen noch nicht freigegebenen Vorschlag (AfA, Abgang) verwerfen.

    Über die Sitzung, nicht als Massen-``DELETE``: Jahres- und Monatssperre und die
    Unveränderbarkeit freigegebener Buchungen greifen, das Journal vermerkt
    ``buchung_verworfen`` (Baustein 7)."""
    zeile = session.get(BuchungssatzRow, str(buchung_id))
    if zeile is not None:
        session.delete(zeile)
    session.flush()
