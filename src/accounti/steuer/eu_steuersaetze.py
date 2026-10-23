"""EU-Umsatzsteuersätze — alle 27 Mitgliedsstaaten + UK (post-Brexit), mit Verlauf.

Jeder Stand eines Landes trägt ``gueltig_ab``: maßgeblich ist der Satz, der am Tag der
Leistung gilt (Art. 63, 93 MwStSystRL; im OSS-Verfahren der Satz des
Bestimmungslands am Tag der Lieferung). ``steuersatz_fuer_land(land, stichtag)``
wählt den Stand; ohne Stichtag gilt der heutige. Der erste Stand eines Landes
(``gueltig_ab=None``) gilt bis zur ersten hinterlegten Änderung — ältere
Rechtsstände sind nicht hinterlegt (die Tabelle deckt Leistungen ab 2025 ab).

Geprüft am 22.10.2026 gegen die EU-Tabelle „Your Europe — VAT rates“ (Stand
13.07.2026) und die nationalen Quellen je Änderung (siehe ``quelle``). Ändert ein
Land seine Sätze, wird ein neuer Stand mit ``gueltig_ab`` angefügt — nie ein alter
überschrieben, sonst rechneten Korrekturen früherer Zeiträume mit dem neuen Satz.

Eine Konfigurationsdatei, die diese Sätze überschreibt, gibt es nicht: die Sätze
gehen direkt in die OSS-Buchung und -Meldung, und eine vom Arbeitsverzeichnis
abhängige Datei rechnete im geplanten Lauf anders als im Aufruf von Hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class SteuersatzInfo:
    """Steuersätze eines Landes ab einem Tag."""

    land_code: str  # ISO 3166-1 alpha-2 (z.B. "DE", "FR")
    land_name: str  # Deutscher Name
    land_name_en: str  # Englischer Name
    normal: Decimal  # Normalsatz in Prozent
    ermaessigt: Decimal  # Ermäßigter Satz (erster, häufigster; OSS-„ermäßigt“)
    ermaessigt_2: Decimal | None = None  # Zweiter ermäßigter Satz (falls vorhanden)
    super_ermaessigt: Decimal | None = None  # Super-ermäßigter Satz
    nullsatz: bool = True  # Gibt es einen 0%-Satz?
    waehrung: str = "EUR"  # Landeswährung
    eu_mitglied: bool = True
    oss_faehig: bool = True  # Am OSS-Verfahren teilnehmend
    parksatz: Decimal | None = None  # Zwischensatz (Art. 118 MwStSystRL), z.B. LU 14
    weitere: tuple[Decimal, ...] = ()  # weitere ermäßigte Sätze
    gueltig_ab: date | None = None  # None: bis zur ersten hinterlegten Änderung
    quelle: str = ""

    @property
    def normal_faktor(self) -> Decimal:
        """Steuerfaktor für Berechnungen (z.B. 0.19 für 19%)."""
        return self.normal / Decimal("100")

    @property
    def ermaessigt_faktor(self) -> Decimal:
        return self.ermaessigt / Decimal("100")

    @property
    def saetze(self) -> frozenset[Decimal]:
        """Alle Sätze dieses Stands (ohne 0 %)."""
        return frozenset(
            s
            for s in (
                self.normal,
                self.ermaessigt,
                self.ermaessigt_2,
                self.super_ermaessigt,
                self.parksatz,
                *self.weitere,
            )
            if s is not None
        )


D = Decimal
_YOUR_EUROPE = "EU Your Europe, VAT rates (Stand 13.07.2026)"


def _land(
    code: str, name: str, name_en: str, *staende: dict[str, object]
) -> tuple[SteuersatzInfo, ...]:
    """Stände eines Landes, aufsteigend nach ``gueltig_ab``; Felder des Vorgängers
    gelten weiter, soweit ein Stand sie nicht ändert."""
    ergebnis: list[SteuersatzInfo] = []
    werte: dict[str, object] = {}
    for stand in staende:
        werte = {**werte, **stand}
        ergebnis.append(
            SteuersatzInfo(
                land_code=code,
                land_name=name,
                land_name_en=name_en,
                **werte,  # type: ignore[arg-type]
            )
        )
    return tuple(ergebnis)


# Land → Stände, aufsteigend nach gueltig_ab (der erste ohne Datum)
EU_STEUERSAETZE_VERLAUF: dict[str, tuple[SteuersatzInfo, ...]] = {
    # --- Westeuropa ---
    "DE": _land(
        "DE", "Deutschland", "Germany", {"normal": D("19"), "ermaessigt": D("7")}
    ),
    "FR": _land(
        "FR",
        "Frankreich",
        "France",
        {
            "normal": D("20"),
            "ermaessigt": D("5.5"),
            "ermaessigt_2": D("10"),
            "super_ermaessigt": D("2.1"),
        },
    ),
    "NL": _land(
        "NL", "Niederlande", "Netherlands", {"normal": D("21"), "ermaessigt": D("9")}
    ),
    "BE": _land(
        "BE",
        "Belgien",
        "Belgium",
        {"normal": D("21"), "ermaessigt": D("6"), "ermaessigt_2": D("12")},
    ),
    "LU": _land(
        "LU",
        "Luxemburg",
        "Luxembourg",
        {
            "normal": D("17"),
            "ermaessigt": D("8"),
            "super_ermaessigt": D("3"),
            "parksatz": D("14"),
            "quelle": _YOUR_EUROPE,
        },
    ),
    "AT": _land(
        "AT",
        "Österreich",
        "Austria",
        {"normal": D("20"), "ermaessigt": D("10"), "ermaessigt_2": D("13")},
    ),
    "IE": _land(
        "IE",
        "Irland",
        "Ireland",
        {
            "normal": D("23"),
            "ermaessigt": D("13.5"),
            "ermaessigt_2": D("9"),
            "super_ermaessigt": D("4.8"),
        },
    ),
    # --- Südeuropa ---
    "IT": _land(
        "IT",
        "Italien",
        "Italy",
        {
            "normal": D("22"),
            "ermaessigt": D("10"),
            "ermaessigt_2": D("5"),
            "super_ermaessigt": D("4"),
        },
    ),
    "ES": _land(
        "ES",
        "Spanien",
        "Spain",
        {"normal": D("21"), "ermaessigt": D("10"), "super_ermaessigt": D("4")},
    ),
    "PT": _land(
        "PT",
        "Portugal",
        "Portugal",
        {"normal": D("23"), "ermaessigt": D("13"), "ermaessigt_2": D("6")},
    ),
    "GR": _land(
        "GR",
        "Griechenland",
        "Greece",
        {"normal": D("24"), "ermaessigt": D("13"), "ermaessigt_2": D("6")},
    ),
    "MT": _land(
        "MT",
        "Malta",
        "Malta",
        {"normal": D("18"), "ermaessigt": D("7"), "ermaessigt_2": D("5")},
        {
            "gueltig_ab": date(2024, 1, 1),
            "parksatz": D("12"),
            "quelle": "Legal Notice 231/2023 (12 % ab 01.01.2024); " + _YOUR_EUROPE,
        },
    ),
    "CY": _land(
        "CY",
        "Zypern",
        "Cyprus",
        {
            "normal": D("19"),
            "ermaessigt": D("9"),
            "ermaessigt_2": D("5"),
            "super_ermaessigt": D("3"),
        },
    ),
    "HR": _land(
        "HR",
        "Kroatien",
        "Croatia",
        {"normal": D("25"), "ermaessigt": D("13"), "ermaessigt_2": D("5")},
    ),
    "SI": _land(
        "SI",
        "Slowenien",
        "Slovenia",
        {"normal": D("22"), "ermaessigt": D("9.5"), "ermaessigt_2": D("5")},
    ),
    # --- Nordeuropa ---
    "SE": _land(
        "SE",
        "Schweden",
        "Sweden",
        {
            "normal": D("25"),
            "ermaessigt": D("12"),
            "ermaessigt_2": D("6"),
            "waehrung": "SEK",
        },
    ),
    "DK": _land(
        "DK",
        "Dänemark",
        "Denmark",
        {"normal": D("25"), "ermaessigt": D("0"), "waehrung": "DKK"},
    ),
    "FI": _land(
        "FI",
        "Finnland",
        "Finland",
        {"normal": D("24"), "ermaessigt": D("14"), "ermaessigt_2": D("10")},
        {
            "gueltig_ab": date(2024, 9, 1),
            "normal": D("25.5"),
            "quelle": "vero.fi, Normalsatz 25,5 % ab 01.09.2024",
        },
        {
            "gueltig_ab": date(2026, 1, 1),
            "ermaessigt": D("13.5"),
            "quelle": "vero.fi „The changes to VAT rates“ (13,5 % ab 01.01.2026); "
            + _YOUR_EUROPE,
        },
    ),
    # --- Osteuropa ---
    "PL": _land(
        "PL",
        "Polen",
        "Poland",
        {
            "normal": D("23"),
            "ermaessigt": D("8"),
            "ermaessigt_2": D("5"),
            "waehrung": "PLN",
        },
    ),
    "CZ": _land(
        "CZ",
        "Tschechien",
        "Czech Republic",
        {"normal": D("21"), "ermaessigt": D("12"), "waehrung": "CZK"},
    ),
    "SK": _land(
        "SK",
        "Slowakei",
        "Slovakia",
        {"normal": D("20"), "ermaessigt": D("10"), "ermaessigt_2": D("5")},
        {
            "gueltig_ab": date(2025, 1, 1),
            "normal": D("23"),
            "ermaessigt": D("19"),
            "quelle": "Konsolidierungspaket 2025, 10 % abgeschafft (PwC SK, Accace); "
            + _YOUR_EUROPE,
        },
    ),
    "HU": _land(
        "HU",
        "Ungarn",
        "Hungary",
        {
            "normal": D("27"),
            "ermaessigt": D("18"),
            "ermaessigt_2": D("5"),
            "waehrung": "HUF",
        },
    ),
    "RO": _land(
        "RO",
        "Rumänien",
        "Romania",
        {
            "normal": D("19"),
            "ermaessigt": D("9"),
            "ermaessigt_2": D("5"),
            "waehrung": "RON",
        },
        {
            "gueltig_ab": date(2025, 8, 1),
            "normal": D("21"),
            "ermaessigt": D("11"),
            "ermaessigt_2": None,
            "quelle": "Gesetz 141/2025, MO 699 v. 25.07.2025 (5 % und 9 % "
            "abgeschafft); " + _YOUR_EUROPE,
        },
    ),
    "BG": _land(
        "BG",
        "Bulgarien",
        "Bulgaria",
        {"normal": D("20"), "ermaessigt": D("9"), "waehrung": "BGN"},
        {
            "gueltig_ab": date(2026, 1, 1),
            "waehrung": "EUR",
            "quelle": "EU Access2Markets: Bulgaria adopts euro as of 1 January 2026",
        },
    ),
    # --- Baltikum ---
    "EE": _land(
        "EE",
        "Estland",
        "Estonia",
        {"normal": D("22"), "ermaessigt": D("9"), "ermaessigt_2": D("5")},
        {
            "gueltig_ab": date(2025, 1, 1),
            "ermaessigt_2": D("13"),
            "quelle": "EMTA: Beherbergung 13 %, Presse 9 % ab 01.01.2025",
        },
        {
            "gueltig_ab": date(2025, 7, 1),
            "normal": D("24"),
            "quelle": "EMTA: Normalsatz 24 % ab 01.07.2025; " + _YOUR_EUROPE,
        },
    ),
    "LV": _land(
        "LV",
        "Lettland",
        "Latvia",
        {"normal": D("21"), "ermaessigt": D("12"), "ermaessigt_2": D("5")},
    ),
    "LT": _land(
        "LT",
        "Litauen",
        "Lithuania",
        {"normal": D("21"), "ermaessigt": D("9"), "ermaessigt_2": D("5")},
        {
            "gueltig_ab": date(2026, 1, 1),
            "ermaessigt": D("12"),
            "quelle": "Seimas, Gesetz XV-287 (9 % abgeschafft, 12 % ab 01.01.2026); "
            + _YOUR_EUROPE,
        },
    ),
    # --- UK (post-Brexit, kein OSS) ---
    "GB": _land(
        "GB",
        "Vereinigtes Königreich",
        "United Kingdom",
        {
            "normal": D("20"),
            "ermaessigt": D("5"),
            "waehrung": "GBP",
            "eu_mitglied": False,
            "oss_faehig": False,
        },
    ),
}

# Neuester hinterlegter Stand je Land — für Namen, Mitgliedschaft und Währung. Wer
# Steuer rechnet oder Sätze prüft, nimmt ``steuersatz_fuer_land(land, stichtag)``.
EU_STEUERSAETZE: dict[str, SteuersatzInfo] = {
    code: staende[-1] for code, staende in EU_STEUERSAETZE_VERLAUF.items()
}


def steuersatz_fuer_land(
    land_code: str, stichtag: date | None = None
) -> SteuersatzInfo:
    """Steuersätze eines Landes am ``stichtag`` (Tag der Leistung; ohne: heute).

    Raises:
        KeyError: Wenn der Ländercode unbekannt ist.
    """
    code = land_code.upper().strip()
    staende = EU_STEUERSAETZE_VERLAUF.get(code)
    if staende is None:
        verfuegbar = ", ".join(sorted(EU_STEUERSAETZE_VERLAUF))
        msg = f"Unbekannter Ländercode: '{code}'. Verfügbar: {verfuegbar}"
        raise KeyError(msg)
    tag = stichtag or date.today()
    gueltig = staende[0]
    for stand in staende[1:]:
        if stand.gueltig_ab is not None and stand.gueltig_ab <= tag:
            gueltig = stand
    return gueltig


def steuersatz_oder_none(
    land_code: str, stichtag: date | None = None
) -> SteuersatzInfo | None:
    """Wie ``steuersatz_fuer_land``, unbekanntes Land → ``None``."""
    try:
        return steuersatz_fuer_land(land_code, stichtag)
    except KeyError:
        return None


def ist_eu_land(land_code: str) -> bool:
    """Prüft ob ein Land EU-Mitglied ist."""
    info = EU_STEUERSAETZE.get(land_code.upper().strip())
    return info is not None and info.eu_mitglied


def ist_oss_land(land_code: str) -> bool:
    """Prüft ob ein Land am OSS-Verfahren teilnimmt."""
    info = EU_STEUERSAETZE.get(land_code.upper().strip())
    return info is not None and info.oss_faehig
