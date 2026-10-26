"""Zwischenmodell nach EN 16931 — alle Formate werden hierauf abgebildet.

Die BT-Nummern verweisen auf die Business Terms der Norm. Die restliche Anwendung
kennt nur dieses Modell, nie UBL oder CII.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


class ERechnungError(ValueError):
    """Die Datei ist keine lesbare E-Rechnung."""


class Profil(str, enum.Enum):
    MINIMUM = "minimum"
    BASIC_WL = "basic_wl"
    BASIC = "basic"
    EN16931 = "en16931"
    EXTENDED = "extended"
    XRECHNUNG = "xrechnung"
    UNBEKANNT = "unbekannt"

    @property
    def reduziert(self) -> bool:
        """MINIMUM und BASIC WL: keine Positionen, keine E-Rechnung nach § 14 UStG."""
        return self in (Profil.MINIMUM, Profil.BASIC_WL)


def erkenne_profil(spezifikation: str | None) -> Profil:
    """Profil aus der Spezifikationskennung (BT-24)."""
    s = (spezifikation or "").lower()
    if "xrechnung" in s:
        return Profil.XRECHNUNG
    if "minimum" in s:
        return Profil.MINIMUM
    if "basicwl" in s:
        return Profil.BASIC_WL
    if "basic" in s:
        return Profil.BASIC
    if "extended" in s:
        return Profil.EXTENDED
    if s.startswith("urn:cen.eu:en16931:2017"):
        return Profil.EN16931
    return Profil.UNBEKANNT


@dataclass
class Anschrift:
    strasse: str | None = None  # BT-35 / BT-50
    plz: str | None = None  # BT-38 / BT-53
    ort: str | None = None  # BT-37 / BT-52
    land: str | None = None  # BT-40 / BT-55


@dataclass
class Partei:
    name: str | None = None  # BT-27 / BT-44
    ust_id: str | None = None  # BT-31 / BT-48
    steuernummer: str | None = None  # BT-32
    anschrift: Anschrift = field(default_factory=Anschrift)
    email: str | None = None  # BT-34 / BT-49 (elektronische Adresse)
    kontakt_name: str | None = None  # BT-41
    kontakt_telefon: str | None = None  # BT-42
    kontakt_email: str | None = None  # BT-43


@dataclass
class Rechnungszeile:
    id: str | None  # BT-126
    bezeichnung: str | None  # BT-153
    menge: Decimal | None  # BT-129
    einheit: str | None  # BT-130
    einzelpreis: Decimal | None  # BT-146
    netto: Decimal | None  # BT-131
    steuerkategorie: str | None  # BT-151
    steuersatz: Decimal | None  # BT-152


@dataclass
class ZuAbschlag:
    """Nachlass (BG-20) oder Zuschlag (BG-21) auf Belegebene."""

    zuschlag: bool
    betrag: Decimal | None  # BT-92 / BT-99
    grund: str | None  # BT-97 / BT-104
    steuerkategorie: str | None  # BT-95 / BT-102
    steuersatz: Decimal | None  # BT-96 / BT-103


@dataclass
class Steueraufschluesselung:
    """BG-23: eine Zeile je Steuerkategorie und Satz."""

    kategorie: str | None  # BT-118
    satz: Decimal | None  # BT-119
    basis: Decimal | None  # BT-116
    betrag: Decimal | None  # BT-117
    befreiungsgrund: str | None = None  # BT-120
    befreiungsgrund_code: str | None = None  # BT-121 (z.B. VATEX-EU-AE)


@dataclass
class Summen:
    positionen_netto: Decimal | None = None  # BT-106
    abschlaege: Decimal | None = None  # BT-107
    zuschlaege: Decimal | None = None  # BT-108
    netto: Decimal | None = None  # BT-109
    steuer: Decimal | None = None  # BT-110
    brutto: Decimal | None = None  # BT-112
    vorauszahlung: Decimal | None = None  # BT-113
    rundung: Decimal | None = None  # BT-114
    zahlbetrag: Decimal | None = None  # BT-115


_SKONTO = re.compile(r"#SKONTO#TAGE=(\d+)#PROZENT=(\d+(?:\.\d+)?)#", re.IGNORECASE)


@dataclass
class Rechnung:
    syntax: str  # "CII" oder "UBL"
    spezifikation: str | None = None  # BT-24
    nummer: str | None = None  # BT-1
    datum: date | None = None  # BT-2
    typ: str | None = None  # BT-3 (380 Rechnung, 381 Gutschrift, 384 Korrektur …)
    waehrung: str | None = None  # BT-5
    faellig: date | None = None  # BT-9
    kaeufer_referenz: str | None = None  # BT-10 (Leitweg-ID)
    bestellnummer: str | None = None  # BT-13
    vorgaenger_nummer: str | None = None  # BT-25 (Bezug einer Gutschrift/Korrektur)
    vorgaenger_datum: date | None = None  # BT-26
    notizen: list[str] = field(default_factory=list)  # BT-22
    leistungsdatum: date | None = None  # BT-72
    leistungszeitraum_von: date | None = None  # BT-73
    leistungszeitraum_bis: date | None = None  # BT-74
    lieferanschrift: Anschrift | None = None  # BG-15 (BT-75, BT-77, BT-78, BT-80)
    verkaeufer: Partei = field(default_factory=Partei)
    kaeufer: Partei = field(default_factory=Partei)
    zahlungsart: str | None = None  # BT-81
    iban: str | None = None  # BT-84
    zahlungsbedingungen: str | None = None  # BT-20
    zeilen: list[Rechnungszeile] = field(default_factory=list)
    zu_abschlaege: list[ZuAbschlag] = field(default_factory=list)
    steuern: list[Steueraufschluesselung] = field(default_factory=list)
    summen: Summen = field(default_factory=Summen)

    @property
    def profil(self) -> Profil:
        return erkenne_profil(self.spezifikation)

    @property
    def erweitert(self) -> bool:
        """Extension-Profile (``#conformant#``) dürfen über EN 16931 hinausgehen."""
        return "#conformant#" in (self.spezifikation or "")

    @property
    def skonto(self) -> tuple[Decimal, int] | None:
        """(Prozent, Tage) nach der XRechnung-Konvention in BT-20."""
        m = _SKONTO.search(self.zahlungsbedingungen or "")
        return (Decimal(m.group(2)), int(m.group(1))) if m else None
