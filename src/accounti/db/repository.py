"""Mapping zwischen Domänen- (Pydantic) und Persistenz- (ORM) Modellen."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.tabellen import (
    BelegEingangRow,
    BelegpositionRow,
    BelegRow,
    BuchungssatzRow,
    TransaktionRow,
)
from accounti.models import (
    Beleg,
    Belegart,
    BelegEingang,
    Belegposition,
    Belegrichtung,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Eingangsergebnis,
    Transaktion,
    TransaktionQuelle,
)

# ---------------------------------------------------------------------------
# Row <-> Domänenobjekt
# ---------------------------------------------------------------------------


def _dec(wert: Decimal | None) -> Decimal | None:
    return Decimal(str(wert)) if wert is not None else None


def _uuid(wert: str | None) -> UUID | None:
    return UUID(wert) if wert is not None else None


def _str(wert: UUID | None) -> str | None:
    return str(wert) if wert is not None else None


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
        steuer_betrag=_dec(r.steuer_betrag),
        buchungstext=r.buchungstext,
        beleg_position_id=_uuid(r.beleg_position_id),
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
            beleg_position_id=_str(b.beleg_position_id),
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


# ---------------------------------------------------------------------------
# Belege
# ---------------------------------------------------------------------------


def _row_zu_position(r: BelegpositionRow) -> Belegposition:
    return Belegposition(
        id=UUID(r.id),
        beleg_id=UUID(r.beleg_id),
        bezeichnung=r.bezeichnung,
        menge=Decimal(str(r.menge)),
        netto=Decimal(str(r.netto)),
        steuersatz=_dec(r.steuersatz),
        steuer_betrag=_dec(r.steuer_betrag),
        konto_vorschlag=r.konto_vorschlag,
        confidence=r.confidence,
    )


def _row_zu_beleg(r: BelegRow, positionen: list[Belegposition]) -> Beleg:
    return Beleg(
        id=UUID(r.id),
        belegart=Belegart(r.belegart),
        richtung=Belegrichtung(r.richtung),
        belegnummer=r.belegnummer,
        belegdatum=r.belegdatum,
        leistungsdatum=r.leistungsdatum,
        kontakt_id=_uuid(r.kontakt_id),
        lieferant_name=r.lieferant_name,
        lieferant_ust_id=r.lieferant_ust_id,
        netto=_dec(r.netto),
        steuer=_dec(r.steuer),
        brutto=_dec(r.brutto),
        waehrung=r.waehrung,
        zahlungsziel=r.zahlungsziel,
        skonto_prozent=_dec(r.skonto_prozent),
        skonto_tage=r.skonto_tage,
        datei_hash=r.datei_hash,
        dateiname=r.dateiname,
        kanal=r.kanal,
        herkunft=r.herkunft,
        eingegangen_am=r.eingegangen_am,
        aufbewahren_bis=r.aufbewahren_bis,
        status=BelegStatus(r.status),
        pruef_grund=r.pruef_grund,
        confidence=r.confidence,
        positionen=positionen,
    )


def speichere_beleg(session: Session, b: Beleg) -> None:
    session.add(
        BelegRow(
            id=str(b.id),
            belegart=b.belegart.value,
            richtung=b.richtung.value,
            belegnummer=b.belegnummer,
            belegdatum=b.belegdatum,
            leistungsdatum=b.leistungsdatum,
            kontakt_id=_str(b.kontakt_id),
            lieferant_name=b.lieferant_name,
            lieferant_ust_id=b.lieferant_ust_id,
            netto=b.netto,
            steuer=b.steuer,
            brutto=b.brutto,
            waehrung=b.waehrung,
            zahlungsziel=b.zahlungsziel,
            skonto_prozent=b.skonto_prozent,
            skonto_tage=b.skonto_tage,
            datei_hash=b.datei_hash,
            dateiname=b.dateiname,
            kanal=b.kanal,
            herkunft=b.herkunft,
            eingegangen_am=b.eingegangen_am,
            aufbewahren_bis=b.aufbewahren_bis,
            status=b.status.value,
            pruef_grund=b.pruef_grund,
            confidence=b.confidence,
        )
    )
    for nr, p in enumerate(b.positionen, start=1):
        session.add(
            BelegpositionRow(
                id=str(p.id),
                beleg_id=str(b.id),
                nr=nr,
                bezeichnung=p.bezeichnung,
                menge=p.menge,
                netto=p.netto,
                steuersatz=p.steuersatz,
                steuer_betrag=p.steuer_betrag,
                konto_vorschlag=p.konto_vorschlag,
                confidence=p.confidence,
            )
        )


def lade_belege(
    session: Session,
    status: set[BelegStatus] | None = None,
) -> list[Beleg]:
    query = session.query(BelegRow).order_by(BelegRow.eingegangen_am)
    if status is not None:
        query = query.filter(BelegRow.status.in_([s.value for s in status]))
    rows = query.all()
    positionen: dict[str, list[Belegposition]] = {r.id: [] for r in rows}
    if rows:
        pos_rows = (
            session.query(BelegpositionRow)
            .filter(BelegpositionRow.beleg_id.in_(list(positionen)))
            .order_by(BelegpositionRow.nr)
            .all()
        )
        for p in pos_rows:
            positionen[p.beleg_id].append(_row_zu_position(p))
    return [_row_zu_beleg(r, positionen[r.id]) for r in rows]


def speichere_eingang(session: Session, e: BelegEingang) -> None:
    session.add(
        BelegEingangRow(
            id=str(e.id),
            kanal=e.kanal,
            dateiname=e.dateiname,
            herkunft=e.herkunft,
            datei_hash=e.datei_hash,
            eingegangen_am=e.eingegangen_am,
            ergebnis=e.ergebnis.value,
            beleg_id=_str(e.beleg_id),
            hinweis=e.hinweis,
        )
    )


def lade_eingaenge(session: Session) -> list[BelegEingang]:
    rows = session.query(BelegEingangRow).order_by(BelegEingangRow.eingegangen_am)
    return [
        BelegEingang(
            id=UUID(r.id),
            kanal=r.kanal,
            dateiname=r.dateiname,
            herkunft=r.herkunft,
            datei_hash=r.datei_hash,
            eingegangen_am=r.eingegangen_am,
            ergebnis=Eingangsergebnis(r.ergebnis),
            beleg_id=_uuid(r.beleg_id),
            hinweis=r.hinweis,
        )
        for r in rows.all()
    ]
