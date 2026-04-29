"""Umsatzsteuer-Berechnung — Netto/Brutto, Steuerautomatik, Buchungssplit.

Berechnet Umsatzsteuer und Vorsteuer, erzeugt die korrekten
Steuer-Gegenbuchungen und unterstützt alle gängigen Szenarien:
- Inlandsverkauf (19%, 7%)
- Innergemeinschaftliche Lieferung (0%, Reverse Charge)
- OSS-Verkauf (Steuersatz des Bestimmungslands)
- Drittlandsverkauf (0%, Ausfuhr)
- Vorsteuerabzug aus Eingangsrechnungen
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from accounti.steuer.eu_steuersaetze import (
    EU_STEUERSAETZE,
    SteuersatzInfo,
    ist_eu_land,
    ist_oss_land,
)


class Geschaeftsvorfall(str, enum.Enum):
    """Umsatzsteuerlicher Geschäftsvorfall."""

    INLAND = "inland"                           # B2C/B2B Inland
    EU_B2C_OSS = "eu_b2c_oss"                   # B2C EU → OSS-Verfahren
    EU_B2B_REVERSE_CHARGE = "eu_b2b_rc"          # B2B EU → Reverse Charge (steuerfrei)
    EU_INNERGEMEINSCHAFTLICH = "eu_ig_lieferung"  # ig. Lieferung § 4 Nr. 1b UStG
    DRITTLAND_AUSFUHR = "drittland"              # Ausfuhr § 4 Nr. 1a UStG
    VORSTEUER = "vorsteuer"                      # Eingangsrechnung mit VSt
    STEUERFREI_INLAND = "steuerfrei"             # Steuerbefreit § 4 UStG


@dataclass
class UStPosition:
    """Eine berechnete Umsatzsteuer-Position."""

    netto: Decimal
    steuersatz: Decimal          # in Prozent (z.B. 19, 7, 22)
    steuerbetrag: Decimal
    brutto: Decimal
    geschaeftsvorfall: Geschaeftsvorfall
    bestimmungsland: str = "DE"  # ISO-Code
    steuer_konto: str = ""       # Konto für USt/VSt-Buchung (z.B. "1776")
    datev_schluessel: int | None = None  # DATEV BU-Schlüssel
    kennziffer_ust_va: int | None = None  # ELSTER-Kennziffer für USt-VA

    @property
    def ist_steuerfrei(self) -> bool:
        return self.steuersatz == Decimal("0")


# ---------------------------------------------------------------------------
# SKR03 Steuerkonten-Mapping
# ---------------------------------------------------------------------------

# Umsatzsteuer (Ausgangsrechnungen)
UST_KONTEN_SKR03: dict[str, str] = {
    "19":   "1776",   # Umsatzsteuer 19%
    "7":    "1771",   # Umsatzsteuer 7%
    "0":    "",       # Steuerfrei → kein Steuerkonto
}

# Vorsteuer (Eingangsrechnungen)
VST_KONTEN_SKR03: dict[str, str] = {
    "19":   "1576",   # Vorsteuer 19%
    "7":    "1571",   # Vorsteuer 7%
}

# OSS-Umsatzsteuerkonten (für EU-B2C)
# Im SKR03 gibt es keine Standard-OSS-Konten — die müssen angelegt werden.
# Empfohlene Konvention: 1777xx pro Land
OSS_UST_KONTEN_SKR03: dict[str, str] = {
    "FR": "177720",  # USt OSS Frankreich 20%
    "IT": "177722",  # USt OSS Italien 22%
    "ES": "177721",  # USt OSS Spanien 21%
    "NL": "177721",  # USt OSS Niederlande 21%
    "SE": "177725",  # USt OSS Schweden 25%
    "PL": "177723",  # USt OSS Polen 23%
    "AT": "177720",  # USt OSS Österreich 20%
    "BE": "177721",  # USt OSS Belgien 21%
    # Weitere Länder → config/oss_konten.yaml
}

# Erlöskonten für OSS (SKR03)
OSS_ERLOES_KONTEN_SKR03: dict[str, str] = {
    "FR": "8320",   # Erlöse OSS Frankreich
    "IT": "8321",   # Erlöse OSS Italien
    "ES": "8322",   # Erlöse OSS Spanien
    "NL": "8323",   # Erlöse OSS Niederlande
    "SE": "8324",   # Erlöse OSS Schweden
    "PL": "8325",   # Erlöse OSS Polen
    "AT": "8326",   # Erlöse OSS Österreich
    "BE": "8327",   # Erlöse OSS Belgien
    # Alternativ: Ein Sammelkonto 8320 "Erlöse OSS EU"
    # mit Aufschlüsselung per Kostenstelle/Dimension
}

# DATEV BU-Schlüssel für besondere Vorgänge
DATEV_BU_SCHLUESSEL = {
    "ust_19": 3,
    "ust_7": 2,
    "vst_19": 9,
    "vst_7": 8,
    "ig_lieferung": 40,         # Innergemeinschaftliche Lieferung
    "ig_erwerb_19": 10,         # ig. Erwerb 19% VSt + USt
    "ig_erwerb_7": 11,          # ig. Erwerb 7% VSt + USt
    "reverse_charge": 19,       # Reverse Charge § 13b
    "ausfuhr": 1,               # Steuerfreie Ausfuhr
    "oss": None,                # OSS hat keinen Standard-BU-Schlüssel
}

# ELSTER USt-VA Kennziffern
ELSTER_KENNZIFFERN = {
    "umsaetze_19": 81,          # Steuerpflichtige Umsätze 19%
    "steuer_19": None,          # Wird automatisch berechnet
    "umsaetze_7": 86,           # Steuerpflichtige Umsätze 7%
    "steuer_7": None,
    "ig_lieferung": 41,         # Innergemeinschaftliche Lieferungen
    "ausfuhr": 43,              # Ausfuhrlieferungen
    "ig_erwerb": 89,            # Innergemeinschaftliche Erwerbe
    "abziehbare_vst": 66,       # Vorsteuerbeträge
    "oss_nicht_de": None,       # OSS wird separat gemeldet (nicht in USt-VA)
}


class UStBerechner:
    """Umsatzsteuer-Berechner mit Unterstützung für alle Szenarien."""

    def __init__(
        self,
        firmen_land: str = "DE",
        oss_registriert: bool = True,
        oss_schwelle_ueberschritten: bool = True,
    ) -> None:
        """
        Args:
            firmen_land: ISO-Code des Firmensitzes
            oss_registriert: Ist die Firma für OSS registriert?
            oss_schwelle_ueberschritten: Wurde die €10.000-Schwelle überschritten?
        """
        self.firmen_land = firmen_land.upper()
        self.oss_registriert = oss_registriert
        self.oss_schwelle_ueberschritten = oss_schwelle_ueberschritten

    def _runde(self, betrag: Decimal) -> Decimal:
        """Kaufmännisch auf 2 Nachkommastellen runden."""
        return betrag.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def bestimme_vorfall(
        self,
        bestimmungsland: str,
        ist_b2b: bool = False,
        kaeufer_hat_ust_id: bool = False,
    ) -> Geschaeftsvorfall:
        """Bestimmt den umsatzsteuerlichen Geschäftsvorfall.

        Args:
            bestimmungsland: ISO-Code des Käufer-/Bestimmungslandes
            ist_b2b: Ist es ein B2B-Geschäft?
            kaeufer_hat_ust_id: Hat der Käufer eine gültige USt-ID?

        Returns:
            Der zutreffende Geschäftsvorfall
        """
        land = bestimmungsland.upper().strip()

        # Inland
        if land == self.firmen_land:
            return Geschaeftsvorfall.INLAND

        # EU-Land
        if ist_eu_land(land):
            # B2B mit USt-ID → Reverse Charge / ig. Lieferung
            if ist_b2b and kaeufer_hat_ust_id:
                return Geschaeftsvorfall.EU_INNERGEMEINSCHAFTLICH

            # B2C → OSS (wenn registriert und Schwelle überschritten)
            if self.oss_registriert and self.oss_schwelle_ueberschritten:
                return Geschaeftsvorfall.EU_B2C_OSS

            # B2C unter Schwelle → Inland-Steuersatz
            return Geschaeftsvorfall.INLAND

        # Drittland (UK, CH, US, etc.)
        return Geschaeftsvorfall.DRITTLAND_AUSFUHR

    def berechne_ust(
        self,
        netto: Decimal,
        bestimmungsland: str = "DE",
        ist_b2b: bool = False,
        kaeufer_hat_ust_id: bool = False,
        ermaessigt: bool = False,
    ) -> UStPosition:
        """Berechnet Umsatzsteuer für einen Verkauf.

        Args:
            netto: Nettobetrag
            bestimmungsland: ISO-Code Bestimmungsland
            ist_b2b: B2B-Geschäft?
            kaeufer_hat_ust_id: Käufer hat gültige USt-ID?
            ermaessigt: Ermäßigter Steuersatz?

        Returns:
            Vollständige UStPosition mit allen Buchungsinfos
        """
        vorfall = self.bestimme_vorfall(bestimmungsland, ist_b2b, kaeufer_hat_ust_id)
        land = bestimmungsland.upper().strip()

        # Steuersatz bestimmen
        steuersatz: Decimal
        steuer_konto: str
        datev_schluessel: int | None = None
        kennziffer: int | None = None

        if vorfall == Geschaeftsvorfall.INLAND:
            info = EU_STEUERSAETZE[self.firmen_land]
            steuersatz = info.ermaessigt if ermaessigt else info.normal
            schluessel = str(int(steuersatz))
            steuer_konto = UST_KONTEN_SKR03.get(schluessel, "1776")
            datev_schluessel = DATEV_BU_SCHLUESSEL.get(
                f"ust_{int(steuersatz)}", 3
            )
            kennziffer = ELSTER_KENNZIFFERN.get(
                f"umsaetze_{int(steuersatz)}", 81
            )

        elif vorfall == Geschaeftsvorfall.EU_B2C_OSS:
            info = EU_STEUERSAETZE.get(land)
            if info is None:
                msg = f"Kein Steuersatz für Land '{land}' hinterlegt"
                raise ValueError(msg)
            steuersatz = info.ermaessigt if ermaessigt else info.normal
            steuer_konto = OSS_UST_KONTEN_SKR03.get(land, "1779")
            datev_schluessel = DATEV_BU_SCHLUESSEL.get("oss")
            kennziffer = None  # OSS wird separat gemeldet

        elif vorfall in (
            Geschaeftsvorfall.EU_INNERGEMEINSCHAFTLICH,
            Geschaeftsvorfall.EU_B2B_REVERSE_CHARGE,
        ):
            steuersatz = Decimal("0")
            steuer_konto = ""
            datev_schluessel = DATEV_BU_SCHLUESSEL["ig_lieferung"]
            kennziffer = ELSTER_KENNZIFFERN["ig_lieferung"]

        elif vorfall == Geschaeftsvorfall.DRITTLAND_AUSFUHR:
            steuersatz = Decimal("0")
            steuer_konto = ""
            datev_schluessel = DATEV_BU_SCHLUESSEL["ausfuhr"]
            kennziffer = ELSTER_KENNZIFFERN["ausfuhr"]

        else:
            steuersatz = Decimal("0")
            steuer_konto = ""

        # Berechnung
        steuerbetrag = self._runde(netto * steuersatz / Decimal("100"))
        brutto = netto + steuerbetrag

        return UStPosition(
            netto=netto,
            steuersatz=steuersatz,
            steuerbetrag=steuerbetrag,
            brutto=brutto,
            geschaeftsvorfall=vorfall,
            bestimmungsland=land,
            steuer_konto=steuer_konto,
            datev_schluessel=datev_schluessel,
            kennziffer_ust_va=kennziffer,
        )

    def berechne_vst(
        self,
        brutto: Decimal,
        steuersatz: Decimal = Decimal("19"),
    ) -> UStPosition:
        """Berechnet Vorsteuer aus einer Eingangsrechnung (Brutto → Netto).

        Args:
            brutto: Bruttobetrag der Eingangsrechnung
            steuersatz: Steuersatz in Prozent

        Returns:
            UStPosition mit Netto, VSt-Betrag und Steuerkonto
        """
        faktor = Decimal("1") + steuersatz / Decimal("100")
        netto = self._runde(brutto / faktor)
        steuerbetrag = brutto - netto

        schluessel = str(int(steuersatz))
        steuer_konto = VST_KONTEN_SKR03.get(schluessel, "1576")

        return UStPosition(
            netto=netto,
            steuersatz=steuersatz,
            steuerbetrag=steuerbetrag,
            brutto=brutto,
            geschaeftsvorfall=Geschaeftsvorfall.VORSTEUER,
            bestimmungsland=self.firmen_land,
            steuer_konto=steuer_konto,
            datev_schluessel=DATEV_BU_SCHLUESSEL.get(f"vst_{int(steuersatz)}", 9),
            kennziffer_ust_va=ELSTER_KENNZIFFERN["abziehbare_vst"],
        )

    def brutto_zu_netto(
        self,
        brutto: Decimal,
        steuersatz: Decimal = Decimal("19"),
    ) -> Decimal:
        """Einfache Brutto-zu-Netto-Umrechnung."""
        faktor = Decimal("1") + steuersatz / Decimal("100")
        return self._runde(brutto / faktor)

    def netto_zu_brutto(
        self,
        netto: Decimal,
        steuersatz: Decimal = Decimal("19"),
    ) -> Decimal:
        """Einfache Netto-zu-Brutto-Umrechnung."""
        steuerbetrag = self._runde(netto * steuersatz / Decimal("100"))
        return netto + steuerbetrag
