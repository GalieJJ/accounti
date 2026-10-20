"""Umsatzsteuer-Voranmeldung nach dem amtlichen Vordruck USt 1 A 2026.

Grundlage: BMF-Schreiben vom 29.12.2025, III C 3 - S 7344/00039/007/036, mit Vordruck
USt 1 A 2026 und Anleitung USt 1 E 2026. Die Kennziffern tragen ihre Zeile im Vordruck.

Zwei Regeln des Vordrucks prägen die Rechnung:

- Bemessungsgrundlagen stehen in **vollen Euro**, Steuerbeträge mit Cent (USt 1 E).
  Centbeträge der Bemessungsgrundlage werden abgeschnitten.
- Zu Kz 81, 86, 87, 89, 93 und 90 gibt es kein Steuerfeld: ELSTER rechnet die Steuer
  selbst aus der Bemessungsgrundlage in vollen Euro. Damit Kz 83 zu ELSTERs Rechnung
  passt, rechnet accounti genauso — nicht mit der gebuchten Steuer.

Innergemeinschaftliche Fernverkäufe im OSS erscheinen als Nettoumsatz in Kz 45
(Zeile 36), die Steuer darauf geht über die OSS-Meldung.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

from accounti.anzeige import betrag_de

NULL = Decimal("0.00")
CENT = Decimal("0.01")


class Art(str, enum.Enum):
    BMG = "bmg"  # Bemessungsgrundlage, volle Euro
    STEUER = "steuer"  # Euro und Cent
    MERKER = "merker"  # 1 = Ja bzw. Auswahlwert


@dataclass(frozen=True)
class UStKennziffer:
    """Eine Kennziffer des Vordrucks."""

    kz: int
    zeile: int
    abschnitt: str
    bezeichnung: str
    art: Art
    satz: Decimal | None = None  # Steuer berechnet ELSTER aus der BMG
    steuer_kz: int | None = None  # Steuerfeld zu dieser Bemessungsgrundlage


def _k(
    kz: int,
    zeile: int,
    abschnitt: str,
    bezeichnung: str,
    art: Art = Art.BMG,
    satz: str | None = None,
    steuer_kz: int | None = None,
) -> UStKennziffer:
    return UStKennziffer(
        kz,
        zeile,
        abschnitt,
        bezeichnung,
        art,
        Decimal(satz) if satz is not None else None,
        steuer_kz,
    )


_S = Art.STEUER
_M = Art.MERKER

KENNZIFFERN_2026: dict[int, UStKennziffer] = {
    k.kz: k
    for k in (
        _k(10, 10, "Kopf", "Berichtigte Anmeldung", _M),
        _k(22, 11, "Kopf", "Belege werden gesondert eingereicht", _M),
        _k(70, 12, "Kopf", "Datum des Wechsels von der Kleinunternehmer-Regelung", _M),
        # A. Steuerpflichtige Lieferungen, sonstige Leistungen, unentg. Wertabgaben
        _k(81, 13, "A", "Steuerpflichtige Umsätze zum Steuersatz von 19 %", satz="19"),
        _k(86, 14, "A", "Steuerpflichtige Umsätze zum Steuersatz von 7 %", satz="7"),
        _k(87, 15, "A", "Steuerpflichtige Umsätze zum Steuersatz von 0 %", satz="0"),
        _k(35, 16, "A", "Umsätze zu anderen Steuersätzen", steuer_kz=36),
        _k(36, 16, "A", "Steuer zu Kz 35", _S),
        _k(
            77,
            17,
            "A",
            "Lieferungen land-/forstw. Betriebe (§ 24) an Abnehmer mit USt-IdNr.",
        ),
        _k(76, 18, "A", "Umsätze mit Steuer nach § 24 UStG", steuer_kz=80),
        _k(80, 18, "A", "Steuer zu Kz 76", _S),
        # B. Steuerfreie Lieferungen, sonstige Leistungen, unentgeltliche Wertabgaben
        _k(41, 19, "B", "Innergemeinschaftliche Lieferungen an Abnehmer mit USt-IdNr."),
        _k(44, 20, "B", "Ig. Lieferungen neuer Fahrzeuge an Abnehmer ohne USt-IdNr."),
        _k(49, 21, "B", "Ig. Lieferungen neuer Fahrzeuge außerhalb eines Unternehmens"),
        _k(
            43,
            22,
            "B",
            "Weitere steuerfreie Umsätze mit Vorsteuerabzug (z. B. Ausfuhr)",
        ),
        _k(48, 23, "B", "Steuerfreie Umsätze ohne Vorsteuerabzug (§ 4 Nr. 8–29, § 19)"),
        # C. Innergemeinschaftliche Erwerbe
        _k(91, 24, "C", "Steuerfreie ig. Erwerbe (§§ 4b, 25c UStG)"),
        _k(
            89,
            25,
            "C",
            "Steuerpflichtige ig. Erwerbe zum Steuersatz von 19 %",
            satz="19",
        ),
        _k(
            93, 26, "C", "Steuerpflichtige ig. Erwerbe zum Steuersatz von 7 %", satz="7"
        ),
        _k(
            90, 27, "C", "Steuerpflichtige ig. Erwerbe zum Steuersatz von 0 %", satz="0"
        ),
        _k(95, 28, "C", "Ig. Erwerbe zu anderen Steuersätzen", steuer_kz=98),
        _k(98, 28, "C", "Steuer zu Kz 95", _S),
        _k(94, 29, "C", "Ig. Erwerbe neuer Fahrzeuge ohne USt-IdNr.", steuer_kz=96),
        _k(96, 29, "C", "Steuer zu Kz 94", _S),
        # D. Leistungsempfänger als Steuerschuldner (§ 13b UStG)
        _k(
            46,
            30,
            "D",
            "Sonstige Leistungen nach § 3a Abs. 2 UStG eines im übrigen "
            "Gemeinschaftsgebiet ansässigen Unternehmers (§ 13b Abs. 1 UStG)",
            steuer_kz=47,
        ),
        _k(47, 30, "D", "Steuer zu Kz 46", _S),
        _k(
            73,
            31,
            "D",
            "Umsätze, die unter das GrEStG fallen (§ 13b Abs. 2 Nr. 3)",
            steuer_kz=74,
        ),
        _k(74, 31, "D", "Steuer zu Kz 73", _S),
        _k(
            84,
            32,
            "D",
            "Andere Leistungen (§ 13b Abs. 2 Nr. 1, 2, 4 bis 12)",
            steuer_kz=85,
        ),
        _k(85, 32, "D", "Steuer zu Kz 84", _S),
        # E. Ergänzende Angaben zu Umsätzen
        _k(42, 33, "E", "Lieferungen des ersten Abnehmers bei ig. Dreiecksgeschäften"),
        _k(
            60,
            34,
            "E",
            "Umsätze, für die der Leistungsempfänger nach § 13b Abs. 5 schuldet",
        ),
        _k(
            21,
            35,
            "E",
            "Nicht steuerbare sonstige Leistungen (§ 18b Satz 1 Nr. 2 UStG)",
        ),
        _k(
            45,
            36,
            "E",
            "Übrige nicht steuerbare Umsätze (Leistungsort nicht im Inland)",
        ),
        # F. Abziehbare Vorsteuerbeträge
        _k(66, 38, "F", "Vorsteuer aus Rechnungen anderer Unternehmer", _S),
        _k(61, 39, "F", "Vorsteuer aus ig. Erwerben", _S),
        _k(62, 40, "F", "Entstandene Einfuhrumsatzsteuer", _S),
        _k(67, 41, "F", "Vorsteuer aus Leistungen im Sinne des § 13b UStG", _S),
        _k(63, 42, "F", "Vorsteuer nach Durchschnittssätzen (§ 23a UStG)", _S),
        _k(59, 43, "F", "Vorsteuerabzug § 2a / § 19 UStG (§ 15 Abs. 4a)", _S),
        _k(64, 44, "F", "Berichtigung des Vorsteuerabzugs (§ 15a UStG)", _S),
        # G. Andere Steuerbeträge
        _k(
            65, 46, "G", "Steuer infolge Wechsels der Besteuerungsform / Nachsteuer", _S
        ),
        _k(69, 47, "G", "Unrichtig/unberechtigt ausgewiesene Steuer (§ 14c) u. a.", _S),
        # H. Vorauszahlung/Überschuss
        _k(39, 49, "H", "Abzug der festgesetzten Sondervorauszahlung", _S),
        _k(83, 50, "H", "Verbleibende Umsatzsteuer-Vorauszahlung / Überschuss", _S),
        # I. Ergänzende Angaben zu Minderungen nach § 17 UStG
        _k(50, 51, "I", "Minderung der Bemessungsgrundlage (§ 17, in Zeilen 13–18)"),
        _k(37, 52, "I", "Minderung der abziehbaren Vorsteuerbeträge (§ 17)", _S),
        # J. Sonstige Angaben
        _k(
            29, 53, "J", "Verrechnung des Erstattungsbetrags erwünscht / abgetreten", _M
        ),
        _k(26, 54, "J", "SEPA-Lastschriftmandat ausnahmsweise nicht verwenden", _M),
        _k(500, 55, "J", "Ergänzende Angaben zur Steueranmeldung (1–4)", _M),
    )
}

# Zeile 37: Summe der Zeilen 13 bis 18 und 25 bis 32
_UMSATZSTEUER_BMG = (81, 86, 87, 89, 93, 90)
_UMSATZSTEUER_FELDER = (36, 80, 98, 96, 47, 74, 85)
_VORSTEUER = (66, 61, 62, 67, 63, 59, 64)  # Zeilen 38 bis 44
_ANDERE = (65, 69)  # Zeilen 46 und 47


def volle_euro(betrag: Decimal) -> Decimal:
    """Centbeträge abschneiden (gegen null)."""
    return betrag.quantize(Decimal("1"), rounding=ROUND_DOWN)


@dataclass
class UStVoranmeldung:
    """Voranmeldung eines Zeitraums: exakte Werte je Kennziffer, Formular nach Vordruck.

    ``werte`` hält Bemessungsgrundlagen und Steuerbeträge mit Cent, so wie sie aus den
    Buchungen kommen. Was in den Vordruck geht, liefert ``formularwerte()``.
    """

    zeitraum: str  # z.B. "2026-08" oder "2026-Q3"
    werte: dict[int, Decimal] = field(default_factory=dict)
    berichtigt: bool = False
    firmen_name: str = ""
    steuernummer: str = ""
    ust_id: str = ""

    def addiere(self, kz: int, betrag: Decimal) -> None:
        if kz not in KENNZIFFERN_2026 or kz == 83:
            msg = f"Kennziffer {kz} gibt es im Vordruck 2026 nicht (oder ist berechnet)"
            raise KeyError(msg)
        self.werte[kz] = self.werte.get(kz, NULL) + betrag

    def wert(self, kz: int) -> Decimal:
        return self.werte.get(kz, NULL)

    def bmg(self, kz: int) -> Decimal:
        """Bemessungsgrundlage in vollen Euro."""
        return volle_euro(self.wert(kz))

    def steuer(self, kz: int) -> Decimal:
        """Steuer zu einer Bemessungsgrundlage — berechnet wie ELSTER oder gemeldet."""
        k = KENNZIFFERN_2026[kz]
        if k.satz is not None:
            return (self.bmg(kz) * k.satz / 100).quantize(CENT)
        if k.steuer_kz is not None:
            return self.wert(k.steuer_kz).quantize(CENT)
        return self.wert(kz).quantize(CENT)

    @property
    def umsatzsteuer(self) -> Decimal:
        """Zeile 37."""
        berechnet = sum((self.steuer(kz) for kz in _UMSATZSTEUER_BMG), NULL)
        gemeldet = sum((self.wert(kz) for kz in _UMSATZSTEUER_FELDER), NULL)
        return (berechnet + gemeldet).quantize(CENT)

    @property
    def vorsteuer(self) -> Decimal:
        """Zeilen 38 bis 44."""
        return sum((self.wert(kz) for kz in _VORSTEUER), NULL).quantize(CENT)

    @property
    def verbleibend(self) -> Decimal:
        """Zeile 45."""
        return self.umsatzsteuer - self.vorsteuer

    @property
    def vorauszahlung_vor_abzug(self) -> Decimal:
        """Zeile 48: Summe der Zeilen 45 bis 47."""
        andere = sum((self.wert(kz) for kz in _ANDERE), NULL).quantize(CENT)
        return self.verbleibend + andere

    @property
    def kz83(self) -> Decimal:
        """Zeile 50: verbleibende Vorauszahlung (positiv) oder Überschuss (negativ)."""
        return self.vorauszahlung_vor_abzug - self.wert(39).quantize(CENT)

    @property
    def zahllast(self) -> Decimal:
        return self.kz83

    @property
    def ist_erstattung(self) -> bool:
        return self.kz83 < 0

    def formularwerte(self) -> dict[int, Decimal]:
        """Kennziffern, wie sie in Vordruck und Datensatz stehen (ohne Nullwerte)."""
        werte: dict[int, Decimal] = {}
        for kz, betrag in self.werte.items():
            k = KENNZIFFERN_2026[kz]
            wert = volle_euro(betrag) if k.art is Art.BMG else betrag.quantize(CENT)
            if k.art is Art.MERKER:
                wert = betrag
            if wert != 0:
                werte[kz] = wert
        if self.berichtigt:
            werte[10] = Decimal("1")
        werte[83] = self.kz83
        return dict(sorted(werte.items()))

    def zusammenfassung(self) -> str:
        """Textfassung zur Durchsicht: Kennziffern mit Zeile, dann das Ergebnis."""
        zeilen = [f"USt-Voranmeldung {self.zeitraum}", "=" * 72]
        werte = self.formularwerte()
        for kz, wert in sorted(
            werte.items(), key=lambda e: KENNZIFFERN_2026[e[0]].zeile
        ):
            if kz == 83:
                continue
            k = KENNZIFFERN_2026[kz]
            text = f"Zeile {k.zeile:>2}  Kz {kz:<3}  {k.bezeichnung[:44]:<44}"
            if k.art is Art.BMG:
                text += f" {betrag_de(wert):>14}"
                if k.satz is not None:
                    text += f"  Steuer {betrag_de(self.steuer(kz)):>12}"
            else:
                text += f" {betrag_de(wert):>14}"
            zeilen.append(text)
        zeilen += [
            "-" * 72,
            f"Zeile 37  Umsatzsteuer                {betrag_de(self.umsatzsteuer):>16}",
            f"Zeile 38–44  Vorsteuer                {betrag_de(self.vorsteuer):>16}",
            f"Zeile 50  Kz 83   "
            f"{'Überschuss' if self.ist_erstattung else 'Vorauszahlung'}"
            f"{'':>10}{betrag_de(self.kz83):>16}",
        ]
        return "\n".join(zeilen)
