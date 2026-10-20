"""Domänenmodelle für Marktplatz- und Zahlungsdienstleister-Abrechnungen (Baustein 11).

Eine *Abrechnung* ist ein Abrechnungszeitraum mit genau einem Abgleichspunkt: bei Amazon
eine Settlement-ID, bei eBay und Shopify eine Auszahlung, bei PayPal der Zeitraum der
Datei (PayPal ist ein eigenes Konto mit Guthaben). Ihre *Posten* sind die einzelnen
Bestandteile — Erlöse, Erstattungen, Gebühren, Einbehalte, Auszahlungen —, jeweils mit
Vorzeichen aus Sicht des Guthabens beim Marktplatz: positiv erhöht das Guthaben.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Postenart(str, enum.Enum):
    """Was ein Posten einer Abrechnung ist."""

    ERLOES = "erloes"  # Verkauf: Artikel, Versand, Geschenkverpackung, Rabatt (brutto)
    ERSTATTUNG = "erstattung"  # Rückerstattung an den Käufer (brutto, negativ)
    GEBUEHR = "gebuehr"  # Gebühr des Marktplatzes (negativ; Rückvergütung positiv)
    WERBUNG = "werbung"  # Werbekosten, mit dem Guthaben verrechnet
    EINBEHALT = "einbehalt"  # Reserve: negativ einbehalten, positiv freigegeben
    ERSATZ = "ersatz"  # Ersatzleistung des Marktplatzes (z.B. verlorene Ware)
    AUSZAHLUNG = "auszahlung"  # Überweisung an die Bank (negativ)
    EINZAHLUNG = "einzahlung"  # Überweisung von der Bank (PayPal, positiv)
    UMRECHNUNG = "umrechnung"  # Währungsumrechnung (PayPal) — wird nicht gebucht
    ZAHLUNG = "zahlung"  # PayPal: Einkauf o.ä. — läuft durch die normale Kontierung
    SONSTIGES = "sonstiges"  # unbekannt oder Korrektur — gebucht, aber zur Prüfung


class Gebuehrenart(str, enum.Enum):
    """Wofür eine Gebühr anfällt — bestimmt das Aufwandskonto."""

    VERKAUF = "verkauf"  # Verkaufsprovision
    VERSAND = "versand"  # Versand-/Fulfillment-Gebühr, Versandetikett
    LAGER = "lager"  # Lagergebühr
    ZAHLUNG = "zahlung"  # Gebühr für die Zahlungsabwicklung
    SONSTIGE = "sonstige"  # Grundgebühr, Abo, sonstige


class Schweregrad(str, enum.Enum):
    FEHLER = "fehler"  # Zahlen stimmen nicht — Mensch muss ran
    WARNUNG = "warnung"  # gebucht, aber zur Prüfung
    HINWEIS = "hinweis"  # zur Kenntnis


class AbrechnungStatus(str, enum.Enum):
    GEBUCHT = "gebucht"  # Posten gebucht, Auszahlung noch nicht auf der Bank gefunden
    ABGEGLICHEN = "abgeglichen"  # Auszahlung(en) gegen die Bank abgeglichen
    ABWEICHUNG = "abweichung"  # mindestens ein Fehler-Befund


class Befund(BaseModel):
    """Eine Feststellung zu einer Abrechnung — die Grundlage für Baustein 7."""

    id: UUID = Field(default_factory=uuid4)
    code: str = Field(description="z.B. summe_abweichung, land_fehlt")
    schweregrad: Schweregrad
    text: str
    posten_nr: int | None = None
    erstellt_am: datetime = Field(default_factory=datetime.now)


class Laenderangabe(BaseModel):
    """Bestimmungsland (und mehr) zu einer Bestellnummer, aus einem Zusatzbericht."""

    bestellnummer: str
    bestimmungsland: str | None = None
    abgangsland: str | None = None
    kaeufer_ust_id: str | None = None


class Marktplatzposten(BaseModel):
    """Ein Bestandteil einer Abrechnung, Vorzeichen aus Sicht des Guthabens."""

    id: UUID = Field(default_factory=uuid4)
    nr: int = Field(description="Zeile in der Datei")
    art: Postenart
    datum: date
    betrag: Decimal
    waehrung: str = Field(default="EUR", max_length=3)
    betrag_eur: Decimal | None = Field(
        default=None, description="Auszahlung in EUR bei Fremdwährung (nach Kurs)"
    )
    beschreibung: str = ""
    gebuehrenart: Gebuehrenart | None = None
    bestellnummer: str | None = None
    artikel: str | None = Field(default=None, description="SKU/Artikelnummer")
    bestimmungsland: str | None = Field(default=None, min_length=2, max_length=2)
    abgangsland: str | None = Field(default=None, min_length=2, max_length=2)
    kaeufer_ust_id: str | None = None
    auszahlungs_nr: str | None = None
    referenz: str | None = Field(
        default=None, description="PayPal: Transaktionscode der Guthabenbewegung"
    )
    gegenpartei: str | None = None
    bank_transaktion_id: UUID | None = Field(
        default=None, description="Bankumsatz der Auszahlung (nach dem Abgleich)"
    )


class Abrechnung(BaseModel):
    """Ein Abrechnungszeitraum eines Marktplatzes mit seinen Posten."""

    id: UUID = Field(default_factory=uuid4)
    marktplatz: str = Field(description="amazon, ebay, paypal, shopify")
    nummer: str = Field(description="Settlement-ID, Auszahlungsnummer, Zeitraum")
    von: date
    bis: date
    auszahlungsdatum: date | None = None
    waehrung: str = Field(default="EUR", max_length=3)
    auszahlung: Decimal | None = Field(
        default=None, description="Auszahlung laut Bericht (None: steht nicht drin)"
    )
    kurs: Decimal | None = Field(
        default=None, description="Einheiten Fremdwährung je 1 EUR"
    )
    anfangssaldo: Decimal | None = Field(default=None, description="PayPal-Guthaben")
    endsaldo: Decimal | None = None
    dateiname: str = ""
    beleg_id: UUID | None = None
    status: AbrechnungStatus = AbrechnungStatus.GEBUCHT
    importiert_am: datetime = Field(default_factory=datetime.now)
    posten: list[Marktplatzposten] = Field(default_factory=list)
    befunde: list[Befund] = Field(default_factory=list)

    def summe(self, *arten: Postenart) -> Decimal:
        """Summe der Posten (ohne Angabe: aller Posten)."""
        return sum(
            (p.betrag for p in self.posten if not arten or p.art in arten),
            Decimal("0"),
        )
