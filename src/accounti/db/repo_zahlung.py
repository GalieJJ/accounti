"""Repository des Zahlungsverkehrs: Läufe, Zahlungen, Protokoll, Sperren."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from accounti.db.tabellen_zahlung import (
    IbanKlaerungRow,
    LaufProtokollRow,
    ZahlungRow,
    ZahlungslaufRow,
    ZahlungssperreRow,
)
from accounti.models.zahlung import (
    AKTIVE_STATUS,
    IbanKlaerung,
    LaufProtokoll,
    LaufStatus,
    Zahlung,
    Zahlungslauf,
    Zahlungssperre,
)


class PostenImLaufError(ValueError):
    """Ein Posten steht schon in einem aktiven Zahlungslauf."""


class LaufVeraltetError(ValueError):
    """Der Lauf wurde seit dem Lesen von jemand anderem geändert."""


_ZAHLUNG_FELDER = (
    "nr",
    "empfaenger",
    "iban",
    "strasse",
    "plz",
    "ort",
    "land",
    "betrag",
    "skonto",
    "restbetrag_vorher",
    "verwendungszweck",
    "end_to_end_id",
    "belegnummer",
    "belegdatum",
    "grund",
)
_LAUF_FELDER = (
    "nr",
    "stichtag",
    "ausfuehrung",
    "auftraggeber_name",
    "auftraggeber_iban",
    "auftraggeber_bic",
    "erstellt_am",
    "erstellt_von",
    "freigabe_hash",
    "msg_id",
    "datei",
    "datei_hash",
    "eingereicht_am",
)


def _zahlung(r: ZahlungRow) -> Zahlung:
    werte = {f: getattr(r, f) for f in _ZAHLUNG_FELDER}
    for feld in ("betrag", "skonto", "restbetrag_vorher"):
        werte[feld] = Decimal(str(werte[feld]))
    return Zahlung(
        id=UUID(r.id),
        lauf_id=UUID(r.lauf_id),
        posten_id=UUID(r.posten_id),
        kontakt_id=UUID(r.kontakt_id),
        **werte,
    )


def _zahlung_zeile(z: Zahlung, aktiv: bool) -> ZahlungRow:
    return ZahlungRow(
        id=str(z.id),
        lauf_id=str(z.lauf_id),
        posten_id=str(z.posten_id),
        sperre=str(z.posten_id) if aktiv else None,
        kontakt_id=str(z.kontakt_id),
        **{f: getattr(z, f) for f in _ZAHLUNG_FELDER},
    )


def _lauf(session: Session, r: ZahlungslaufRow) -> Zahlungslauf:
    zeilen = session.scalars(
        select(ZahlungRow).where(ZahlungRow.lauf_id == r.id).order_by(ZahlungRow.nr)
    ).all()
    return Zahlungslauf(
        id=UUID(r.id),
        status=LaufStatus(r.status),
        zahlungen=[_zahlung(z) for z in zeilen],
        **{f: getattr(r, f) for f in _LAUF_FELDER},
    )


def naechste_laufnummer(session: Session) -> int:
    letzte = session.scalar(select(func.max(ZahlungslaufRow.nr)))
    return (letzte or 0) + 1


def speichere_lauf(session: Session, lauf: Zahlungslauf) -> None:
    """Legt Lauf und Zahlungen an; ein Posten in einem aktiven Lauf scheitert.

    Bei einem Konflikt wird die ganze Transaktion zurückgerollt. Bewusst ohne
    Savepoint: Unter SQLite (pysqlite) würde dessen RELEASE den Lauf schon vor dem
    eigentlichen Commit festschreiben, wenn vorher nur gelesen wurde.
    """
    aktiv = lauf.status in AKTIVE_STATUS
    try:
        session.add(
            ZahlungslaufRow(
                id=str(lauf.id),
                status=lauf.status.value,
                **{f: getattr(lauf, f) for f in _LAUF_FELDER},
            )
        )
        session.flush()
        for z in lauf.zahlungen:
            session.add(_zahlung_zeile(z, aktiv))
        session.flush()
    except IntegrityError as fehler:
        session.rollback()
        msg = "Ein Posten steht schon in einem aktiven Zahlungslauf."
        raise PostenImLaufError(msg) from fehler


def _lauf_zeile(session: Session, nr: int) -> ZahlungslaufRow:
    zeile = session.scalar(select(ZahlungslaufRow).where(ZahlungslaufRow.nr == nr))
    if zeile is None:
        msg = f"Kein Zahlungslauf {nr}."
        raise ValueError(msg)
    return zeile


def lade_lauf(session: Session, nr: int) -> Zahlungslauf:
    return _lauf(session, _lauf_zeile(session, nr))


def lade_laeufe(
    session: Session, status: Iterable[LaufStatus] | None = None
) -> list[Zahlungslauf]:
    abfrage = select(ZahlungslaufRow).order_by(ZahlungslaufRow.nr)
    if status is not None:
        abfrage = abfrage.where(ZahlungslaufRow.status.in_([s.value for s in status]))
    return [_lauf(session, r) for r in session.scalars(abfrage).all()]


def aktualisiere_lauf(session: Session, lauf: Zahlungslauf, von: LaufStatus) -> None:
    """Schreibt Status und Kopfdaten (Freigabe, Datei); Zahlungen bleiben unberührt.

    Nur, wenn der Lauf noch im Status ``von`` ist. Die Versionsspalte macht daraus
    zusätzlich ein ``UPDATE … WHERE version = <gelesen>``: Hat ein anderer Prozess
    den Lauf inzwischen geändert, scheitert es mit ``LaufVeraltetError``, statt
    dessen Stand zu überschreiben.
    """
    zeile = _lauf_zeile(session, lauf.nr)
    if zeile.status != von.value:
        msg = f"Zahlungslauf {lauf.nr} ist inzwischen {zeile.status}."
        raise LaufVeraltetError(msg)
    zeile.status = lauf.status.value
    for feld in _LAUF_FELDER:
        setattr(zeile, feld, getattr(lauf, feld))
    try:
        session.flush()
    except StaleDataError as fehler:
        msg = f"Zahlungslauf {lauf.nr} wurde inzwischen geändert."
        raise LaufVeraltetError(msg) from fehler


def entferne_zahlung(session: Session, zahlung_id: UUID) -> None:
    zeile = session.get(ZahlungRow, str(zahlung_id))
    if zeile is not None:
        session.delete(zeile)
        session.flush()


def gib_posten_frei(session: Session, lauf_id: UUID) -> None:
    """Hebt die Sperre der Posten eines Laufs auf (Storno, Ausführung)."""
    for zeile in session.scalars(
        select(ZahlungRow).where(ZahlungRow.lauf_id == str(lauf_id))
    ):
        zeile.sperre = None
    session.flush()


def posten_in_aktiven_laeufen(
    session: Session,
) -> dict[UUID, tuple[int, LaufStatus]]:
    """Posten → (Laufnummer, Status) aller Läufe, die nicht abgeschlossen sind."""
    zeilen = session.execute(
        select(ZahlungRow.posten_id, ZahlungslaufRow.nr, ZahlungslaufRow.status)
        .join(ZahlungslaufRow, ZahlungslaufRow.id == ZahlungRow.lauf_id)
        .where(ZahlungslaufRow.status.in_([s.value for s in AKTIVE_STATUS]))
    ).all()
    return {UUID(p): (nr, LaufStatus(s)) for p, nr, s in zeilen}


def zahlungen_zum_posten(
    session: Session, posten_id: UUID
) -> list[tuple[Zahlung, int, LaufStatus]]:
    zeilen = session.execute(
        select(ZahlungRow, ZahlungslaufRow.nr, ZahlungslaufRow.status)
        .join(ZahlungslaufRow, ZahlungslaufRow.id == ZahlungRow.lauf_id)
        .where(ZahlungRow.posten_id == str(posten_id))
        .order_by(ZahlungslaufRow.nr)
    ).all()
    return [(_zahlung(z), nr, LaufStatus(s)) for z, nr, s in zeilen]


# --- Protokoll ------------------------------------------------------------------


def protokolliere(session: Session, eintrag: LaufProtokoll) -> LaufProtokoll:
    letzte = session.scalar(
        select(func.max(LaufProtokollRow.nr)).where(
            LaufProtokollRow.lauf_id == str(eintrag.lauf_id)
        )
    )
    eintrag = eintrag.model_copy(update={"nr": (letzte or 0) + 1})
    session.add(
        LaufProtokollRow(
            id=str(eintrag.id),
            lauf_id=str(eintrag.lauf_id),
            nr=eintrag.nr,
            zeitpunkt=eintrag.zeitpunkt,
            person=eintrag.person,
            aktion=eintrag.aktion,
            von_status=eintrag.von_status.value if eintrag.von_status else None,
            nach_status=eintrag.nach_status.value if eintrag.nach_status else None,
            text=eintrag.text,
        )
    )
    session.flush()
    return eintrag


def lade_protokoll(session: Session, lauf_id: UUID) -> list[LaufProtokoll]:
    zeilen = session.scalars(
        select(LaufProtokollRow)
        .where(LaufProtokollRow.lauf_id == str(lauf_id))
        .order_by(LaufProtokollRow.nr)
    ).all()
    return [
        LaufProtokoll(
            id=UUID(z.id),
            lauf_id=UUID(z.lauf_id),
            nr=z.nr,
            zeitpunkt=z.zeitpunkt,
            person=z.person,
            aktion=z.aktion,
            von_status=LaufStatus(z.von_status) if z.von_status else None,
            nach_status=LaufStatus(z.nach_status) if z.nach_status else None,
            text=z.text,
        )
        for z in zeilen
    ]


# --- Zahlungssperren -------------------------------------------------------------


def setze_zahlungssperre(session: Session, sperre: Zahlungssperre) -> None:
    zeile = session.get(ZahlungssperreRow, str(sperre.kontakt_id))
    if zeile is None:
        zeile = ZahlungssperreRow(kontakt_id=str(sperre.kontakt_id))
        session.add(zeile)
    zeile.grund = sperre.grund
    zeile.gesetzt_am = sperre.gesetzt_am
    zeile.gesetzt_von = sperre.gesetzt_von
    session.flush()


def hebe_zahlungssperre_auf(session: Session, kontakt_id: UUID) -> bool:
    zeile = session.get(ZahlungssperreRow, str(kontakt_id))
    if zeile is None:
        return False
    session.delete(zeile)
    session.flush()
    return True


def lade_zahlungssperren(session: Session) -> dict[UUID, Zahlungssperre]:
    return {
        UUID(z.kontakt_id): Zahlungssperre(
            kontakt_id=UUID(z.kontakt_id),
            grund=z.grund,
            gesetzt_am=z.gesetzt_am,
            gesetzt_von=z.gesetzt_von,
        )
        for z in session.scalars(select(ZahlungssperreRow)).all()
    }


# --- IBAN-Klärungen --------------------------------------------------------------


def speichere_iban_klaerung(session: Session, k: IbanKlaerung) -> None:
    session.add(
        IbanKlaerungRow(
            id=str(k.id),
            posten_id=str(k.posten_id),
            rechnungs_iban=k.rechnungs_iban,
            stammsatz_iban=k.stammsatz_iban,
            grund=k.grund,
            person=k.person,
            zeitpunkt=k.zeitpunkt,
        )
    )
    session.flush()


def lade_iban_klaerungen(session: Session, posten_id: UUID) -> list[IbanKlaerung]:
    zeilen = session.scalars(
        select(IbanKlaerungRow)
        .where(IbanKlaerungRow.posten_id == str(posten_id))
        .order_by(IbanKlaerungRow.zeitpunkt)
    ).all()
    return [
        IbanKlaerung(
            id=UUID(z.id),
            posten_id=UUID(z.posten_id),
            rechnungs_iban=z.rechnungs_iban,
            stammsatz_iban=z.stammsatz_iban,
            grund=z.grund,
            person=z.person,
            zeitpunkt=z.zeitpunkt,
        )
        for z in zeilen
    ]
