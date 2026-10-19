"""SQLAlchemy-Tabellen (Persistenzschicht, portabel SQLite/Postgres)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
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


class BuchungssatzRow(Base):
    __tablename__ = "buchungssaetze"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaktion_id: Mapped[str] = mapped_column(String(36))
    datum: Mapped[date] = mapped_column(Date)
    soll_konto: Mapped[str] = mapped_column(String(10))
    haben_konto: Mapped[str] = mapped_column(String(10))
    betrag_netto: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    steuer_schluessel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    steuer_betrag: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    buchungstext: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    geprueft_von: Mapped[str | None] = mapped_column(String(50), nullable=True)
    beleg_position_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


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
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


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
