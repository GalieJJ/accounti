"""accounti Datenmodell — die zentralen Entitäten der Buchhaltungspipeline."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Kontenrahmen(str, enum.Enum):
    """Unterstützte Kontenrahmen."""

    SKR03 = "SKR03"
    SKR04 = "SKR04"


class TransaktionQuelle(str, enum.Enum):
    """Herkunft einer Transaktion."""

    BANK = "bank"
    JTL_WAWI = "jtl_wawi"
    AMAZON = "amazon"
    EBAY = "ebay"
    SHOPIFY = "shopify"
    PAYPAL = "paypal"
    MANUELL = "manuell"


class BuchungStatus(str, enum.Enum):
    """Status eines Buchungssatzes in der Pipeline."""

    ENTWURF = "entwurf"  # Vom System vorgeschlagen
    AUTO_GEBUCHT = "auto"  # Automatisch gebucht (hohe Confidence)
    ZUR_PRUEFUNG = "pruefung"  # Muss vom Supervisor geprüft werden
    GEPRUEFT = "geprueft"  # Vom Supervisor bestätigt
    KORRIGIERT = "korrigiert"  # Vom Supervisor korrigiert
    EXPORTIERT = "exportiert"  # In DATEV exportiert


class Belegart(str, enum.Enum):
    """Art eines Belegs."""

    EINGANGSRECHNUNG = "eingangsrechnung"
    AUSGANGSRECHNUNG = "ausgangsrechnung"
    QUITTUNG = "quittung"
    KONTOAUSZUG = "kontoauszug"
    VERTRAG = "vertrag"
    SONSTIGES = "sonstiges"
    UNBEKANNT = "unbekannt"  # Noch nicht erkannt


class Belegrichtung(str, enum.Enum):
    """Richtung eines Belegs aus Sicht des eigenen Unternehmens."""

    EINGANG = "eingang"
    AUSGANG = "ausgang"


class BelegStatus(str, enum.Enum):
    """Status eines Belegs in der Erfassung."""

    EINGEGANGEN = "eingegangen"  # Archiviert, noch nicht gelesen
    ZUR_PRUEFUNG = "pruefung"  # Mensch muss ran, Grund steht in pruef_grund
    ERFASST = "erfasst"  # Strukturiert erfasst


class Eingangsergebnis(str, enum.Enum):
    """Ergebnis der Dublettenprüfung für einen Eingang."""

    NEU = "neu"
    DUBLETTE = "dublette"  # Verworfen, verweist auf den vorhandenen Beleg
    VERDACHT = "verdacht"  # Gespeichert, aber zur Prüfung vorgelegt


# ---------------------------------------------------------------------------
# Transaktion — Rohdaten aus Import
# ---------------------------------------------------------------------------


class Transaktion(BaseModel):
    """Eine importierte Transaktion (Bankbuchung, ERP-Vorgang, etc.)."""

    id: UUID = Field(default_factory=uuid4)
    datum: date
    betrag: Decimal = Field(description="Positiv = Einnahme, Negativ = Ausgabe")
    waehrung: str = Field(default="EUR", max_length=3)
    verwendungszweck: str
    gegenkonto_name: str | None = Field(
        default=None, description="Name des Kontoinhabers"
    )
    gegenkonto_iban: str | None = None
    quelle: TransaktionQuelle
    quelle_referenz: str | None = Field(
        default=None, description="z.B. JTL-Rechnungsnummer"
    )
    rohtext: str = Field(description="Originalzeile aus Import, für Debugging")
    importiert_am: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Beleg — Rechnung, Quittung & Co. mit ihren Positionen
# ---------------------------------------------------------------------------


class Belegposition(BaseModel):
    """Eine Position eines Belegs; kontiert wird auf Positionen, nicht auf Belegen."""

    id: UUID = Field(default_factory=uuid4)
    beleg_id: UUID
    bezeichnung: str
    menge: Decimal = Field(default=Decimal("1"))
    netto: Decimal
    steuersatz: Decimal | None = Field(default=None, description="in Prozent")
    steuer_betrag: Decimal | None = None
    konto_vorschlag: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Beleg(BaseModel):
    """Ein erfasster Beleg. Die Originaldatei liegt über datei_hash im Archiv."""

    id: UUID = Field(default_factory=uuid4)
    belegart: Belegart = Field(default=Belegart.UNBEKANNT)
    richtung: Belegrichtung = Field(default=Belegrichtung.EINGANG)
    belegnummer: str | None = Field(default=None, description="z.B. Rechnungsnummer")
    belegdatum: date | None = None
    leistungsdatum: date | None = None
    kontakt_id: UUID | None = Field(default=None, description="Kontakt (Baustein 4)")
    lieferant_name: str | None = Field(
        default=None, description="Freitext, bis Kontakte existieren"
    )
    lieferant_ust_id: str | None = None
    iban: str | None = Field(default=None, description="Bankverbindung des Ausstellers")
    netto: Decimal | None = None
    steuer: Decimal | None = None
    brutto: Decimal | None = None
    waehrung: str = Field(default="EUR", max_length=3)
    zahlungsziel: date | None = None
    skonto_prozent: Decimal | None = None
    skonto_tage: int | None = None
    datei_hash: str = Field(description="SHA-256 der Originaldatei")
    dateiname: str
    kanal: str = Field(description="Eingangskanal, z.B. 'ordner'")
    herkunft: str = Field(description="Pfad, Absender o.ä. — Hinweis, keine Logik")
    eingegangen_am: datetime = Field(default_factory=datetime.now)
    aufbewahren_bis: date
    status: BelegStatus = Field(default=BelegStatus.EINGEGANGEN)
    pruef_grund: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    positionen: list[Belegposition] = Field(default_factory=list)


class BelegEingang(BaseModel):
    """Protokolleintrag für jeden Eingang — auch für verworfene Dubletten."""

    id: UUID = Field(default_factory=uuid4)
    kanal: str
    dateiname: str
    herkunft: str
    datei_hash: str
    eingegangen_am: datetime = Field(default_factory=datetime.now)
    ergebnis: Eingangsergebnis
    beleg_id: UUID | None = Field(
        default=None, description="Neuer Beleg bzw. der vorhandene bei einer Dublette"
    )
    hinweis: str | None = None


# ---------------------------------------------------------------------------
# Ausgangsrechnung — in accounti geschrieben, als E-Rechnung ausgestellt
# ---------------------------------------------------------------------------


class AusgangsrechnungStatus(str, enum.Enum):
    ENTWURF = "entwurf"  # frei änderbar, noch ohne Nummer
    AUSGESTELLT = "ausgestellt"  # Nummer vergeben, E-Rechnung erzeugt, unveränderlich


class Rechnungsempfaenger(BaseModel):
    """Kunde einer Ausgangsrechnung (bis Debitoren aus Baustein 4 existieren)."""

    name: str
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str = Field(default="DE", min_length=2, max_length=2)
    ust_id: str | None = None
    email: str | None = Field(default=None, description="Elektronische Adresse (BT-49)")
    leitweg_id: str | None = Field(default=None, description="Käuferreferenz (BT-10)")
    privat: bool = Field(default=False, description="Verbraucher statt Unternehmen")


class AusgangsPosition(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    bezeichnung: str
    menge: Decimal = Field(default=Decimal("1"))
    einheit: str = Field(default="C62", description="UN/ECE Rec. 20, z.B. C62, HUR")
    einzelpreis: Decimal
    ermaessigt: bool = False
    sonstige_leistung: bool = Field(
        default=False, description="Dienstleistung statt Lieferung (Reverse Charge)"
    )

    @property
    def netto(self) -> Decimal:
        return (self.menge * self.einzelpreis).quantize(Decimal("0.01"))


class Ausgangsrechnung(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: AusgangsrechnungStatus = AusgangsrechnungStatus.ENTWURF
    nummer: str | None = None
    kunde: Rechnungsempfaenger
    positionen: list[AusgangsPosition] = Field(default_factory=list)
    leistungsdatum: date | None = None
    bestellnummer: str | None = None
    notiz: str | None = None
    skonto_prozent: Decimal | None = None
    skonto_tage: int | None = None
    rechnungsdatum: date | None = None
    zahlungsziel: date | None = None
    beleg_id: UUID | None = None
    datei_hash: str | None = Field(default=None, description="XRechnung im Archiv")
    pdf_hash: str | None = Field(default=None, description="ZUGFeRD-PDF im Archiv")
    erstellt_am: datetime = Field(default_factory=datetime.now)


class Versandprotokoll(BaseModel):
    """Ein Versandversuch einer Ausgangsrechnung — auch, wenn er scheiterte."""

    id: UUID = Field(default_factory=uuid4)
    rechnung_id: UUID
    zeitpunkt: datetime = Field(default_factory=datetime.now)
    weg: str = Field(description="z.B. 'email'")
    empfaenger: str
    format: str = Field(description="'zugferd' oder 'xrechnung'")
    dateiname: str
    datei_hash: str
    message_id: str | None = None
    erfolgreich: bool
    fehler: str | None = None


# ---------------------------------------------------------------------------
# Kontakte (Debitoren/Kreditoren) und offene Posten
# ---------------------------------------------------------------------------


class KontaktStatus(str, enum.Enum):
    GEPRUEFT = "geprueft"
    ZUR_PRUEFUNG = "pruefung"  # automatisch angelegt, Mensch bestätigt


class Kontakt(BaseModel):
    """Lieferant, Kunde oder beides — mit Personenkonto je Rolle."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str = Field(default="DE", min_length=2, max_length=2)
    ust_id: str | None = None
    steuernummer: str | None = None
    iban: str | None = None
    email: str | None = None
    kreditor_konto: str | None = Field(default=None, description="z.B. 70001")
    debitor_konto: str | None = Field(default=None, description="z.B. 10001")
    zahlungsziel_tage: int | None = None
    skonto_prozent: Decimal | None = None
    skonto_tage: int | None = None
    sachkonto: str | None = Field(
        default=None, description="Vorschlag für wiederkehrende Buchungen"
    )
    status: KontaktStatus = KontaktStatus.GEPRUEFT
    pruef_grund: str | None = None
    erstellt_am: datetime = Field(default_factory=datetime.now)

    @property
    def ist_kreditor(self) -> bool:
        return self.kreditor_konto is not None

    @property
    def ist_debitor(self) -> bool:
        return self.debitor_konto is not None


class PostenRichtung(str, enum.Enum):
    VERBINDLICHKEIT = "verbindlichkeit"  # Eingangsrechnung, Kreditor
    FORDERUNG = "forderung"  # Ausgangsrechnung, Debitor


class PostenStatus(str, enum.Enum):
    OFFEN = "offen"
    TEILBEZAHLT = "teilbezahlt"
    AUSGEGLICHEN = "ausgeglichen"


class OffenerPosten(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kontakt_id: UUID
    beleg_id: UUID
    richtung: PostenRichtung
    belegnummer: str | None = None
    belegdatum: date
    betrag: Decimal = Field(description="Brutto; Gutschriften negativ")
    restbetrag: Decimal
    faellig_am: date
    skonto_bis: date | None = None
    skonto_prozent: Decimal | None = None
    skonto_betrag: Decimal | None = None
    status: PostenStatus = PostenStatus.OFFEN
    mahnstufe: int = 0
    erstellt_am: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="before")
    @classmethod
    def _restbetrag(cls, daten: Any) -> Any:
        if isinstance(daten, dict) and daten.get("restbetrag") is None:
            daten = {**daten, "restbetrag": daten.get("betrag")}
        return daten


class ZuordnungStatus(str, enum.Enum):
    VORGESCHLAGEN = "vorgeschlagen"  # wartet auf Bestätigung
    GEBUCHT = "gebucht"  # Ausgleich gebucht
    ABGELEHNT = "abgelehnt"  # Transaktion geht zurück in die Kontierung


class Zahlungszuordnung(BaseModel):
    """Ein Anteil einer Banktransaktion an einem offenen Posten."""

    id: UUID = Field(default_factory=uuid4)
    transaktion_id: UUID
    posten_id: UUID
    betrag: Decimal = Field(description="gezahlt, positiv")
    skonto: Decimal = Field(default=Decimal("0"), description="abgezogen, positiv")
    stufe: str = Field(description="referenz, exakt, skonto, teil, sammel, …")
    status: ZuordnungStatus
    confidence: float = Field(ge=0.0, le=1.0)
    begruendung: str
    erstellt_am: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Konto — aus Kontenrahmen (SKR03/SKR04)
# ---------------------------------------------------------------------------


class Konto(BaseModel):
    """Ein Konto aus dem Kontenrahmen."""

    nummer: str = Field(description="z.B. '8400' oder '4970'")
    name: str = Field(description="z.B. 'Erlöse 19% USt'")
    typ: str = Field(description="aktiv, passiv, erloes, aufwand")
    kontenrahmen: Kontenrahmen
    bwa_zeile: int | None = Field(default=None, description="Zuordnung zur BWA-Zeile")
    steuer_schluessel: int | None = Field(
        default=None, description="DATEV-Steuerschlüssel"
    )
    steuer_automatik: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Buchungssatz — das Herzstück
# ---------------------------------------------------------------------------


class Buchungssatz(BaseModel):
    """Ein vollständiger Buchungssatz (Soll an Haben)."""

    id: UUID = Field(default_factory=uuid4)
    transaktion_id: UUID | None = Field(
        default=None, description="Banktransaktion (bei Bankbuchungen)"
    )
    beleg_id: UUID | None = Field(
        default=None, description="Beleg (bei Belegbuchungen)"
    )
    datum: date
    soll_konto: str = Field(description="Kontonummer Soll-Seite")
    haben_konto: str = Field(description="Kontonummer Haben-Seite")
    betrag_netto: Decimal
    steuer_schluessel: int | None = None
    steuer_betrag: Decimal | None = None
    buchungstext: str = Field(description="Kurztext für den Buchungssatz")
    beleg_nummer: str | None = None
    beleg_position_id: UUID | None = Field(
        default=None, description="Belegposition, auf die diese Buchung zeigt"
    )
    kostenstelle: str | None = None
    status: BuchungStatus = Field(default=BuchungStatus.ENTWURF)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence der KI-Klassifikation (0.0-1.0)",
    )
    erstellt_am: datetime = Field(default_factory=datetime.now)
    geprueft_am: datetime | None = None
    geprueft_von: str | None = None


# ---------------------------------------------------------------------------
# Klassifikationsergebnis — Ausgabe der KI-Engine
# ---------------------------------------------------------------------------


class Klassifikationsergebnis(BaseModel):
    """Ergebnis der KI-Kontierung für eine Transaktion."""

    transaktion_id: UUID
    soll_konto: str
    haben_konto: str
    steuer_schluessel: int | None = None
    buchungstext: str
    confidence: float = Field(ge=0.0, le=1.0)
    begruendung: str = Field(
        description="Erklärung der KI warum dieses Konto gewählt wurde"
    )
    quelle: str = Field(description="'regelwerk' oder 'llm'")


# ---------------------------------------------------------------------------
# BWA-Zeile
# ---------------------------------------------------------------------------


class BWAZeile(BaseModel):
    """Eine Zeile der Betriebswirtschaftlichen Auswertung."""

    nummer: int
    bezeichnung: str
    betrag_aktuell: Decimal = Field(default=Decimal("0.00"))
    betrag_vorjahr: Decimal | None = None
    betrag_kumuliert: Decimal = Field(default=Decimal("0.00"))


class BWA(BaseModel):
    """Vollständige Betriebswirtschaftliche Auswertung."""

    mandant: str
    zeitraum: str = Field(description="z.B. '2026-04'")
    kontenrahmen: Kontenrahmen
    zeilen: list[BWAZeile] = Field(default_factory=list)
    erstellt_am: datetime = Field(default_factory=datetime.now)
