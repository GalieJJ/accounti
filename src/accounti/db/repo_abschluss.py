"""Repository des Jahresabschlusses (Baustein 12)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from accounti.db.tabellen_abschluss import (
    AbgrenzungRow,
    AbschlussRow,
    JahrGesperrtError,
    KontoauszugssaldoRow,
    ProtokollRow,
    gesperrte_jahre,
    jahr_gesperrt,
)
from accounti.models.abschluss import (
    Abgrenzung,
    AbgrenzungArt,
    AbgrenzungStatus,
    Jahresabschluss,
    Kontoauszugssaldo,
    Protokolleintrag,
)


def _uuid(wert: str | None) -> UUID | None:
    return UUID(wert) if wert else None


def _kurz(wert: str | None, laenge: int) -> str | None:
    """Freitext auf die Spaltenlänge kürzen — Postgres lehnte ihn sonst ab."""
    return wert[:laenge] if wert is not None else None


# --- Kontoauszugssalden -----------------------------------------------------------


def speichere_kontoauszugssaldo(session: Session, k: Kontoauszugssaldo) -> None:
    session.add(
        KontoauszugssaldoRow(
            id=str(k.id),
            bankkonto_id=str(k.bankkonto_id),
            stichtag=k.stichtag,
            saldo=k.saldo,
            erfasst_am=k.erfasst_am,
            erfasst_von=_kurz(k.erfasst_von, 50),
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


# --- Jahressperre -----------------------------------------------------------------


def ist_gesperrt(session: Session, jahr: int) -> bool:
    return jahr_gesperrt(session.connection(), jahr)


def lade_gesperrte_jahre(session: Session) -> set[int]:
    """Abgeschlossene Geschäftsjahre — dort lässt sich nichts mehr buchen."""
    return gesperrte_jahre(session.connection())


def pruefe_jahr_offen(session: Session, jahr: int) -> None:
    if ist_gesperrt(session, jahr):
        msg = (
            f"Geschäftsjahr {jahr} ist abgeschlossen — nichts mehr zu buchen "
            f"(accounti abschluss oeffnen --jahr {jahr})"
        )
        raise JahrGesperrtError(msg)


def lade_jahresabschluss(session: Session, jahr: int) -> Jahresabschluss | None:
    row = session.get(AbschlussRow, jahr)
    if row is None:
        return None
    return Jahresabschluss(
        jahr=row.jahr,
        gesperrt=row.gesperrt,
        gewinnermittlung=row.gewinnermittlung,
        ergebnis=Decimal(str(row.ergebnis)),
        abgeschlossen_am=row.abgeschlossen_am,
        von=row.von,
    )


def setze_jahresabschluss(session: Session, a: Jahresabschluss) -> None:
    row = session.get(AbschlussRow, a.jahr)
    if row is None:
        row = AbschlussRow(jahr=a.jahr)
        session.add(row)
    row.gesperrt = a.gesperrt
    row.gewinnermittlung = a.gewinnermittlung
    row.ergebnis = a.ergebnis
    row.abgeschlossen_am = a.abgeschlossen_am
    row.von = a.von[:50]
    session.flush()


# --- Abgrenzungen -----------------------------------------------------------------

_ABGRENZUNG_FELDER = (
    "nr",
    "jahr",
    "konto",
    "rap_konto",
    "betrag",
    "von",
    "bis",
    "rechenweg",
    "erstellt_am",
    "entschieden_am",
    "entschieden_von",
)


def _row_zu_abgrenzung(r: AbgrenzungRow) -> Abgrenzung:
    return Abgrenzung.model_validate(
        {
            **{feld: getattr(r, feld) for feld in _ABGRENZUNG_FELDER},
            "id": UUID(r.id),
            "buchung_id": UUID(r.buchung_id),
            "art": AbgrenzungArt(r.art),
            "status": AbgrenzungStatus(r.status),
            "betrag": Decimal(str(r.betrag)),
            "abgrenzung_buchung_id": _uuid(r.abgrenzung_buchung_id),
            "aufloesung_buchung_id": _uuid(r.aufloesung_buchung_id),
        }
    )


def speichere_abgrenzung(session: Session, a: Abgrenzung) -> Abgrenzung:
    letzte = session.query(func.max(AbgrenzungRow.nr)).scalar() or 0
    a = a.model_copy(update={"nr": letzte + 1, "rechenweg": a.rechenweg[:500]})
    werte = {feld: getattr(a, feld) for feld in _ABGRENZUNG_FELDER}
    session.add(
        AbgrenzungRow(
            id=str(a.id),
            buchung_id=str(a.buchung_id),
            art=a.art.value,
            status=a.status.value,
            **werte,
        )
    )
    session.flush()
    return a


def aktualisiere_abgrenzung(session: Session, a: Abgrenzung) -> None:
    row = session.get(AbgrenzungRow, str(a.id))
    if row is None:
        raise ValueError(f"Abgrenzung {a.nr} nicht gefunden")
    row.status = a.status.value
    row.abgrenzung_buchung_id = (
        str(a.abgrenzung_buchung_id) if a.abgrenzung_buchung_id else None
    )
    row.aufloesung_buchung_id = (
        str(a.aufloesung_buchung_id) if a.aufloesung_buchung_id else None
    )
    row.entschieden_am = a.entschieden_am
    row.entschieden_von = _kurz(a.entschieden_von, 50)
    session.flush()


def lade_abgrenzungen(
    session: Session,
    jahr: int | None = None,
    status: AbgrenzungStatus | None = None,
) -> list[Abgrenzung]:
    query = session.query(AbgrenzungRow)
    if jahr is not None:
        query = query.filter(AbgrenzungRow.jahr == jahr)
    if status is not None:
        query = query.filter(AbgrenzungRow.status == status.value)
    return [_row_zu_abgrenzung(r) for r in query.order_by(AbgrenzungRow.nr).all()]


def abgegrenzte_buchungen(session: Session) -> set[UUID]:
    """Buchungen mit einem Abgrenzungsvorschlag — gleich welcher Status."""
    return {UUID(b) for (b,) in session.query(AbgrenzungRow.buchung_id).all()}


def lade_abgrenzung(session: Session, schluessel: str) -> Abgrenzung:
    """Abgrenzung über ihre Nummer oder den Anfang der ID."""
    if schluessel.isdigit():
        treffer = session.query(AbgrenzungRow).filter_by(nr=int(schluessel)).all()
    else:
        treffer = (
            session.query(AbgrenzungRow)
            .filter(AbgrenzungRow.id.like(f"{schluessel.lower()}%"))
            .all()
        )
    if len(treffer) != 1:
        grund = "nicht eindeutig" if treffer else "nicht gefunden"
        raise ValueError(f"Abgrenzung '{schluessel}' {grund}")
    return _row_zu_abgrenzung(treffer[0])


# --- Abschlussprotokoll (nur anfügen) ---------------------------------------------


def lade_protokoll(session: Session) -> list[Protokolleintrag]:
    rows = session.query(ProtokollRow).order_by(ProtokollRow.nr).all()
    return [
        Protokolleintrag(
            nr=r.nr,
            jahr=r.jahr,
            zeitpunkt=r.zeitpunkt,
            aktion=r.aktion,
            von=r.von,
            grund=r.grund,
            details=r.details,
            vorgaenger_hash=r.vorgaenger_hash,
            hash=r.hash,
        )
        for r in rows
    ]


def speichere_protokolleintrag(session: Session, e: Protokolleintrag) -> None:
    session.add(ProtokollRow(**e.model_dump()))
    session.flush()
