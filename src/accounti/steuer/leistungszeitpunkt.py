"""Umsatzsteuerlicher Zeitpunkt einer Ausgangsrechnung — in welchen Monat sie gehört.

Bei der Sollversteuerung entsteht die Steuer mit Ablauf des Voranmeldungszeitraums, in
dem die Leistung ausgeführt wurde — unabhängig davon, wann die Rechnung geschrieben wird
(§ 13 Abs. 1 Nr. 1 Buchst. a Satz 1 UStG, Abschn. 13.1 Abs. 1 UStAE). accounti bucht
eine Ausgangsrechnung deshalb zum Leistungsdatum, wenn die Leistung in einem früheren
Monat lag als die Rechnung; damit stimmen Voranmeldung, Zusammenfassende Meldung,
OSS-Meldung, Saldenliste und DATEV-Export ohne eigenes Steuerperioden-Feld überein, und
der Erlös steht im Geschäftsjahr der Leistung (Realisationsprinzip, § 252 Abs. 1 Nr. 4
HGB).

Ausnahmen:

* Innergemeinschaftliche Lieferung (Kategorie K): Monat der Rechnung, spätestens der
  Monat nach der Lieferung (§ 13 Abs. 1 Nr. 6, § 18b Satz 2, § 18a Abs. 8 UStG).
* Gutschrift/Rechnungskorrektur: Die Minderung gehört in den Monat, in dem sie
  eintritt (§ 17 Abs. 1 Satz 7 UStG) — also zum Datum der Korrektur.
* Leistung nach dem Rechnungsdatum (Voraus- oder Anzahlungsrechnung): accounti bleibt
  beim Rechnungsdatum und weist darauf hin — bei Anzahlungen entsteht die Steuer mit
  der Vereinnahmung (Satz 4), das bildet accounti nicht gesondert ab.
"""

from __future__ import annotations

import calendar
from datetime import date


def monatsende(tag: date) -> date:
    return date(tag.year, tag.month, calendar.monthrange(tag.year, tag.month)[1])


def ende_folgemonat(tag: date) -> date:
    jahr, monat = (tag.year + 1, 1) if tag.month == 12 else (tag.year, tag.month + 1)
    return monatsende(date(jahr, monat, 1))


def steuertag(
    rechnungsdatum: date,
    leistungsdatum: date | None,
    kategorie: str | None,
    korrektur: bool = False,
) -> tuple[date, str | None]:
    """(Buchungstag, Hinweis) für den Teil einer Ausgangsrechnung mit dieser
    Steuerkategorie (EN 16931, BT-151)."""
    leistung = leistungsdatum
    if korrektur or leistung is None or leistung == rechnungsdatum:
        return rechnungsdatum, None
    if kategorie == "K":
        spaetestens = ende_folgemonat(leistung)
        if rechnungsdatum <= spaetestens:
            return rechnungsdatum, None
        return spaetestens, (
            f"ig. Lieferung vom {leistung:%d.%m.%Y}, Rechnung erst vom "
            f"{rechnungsdatum:%d.%m.%Y}: gebucht zum {spaetestens:%d.%m.%Y} — Kz 41 "
            "und Zusammenfassende Meldung spätestens im Monat nach der Lieferung "
            "(§ 13 Abs. 1 Nr. 6, § 18b Satz 2, § 18a Abs. 8 UStG)"
        )
    monat_leistung = (leistung.year, leistung.month)
    monat_rechnung = (rechnungsdatum.year, rechnungsdatum.month)
    if monat_leistung < monat_rechnung:
        return leistung, (
            f"gebucht zum Leistungsdatum {leistung:%d.%m.%Y} statt zum Rechnungsdatum "
            f"{rechnungsdatum:%d.%m.%Y}: die Umsatzsteuer entsteht mit Ablauf des "
            "Voranmeldungszeitraums der Leistung (§ 13 Abs. 1 Nr. 1 Buchst. a UStG)"
        )
    if monat_leistung > monat_rechnung:
        return rechnungsdatum, (
            f"Leistung am {leistung:%d.%m.%Y} nach dem Rechnungsdatum: gebucht zum "
            "Rechnungsdatum — die Umsatzsteuer entsteht erst mit Ablauf des "
            "Voranmeldungszeitraums der Leistung, bei einer Anzahlung mit der "
            "Vereinnahmung (§ 13 Abs. 1 Nr. 1 Buchst. a Satz 1 und 4 UStG); "
            "Anzahlungsrechnungen bildet accounti nicht gesondert ab — prüfen"
        )
    return rechnungsdatum, None
