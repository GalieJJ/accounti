"""SQLAlchemy-Tabellen (Persistenzschicht, portabel SQLite/Postgres)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Connection,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base


class TransaktionRow(Base):
    __tablename__ = "transaktionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    datum: Mapped[date] = mapped_column(Date)
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    waehrung: Mapped[str] = mapped_column(String(3), default="EUR")
    verwendungszweck: Mapped[str] = mapped_column(String(500))
    gegenkonto_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gegenkonto_iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    quelle: Mapped[str] = mapped_column(String(20))
    rohtext: Mapped[str] = mapped_column(String(2000))
    bankkonto_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    sachkonto: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dublettenschluessel: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )


class BuchungssatzRow(Base):
    __tablename__ = "buchungssaetze"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaktion_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    beleg_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # active_history: das alte Datum kennt die Sperre auch, wenn es abgelaufen war
    datum: Mapped[date] = mapped_column(Date, active_history=True)
    soll_konto: Mapped[str] = mapped_column(String(10))
    haben_konto: Mapped[str] = mapped_column(String(10))
    betrag_netto: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    steuer_schluessel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    steuer_betrag: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    buchungstext: Mapped[str] = mapped_column(String(60))
    beleg_nummer: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    geprueft_von: Mapped[str | None] = mapped_column(String(50), nullable=True)
    beleg_position_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Storno statt Änderung (Baustein 7) — eindeutig: höchstens ein Storno je Buchung.
    # Als benannter Unique-Index (ix_buchungssaetze_…), nicht als unbenannte
    # Unique-Constraint: die Migration fügt ihn per batch_alter_table hinzu.
    storniert_durch: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True, active_history=True
    )
    storno_von: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )


class BelegRow(Base):
    __tablename__ = "belege"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    belegart: Mapped[str] = mapped_column(String(20))
    richtung: Mapped[str] = mapped_column(String(10))
    belegnummer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    belegdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    leistungsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    kontakt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lieferant_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lieferant_ust_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    netto: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    steuer: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    brutto: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    waehrung: Mapped[str] = mapped_column(String(3), default="EUR")
    zahlungsziel: Mapped[date | None] = mapped_column(Date, nullable=True)
    skonto_prozent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    skonto_tage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    datei_hash: Mapped[str] = mapped_column(String(64), index=True)
    dateiname: Mapped[str] = mapped_column(String(255))
    kanal: Mapped[str] = mapped_column(String(20))
    herkunft: Mapped[str] = mapped_column(String(500))
    eingegangen_am: Mapped[datetime] = mapped_column(DateTime)
    aufbewahren_bis: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    pruef_grund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)


class BelegpositionRow(Base):
    __tablename__ = "belegpositionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    beleg_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("belege.id"), index=True
    )
    nr: Mapped[int] = mapped_column(Integer)
    bezeichnung: Mapped[str] = mapped_column(String(500))
    menge: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    netto: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    steuersatz: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    steuer_betrag: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    konto_vorschlag: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)


class BelegEingangRow(Base):
    __tablename__ = "beleg_eingaenge"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kanal: Mapped[str] = mapped_column(String(20))
    dateiname: Mapped[str] = mapped_column(String(255))
    herkunft: Mapped[str] = mapped_column(String(500))
    datei_hash: Mapped[str] = mapped_column(String(64))
    eingegangen_am: Mapped[datetime] = mapped_column(DateTime)
    ergebnis: Mapped[str] = mapped_column(String(10))
    beleg_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    hinweis: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AusgangsrechnungRow(Base):
    __tablename__ = "ausgangsrechnungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    nummer: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    kunde_name: Mapped[str] = mapped_column(String(200))
    kunde_strasse: Mapped[str | None] = mapped_column(String(200), nullable=True)
    kunde_plz: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kunde_ort: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kunde_land: Mapped[str] = mapped_column(String(2))
    kunde_ust_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kunde_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    kunde_leitweg_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kunde_privat: Mapped[bool] = mapped_column(Boolean, default=False)
    leistungsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    bestellnummer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notiz: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    skonto_prozent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    skonto_tage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rechnungsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    zahlungsziel: Mapped[date | None] = mapped_column(Date, nullable=True)
    beleg_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    datei_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pdf_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class VersandprotokollRow(Base):
    __tablename__ = "versandprotokolle"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rechnung_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ausgangsrechnungen.id"), index=True
    )
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
    weg: Mapped[str] = mapped_column(String(20))
    empfaenger: Mapped[str] = mapped_column(String(320))
    format: Mapped[str] = mapped_column(String(20))
    dateiname: Mapped[str] = mapped_column(String(255))
    datei_hash: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    erfolgreich: Mapped[bool] = mapped_column(Boolean)
    fehler: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class AusgangspositionRow(Base):
    __tablename__ = "ausgangspositionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rechnung_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ausgangsrechnungen.id"), index=True
    )
    nr: Mapped[int] = mapped_column(Integer)
    bezeichnung: Mapped[str] = mapped_column(String(500))
    menge: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    einheit: Mapped[str] = mapped_column(String(10))
    einzelpreis: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    ermaessigt: Mapped[bool] = mapped_column(Boolean, default=False)
    sonstige_leistung: Mapped[bool] = mapped_column(Boolean, default=False)


class NummernkreisRow(Base):
    """Fortlaufende Rechnungsnummern je Kreis (Gesellschaft) und Jahr."""

    __tablename__ = "nummernkreise"

    kreis: Mapped[str] = mapped_column(String(50), primary_key=True)
    jahr: Mapped[int] = mapped_column(Integer, primary_key=True)
    letzte: Mapped[int] = mapped_column(Integer)


class KontaktRow(Base):
    __tablename__ = "kontakte"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    strasse: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plz: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ort: Mapped[str | None] = mapped_column(String(100), nullable=True)
    land: Mapped[str] = mapped_column(String(2))
    ust_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    steuernummer: Mapped[str | None] = mapped_column(String(30), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    kreditor_konto: Mapped[str | None] = mapped_column(
        String(10), nullable=True, unique=True
    )
    debitor_konto: Mapped[str | None] = mapped_column(
        String(10), nullable=True, unique=True
    )
    zahlungsziel_tage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skonto_prozent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    skonto_tage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sachkonto: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    pruef_grund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class OffenerPostenRow(Base):
    __tablename__ = "offene_posten"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kontakt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kontakte.id"), index=True
    )
    # Ein Beleg wird genau einmal verbucht.
    beleg_id: Mapped[str] = mapped_column(String(36), unique=True)
    richtung: Mapped[str] = mapped_column(String(20))
    belegnummer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    belegdatum: Mapped[date] = mapped_column(Date)
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    restbetrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    faellig_am: Mapped[date] = mapped_column(Date, index=True)
    skonto_bis: Mapped[date | None] = mapped_column(Date, nullable=True)
    skonto_prozent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    skonto_betrag: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    mahnstufe: Mapped[int] = mapped_column(Integer, default=0)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class ZahlungszuordnungRow(Base):
    __tablename__ = "zahlungszuordnungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaktion_id: Mapped[str] = mapped_column(String(36), index=True)
    posten_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offene_posten.id"), index=True
    )
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    skonto: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    stufe: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    begruendung: Mapped[str] = mapped_column(String(500))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class VerrechnungRow(Base):
    """Verrechnung gegenläufiger offener Posten ohne Buchung — nur anfügen."""

    __tablename__ = "verrechnungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kontakt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kontakte.id"), index=True
    )
    posten_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offene_posten.id"), index=True
    )
    gegen_posten_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offene_posten.id"), index=True
    )
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    datum: Mapped[date] = mapped_column(Date)
    person: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class BankkontoRow(Base):
    __tablename__ = "bankkonten"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    iban: Mapped[str] = mapped_column(String(34), unique=True)
    bezeichnung: Mapped[str] = mapped_column(String(100))
    sachkonto: Mapped[str] = mapped_column(String(10))
    provider: Mapped[str] = mapped_column(String(20))
    einstellungen: Mapped[str] = mapped_column(Text)  # JSON, nicht geheim
    zugang: Mapped[str | None] = mapped_column(Text, nullable=True)  # verschlüsselt
    abrufstand: Mapped[date | None] = mapped_column(Date, nullable=True)
    letzter_abruf: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    zustand: Mapped[str] = mapped_column(String(20))
    meldung: Mapped[str | None] = mapped_column(String(500), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class BelegabgleichRow(Base):
    __tablename__ = "belegabgleiche"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaktion_id: Mapped[str] = mapped_column(String(36), index=True)
    beleg_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("belege.id"), index=True
    )
    stufe: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    begruendung: Mapped[str] = mapped_column(String(500))
    differenz: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class UnveraenderbarError(RuntimeError):
    """Ein Protokolleintrag soll geändert oder gelöscht werden."""


class UstIdPruefungRow(Base):
    """Protokoll der USt-IdNr.-Bestätigungen — nur anfügen, verkettet per Hash."""

    __tablename__ = "ustid_pruefungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nr: Mapped[int] = mapped_column(Integer, unique=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
    kontakt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("kontakte.id"), nullable=True, index=True
    )
    eigene_ust_id: Mapped[str] = mapped_column(String(20))
    ust_id: Mapped[str] = mapped_column(String(20), index=True)
    art: Mapped[str] = mapped_column(String(20))
    firmenname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strasse: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plz: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ort: Mapped[str | None] = mapped_column(String(255), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bzst_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bzst_zeitpunkt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gueltig_ab: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gueltig_bis: Mapped[str | None] = mapped_column(String(32), nullable=True)
    erg_firmenname: Mapped[str | None] = mapped_column(String(1), nullable=True)
    erg_strasse: Mapped[str | None] = mapped_column(String(1), nullable=True)
    erg_plz: Mapped[str | None] = mapped_column(String(1), nullable=True)
    erg_ort: Mapped[str | None] = mapped_column(String(1), nullable=True)
    fehler: Mapped[str | None] = mapped_column(Text, nullable=True)
    anfrage: Mapped[str] = mapped_column(Text)
    antwort: Mapped[str | None] = mapped_column(Text, nullable=True)
    aufbewahren_bis: Mapped[date] = mapped_column(Date)
    vorgaenger_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


@event.listens_for(VerrechnungRow, "before_update")
@event.listens_for(VerrechnungRow, "before_delete")
def _verrechnung_nur_anfuegen(*_: object) -> None:
    msg = "Verrechnungen sind unveränderbar — eine Gegenverrechnung neu anlegen"
    raise UnveraenderbarError(msg)


@event.listens_for(UstIdPruefungRow, "before_update")
@event.listens_for(UstIdPruefungRow, "before_delete")
def _nur_anfuegen(*_: object) -> None:
    msg = "Das USt-IdNr.-Protokoll ist unveränderbar — Einträge nur anfügen"
    raise UnveraenderbarError(msg)


# SQLite sperrt auch rohes SQL; Postgres verlässt sich auf ORM-Sperre und Hash-Kette.
USTID_TRIGGER = [
    f"CREATE TRIGGER ustid_pruefungen_kein_{aktion.lower()} BEFORE {aktion} "
    "ON ustid_pruefungen BEGIN "
    "SELECT RAISE(ABORT, 'USt-IdNr.-Protokoll ist unveränderbar'); END"
    for aktion in ("UPDATE", "DELETE")
]


@event.listens_for(UstIdPruefungRow.__table__, "after_create")
def _ustid_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in USTID_TRIGGER:
            verbindung.execute(text(sql))
