"""DATEV-Export — Buchungsstapel im EXTF-Format.

Erzeugt DATEV-konforme ASCII-Dateien nach dem
Buchungsstapel-Format (Header Version 700).

Referenz: DATEV-Schnittstellenbeschreibung für Buchungsdaten
https://developer.datev.de/datev/platform/de/dtvf
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from accounti.models import Buchungssatz


@dataclass
class DATEVConfig:
    """Konfiguration für den DATEV-Export."""

    berater_nummer: str        # z.B. "23426"
    mandanten_nummer: str      # z.B. "40005"
    wirtschaftsjahr_beginn: date = date(2026, 1, 1)
    sachkonten_laenge: int = 4  # 4-stellig Standard, auch 6 möglich
    datum_von: date = date(2026, 1, 1)
    datum_bis: date = date(2026, 12, 31)
    bezeichnung: str = "accounti Export"
    waehrung: str = "EUR"


class DATEVExporter:
    """Erzeugt DATEV-konforme Buchungsstapel-Dateien."""

    # DATEV EXTF Header-Felder (Version 700)
    HEADER_VERSION = "700"
    FORMAT_KATEGORIE = "21"  # Buchungsstapel
    FORMAT_NAME = "Buchungsstapel"
    FORMAT_VERSION = "13"

    def __init__(self, config: DATEVConfig) -> None:
        self.config = config

    def _erzeuge_header(self) -> str:
        """DATEV EXTF Header-Zeile generieren."""
        now = datetime.now()
        felder = [
            '"EXTF"',                          # Kennzeichen
            self.HEADER_VERSION,               # Versionsnummer
            self.FORMAT_KATEGORIE,             # Kategorie (21 = Buchungsstapel)
            f'"{self.FORMAT_NAME}"',           # Format-Name
            self.FORMAT_VERSION,               # Format-Version
            f"{now:%Y%m%d%H%M%S}000",         # Erzeugt am
            "",                                # Importiert (leer)
            '"accounti"',                      # Herkunft
            '""',                              # Exportiert von
            '""',                              # Importiert von
            self.config.berater_nummer,        # Berater-Nr.
            self.config.mandanten_nummer,      # Mandanten-Nr.
            f"{self.config.wirtschaftsjahr_beginn:%Y%m%d}",  # WJ-Beginn
            str(self.config.sachkonten_laenge), # Sachkontenlänge
            f"{self.config.datum_von:%Y%m%d}", # Datum von
            f"{self.config.datum_bis:%Y%m%d}", # Datum bis
            f'"{self.config.bezeichnung}"',    # Bezeichnung
            '""',                              # Diktatkürzel
            "0",                               # Buchungstyp (0 = Finanzbuchführung)
            "0",                               # Rechnungslegungszweck
            "0",                               # Festschreibung
            f'"{self.config.waehrung}"',       # WKZ
            "",                                # Reservefeld
            "",                                # Derivatskennzeichen
            "",                                # Reservefeld
            "",                                # Reservefeld
            '""',                              # SKR (leer = automatisch)
            "",                                # Branchen-ID
            "",                                # Reservefeld
            '""',                              # Anwendungsinfo
        ]
        return ";".join(felder)

    def _buchung_zu_zeile(self, buchung: Buchungssatz) -> dict[str, str]:
        """Einzelnen Buchungssatz in DATEV-Zeilenformat umwandeln."""
        # Betrag: immer positiv, mit Komma als Dezimaltrenner
        betrag = abs(buchung.betrag_netto)
        if buchung.steuer_betrag:
            betrag += abs(buchung.steuer_betrag)
        betrag_str = f"{betrag:.2f}".replace(".", ",")

        # Soll/Haben-Kennzeichen
        # S = Soll, H = Haben
        soll_haben = "S"

        return {
            "Umsatz (ohne Soll/Haben-Kz)": betrag_str,
            "Soll/Haben-Kennzeichen": soll_haben,
            "WKZ Umsatz": self.config.waehrung,
            "Kurs": "",
            "Basis-Umsatz": "",
            "WKZ Basis-Umsatz": "",
            "Konto": buchung.soll_konto,
            "Gegenkonto (ohne BU-Schlüssel)": buchung.haben_konto,
            "BU-Schlüssel": str(buchung.steuer_schluessel or ""),
            "Belegdatum": f"{buchung.datum:%d%m}",  # TTMM
            "Belegfeld 1": buchung.beleg_nummer or "",
            "Belegfeld 2": "",
            "Skonto": "",
            "Buchungstext": buchung.buchungstext[:60],
            "Postensperre": "",
            "Diverse Adressnummer": "",
            "Geschäftspartnerbank": "",
            "Sachverhalt": "",
            "Zinssperre": "",
            "Beleglink": "",
            "Beleginfo - Art 1": "",
            "Beleginfo - Inhalt 1": "",
            "Kostenstelle": buchung.kostenstelle or "",
        }

    def exportiere(
        self,
        buchungen: list[Buchungssatz],
        ausgabe_pfad: Path,
    ) -> Path:
        """Buchungsstapel als DATEV-ASCII-Datei exportieren.

        Args:
            buchungen: Liste der zu exportierenden Buchungssätze
            ausgabe_pfad: Verzeichnis für die Ausgabedatei

        Returns:
            Pfad zur erzeugten Datei
        """
        ausgabe_pfad = Path(ausgabe_pfad)
        ausgabe_pfad.mkdir(parents=True, exist_ok=True)

        dateiname = (
            f"EXTF_Buchungsstapel_"
            f"{self.config.datum_von:%Y%m%d}_"
            f"{self.config.datum_bis:%Y%m%d}.csv"
        )
        datei = ausgabe_pfad / dateiname

        # Header
        header = self._erzeuge_header()

        # Spaltenüberschriften (gekürzt — DATEV hat 116+ Spalten)
        spalten = [
            "Umsatz (ohne Soll/Haben-Kz)",
            "Soll/Haben-Kennzeichen",
            "WKZ Umsatz",
            "Kurs",
            "Basis-Umsatz",
            "WKZ Basis-Umsatz",
            "Konto",
            "Gegenkonto (ohne BU-Schlüssel)",
            "BU-Schlüssel",
            "Belegdatum",
            "Belegfeld 1",
            "Belegfeld 2",
            "Skonto",
            "Buchungstext",
            "Postensperre",
            "Diverse Adressnummer",
            "Geschäftspartnerbank",
            "Sachverhalt",
            "Zinssperre",
            "Beleglink",
            "Beleginfo - Art 1",
            "Beleginfo - Inhalt 1",
            "Kostenstelle",
        ]

        output = io.StringIO()
        # Zeile 1: Header
        output.write(header + "\n")
        # Zeile 2: Spaltenüberschriften
        writer = csv.DictWriter(output, fieldnames=spalten, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        # Datenzeilen
        for buchung in buchungen:
            zeile = self._buchung_zu_zeile(buchung)
            writer.writerow(zeile)

        datei.write_text(output.getvalue(), encoding="cp1252")
        return datei
