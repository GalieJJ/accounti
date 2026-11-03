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
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from accounti.steuer.eu_steuersaetze import (
    ist_eu_land,
    steuersatz_oder_none,
)


class Geschaeftsvorfall(str, enum.Enum):
    """Umsatzsteuerlicher Geschäftsvorfall."""

    INLAND = "inland"  # B2C/B2B Inland
    EU_B2C_OSS = "eu_b2c_oss"  # B2C EU → OSS-Verfahren
    EU_B2B_REVERSE_CHARGE = "eu_b2b_rc"  # B2B EU → Reverse Charge (steuerfrei)
    EU_INNERGEMEINSCHAFTLICH = "eu_ig_lieferung"  # ig. Lieferung § 4 Nr. 1b UStG
    DRITTLAND_AUSFUHR = "drittland"  # Ausfuhr § 4 Nr. 1a UStG
    NICHT_STEUERBAR = "nicht_steuerbar"  # Leistungsort im Drittland (§ 3a Abs. 2, 5)
    VORSTEUER = "vorsteuer"  # Eingangsrechnung mit VSt
    STEUERFREI_INLAND = "steuerfrei"  # Steuerbefreit § 4 UStG


@dataclass
class UStPosition:
    """Eine berechnete Umsatzsteuer-Position."""

    netto: Decimal
    steuersatz: Decimal  # in Prozent (z.B. 19, 7, 22)
    steuerbetrag: Decimal
    brutto: Decimal
    geschaeftsvorfall: Geschaeftsvorfall
    bestimmungsland: str = "DE"  # ISO-Code
    steuer_konto: str = ""  # Konto für USt/VSt-Buchung (z.B. "1776")
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
    "19": "1776",  # Umsatzsteuer 19%
    "7": "1771",  # Umsatzsteuer 7%
    "0": "",  # Steuerfrei → kein Steuerkonto
}

# Vorsteuer (Eingangsrechnungen)
VST_KONTEN_SKR03: dict[str, str] = {
    "19": "1576",  # Vorsteuer 19%
    "7": "1571",  # Vorsteuer 7%
}

# OSS-Umsatzsteuer (für EU-B2C): DATEV-Sammelkonto „Umsatzsteuer aus im anderen
# EU-Land steuerpflichtigen Lieferungen“ (SKR03 1767, SKR04 3817; Kontenrahmen 2026) —
# vierstellig, passt zur Sachkontenlänge 4 des DATEV-Stapels; das Land steht im
# Buchungstext. Eigene Konten je Land: integrationen.oss_ust_konten.
OSS_UST_KONTO_SKR03 = "1767"

# Erlöskonten für OSS (SKR03) — Vorgabe; weitere: integrationen.oss_erloes_konten
OSS_ERLOES_KONTEN_SKR03: dict[str, str] = {
    "FR": "8320",  # Erlöse OSS Frankreich
    "IT": "8321",  # Erlöse OSS Italien
    "ES": "8322",  # Erlöse OSS Spanien
    "NL": "8323",  # Erlöse OSS Niederlande
    "SE": "8324",  # Erlöse OSS Schweden
    "PL": "8325",  # Erlöse OSS Polen
    "AT": "8326",  # Erlöse OSS Österreich
    "BE": "8327",  # Erlöse OSS Belgien
    # Alternativ: Ein Sammelkonto 8320 "Erlöse OSS EU"
    # mit Aufschlüsselung per Kostenstelle/Dimension
}

# Erlöskonten für OSS (SKR04): DATEV SKR 04 4320 „Erlöse aus im anderen EU-Land
# steuerpflichtigen Lieferungen“ (Gegenstück zu SKR03 8320) — je Bestimmungsland ein
# Konto in derselben Gruppe wie im SKR03 (Konvention von accounti, Gesamttest 10b-1
# Runde 3): Die OSS-Meldung (§ 18j UStG) ordnet die Erlöse über das Konto dem Land zu
OSS_ERLOES_KONTEN_SKR04: dict[str, str] = {
    "FR": "4320",
    "IT": "4321",
    "ES": "4322",
    "NL": "4323",
    "SE": "4324",
    "PL": "4325",
    "AT": "4326",
    "BE": "4327",
}
# Gegenstück zu SKR03 1767 (DATEV-Kontenrahmen § 4 Abs. 3 EStG 2026, gleich bezeichnet)
OSS_UST_KONTO_SKR04 = "3817"


def oss_erloeskonten(kontenrahmen: str = "SKR03") -> dict[str, str]:
    """Land → OSS-Erlöskonto des Kontenrahmens (Belegbuchung, OPOS)."""
    if kontenrahmen.upper() == "SKR04":
        return dict(OSS_ERLOES_KONTEN_SKR04)
    return dict(OSS_ERLOES_KONTEN_SKR03)


def oss_konto_land(kontenrahmen: str = "SKR03") -> dict[str, str]:
    """OSS-Erlöskonto → Bestimmungsland, wie OSS-Meldung, Lieferschwelle und
    Kennziffer 45 sie lesen. Im SKR04 dazu die SKR03-Konten 8320–8327: Dort buchte die
    Marktplatz-Abrechnung (``integrationen``) bis Paket E, und dorthin legt sie, wer
    ``integrationen.oss_erloes_konten`` so setzt — die Kontenklasse 8 steht im SKR04
    zur freien Verfügung. Im SKR03 nie die SKR04-Konten (4320 ist dort
    Gewerbesteuer)."""
    konten = {konto: land for land, konto in OSS_ERLOES_KONTEN_SKR03.items()}
    if kontenrahmen.upper() == "SKR04":
        konten |= {konto: land for land, konto in OSS_ERLOES_KONTEN_SKR04.items()}
    return konten


# DATEV BU-Schlüssel für besondere Vorgänge
DATEV_BU_SCHLUESSEL = {
    "ust_19": 3,
    "ust_7": 2,
    "vst_19": 9,
    "vst_7": 8,
    "ig_lieferung": 40,  # Innergemeinschaftliche Lieferung
    "ig_erwerb_19": 19,  # ig. Erwerb 19% VSt + USt
    "ig_erwerb_7": 18,  # ig. Erwerb 7% VSt + USt
    "reverse_charge": 94,  # § 13b 19% VSt + USt (91: 7%)
    "ausfuhr": 1,  # Steuerfreie Ausfuhr
    "oss": None,  # OSS hat keinen Standard-BU-Schlüssel
}

# ELSTER USt-VA Kennziffern
ELSTER_KENNZIFFERN = {
    "umsaetze_19": 81,  # Steuerpflichtige Umsätze 19%
    "steuer_19": None,  # Wird automatisch berechnet
    "umsaetze_7": 86,  # Steuerpflichtige Umsätze 7%
    "steuer_7": None,
    "ig_lieferung": 41,  # Innergemeinschaftliche Lieferungen
    "ausfuhr": 43,  # Ausfuhrlieferungen
    "eu_sonstige_leistung": 21,  # Nicht steuerbare sonstige Leistungen (§ 18b)
    "ig_erwerb": 89,  # Innergemeinschaftliche Erwerbe
    "abziehbare_vst": 66,  # Vorsteuerbeträge
    # OSS: Steuer über die OSS-Meldung, Nettoumsatz in Kz 45 (USt 1 E 2026, Zeile 36)
    "oss_nicht_de": 45,
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
        ist_sonstige_leistung: bool = False,
        ist_elektronisch: bool = False,
    ) -> Geschaeftsvorfall:
        """Bestimmt den umsatzsteuerlichen Geschäftsvorfall.

        Args:
            bestimmungsland: ISO-Code des Käufer-/Bestimmungslandes
            ist_b2b: Ist es ein B2B-Geschäft?
            kaeufer_hat_ust_id: Hat der Käufer eine gültige USt-ID?
            ist_sonstige_leistung: Dienstleistung statt Lieferung? Bei EU-B2B
                schuldet dann der Empfänger die Steuer (§ 3a Abs. 2, Reverse Charge).
            ist_elektronisch: Telekommunikations-, Rundfunk- oder elektronisch
                erbrachte Leistung (§ 3a Abs. 5 Satz 2 UStG).

        Eine sonstige Leistung an Privatkunden wird grundsätzlich am Sitz des
        Leistenden ausgeführt (§ 3a Abs. 1 UStG) bzw. dort, wo gearbeitet wird
        (§ 3a Abs. 3 Nr. 3 Buchst. c UStG, z.B. Rahmung) — also im Inland. Nur die
        elektronischen Leistungen sind im Wohnsitzland steuerbar — weltweit nach § 3a
        Abs. 5 Satz 1 UStG: in der EU über OSS (§ 18j UStG), im Drittland nicht im
        Inland. OSS betrifft sonst nur Fernverkäufe von Waren (§ 3c UStG).
        Grenzen: die übrigen Katalogleistungen des § 3a Abs. 4 an Privatkunden im
        Drittland (z.B. Überlassung von Urheberrechten) und die Sonderorte des § 3a
        Abs. 3 (Grundstück Nr. 1, Vermietung von Beförderungsmitteln Nr. 2,
        Veranstaltungen Nr. 3 Buchst. a, Vermittlung an Privatkunden Nr. 4) sowie
        Beförderungen (§ 3b) erkennt accounti nicht — eine solche Leistung an einen
        Privatkunden gilt als im Inland ausgeführt.

        Returns:
            Der zutreffende Geschäftsvorfall
        """
        land = bestimmungsland.upper().strip()
        sonstige_leistung = ist_sonstige_leistung or ist_elektronisch

        # Inland
        if land == self.firmen_land:
            return Geschaeftsvorfall.INLAND

        # EU-Land
        if ist_eu_land(land):
            # B2B mit USt-ID → Reverse Charge (Leistung) / ig. Lieferung (Ware)
            if ist_b2b and kaeufer_hat_ust_id:
                if sonstige_leistung:
                    return Geschaeftsvorfall.EU_B2B_REVERSE_CHARGE
                return Geschaeftsvorfall.EU_INNERGEMEINSCHAFTLICH

            # B2C-Dienstleistung: Sitz des Leistenden (§ 3a Abs. 1 UStG)
            if sonstige_leistung and not ist_elektronisch:
                return Geschaeftsvorfall.INLAND

            # B2C Fernverkauf bzw. elektronische Leistung → OSS (wenn registriert)
            if self.oss_registriert and self.oss_schwelle_ueberschritten:
                return Geschaeftsvorfall.EU_B2C_OSS

            # B2C unter Schwelle → Inland-Steuersatz
            return Geschaeftsvorfall.INLAND

        # Drittland (UK, CH, US, etc.)
        if sonstige_leistung:
            if ist_b2b or ist_elektronisch:
                return Geschaeftsvorfall.NICHT_STEUERBAR  # § 3a Abs. 2 bzw. Abs. 5
            return Geschaeftsvorfall.INLAND  # § 3a Abs. 1 UStG
        return Geschaeftsvorfall.DRITTLAND_AUSFUHR

    def berechne_ust(
        self,
        netto: Decimal,
        bestimmungsland: str = "DE",
        ist_b2b: bool = False,
        kaeufer_hat_ust_id: bool = False,
        ermaessigt: bool = False,
        ist_sonstige_leistung: bool = False,
        ist_elektronisch: bool = False,
        stichtag: date | None = None,
    ) -> UStPosition:
        """Berechnet Umsatzsteuer für einen Verkauf.

        Args:
            netto: Nettobetrag
            bestimmungsland: ISO-Code Bestimmungsland
            ist_b2b: B2B-Geschäft?
            kaeufer_hat_ust_id: Käufer hat gültige USt-ID?
            ermaessigt: Ermäßigter Steuersatz?
            ist_sonstige_leistung: Dienstleistung statt Lieferung?
            stichtag: Tag der Leistung — der Steuersatz gilt an diesem Tag
                (ohne: heute)

        Returns:
            Vollständige UStPosition mit allen Buchungsinfos
        """
        vorfall = self.bestimme_vorfall(
            bestimmungsland,
            ist_b2b,
            kaeufer_hat_ust_id,
            ist_sonstige_leistung,
            ist_elektronisch,
        )
        land = bestimmungsland.upper().strip()

        # Steuersatz bestimmen
        steuersatz: Decimal
        steuer_konto: str
        datev_schluessel: int | None = None
        kennziffer: int | None = None

        if vorfall == Geschaeftsvorfall.INLAND:
            inland = steuersatz_oder_none(self.firmen_land, stichtag)
            if inland is None:
                msg = f"Kein Steuersatz für Land '{self.firmen_land}' hinterlegt"
                raise ValueError(msg)
            info = inland
            steuersatz = info.ermaessigt if ermaessigt else info.normal
            schluessel = str(int(steuersatz))
            steuer_konto = UST_KONTEN_SKR03.get(schluessel, "1776")
            datev_schluessel = DATEV_BU_SCHLUESSEL.get(f"ust_{int(steuersatz)}", 3)
            kennziffer = ELSTER_KENNZIFFERN.get(f"umsaetze_{int(steuersatz)}", 81)

        elif vorfall == Geschaeftsvorfall.EU_B2C_OSS:
            info_opt = steuersatz_oder_none(land, stichtag)
            if info_opt is None:
                msg = f"Kein Steuersatz für Land '{land}' hinterlegt"
                raise ValueError(msg)
            info = info_opt
            steuersatz = info.ermaessigt if ermaessigt else info.normal
            steuer_konto = OSS_UST_KONTO_SKR03
            datev_schluessel = DATEV_BU_SCHLUESSEL.get("oss")
            kennziffer = ELSTER_KENNZIFFERN["oss_nicht_de"]  # nur der Nettoumsatz

        elif vorfall == Geschaeftsvorfall.EU_INNERGEMEINSCHAFTLICH:
            steuersatz = Decimal("0")
            steuer_konto = ""
            datev_schluessel = DATEV_BU_SCHLUESSEL["ig_lieferung"]
            kennziffer = ELSTER_KENNZIFFERN["ig_lieferung"]

        elif vorfall == Geschaeftsvorfall.EU_B2B_REVERSE_CHARGE:
            steuersatz = Decimal("0")
            steuer_konto = ""
            kennziffer = ELSTER_KENNZIFFERN["eu_sonstige_leistung"]

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
