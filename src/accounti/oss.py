"""OSS-Verfahren (One-Stop-Shop) — EU-weite MwSt-Meldung.

Seit 01.07.2021 können B2C-Verkäufe in andere EU-Länder
über den One-Stop-Shop gemeldet werden, statt sich in
jedem Bestimmungsland einzeln registrieren zu müssen.

Meldezeitraum: Quartalsweise
Frist: Letzter Tag des Folgemonats nach Quartalsende
Zuständig in DE: Bundeszentralamt für Steuern (BZSt)

Schwelle: €10.000 p.a. für alle EU-B2C-Fernverkäufe zusammen.
Über der Schwelle → OSS-Pflicht (Steuersatz des Bestimmungslands).
Unter der Schwelle → Wahlrecht (DE-Steuersatz oder OSS).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from accounti.models import Buchungssatz
from accounti.steuer.eu_steuersaetze import (
    EU_STEUERSAETZE,
    SteuersatzInfo,
    ist_oss_land,
)


# ---------------------------------------------------------------------------
# OSS-Schwellenwert
# ---------------------------------------------------------------------------

OSS_SCHWELLE_EUR = Decimal("10000.00")


# ---------------------------------------------------------------------------
# Datenstrukturen
# ---------------------------------------------------------------------------


@dataclass
class OSSLand:
    """Zusammenfassung der OSS-pflichtigen Umsätze für ein Land."""

    land_code: str
    land_name: str
    steuersatz_normal: Decimal
    steuersatz_ermaessigt: Decimal

    # Normalsteuersatz
    bemessungsgrundlage_normal: Decimal = Decimal("0.00")
    steuer_normal: Decimal = Decimal("0.00")
    anzahl_normal: int = 0

    # Ermäßigter Steuersatz
    bemessungsgrundlage_ermaessigt: Decimal = Decimal("0.00")
    steuer_ermaessigt: Decimal = Decimal("0.00")
    anzahl_ermaessigt: int = 0

    @property
    def bemessungsgrundlage_gesamt(self) -> Decimal:
        return self.bemessungsgrundlage_normal + self.bemessungsgrundlage_ermaessigt

    @property
    def steuer_gesamt(self) -> Decimal:
        return self.steuer_normal + self.steuer_ermaessigt

    @property
    def brutto_gesamt(self) -> Decimal:
        return self.bemessungsgrundlage_gesamt + self.steuer_gesamt

    @property
    def anzahl_gesamt(self) -> int:
        return self.anzahl_normal + self.anzahl_ermaessigt


@dataclass
class OSSMeldung:
    """Vollständige OSS-Meldung für ein Quartal."""

    quartal: str                   # z.B. "2026-Q2"
    jahr: int
    quartal_nr: int                # 1-4
    firmen_land: str = "DE"
    firmen_ust_id: str = ""

    laender: list[OSSLand] = field(default_factory=list)
    erstellt_am: date = field(default_factory=date.today)

    # Fristen
    meldezeitraum_von: date = field(default_factory=date.today)
    meldezeitraum_bis: date = field(default_factory=date.today)
    abgabefrist: date = field(default_factory=date.today)

    @property
    def bemessungsgrundlage_gesamt(self) -> Decimal:
        return sum((l.bemessungsgrundlage_gesamt for l in self.laender), Decimal("0.00"))

    @property
    def steuer_gesamt(self) -> Decimal:
        return sum((l.steuer_gesamt for l in self.laender), Decimal("0.00"))

    @property
    def anzahl_transaktionen(self) -> int:
        return sum(l.anzahl_gesamt for l in self.laender)

    def als_csv_zeilen(self) -> list[str]:
        """Exportiert die Meldung als CSV-Zeilen für Prüfzwecke."""
        zeilen = [
            "Land;Steuersatz;Bemessungsgrundlage;Steuer;Anzahl",
        ]
        for land in sorted(self.laender, key=lambda l: l.land_code):
            if land.bemessungsgrundlage_normal > 0:
                zeilen.append(
                    f"{land.land_code};{land.steuersatz_normal}%;"
                    f"{land.bemessungsgrundlage_normal:.2f};"
                    f"{land.steuer_normal:.2f};{land.anzahl_normal}"
                )
            if land.bemessungsgrundlage_ermaessigt > 0:
                zeilen.append(
                    f"{land.land_code};{land.steuersatz_ermaessigt}%;"
                    f"{land.bemessungsgrundlage_ermaessigt:.2f};"
                    f"{land.steuer_ermaessigt:.2f};{land.anzahl_ermaessigt}"
                )
        zeilen.append(
            f"GESAMT;;{self.bemessungsgrundlage_gesamt:.2f};"
            f"{self.steuer_gesamt:.2f};{self.anzahl_transaktionen}"
        )
        return zeilen


# ---------------------------------------------------------------------------
# OSS-Engine
# ---------------------------------------------------------------------------


class OSSEngine:
    """Engine für OSS-Schwellenwertprüfung und Quartalsmeldung."""

    def __init__(self, firmen_land: str = "DE") -> None:
        self.firmen_land = firmen_land.upper()

    def _runde(self, betrag: Decimal) -> Decimal:
        return betrag.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _quartal_fuer_datum(self, datum: date) -> tuple[int, int]:
        """Gibt (Jahr, Quartalsnummer) für ein Datum zurück."""
        quartal_nr = (datum.month - 1) // 3 + 1
        return datum.year, quartal_nr

    def _quartal_zeitraum(self, jahr: int, quartal_nr: int) -> tuple[date, date]:
        """Start- und Enddatum eines Quartals."""
        monat_start = (quartal_nr - 1) * 3 + 1
        monat_ende = quartal_nr * 3
        # Letzter Tag des Quartals
        if monat_ende == 12:
            letzter_tag = date(jahr, 12, 31)
        else:
            letzter_tag = date(jahr, monat_ende + 1, 1).replace(day=1)
            letzter_tag = date(
                letzter_tag.year, letzter_tag.month, 1
            ) - __import__("datetime").timedelta(days=1)
        return date(jahr, monat_start, 1), letzter_tag

    def _abgabefrist(self, jahr: int, quartal_nr: int) -> date:
        """Letzter Tag des Folgemonats nach Quartalsende."""
        folgemonat = quartal_nr * 3 + 1
        folgejahr = jahr
        if folgemonat > 12:
            folgemonat = 1
            folgejahr = jahr + 1
        # Letzter Tag des Folgemonats
        if folgemonat == 12:
            return date(folgejahr, 12, 31)
        return date(folgejahr, folgemonat + 1, 1) - __import__("datetime").timedelta(days=1)

    def pruefe_schwelle(
        self,
        buchungen: list[Buchungssatz],
        jahr: int,
    ) -> tuple[bool, Decimal]:
        """Prüft ob die €10.000-Schwelle für EU-B2C-Fernverkäufe überschritten ist.

        Args:
            buchungen: Alle Buchungen des Jahres
            jahr: Prüfjahr

        Returns:
            Tuple (schwelle_ueberschritten, summe_eu_b2c)
        """
        # TODO: Hier müsste man wissen, welche Buchungen EU-B2C sind.
        # Das erfordert Metadaten auf dem Buchungssatz (bestimmungsland, ist_b2b).
        # Für jetzt: Summe aller Buchungen auf OSS-Erlöskonten.
        from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03

        oss_konten = set(OSS_ERLOES_KONTEN_SKR03.values())
        summe = Decimal("0.00")

        for b in buchungen:
            if b.datum.year == jahr:
                if b.haben_konto in oss_konten or b.soll_konto in oss_konten:
                    summe += abs(b.betrag_netto)

        return summe > OSS_SCHWELLE_EUR, summe

    def erstelle_meldung(
        self,
        buchungen: list[Buchungssatz],
        jahr: int,
        quartal_nr: int,
    ) -> OSSMeldung:
        """Erstellt eine OSS-Quartalsmeldung aus Buchungssätzen.

        Gruppiert alle OSS-relevanten Buchungen nach Bestimmungsland
        und Steuersatz.

        Args:
            buchungen: Alle Buchungen (werden nach Quartal gefiltert)
            jahr: Meldejahr
            quartal_nr: Quartalsnummer (1-4)

        Returns:
            Vollständige OSSMeldung
        """
        von, bis = self._quartal_zeitraum(jahr, quartal_nr)
        frist = self._abgabefrist(jahr, quartal_nr)

        # Buchungen des Quartals filtern
        quartal_buchungen = [
            b for b in buchungen
            if von <= b.datum <= bis
        ]

        # Nach Land gruppieren
        # TODO: Bestimmungsland muss als Metadatum auf dem Buchungssatz sein.
        # Für jetzt: Ableitung aus dem Erlöskonto.
        from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03

        konto_zu_land = {v: k for k, v in OSS_ERLOES_KONTEN_SKR03.items()}
        laender_daten: dict[str, OSSLand] = {}

        for b in quartal_buchungen:
            # Bestimmungsland aus Erlöskonto ableiten
            land_code = konto_zu_land.get(b.haben_konto)
            if land_code is None:
                land_code = konto_zu_land.get(b.soll_konto)
            if land_code is None:
                continue  # Kein OSS-relevantes Konto

            if land_code not in laender_daten:
                info = EU_STEUERSAETZE.get(land_code)
                if info is None:
                    continue
                laender_daten[land_code] = OSSLand(
                    land_code=land_code,
                    land_name=info.land_name,
                    steuersatz_normal=info.normal,
                    steuersatz_ermaessigt=info.ermaessigt,
                )

            land = laender_daten[land_code]

            # TODO: Ermäßigt vs. Normal unterscheiden (braucht Metadaten)
            # Für jetzt: alles als Normalsatz
            land.bemessungsgrundlage_normal += abs(b.betrag_netto)
            steuer = self._runde(
                abs(b.betrag_netto) * land.steuersatz_normal / Decimal("100")
            )
            land.steuer_normal += steuer
            land.anzahl_normal += 1

        return OSSMeldung(
            quartal=f"{jahr}-Q{quartal_nr}",
            jahr=jahr,
            quartal_nr=quartal_nr,
            firmen_land=self.firmen_land,
            laender=list(laender_daten.values()),
            meldezeitraum_von=von,
            meldezeitraum_bis=bis,
            abgabefrist=frist,
        )
