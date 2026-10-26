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
  eintritt (§ 17 Abs. 1 Satz 8 UStG) — also zum Datum der Korrektur.
* Leistung nach dem Rechnungsdatum (Voraus- oder Anzahlungsrechnung): accounti bleibt
  beim Rechnungsdatum und weist darauf hin — bei Anzahlungen entsteht die Steuer mit
  der Vereinnahmung (Satz 4), das bildet accounti nicht gesondert ab.

Schuldet der Leistungsempfänger die Steuer (Eingangsrechnung,
``steuertag_empfaenger``), entsteht sie

* bei einer sonstigen Leistung eines im übrigen Gemeinschaftsgebiet ansässigen
  Unternehmers mit Ablauf des Voranmeldungszeitraums der Leistung (§ 13b Abs. 1 UStG),
* in den übrigen Fällen des § 13b (Abs. 2: Werklieferungen und sonstige Leistungen
  anderer ausländischer Unternehmer, Bauleistungen, Gebäudereinigung …) und beim
  ig. Erwerb mit Ausstellung der Rechnung, spätestens mit Ablauf des Folgemonats der
  Leistung bzw. des Erwerbs (§ 13b Abs. 2, § 13 Abs. 1 Nr. 6 UStG);

die Vorsteuer ist im selben Zeitraum abziehbar, ohne dass die Rechnung vorliegen muss
(§ 15 Abs. 1 S. 1 Nr. 3, 4 UStG). Welcher Absatz gilt, entscheidet accounti wie die
Voranmeldung (Kz 46/47 oder 84/85) nach dem Land des Leistenden — eine Werklieferung
eines EU-Unternehmers (§ 13b Abs. 2 Nr. 1) erkennt es nicht. Dauerleistungen
(§ 13b Abs. 3) und Anzahlungen (§ 13b Abs. 4 Satz 2) bildet accounti nicht ab.
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


def _monat(tag: date) -> tuple[int, int]:
    return tag.year, tag.month


def steuertag_empfaenger(
    rechnungsdatum: date,
    leistungsdatum: date | None,
    fall: str,
    eu_leistender: bool,
) -> tuple[date, str | None]:
    """(Buchungstag, Hinweis) für den Teil einer Eingangsrechnung, dessen Steuer der
    Empfänger schuldet: ``fall`` AE (§ 13b) oder K (ig. Erwerb); ``eu_leistender``:
    der Leistende sitzt im übrigen Gemeinschaftsgebiet (§ 13b Abs. 1)."""
    leistung = leistungsdatum
    if fall == "AE" and eu_leistender:
        if leistung is None:
            return rechnungsdatum, (
                "§ 13b Abs. 1 UStG (sonstige Leistung eines EU-Unternehmers): die "
                "Steuer entsteht mit Ablauf des Voranmeldungszeitraums der Leistung — "
                "der Beleg nennt kein Leistungsdatum, gebucht zum Rechnungsdatum "
                f"{rechnungsdatum:%d.%m.%Y}; lag die Leistung in einem früheren Monat, "
                "die Buchung auf den Leistungsmonat umdatieren"
            )
        if _monat(leistung) < _monat(rechnungsdatum):
            return leistung, (
                f"gebucht zum Leistungsdatum {leistung:%d.%m.%Y} statt zum "
                f"Rechnungsdatum {rechnungsdatum:%d.%m.%Y}: bei einer sonstigen "
                "Leistung eines EU-Unternehmers entsteht die Steuer mit Ablauf des "
                "Voranmeldungszeitraums der Leistung (§ 13b Abs. 1 UStG), die "
                "Vorsteuer im selben Zeitraum (§ 15 Abs. 1 S. 1 Nr. 4 UStG); bei einer "
                "Werklieferung gilt § 13b Abs. 2 Nr. 1 (Rechnungsmonat, spätestens "
                "Folgemonat; Kz 84/85)"
            )
    elif leistung is not None:
        spaetestens = ende_folgemonat(leistung)
        if rechnungsdatum > spaetestens:
            art, regel, vorsteuer = (
                ("ig. Erwerb", "§ 13 Abs. 1 Nr. 6 UStG", "Nr. 3")
                if fall == "K"
                else ("Leistung nach § 13b", "§ 13b Abs. 2 UStG", "Nr. 4")
            )
            return spaetestens, (
                f"{art} vom {leistung:%d.%m.%Y}, Rechnung erst vom "
                f"{rechnungsdatum:%d.%m.%Y}: gebucht zum {spaetestens:%d.%m.%Y} — die "
                "Steuer entsteht mit Ausstellung der Rechnung, spätestens mit Ablauf "
                f"des Folgemonats ({regel}), die Vorsteuer im selben Zeitraum (§ 15 "
                f"Abs. 1 S. 1 {vorsteuer} UStG)"
            )
    if (
        fall == "AE"
        and leistung is not None
        and _monat(leistung) > _monat(rechnungsdatum)
    ):
        return rechnungsdatum, (
            f"Leistung am {leistung:%d.%m.%Y} nach dem Rechnungsdatum: gebucht zum "
            "Rechnungsdatum — nach § 13b entsteht die Steuer nicht vor der Leistung, "
            "bei Zahlung vorher mit Ablauf des Voranmeldungszeitraums der Zahlung "
            "(§ 13b Abs. 4 Satz 2 UStG); Anzahlungen bildet accounti nicht gesondert "
            "ab — prüfen"
        )
    return rechnungsdatum, None
