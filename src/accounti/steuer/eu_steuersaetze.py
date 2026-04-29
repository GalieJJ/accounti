"""EU-Umsatzsteuersätze — alle 27 Mitgliedsstaaten + UK (post-Brexit).

Stand: 2026. Wird als YAML-Override ergänzbar sein.
Quellen:
- https://ec.europa.eu/taxation_customs/tedb/
- https://europa.eu/youreurope/business/taxation/vat/vat-rules-rates/

Hinweis: Sätze ändern sich gelegentlich. Die YAML-Config
(config/eu_steuersaetze.yaml) hat Vorrang vor diesen Defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SteuersatzInfo:
    """Steuersatzinformation für ein Land."""

    land_code: str          # ISO 3166-1 alpha-2 (z.B. "DE", "FR")
    land_name: str          # Deutscher Name
    land_name_en: str       # Englischer Name
    normal: Decimal         # Normalsatz in Prozent
    ermaessigt: Decimal     # Ermäßigter Satz (erster, häufigster)
    ermaessigt_2: Decimal | None = None  # Zweiter ermäßigter Satz (falls vorhanden)
    super_ermaessigt: Decimal | None = None  # Super-ermäßigter Satz
    nullsatz: bool = True   # Gibt es einen 0%-Satz?
    waehrung: str = "EUR"   # Landeswährung
    eu_mitglied: bool = True
    oss_faehig: bool = True  # Am OSS-Verfahren teilnehmend

    @property
    def normal_faktor(self) -> Decimal:
        """Steuerfaktor für Berechnungen (z.B. 0.19 für 19%)."""
        return self.normal / Decimal("100")

    @property
    def ermaessigt_faktor(self) -> Decimal:
        return self.ermaessigt / Decimal("100")


# ---------------------------------------------------------------------------
# EU-27 + UK Steuersätze (Stand 2026)
# ---------------------------------------------------------------------------

EU_STEUERSAETZE: dict[str, SteuersatzInfo] = {
    # --- Westeuropa ---
    "DE": SteuersatzInfo(
        land_code="DE", land_name="Deutschland", land_name_en="Germany",
        normal=Decimal("19"), ermaessigt=Decimal("7"),
    ),
    "FR": SteuersatzInfo(
        land_code="FR", land_name="Frankreich", land_name_en="France",
        normal=Decimal("20"), ermaessigt=Decimal("5.5"),
        ermaessigt_2=Decimal("10"), super_ermaessigt=Decimal("2.1"),
    ),
    "NL": SteuersatzInfo(
        land_code="NL", land_name="Niederlande", land_name_en="Netherlands",
        normal=Decimal("21"), ermaessigt=Decimal("9"),
    ),
    "BE": SteuersatzInfo(
        land_code="BE", land_name="Belgien", land_name_en="Belgium",
        normal=Decimal("21"), ermaessigt=Decimal("6"),
        ermaessigt_2=Decimal("12"),
    ),
    "LU": SteuersatzInfo(
        land_code="LU", land_name="Luxemburg", land_name_en="Luxembourg",
        normal=Decimal("17"), ermaessigt=Decimal("8"),
        super_ermaessigt=Decimal("3"),
    ),
    "AT": SteuersatzInfo(
        land_code="AT", land_name="Österreich", land_name_en="Austria",
        normal=Decimal("20"), ermaessigt=Decimal("10"),
        ermaessigt_2=Decimal("13"),
    ),
    "IE": SteuersatzInfo(
        land_code="IE", land_name="Irland", land_name_en="Ireland",
        normal=Decimal("23"), ermaessigt=Decimal("13.5"),
        ermaessigt_2=Decimal("9"), super_ermaessigt=Decimal("4.8"),
    ),

    # --- Südeuropa ---
    "IT": SteuersatzInfo(
        land_code="IT", land_name="Italien", land_name_en="Italy",
        normal=Decimal("22"), ermaessigt=Decimal("10"),
        ermaessigt_2=Decimal("5"), super_ermaessigt=Decimal("4"),
    ),
    "ES": SteuersatzInfo(
        land_code="ES", land_name="Spanien", land_name_en="Spain",
        normal=Decimal("21"), ermaessigt=Decimal("10"),
        super_ermaessigt=Decimal("4"),
    ),
    "PT": SteuersatzInfo(
        land_code="PT", land_name="Portugal", land_name_en="Portugal",
        normal=Decimal("23"), ermaessigt=Decimal("13"),
        ermaessigt_2=Decimal("6"),
    ),
    "GR": SteuersatzInfo(
        land_code="GR", land_name="Griechenland", land_name_en="Greece",
        normal=Decimal("24"), ermaessigt=Decimal("13"),
        ermaessigt_2=Decimal("6"),
    ),
    "MT": SteuersatzInfo(
        land_code="MT", land_name="Malta", land_name_en="Malta",
        normal=Decimal("18"), ermaessigt=Decimal("7"),
        ermaessigt_2=Decimal("5"),
    ),
    "CY": SteuersatzInfo(
        land_code="CY", land_name="Zypern", land_name_en="Cyprus",
        normal=Decimal("19"), ermaessigt=Decimal("9"),
        ermaessigt_2=Decimal("5"), super_ermaessigt=Decimal("3"),
    ),
    "HR": SteuersatzInfo(
        land_code="HR", land_name="Kroatien", land_name_en="Croatia",
        normal=Decimal("25"), ermaessigt=Decimal("13"),
        ermaessigt_2=Decimal("5"),
    ),
    "SI": SteuersatzInfo(
        land_code="SI", land_name="Slowenien", land_name_en="Slovenia",
        normal=Decimal("22"), ermaessigt=Decimal("9.5"),
        ermaessigt_2=Decimal("5"),
    ),

    # --- Nordeuropa ---
    "SE": SteuersatzInfo(
        land_code="SE", land_name="Schweden", land_name_en="Sweden",
        normal=Decimal("25"), ermaessigt=Decimal("12"),
        ermaessigt_2=Decimal("6"), waehrung="SEK",
    ),
    "DK": SteuersatzInfo(
        land_code="DK", land_name="Dänemark", land_name_en="Denmark",
        normal=Decimal("25"), ermaessigt=Decimal("0"),
        waehrung="DKK",
    ),
    "FI": SteuersatzInfo(
        land_code="FI", land_name="Finnland", land_name_en="Finland",
        normal=Decimal("25.5"), ermaessigt=Decimal("14"),
        ermaessigt_2=Decimal("10"),
    ),

    # --- Osteuropa ---
    "PL": SteuersatzInfo(
        land_code="PL", land_name="Polen", land_name_en="Poland",
        normal=Decimal("23"), ermaessigt=Decimal("8"),
        ermaessigt_2=Decimal("5"), waehrung="PLN",
    ),
    "CZ": SteuersatzInfo(
        land_code="CZ", land_name="Tschechien", land_name_en="Czech Republic",
        normal=Decimal("21"), ermaessigt=Decimal("12"),
        waehrung="CZK",
    ),
    "SK": SteuersatzInfo(
        land_code="SK", land_name="Slowakei", land_name_en="Slovakia",
        normal=Decimal("23"), ermaessigt=Decimal("10"),
        ermaessigt_2=Decimal("5"),
    ),
    "HU": SteuersatzInfo(
        land_code="HU", land_name="Ungarn", land_name_en="Hungary",
        normal=Decimal("27"), ermaessigt=Decimal("18"),
        ermaessigt_2=Decimal("5"), waehrung="HUF",
    ),
    "RO": SteuersatzInfo(
        land_code="RO", land_name="Rumänien", land_name_en="Romania",
        normal=Decimal("19"), ermaessigt=Decimal("9"),
        ermaessigt_2=Decimal("5"), waehrung="RON",
    ),
    "BG": SteuersatzInfo(
        land_code="BG", land_name="Bulgarien", land_name_en="Bulgaria",
        normal=Decimal("20"), ermaessigt=Decimal("9"),
        waehrung="BGN",
    ),

    # --- Baltikum ---
    "EE": SteuersatzInfo(
        land_code="EE", land_name="Estland", land_name_en="Estonia",
        normal=Decimal("22"), ermaessigt=Decimal("9"),
    ),
    "LV": SteuersatzInfo(
        land_code="LV", land_name="Lettland", land_name_en="Latvia",
        normal=Decimal("21"), ermaessigt=Decimal("12"),
        ermaessigt_2=Decimal("5"),
    ),
    "LT": SteuersatzInfo(
        land_code="LT", land_name="Litauen", land_name_en="Lithuania",
        normal=Decimal("21"), ermaessigt=Decimal("9"),
        ermaessigt_2=Decimal("5"),
    ),

    # --- UK (post-Brexit, kein OSS) ---
    "GB": SteuersatzInfo(
        land_code="GB", land_name="Vereinigtes Königreich", land_name_en="United Kingdom",
        normal=Decimal("20"), ermaessigt=Decimal("5"),
        waehrung="GBP", eu_mitglied=False, oss_faehig=False,
    ),
}


def steuersatz_fuer_land(land_code: str) -> SteuersatzInfo:
    """Steuersatz-Info für einen Ländercode abrufen.

    Raises:
        KeyError: Wenn der Ländercode unbekannt ist.
    """
    code = land_code.upper().strip()
    if code not in EU_STEUERSAETZE:
        verfuegbar = ", ".join(sorted(EU_STEUERSAETZE.keys()))
        msg = f"Unbekannter Ländercode: '{code}'. Verfügbar: {verfuegbar}"
        raise KeyError(msg)
    return EU_STEUERSAETZE[code]


def ist_eu_land(land_code: str) -> bool:
    """Prüft ob ein Land EU-Mitglied ist."""
    info = EU_STEUERSAETZE.get(land_code.upper().strip())
    return info is not None and info.eu_mitglied


def ist_oss_land(land_code: str) -> bool:
    """Prüft ob ein Land am OSS-Verfahren teilnimmt."""
    info = EU_STEUERSAETZE.get(land_code.upper().strip())
    return info is not None and info.oss_faehig
