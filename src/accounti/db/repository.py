"""Mapping zwischen Domänen- (Pydantic) und Persistenz- (ORM) Modellen."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounti.db.tabellen import (
    AusgangspositionRow,
    AusgangsrechnungRow,
    BankkontoRow,
    BelegabgleichRow,
    BelegEingangRow,
    BelegpositionRow,
    BelegRow,
    BuchungssatzRow,
    KontaktRow,
    NummernkreisRow,
    OffenerPostenRow,
    TransaktionRow,
    UstIdPruefungRow,
    VersandprotokollRow,
    ZahlungszuordnungRow,
)
from accounti.models import (
    AbgleichStatus,
    AusgangsPosition,
    Ausgangsrechnung,
    AusgangsrechnungStatus,
    Bankkonto,
    Beleg,
    Belegabgleich,
    Belegart,
    BelegEingang,
    Belegposition,
    Belegrichtung,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Eingangsergebnis,
    Kontakt,
    KontaktStatus,
    KontoZustand,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    Rechnungsempfaenger,
    Transaktion,
    TransaktionQuelle,
    UstIdPruefung,
    Versandprotokoll,
    Zahlungszuordnung,
    ZuordnungStatus,
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
        bankkonto_id=_uuid(r.bankkonto_id),
        sachkonto=r.sachkonto,
        dublettenschluessel=r.dublettenschluessel,
    )


def _row_zu_buchung(r: BuchungssatzRow) -> Buchungssatz:
    return Buchungssatz(
        id=UUID(r.id),
        transaktion_id=_uuid(r.transaktion_id),
        beleg_id=_uuid(r.beleg_id),
        datum=r.datum,
        soll_konto=r.soll_konto,
        haben_konto=r.haben_konto,
        betrag_netto=Decimal(str(r.betrag_netto)),
        steuer_schluessel=r.steuer_schluessel,
        steuer_betrag=_dec(r.steuer_betrag),
        buchungstext=r.buchungstext,
        beleg_nummer=r.beleg_nummer,
        beleg_position_id=_uuid(r.beleg_position_id),
        status=BuchungStatus(r.status),
        confidence=r.confidence,
        geprueft_von=r.geprueft_von,
        storniert_durch=_uuid(r.storniert_durch),
        storno_von=_uuid(r.storno_von),
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
            bankkonto_id=_str(tx.bankkonto_id),
            sachkonto=tx.sachkonto,
            dublettenschluessel=tx.dublettenschluessel,
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
            transaktion_id=_str(b.transaktion_id),
            beleg_id=_str(b.beleg_id),
            datum=b.datum,
            soll_konto=b.soll_konto,
            haben_konto=b.haben_konto,
            betrag_netto=b.betrag_netto,
            steuer_schluessel=b.steuer_schluessel,
            steuer_betrag=b.steuer_betrag,
            buchungstext=b.buchungstext,
            beleg_nummer=b.beleg_nummer,
            beleg_position_id=_str(b.beleg_position_id),
            status=b.status.value,
            confidence=b.confidence,
            geprueft_von=b.geprueft_von,
            storniert_durch=_str(b.storniert_durch),
            storno_von=_str(b.storno_von),
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
        tx_row = (
            session.get(TransaktionRow, r.transaktion_id) if r.transaktion_id else None
        )
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
    row.beleg_nummer = neu.beleg_nummer
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
        iban=r.iban,
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
            iban=b.iban,
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
    _speichere_positionen(session, b)


def _speichere_positionen(session: Session, b: Beleg) -> None:
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


# Herkunft und Archivbezug bleiben fest; alles Erkannte darf neu geschrieben werden.
_ERKANNTE_FELDER = (
    "belegnummer",
    "belegdatum",
    "leistungsdatum",
    "lieferant_name",
    "lieferant_ust_id",
    "iban",
    "netto",
    "steuer",
    "brutto",
    "waehrung",
    "zahlungsziel",
    "skonto_prozent",
    "skonto_tage",
    "pruef_grund",
    "confidence",
)


def aktualisiere_beleg(session: Session, b: Beleg) -> Beleg:
    """Schreibt die erkannten Felder und Positionen eines Belegs neu."""
    row = session.get(BelegRow, str(b.id))
    if row is None:
        msg = f"Beleg {b.id} nicht gefunden."
        raise ValueError(msg)
    for feld in _ERKANNTE_FELDER:
        setattr(row, feld, getattr(b, feld))
    row.belegart = b.belegart.value
    row.richtung = b.richtung.value
    row.kontakt_id = _str(b.kontakt_id)
    row.status = b.status.value
    session.query(BelegpositionRow).filter(BelegpositionRow.beleg_id == row.id).delete()
    _speichere_positionen(session, b)
    return b


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


def lade_beleg(session: Session, beleg_id: str | UUID) -> Beleg | None:
    row = session.get(BelegRow, str(beleg_id))
    if row is None:
        return None
    pos_rows = (
        session.query(BelegpositionRow)
        .filter(BelegpositionRow.beleg_id == row.id)
        .order_by(BelegpositionRow.nr)
        .all()
    )
    return _row_zu_beleg(row, [_row_zu_position(p) for p in pos_rows])


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


# ---------------------------------------------------------------------------
# Ausgangsrechnungen
# ---------------------------------------------------------------------------


def _row_zu_ausgangsrechnung(
    r: AusgangsrechnungRow, positionen: list[AusgangspositionRow]
) -> Ausgangsrechnung:
    return Ausgangsrechnung(
        id=UUID(r.id),
        status=AusgangsrechnungStatus(r.status),
        nummer=r.nummer,
        rechnungstyp=r.rechnungstyp or "380",
        korrektur_zu=r.korrektur_zu,
        kunde=Rechnungsempfaenger(
            name=r.kunde_name,
            strasse=r.kunde_strasse,
            plz=r.kunde_plz,
            ort=r.kunde_ort,
            land=r.kunde_land,
            ust_id=r.kunde_ust_id,
            email=r.kunde_email,
            leitweg_id=r.kunde_leitweg_id,
            privat=r.kunde_privat,
        ),
        positionen=[
            AusgangsPosition(
                id=UUID(p.id),
                bezeichnung=p.bezeichnung,
                menge=Decimal(str(p.menge)).normalize(),
                einheit=p.einheit,
                einzelpreis=Decimal(str(p.einzelpreis)).normalize(),
                ermaessigt=p.ermaessigt,
                sonstige_leistung=p.sonstige_leistung,
                elektronisch=bool(p.elektronisch),
            )
            for p in sorted(positionen, key=lambda p: p.nr)
        ],
        leistungsdatum=r.leistungsdatum,
        bestellnummer=r.bestellnummer,
        notiz=r.notiz,
        skonto_prozent=_dec(r.skonto_prozent),
        skonto_tage=r.skonto_tage,
        rechnungsdatum=r.rechnungsdatum,
        zahlungsziel=r.zahlungsziel,
        beleg_id=_uuid(r.beleg_id),
        datei_hash=r.datei_hash,
        pdf_hash=r.pdf_hash,
        erstellt_am=r.erstellt_am,
    )


def _positions_zeilen(session: Session, rechnung_id: str) -> list[AusgangspositionRow]:
    return (
        session.query(AusgangspositionRow)
        .filter(AusgangspositionRow.rechnung_id == rechnung_id)
        .all()
    )


def speichere_ausgangsrechnung(session: Session, r: Ausgangsrechnung) -> None:
    k = r.kunde
    session.add(
        AusgangsrechnungRow(
            id=str(r.id),
            status=r.status.value,
            nummer=r.nummer,
            rechnungstyp=r.rechnungstyp,
            korrektur_zu=r.korrektur_zu,
            kunde_name=k.name,
            kunde_strasse=k.strasse,
            kunde_plz=k.plz,
            kunde_ort=k.ort,
            kunde_land=k.land.upper(),
            kunde_ust_id=k.ust_id,
            kunde_email=k.email,
            kunde_leitweg_id=k.leitweg_id,
            kunde_privat=k.privat,
            leistungsdatum=r.leistungsdatum,
            bestellnummer=r.bestellnummer,
            notiz=r.notiz,
            skonto_prozent=r.skonto_prozent,
            skonto_tage=r.skonto_tage,
            rechnungsdatum=r.rechnungsdatum,
            zahlungsziel=r.zahlungsziel,
            beleg_id=_str(r.beleg_id),
            datei_hash=r.datei_hash,
            pdf_hash=r.pdf_hash,
            erstellt_am=r.erstellt_am,
        )
    )
    for p in r.positionen:
        _speichere_ausgangsposition(session, str(r.id), p)
    session.flush()


def _speichere_ausgangsposition(
    session: Session, rechnung_id: str, p: AusgangsPosition
) -> None:
    nr = len(_positions_zeilen(session, rechnung_id)) + 1
    session.add(
        AusgangspositionRow(
            id=str(p.id),
            rechnung_id=rechnung_id,
            nr=nr,
            bezeichnung=p.bezeichnung,
            menge=p.menge,
            einheit=p.einheit,
            einzelpreis=p.einzelpreis,
            ermaessigt=p.ermaessigt,
            sonstige_leistung=p.sonstige_leistung,
            elektronisch=p.elektronisch,
        )
    )
    session.flush()


def _finde_ausgangsrechnung(session: Session, schluessel: str) -> AusgangsrechnungRow:
    """Sucht über die Rechnungsnummer oder den Anfang der ID."""
    treffer = (
        session.query(AusgangsrechnungRow)
        .filter(AusgangsrechnungRow.nummer == schluessel)
        .all()
    ) or (
        session.query(AusgangsrechnungRow)
        .filter(AusgangsrechnungRow.id.like(f"{schluessel}%"))
        .all()
    )
    if not treffer:
        msg = f"Keine Rechnung mit Nummer oder ID '{schluessel}' gefunden."
        raise ValueError(msg)
    if len(treffer) > 1:
        msg = f"'{schluessel}' ist mehrdeutig ({len(treffer)} Treffer)."
        raise ValueError(msg)
    return treffer[0]


def lade_ausgangsrechnung(session: Session, schluessel: str) -> Ausgangsrechnung:
    row = _finde_ausgangsrechnung(session, schluessel)
    return _row_zu_ausgangsrechnung(row, _positions_zeilen(session, row.id))


def lade_ausgangsrechnungen(session: Session) -> list[Ausgangsrechnung]:
    rows = session.query(AusgangsrechnungRow).order_by(AusgangsrechnungRow.erstellt_am)
    return [_row_zu_ausgangsrechnung(r, _positions_zeilen(session, r.id)) for r in rows]


def fuege_position_hinzu(
    session: Session, schluessel: str, position: AusgangsPosition
) -> Ausgangsrechnung:
    row = _finde_ausgangsrechnung(session, schluessel)
    if row.status != AusgangsrechnungStatus.ENTWURF.value:
        msg = f"Rechnung {row.nummer} ist bereits ausgestellt und unveränderlich."
        raise ValueError(msg)
    _speichere_ausgangsposition(session, row.id, position)
    return _row_zu_ausgangsrechnung(row, _positions_zeilen(session, row.id))


def markiere_ausgestellt(
    session: Session,
    rechnung_id: UUID,
    *,
    nummer: str,
    rechnungsdatum: date,
    zahlungsziel: date | None,
    beleg_id: UUID,
    datei_hash: str,
    pdf_hash: str | None = None,
) -> None:
    row = session.get(AusgangsrechnungRow, str(rechnung_id))
    if row is None:
        msg = f"Rechnung {rechnung_id} nicht gefunden."
        raise ValueError(msg)
    if row.status != AusgangsrechnungStatus.ENTWURF.value:
        msg = f"Rechnung {row.nummer} ist bereits ausgestellt."
        raise ValueError(msg)
    row.status = AusgangsrechnungStatus.AUSGESTELLT.value
    row.nummer = nummer
    row.rechnungsdatum = rechnungsdatum
    row.zahlungsziel = zahlungsziel
    row.beleg_id = str(beleg_id)
    row.datei_hash = datei_hash
    row.pdf_hash = pdf_hash
    session.flush()


# Jahr eines Nummernkreises, der über den Jahreswechsel weiterzählt (Format ohne {jahr})
JAHRESUEBERGREIFEND = 0


def naechste_nummer(session: Session, kreis: str, jahr: int) -> int:
    """Zählt den Nummernkreis in der laufenden Transaktion hoch.

    Das ``UPDATE`` sperrt die Zeile bis zum Commit; parallele Aussteller warten.
    Wird die Transaktion zurückgerollt, ist die Nummer wieder frei — so bleibt
    der Kreis lückenlos. Ein jahresübergreifender Kreis (``JAHRESUEBERGREIFEND``)
    beginnt hinter dem höchsten Stand der Jahreskreise desselben Kürzels.
    """
    bedingung = (NummernkreisRow.kreis == kreis) & (NummernkreisRow.jahr == jahr)
    erhoeht = session.execute(
        update(NummernkreisRow)
        .where(bedingung)
        .values(letzte=NummernkreisRow.letzte + 1)
    )
    if erhoeht.rowcount == 0:  # type: ignore[attr-defined]
        erste = 1
        if jahr == JAHRESUEBERGREIFEND:
            bisher = (
                session.query(func.max(NummernkreisRow.letzte))
                .filter(NummernkreisRow.kreis == kreis)
                .scalar()
            )
            erste = int(bisher or 0) + 1
        try:
            with session.begin_nested():
                session.add(NummernkreisRow(kreis=kreis, jahr=jahr, letzte=erste))
            return erste
        except IntegrityError:
            # Ein paralleler Aussteller hat den Kreis gerade angelegt.
            session.execute(
                update(NummernkreisRow)
                .where(bedingung)
                .values(letzte=NummernkreisRow.letzte + 1)
            )
    wert = session.query(NummernkreisRow.letzte).filter(bedingung).scalar()
    return int(wert)


def nummer_vergeben(session: Session, nummer: str) -> bool:
    """Trägt schon eine Ausgangsrechnung diese Nummer?"""
    return (
        session.query(AusgangsrechnungRow.id)
        .filter(AusgangsrechnungRow.nummer == nummer)
        .first()
        is not None
    )


def speichere_versandprotokoll(session: Session, p: Versandprotokoll) -> None:
    session.add(
        VersandprotokollRow(
            id=str(p.id),
            rechnung_id=str(p.rechnung_id),
            zeitpunkt=p.zeitpunkt,
            weg=p.weg,
            empfaenger=p.empfaenger,
            format=p.format,
            dateiname=p.dateiname,
            datei_hash=p.datei_hash,
            message_id=p.message_id,
            erfolgreich=p.erfolgreich,
            fehler=p.fehler,
        )
    )
    session.flush()


def lade_versandprotokolle(session: Session, schluessel: str) -> list[Versandprotokoll]:
    row = _finde_ausgangsrechnung(session, schluessel)
    zeilen = (
        session.query(VersandprotokollRow)
        .filter(VersandprotokollRow.rechnung_id == row.id)
        .order_by(VersandprotokollRow.zeitpunkt)
        .all()
    )
    return [
        Versandprotokoll(
            id=UUID(z.id),
            rechnung_id=UUID(z.rechnung_id),
            zeitpunkt=z.zeitpunkt,
            weg=z.weg,
            empfaenger=z.empfaenger,
            format=z.format,
            dateiname=z.dateiname,
            datei_hash=z.datei_hash,
            message_id=z.message_id,
            erfolgreich=z.erfolgreich,
            fehler=z.fehler,
        )
        for z in zeilen
    ]


# ---------------------------------------------------------------------------
# Kontakte
# ---------------------------------------------------------------------------

_KONTAKT_FELDER = (
    "name",
    "strasse",
    "plz",
    "ort",
    "land",
    "ust_id",
    "steuernummer",
    "iban",
    "email",
    "kreditor_konto",
    "debitor_konto",
    "zahlungsziel_tage",
    "skonto_prozent",
    "skonto_tage",
    "sachkonto",
    "pruef_grund",
)


def _row_zu_kontakt(r: KontaktRow) -> Kontakt:
    return Kontakt(
        id=UUID(r.id),
        **{f: getattr(r, f) for f in _KONTAKT_FELDER if f != "skonto_prozent"},
        skonto_prozent=_dec(r.skonto_prozent),
        status=KontaktStatus(r.status),
        erstellt_am=r.erstellt_am,
    )


def speichere_kontakt(session: Session, k: Kontakt) -> None:
    session.add(
        KontaktRow(
            id=str(k.id),
            **{f: getattr(k, f) for f in _KONTAKT_FELDER},
            status=k.status.value,
            erstellt_am=k.erstellt_am,
        )
    )
    session.flush()


def lade_kontakte(session: Session) -> list[Kontakt]:
    rows = session.query(KontaktRow).order_by(KontaktRow.erstellt_am).all()
    return [_row_zu_kontakt(r) for r in rows]


def _finde_kontakt_zeile(session: Session, schluessel: str) -> KontaktRow:
    """Sucht über Personenkontonummer oder den Anfang der ID."""
    treffer = (
        session.query(KontaktRow)
        .filter(
            (KontaktRow.kreditor_konto == schluessel)
            | (KontaktRow.debitor_konto == schluessel)
        )
        .all()
    ) or session.query(KontaktRow).filter(KontaktRow.id.like(f"{schluessel}%")).all()
    if not treffer:
        msg = f"Kein Kontakt mit Konto oder ID '{schluessel}' gefunden."
        raise ValueError(msg)
    if len(treffer) > 1:
        msg = f"'{schluessel}' ist mehrdeutig ({len(treffer)} Treffer)."
        raise ValueError(msg)
    return treffer[0]


def lade_kontakt(session: Session, schluessel: str) -> Kontakt:
    return _row_zu_kontakt(_finde_kontakt_zeile(session, schluessel))


def aktualisiere_kontakt(session: Session, k: Kontakt) -> Kontakt:
    row = session.get(KontaktRow, str(k.id))
    if row is None:
        msg = f"Kontakt {k.id} nicht gefunden."
        raise ValueError(msg)
    for feld in _KONTAKT_FELDER:
        setattr(row, feld, getattr(k, feld))
    row.status = k.status.value
    session.flush()
    return _row_zu_kontakt(row)


# ---------------------------------------------------------------------------
# Offene Posten
# ---------------------------------------------------------------------------


def _row_zu_posten(r: OffenerPostenRow) -> OffenerPosten:
    return OffenerPosten(
        id=UUID(r.id),
        kontakt_id=UUID(r.kontakt_id),
        beleg_id=UUID(r.beleg_id),
        richtung=PostenRichtung(r.richtung),
        belegnummer=r.belegnummer,
        belegdatum=r.belegdatum,
        betrag=Decimal(str(r.betrag)),
        restbetrag=Decimal(str(r.restbetrag)),
        faellig_am=r.faellig_am,
        skonto_bis=r.skonto_bis,
        skonto_prozent=_dec(r.skonto_prozent),
        skonto_betrag=_dec(r.skonto_betrag),
        status=PostenStatus(r.status),
        mahnstufe=r.mahnstufe,
        erstellt_am=r.erstellt_am,
    )


def speichere_posten(session: Session, p: OffenerPosten) -> None:
    session.add(
        OffenerPostenRow(
            id=str(p.id),
            kontakt_id=str(p.kontakt_id),
            beleg_id=str(p.beleg_id),
            richtung=p.richtung.value,
            belegnummer=p.belegnummer,
            belegdatum=p.belegdatum,
            betrag=p.betrag,
            restbetrag=p.restbetrag,
            faellig_am=p.faellig_am,
            skonto_bis=p.skonto_bis,
            skonto_prozent=p.skonto_prozent,
            skonto_betrag=p.skonto_betrag,
            status=p.status.value,
            mahnstufe=p.mahnstufe,
            erstellt_am=p.erstellt_am,
        )
    )
    session.flush()


def lade_posten(
    session: Session,
    richtung: PostenRichtung | None = None,
    status: set[PostenStatus] | None = None,
) -> list[OffenerPosten]:
    query = session.query(OffenerPostenRow).order_by(OffenerPostenRow.faellig_am)
    if richtung is not None:
        query = query.filter(OffenerPostenRow.richtung == richtung.value)
    if status is not None:
        query = query.filter(OffenerPostenRow.status.in_([s.value for s in status]))
    return [_row_zu_posten(r) for r in query.all()]


def verbuchte_beleg_ids(session: Session) -> set[UUID]:
    return {UUID(b) for (b,) in session.query(OffenerPostenRow.beleg_id).all()}


def lade_posten_fuer_beleg(session: Session, beleg_id: UUID) -> OffenerPosten | None:
    row = (
        session.query(OffenerPostenRow)
        .filter(OffenerPostenRow.beleg_id == str(beleg_id))
        .one_or_none()
    )
    return _row_zu_posten(row) if row is not None else None


def lade_einen_posten(session: Session, posten_id: UUID) -> OffenerPosten:
    row = session.get(OffenerPostenRow, str(posten_id))
    if row is None:
        msg = f"Offener Posten {posten_id} nicht gefunden."
        raise ValueError(msg)
    return _row_zu_posten(row)


def aktualisiere_posten(
    session: Session, posten_id: UUID, restbetrag: Decimal, status: PostenStatus
) -> None:
    row = session.get(OffenerPostenRow, str(posten_id))
    if row is None:
        msg = f"Offener Posten {posten_id} nicht gefunden."
        raise ValueError(msg)
    row.restbetrag = restbetrag
    row.status = status.value
    session.flush()


def lade_belegbuchungen(session: Session, beleg_id: UUID) -> list[Buchungssatz]:
    """Die Buchungen aus der Verbuchung eines Belegs (ohne Zahlungsbuchungen).

    Stornierte Buchungen und ihre Stornobuchungen heben sich auf und zählen nicht;
    die Neubuchung einer Korrektur zählt.
    """
    rows = (
        session.query(BuchungssatzRow)
        .filter(
            BuchungssatzRow.beleg_id == str(beleg_id),
            BuchungssatzRow.transaktion_id.is_(None),
            BuchungssatzRow.storniert_durch.is_(None),
            BuchungssatzRow.storno_von.is_(None),
        )
        .all()
    )
    return [_row_zu_buchung(r) for r in rows]


# ---------------------------------------------------------------------------
# Zahlungszuordnungen
# ---------------------------------------------------------------------------


def _row_zu_zuordnung(r: ZahlungszuordnungRow) -> Zahlungszuordnung:
    return Zahlungszuordnung(
        id=UUID(r.id),
        transaktion_id=UUID(r.transaktion_id),
        posten_id=UUID(r.posten_id),
        betrag=Decimal(str(r.betrag)),
        skonto=Decimal(str(r.skonto)),
        stufe=r.stufe,
        status=ZuordnungStatus(r.status),
        confidence=r.confidence,
        begruendung=r.begruendung,
        erstellt_am=r.erstellt_am,
    )


def speichere_zuordnung(session: Session, z: Zahlungszuordnung) -> None:
    session.add(
        ZahlungszuordnungRow(
            id=str(z.id),
            transaktion_id=str(z.transaktion_id),
            posten_id=str(z.posten_id),
            betrag=z.betrag,
            skonto=z.skonto,
            stufe=z.stufe,
            status=z.status.value,
            confidence=z.confidence,
            begruendung=z.begruendung[:500],
            erstellt_am=z.erstellt_am,
        )
    )
    session.flush()


def lade_zuordnungen(
    session: Session,
    status: set[ZuordnungStatus] | None = None,
    transaktion_praefix: str | None = None,
) -> list[Zahlungszuordnung]:
    query = session.query(ZahlungszuordnungRow).order_by(
        ZahlungszuordnungRow.erstellt_am
    )
    if status is not None:
        query = query.filter(ZahlungszuordnungRow.status.in_([s.value for s in status]))
    if transaktion_praefix is not None:
        query = query.filter(
            ZahlungszuordnungRow.transaktion_id.like(f"{transaktion_praefix}%")
        )
    return [_row_zu_zuordnung(r) for r in query.all()]


def setze_zuordnungen_status(
    session: Session, transaktion_id: UUID, status: ZuordnungStatus
) -> None:
    session.query(ZahlungszuordnungRow).filter(
        ZahlungszuordnungRow.transaktion_id == str(transaktion_id),
        ZahlungszuordnungRow.status == ZuordnungStatus.VORGESCHLAGEN.value,
    ).update({"status": status.value})
    session.flush()


def gebuchte_transaktion_ids(session: Session) -> set[UUID]:
    """Transaktionen, zu denen schon eine Buchung existiert.

    Ein Storno-Paar am selben Umsatz (Original und Stornobuchung, Baustein 7) hebt
    sich auf und zählt nicht: Nach einem reinen Storno ist der Umsatz wieder offen
    (classify, Periodenabschluss, Abschlussprüfung, Kartenabgleich). Die Neubuchung
    einer Korrektur zählt; eine Gegenbuchung an einem anderen Umsatz (Kassen-Storno)
    lässt beide Umsätze gebucht.
    """
    rows = (
        session.query(
            BuchungssatzRow.id,
            BuchungssatzRow.transaktion_id,
            BuchungssatzRow.storno_von,
        )
        .filter(BuchungssatzRow.transaktion_id.is_not(None))
        .all()
    )
    umsatz = {ident: tx for ident, tx, _ in rows}
    aufgehoben = {
        x
        for ident, tx, storno_von in rows
        if storno_von is not None and umsatz.get(storno_von) == tx
        for x in (ident, storno_von)
    }
    return {UUID(tx) for ident, tx, _ in rows if tx and ident not in aufgehoben}


# --- USt-IdNr.-Protokoll (nur anfügen) ------------------------------------------


def _row_zu_ustid(r: UstIdPruefungRow) -> UstIdPruefung:
    return UstIdPruefung.model_validate(
        {feld: getattr(r, feld) for feld in UstIdPruefung.model_fields}
    )


def speichere_ustid_pruefung(session: Session, p: UstIdPruefung) -> None:
    werte = p.model_dump()
    werte.update(
        id=str(p.id),
        kontakt_id=str(p.kontakt_id) if p.kontakt_id else None,
        art=p.art.value,
    )
    session.add(UstIdPruefungRow(**werte))
    session.flush()


def lade_ustid_pruefungen(
    session: Session, ust_id: str | None = None
) -> list[UstIdPruefung]:
    query = session.query(UstIdPruefungRow).order_by(UstIdPruefungRow.nr)
    if ust_id is not None:
        query = query.filter(UstIdPruefungRow.ust_id == ust_id)
    return [_row_zu_ustid(r) for r in query.all()]


def letzte_ustid_pruefung(session: Session) -> UstIdPruefung | None:
    r = session.query(UstIdPruefungRow).order_by(UstIdPruefungRow.nr.desc()).first()
    return _row_zu_ustid(r) if r is not None else None


# --- Belegabgleich (Baustein 5) -------------------------------------------------


def _row_zu_abgleich(r: BelegabgleichRow) -> Belegabgleich:
    return Belegabgleich(
        id=UUID(r.id),
        transaktion_id=UUID(r.transaktion_id),
        beleg_id=UUID(r.beleg_id),
        stufe=r.stufe,
        status=AbgleichStatus(r.status),
        confidence=r.confidence,
        begruendung=r.begruendung,
        differenz=Decimal(str(r.differenz)),
        erstellt_am=r.erstellt_am,
    )


def speichere_abgleich(session: Session, a: Belegabgleich) -> None:
    session.add(
        BelegabgleichRow(
            id=str(a.id),
            transaktion_id=str(a.transaktion_id),
            beleg_id=str(a.beleg_id),
            stufe=a.stufe,
            status=a.status.value,
            confidence=a.confidence,
            begruendung=a.begruendung[:500],
            differenz=a.differenz,
            erstellt_am=a.erstellt_am,
        )
    )
    session.flush()


def lade_abgleiche(
    session: Session,
    status: set[AbgleichStatus] | None = None,
    praefix: str | None = None,
) -> list[Belegabgleich]:
    query = session.query(BelegabgleichRow).order_by(BelegabgleichRow.erstellt_am)
    if status is not None:
        query = query.filter(BelegabgleichRow.status.in_([s.value for s in status]))
    if praefix is not None:
        query = query.filter(BelegabgleichRow.id.like(f"{praefix}%"))
    return [_row_zu_abgleich(r) for r in query.all()]


def setze_abgleich_status(
    session: Session, abgleich_id: UUID, status: AbgleichStatus
) -> None:
    row = session.get(BelegabgleichRow, str(abgleich_id))
    if row is None:
        raise ValueError(f"Abgleich {abgleich_id} nicht gefunden")
    row.status = status.value
    session.flush()


def gebuchte_beleg_ids(session: Session) -> set[UUID]:
    """Belege, auf die schon ein Buchungssatz zeigt."""
    rows = (
        session.query(BuchungssatzRow.beleg_id)
        .filter(BuchungssatzRow.beleg_id.is_not(None))
        .distinct()
        .all()
    )
    return {UUID(b) for (b,) in rows if b}


# --- Bankkonten (Baustein 5) ----------------------------------------------------


def vorhandene_dublettenschluessel(session: Session, schluessel: set[str]) -> set[str]:
    """Welche dieser Dublettenschlüssel stehen schon in der Datenbank?"""
    if not schluessel:
        return set()
    rows = (
        session.query(TransaktionRow.dublettenschluessel)
        .filter(TransaktionRow.dublettenschluessel.in_(list(schluessel)))
        .all()
    )
    return {s for (s,) in rows if s}


def _row_zu_bankkonto(r: BankkontoRow) -> Bankkonto:
    return Bankkonto(
        id=UUID(r.id),
        iban=r.iban,
        bezeichnung=r.bezeichnung,
        sachkonto=r.sachkonto,
        provider=r.provider,
        einstellungen=json.loads(r.einstellungen or "{}"),
        zugang=r.zugang,
        abrufstand=r.abrufstand,
        letzter_abruf=r.letzter_abruf,
        zustand=KontoZustand(r.zustand),
        meldung=r.meldung,
        erstellt_am=r.erstellt_am,
    )


def _bankkonto_werte(k: Bankkonto) -> dict[str, object]:
    return {
        "iban": k.iban,
        "bezeichnung": k.bezeichnung,
        "sachkonto": k.sachkonto,
        "provider": k.provider,
        "einstellungen": json.dumps(k.einstellungen, ensure_ascii=False),
        "zugang": k.zugang,
        "abrufstand": k.abrufstand,
        "letzter_abruf": k.letzter_abruf,
        "zustand": k.zustand.value,
        "meldung": (k.meldung or "")[:500] or None,
        "erstellt_am": k.erstellt_am,
    }


def speichere_bankkonto(session: Session, k: Bankkonto) -> None:
    try:
        with session.begin_nested():
            session.add(BankkontoRow(id=str(k.id), **_bankkonto_werte(k)))
    except IntegrityError as fehler:
        raise ValueError(f"Konto {k.iban} ist schon eingerichtet") from fehler


def aktualisiere_bankkonto(session: Session, k: Bankkonto) -> None:
    row = session.get(BankkontoRow, str(k.id))
    if row is None:
        raise ValueError(f"Konto {k.iban} nicht gefunden")
    for feld, wert in _bankkonto_werte(k).items():
        setattr(row, feld, wert)
    session.flush()


def lade_bankkonten(session: Session) -> list[Bankkonto]:
    rows = session.query(BankkontoRow).order_by(BankkontoRow.erstellt_am).all()
    return [_row_zu_bankkonto(r) for r in rows]


def lade_bankkonto(session: Session, schluessel: str) -> Bankkonto:
    """Konto über IBAN (Leerzeichen egal) oder den Anfang der ID."""
    kompakt = re.sub(r"\s", "", schluessel).upper()
    treffer = [
        k
        for k in lade_bankkonten(session)
        if k.iban == kompakt or str(k.id).startswith(schluessel.lower())
    ]
    if len(treffer) != 1:
        msg = (
            f"Kein Bankkonto '{schluessel}'"
            if not treffer
            else f"'{schluessel}' ist nicht eindeutig"
        )
        raise ValueError(msg)
    return treffer[0]
