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

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from accounti.models import Buchungssatz
from accounti.steuer.eu_steuersaetze import (
    EU_STEUERSAETZE,
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
class OSSKorrektur:
    """Berichtigung eines früheren Meldezeitraums (Art. 61 MwSt-DVO, § 18j UStG).

    Eine Erlösminderung (z.B. Erstattung) zu einer Lieferung aus einem früheren
    Quartal wird nicht mit dem laufenden Quartal verrechnet — das BZSt nimmt keine
    negativen Beträge an —, sondern in der laufenden Meldung als Korrektur des
    ursprünglichen Quartals angegeben.
    """

    land_code: str
    jahr: int
    quartal_nr: int
    steuersatz: Decimal
    bemessungsgrundlage: Decimal = Decimal("0.00")
    steuer: Decimal = Decimal("0.00")
    anzahl: int = 0

    @property
    def zeitraum(self) -> str:
        return f"{self.jahr}-Q{self.quartal_nr}"


@dataclass
class OSSMeldung:
    """Vollständige OSS-Meldung für ein Quartal."""

    quartal: str  # z.B. "2026-Q2"
    jahr: int
    quartal_nr: int  # 1-4
    firmen_land: str = "DE"
    firmen_ust_id: str = ""

    laender: list[OSSLand] = field(default_factory=list)
    korrekturen: list[OSSKorrektur] = field(default_factory=list)
    erstellt_am: date = field(default_factory=date.today)

    # Fristen
    meldezeitraum_von: date = field(default_factory=date.today)
    meldezeitraum_bis: date = field(default_factory=date.today)
    abgabefrist: date = field(default_factory=date.today)

    @property
    def bemessungsgrundlage_gesamt(self) -> Decimal:
        return sum(
            (land.bemessungsgrundlage_gesamt for land in self.laender),
            Decimal("0.00"),
        )

    @property
    def steuer_gesamt(self) -> Decimal:
        return sum((land.steuer_gesamt for land in self.laender), Decimal("0.00"))

    @property
    def anzahl_transaktionen(self) -> int:
        return sum(land.anzahl_gesamt for land in self.laender)

    def als_csv_zeilen(self) -> list[str]:
        """Exportiert die Meldung als CSV-Zeilen für Prüfzwecke."""
        zeilen = [
            "Land;Steuersatz;Bemessungsgrundlage;Steuer;Anzahl",
        ]
        # jede Zeile mit Buchungen, auch negative — die Länderzeilen ergeben GESAMT
        for land in sorted(self.laender, key=lambda eintrag: eintrag.land_code):
            if land.anzahl_normal or land.bemessungsgrundlage_normal:
                zeilen.append(
                    f"{land.land_code};{land.steuersatz_normal}%;"
                    f"{land.bemessungsgrundlage_normal:.2f};"
                    f"{land.steuer_normal:.2f};{land.anzahl_normal}"
                )
            if land.anzahl_ermaessigt or land.bemessungsgrundlage_ermaessigt:
                zeilen.append(
                    f"{land.land_code};{land.steuersatz_ermaessigt}%;"
                    f"{land.bemessungsgrundlage_ermaessigt:.2f};"
                    f"{land.steuer_ermaessigt:.2f};{land.anzahl_ermaessigt}"
                )
        zeilen.append(
            f"GESAMT;;{self.bemessungsgrundlage_gesamt:.2f};"
            f"{self.steuer_gesamt:.2f};{self.anzahl_transaktionen}"
        )
        if self.korrekturen:
            zeilen.append("Korrektur;Land;Steuersatz;Bemessungsgrundlage;Steuer;Anzahl")
            for k in sorted(
                self.korrekturen, key=lambda x: (x.jahr, x.quartal_nr, x.land_code)
            ):
                zeilen.append(
                    f"{k.zeitraum};{k.land_code};{k.steuersatz}%;"
                    f"{k.bemessungsgrundlage:.2f};{k.steuer:.2f};{k.anzahl}"
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

    def _steuer(self, basis: Decimal, satz: Decimal) -> Decimal:
        """Steuer auf eine Bemessungsgrundlage (Vorzeichen bleibt erhalten)."""
        betrag = self._runde(abs(basis) * satz / Decimal("100"))
        return -betrag if basis < 0 else betrag

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
            letzter_tag = date(letzter_tag.year, letzter_tag.month, 1) - __import__(
                "datetime"
            ).timedelta(days=1)
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
        return date(folgejahr, folgemonat + 1, 1) - timedelta(days=1)

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
            if b.datum.year == jahr and (
                b.haben_konto in oss_konten or b.soll_konto in oss_konten
            ):
                # Haben = Erlös, Soll = Erlösminderung (Erstattung, Gutschrift)
                vorzeichen = 1 if b.haben_konto in oss_konten else -1
                summe += vorzeichen * abs(b.betrag_netto)

        return summe > OSS_SCHWELLE_EUR, summe

    def erstelle_meldung(
        self,
        buchungen: list[Buchungssatz],
        jahr: int,
        quartal_nr: int,
        erloes_konten_ermaessigt: Mapping[str, str] | None = None,
    ) -> OSSMeldung:
        """Erstellt eine OSS-Quartalsmeldung aus Buchungssätzen.

        Gruppiert die OSS-Buchungen des Quartals nach Bestimmungsland und
        Steuersatz; die Steuer wird je Land und Satz einmal aus der Summe der
        Bemessungsgrundlagen gerundet. Eine Erlösminderung (OSS-Erlöskonto im Soll),
        deren Erlös mit derselben Belegnummer in einem früheren Quartal liegt, wird
        als Korrektur dieses Quartals ausgewiesen.

        Args:
            buchungen: Alle Buchungen bis Quartalsende (frühere für die Zuordnung
                von Erstattungen; nach Quartal wird hier gefiltert)
            jahr: Meldejahr
            quartal_nr: Quartalsnummer (1-4)
            erloes_konten_ermaessigt: Land → Erlöskonto für Umsätze zum ermäßigten
                Satz des Bestimmungslands

        Returns:
            Vollständige OSSMeldung
        """
        von, bis = self._quartal_zeitraum(jahr, quartal_nr)
        frist = self._abgabefrist(jahr, quartal_nr)

        # TODO: Bestimmungsland muss als Metadatum auf dem Buchungssatz sein.
        # Für jetzt: Ableitung aus dem Erlöskonto (ermäßigt: eigene Konten).
        from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03

        konto_zu_land: dict[str, tuple[str, bool]] = {
            konto: (land, False) for land, konto in OSS_ERLOES_KONTEN_SKR03.items()
        }
        for code, konto in (erloes_konten_ermaessigt or {}).items():
            konto_zu_land[konto] = (code.upper(), True)

        # Ursprung je Erlös: frühestes Datum je (Erlöskonto, Belegnummer)
        ursprung: dict[tuple[str, str], date] = {}
        for b in buchungen:
            if b.beleg_nummer and b.haben_konto in konto_zu_land and b.datum <= bis:
                schluessel = (b.haben_konto, b.beleg_nummer)
                if schluessel not in ursprung or b.datum < ursprung[schluessel]:
                    ursprung[schluessel] = b.datum

        basen: dict[tuple[str, bool], list[Decimal]] = {}
        korrekturen: dict[tuple[str, bool, int, int], list[Decimal]] = {}
        for b in buchungen:
            if not von <= b.datum <= bis:
                continue
            # Haben = Erlös; im Soll ist es eine Erlösminderung (Erstattung,
            # Gutschrift) und mindert die Meldung
            konto, vorzeichen = b.haben_konto, Decimal(1)
            if konto not in konto_zu_land:
                konto, vorzeichen = b.soll_konto, Decimal(-1)
            if konto not in konto_zu_land:
                continue  # Kein OSS-relevantes Konto
            land_code, ermaessigt = konto_zu_land[konto]
            if land_code not in EU_STEUERSAETZE:
                continue
            betrag = vorzeichen * abs(b.betrag_netto)
            frueher = (
                ursprung.get((konto, b.beleg_nummer))
                if vorzeichen < 0 and b.beleg_nummer
                else None
            )
            if frueher is not None and frueher < von:
                j, q = self._quartal_fuer_datum(frueher)
                summe = korrekturen.setdefault((land_code, ermaessigt, j, q), [])
            else:
                summe = basen.setdefault((land_code, ermaessigt), [])
            summe.append(betrag)

        laender_daten: dict[str, OSSLand] = {}
        for (land_code, ermaessigt), betraege in sorted(basen.items()):
            info = EU_STEUERSAETZE[land_code]
            land = laender_daten.setdefault(
                land_code,
                OSSLand(
                    land_code=land_code,
                    land_name=info.land_name,
                    steuersatz_normal=info.normal,
                    steuersatz_ermaessigt=info.ermaessigt,
                ),
            )
            basis = sum(betraege, Decimal("0.00"))
            if ermaessigt:
                land.bemessungsgrundlage_ermaessigt = basis
                land.steuer_ermaessigt = self._steuer(basis, info.ermaessigt)
                land.anzahl_ermaessigt = len(betraege)
            else:
                land.bemessungsgrundlage_normal = basis
                land.steuer_normal = self._steuer(basis, info.normal)
                land.anzahl_normal = len(betraege)

        korrektur_liste = []
        for (land_code, ermaessigt, j, q), betraege in sorted(korrekturen.items()):
            info = EU_STEUERSAETZE[land_code]
            satz = info.ermaessigt if ermaessigt else info.normal
            basis = sum(betraege, Decimal("0.00"))
            korrektur_liste.append(
                OSSKorrektur(
                    land_code=land_code,
                    jahr=j,
                    quartal_nr=q,
                    steuersatz=satz,
                    bemessungsgrundlage=basis,
                    steuer=self._steuer(basis, satz),
                    anzahl=len(betraege),
                )
            )

        return OSSMeldung(
            quartal=f"{jahr}-Q{quartal_nr}",
            jahr=jahr,
            quartal_nr=quartal_nr,
            firmen_land=self.firmen_land,
            laender=list(laender_daten.values()),
            korrekturen=korrektur_liste,
            meldezeitraum_von=von,
            meldezeitraum_bis=bis,
            abgabefrist=frist,
        )
