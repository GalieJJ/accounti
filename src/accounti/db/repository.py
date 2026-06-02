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

# ---------------------------------------------------------------------------
# Row <-> Domänenobjekt
# ---------------------------------------------------------------------------


def _row_zu_transaktion(r: TransaktionRow) -> Transaktion:
    return Transaktion(
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


def _row_zu_buchung(r: BuchungssatzRow) -> Buchungssatz:
    return Buchungssatz(
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
        geprueft_von=r.geprueft_von,
    )


# ---------------------------------------------------------------------------
# Transaktionen
# ---------------------------------------------------------------------------


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
    return [_row_zu_transaktion(r) for r in session.query(TransaktionRow).all()]


def lade_transaktion(session: Session, tx_id: str | UUID) -> Transaktion | None:
    row = session.get(TransaktionRow, str(tx_id))
    return _row_zu_transaktion(row) if row is not None else None


# ---------------------------------------------------------------------------
# Buchungssätze
# ---------------------------------------------------------------------------


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
            geprueft_von=b.geprueft_von,
        )
    )


def lade_buchungen(
    session: Session,
    status: set[BuchungStatus] | None = None,
) -> list[Buchungssatz]:
    query = session.query(BuchungssatzRow)
    if status is not None:
        query = query.filter(BuchungssatzRow.status.in_([s.value for s in status]))
    return [_row_zu_buchung(r) for r in query.all()]


def lade_pruefliste(
    session: Session,
) -> list[tuple[Buchungssatz, Transaktion | None]]:
    """Buchungen mit Status ZUR_PRUEFUNG samt zugehöriger Transaktion."""
    rows = (
        session.query(BuchungssatzRow)
        .filter(BuchungssatzRow.status == BuchungStatus.ZUR_PRUEFUNG.value)
        .all()
    )
    ergebnis: list[tuple[Buchungssatz, Transaktion | None]] = []
    for r in rows:
        tx_row = session.get(TransaktionRow, r.transaktion_id)
        tx = _row_zu_transaktion(tx_row) if tx_row is not None else None
        ergebnis.append((_row_zu_buchung(r), tx))
    return ergebnis


def _finde_zeile(session: Session, id_prefix: str) -> BuchungssatzRow:
    treffer = (
        session.query(BuchungssatzRow)
        .filter(BuchungssatzRow.id.like(f"{id_prefix}%"))
        .all()
    )
    if not treffer:
        msg = f"Keine Buchung mit ID '{id_prefix}' gefunden."
        raise ValueError(msg)
    if len(treffer) > 1:
        msg = f"ID '{id_prefix}' ist mehrdeutig ({len(treffer)} Treffer)."
        raise ValueError(msg)
    return treffer[0]


def finde_buchung(session: Session, id_prefix: str) -> Buchungssatz:
    return _row_zu_buchung(_finde_zeile(session, id_prefix))


def setze_status(
    session: Session,
    id_prefix: str,
    status: BuchungStatus,
    geprueft_von: str | None = None,
) -> Buchungssatz:
    row = _finde_zeile(session, id_prefix)
    row.status = status.value
    if geprueft_von is not None:
        row.geprueft_von = geprueft_von
    return _row_zu_buchung(row)


def aktualisiere_buchung(
    session: Session,
    id_prefix: str,
    neu: Buchungssatz,
) -> Buchungssatz:
    """Überschreibt die Felder einer Buchung (ID bleibt erhalten)."""
    row = _finde_zeile(session, id_prefix)
    row.soll_konto = neu.soll_konto
    row.haben_konto = neu.haben_konto
    row.betrag_netto = neu.betrag_netto
    row.steuer_schluessel = neu.steuer_schluessel
    row.steuer_betrag = neu.steuer_betrag
    row.buchungstext = neu.buchungstext
    row.status = neu.status.value
    row.confidence = neu.confidence
    row.geprueft_von = neu.geprueft_von
    return _row_zu_buchung(row)
