"""DATEV-Export — Buchungsstapel im EXTF-Format.

Erzeugt DATEV-konforme ASCII-Dateien nach dem
Buchungsstapel-Format (Header Version 700).

Referenz: DATEV-Schnittstellenbeschreibung für Buchungsdaten
https://developer.datev.de/datev/platform/de/dtvf
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from accounti.export.datev_format import (
    automatik_widerspruch,
    belegfeld2_storno,
    bu_schluessel,
    datev_umsatz,
    kontoart,
)
from accounti.models import Buchungssatz


@dataclass
class DATEVConfig:
    """Konfiguration für den DATEV-Export."""

    berater_nummer: str  # z.B. "23426"
    mandanten_nummer: str  # z.B. "40005"
    wirtschaftsjahr_beginn: date = date(2026, 1, 1)
    sachkonten_laenge: int = 4  # 4-stellig Standard, auch 6 möglich
    # Bereiche der Personenkonten (buchhaltung.debitoren_von … kreditoren_bis): sie
    # sind eine Stelle länger als die Sachkonten
    personenkonten: tuple[tuple[int, int], ...] = ((10000, 69999), (70000, 99999))
    datum_von: date = date(2026, 1, 1)
    datum_bis: date = date(2026, 12, 31)
    bezeichnung: str = "accounti Export"
    waehrung: str = "EUR"
    # DATEV-Automatikkonten (AV/AM) → Schlüssel; eine Buchung ohne Schlüssel darauf
    # bekommt BU 40 (Aufhebung der Automatik), sonst rechnete DATEV Steuer heraus
    automatikkonten: Mapping[str, int] = field(default_factory=dict)


class DATEVExporter:
    """Erzeugt DATEV-konforme Buchungsstapel-Dateien."""

    # DATEV EXTF Header-Felder (Version 700)
    HEADER_VERSION = "700"
    FORMAT_KATEGORIE = "21"  # Buchungsstapel
    FORMAT_NAME = "Buchungsstapel"
    FORMAT_VERSION = "13"

    def __init__(self, config: DATEVConfig) -> None:
        self.config = config
        # vor dem Import zu klären (z.B. anderer Schlüssel auf einem Automatikkonto)
        self.warnungen: list[str] = []

    def _ist_personenkonto(self, konto: str) -> bool:
        return konto.isdigit() and any(
            von <= int(konto) <= bis for von, bis in self.config.personenkonten
        )

    def _erzeuge_header(self) -> str:
        """DATEV EXTF Header-Zeile generieren."""
        now = datetime.now()
        felder = [
            '"EXTF"',  # Kennzeichen
            self.HEADER_VERSION,  # Versionsnummer
            self.FORMAT_KATEGORIE,  # Kategorie (21 = Buchungsstapel)
            f'"{self.FORMAT_NAME}"',  # Format-Name
            self.FORMAT_VERSION,  # Format-Version
            f"{now:%Y%m%d%H%M%S}000",  # Erzeugt am
            "",  # Importiert (leer)
            '"accounti"',  # Herkunft
            '""',  # Exportiert von
            '""',  # Importiert von
            self.config.berater_nummer,  # Berater-Nr.
            self.config.mandanten_nummer,  # Mandanten-Nr.
            f"{self.config.wirtschaftsjahr_beginn:%Y%m%d}",  # WJ-Beginn
            str(self.config.sachkonten_laenge),  # Sachkontenlänge
            f"{self.config.datum_von:%Y%m%d}",  # Datum von
            f"{self.config.datum_bis:%Y%m%d}",  # Datum bis
            f'"{self.config.bezeichnung}"',  # Bezeichnung
            '""',  # Diktatkürzel
            "0",  # Buchungstyp (0 = Finanzbuchführung)
            "0",  # Rechnungslegungszweck
            "0",  # Festschreibung
            f'"{self.config.waehrung}"',  # WKZ
            "",  # Reservefeld
            "",  # Derivatskennzeichen
            "",  # Reservefeld
            "",  # Reservefeld
            '""',  # SKR (leer = automatisch)
            "",  # Branchen-ID
            "",  # Reservefeld
            '""',  # Anwendungsinfo
        ]
        return ";".join(felder)

    def _buchung_zu_zeile(self, buchung: Buchungssatz) -> dict[str, str]:
        """Einzelnen Buchungssatz in DATEV-Zeilenformat umwandeln."""
        # Betrag: immer positiv, mit Komma als Dezimaltrenner
        betrag = datev_umsatz(buchung)
        betrag_str = f"{betrag:.2f}".replace(".", ",")

        # Soll/Haben-Kennzeichen
        # S = Soll, H = Haben
        soll_haben = "S"

        return {
            "Umsatz (ohne Soll/Haben-Kz)": betrag_str,
            "Soll/Haben-Kennzeichen": soll_haben,
            "WKZ Umsatz": "",  # Währung steht im Header, nicht pro Zeile
            "Kurs": "",
            "Basis-Umsatz": "",
            "WKZ Basis-Umsatz": "",
            "Konto": buchung.soll_konto,
            "Gegenkonto (ohne BU-Schlüssel)": buchung.haben_konto,
            "BU-Schlüssel": bu_schluessel(buchung, self.config.automatikkonten),
            "Belegdatum": f"{buchung.datum:%d%m}",  # TTMM
            "Belegfeld 1": buchung.beleg_nummer or "",
            "Belegfeld 2": belegfeld2_storno(
                buchung.storno_von, buchung.storniert_durch, buchung.id
            ),
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
        ausgabe_pfad: str | Path,
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

        # DATEV-Konformität: nur Textfelder werden gequotet, Beträge und
        # Kontonummern bleiben ohne Anführungszeichen. CRLF als Zeilenende,
        # newline="" beim Schreiben verhindert doppelte Umbrüche.
        text_spalten = {
            "Soll/Haben-Kennzeichen",
            "WKZ Umsatz",
            "WKZ Basis-Umsatz",
            "Buchungstext",
            "Diverse Adressnummer",
            "Geschäftspartnerbank",
            "Beleglink",
            "Beleginfo - Art 1",
            "Beleginfo - Inhalt 1",
        }

        def quote_text(spalte: str, wert: str) -> str:
            return f'"{wert}"' if (spalte in text_spalten and wert != "") else wert

        zeilen: list[str] = [header]
        zeilen.append(";".join(spalten))  # Spaltenüberschriften unquoted
        self.warnungen = [
            w
            for b in buchungen
            if (w := automatik_widerspruch(b, self.config.automatikkonten)) is not None
        ]
        laenge = self.config.sachkonten_laenge
        # wie datev belege: ein Konto, das nicht zur Sachkontenlänge der Kopfzeile
        # passt, lehnt DATEV ab (Personenkonten: eine Stelle länger) — Runde 5, g4w N5
        self.warnungen += [
            f"Buchung {b.beleg_nummer or str(b.id)[:8]}: Konto {konto} passt nicht "
            f"zur Sachkontenlänge {laenge} (mandant.sachkonten_laenge)"
            for b in buchungen
            for konto in (b.soll_konto, b.haben_konto)
            if kontoart(konto, laenge) is None
        ]
        # ein Personenkonto, das kürzer ist, läse DATEV als Sachkonto — bei Länge 6
        # oder 8 etwa die 5-stelligen Debitoren (Runde 6, g5w-konten N2)
        self.warnungen += [
            f"Personenkonto {konto} (buchhaltung.debitoren/kreditoren) passt nicht zur "
            f"Sachkontenlänge {laenge} (erwartet {laenge + 1} Stellen, "
            "mandant.sachkonten_laenge) — DATEV liest es als Sachkonto"
            for konto in sorted(
                {k for b in buchungen for k in (b.soll_konto, b.haben_konto)}
            )
            if self._ist_personenkonto(konto)
            and kontoart(konto, laenge) is not None
            and len(konto) != laenge + 1
        ]
        for buchung in buchungen:
            roh = self._buchung_zu_zeile(buchung)
            zeilen.append(";".join(quote_text(s, roh[s]) for s in spalten))

        inhalt = "\r\n".join(zeilen) + "\r\n"
        datei.write_text(inhalt, encoding="cp1252", newline="")
        return datei
