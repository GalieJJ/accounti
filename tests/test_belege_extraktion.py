from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.belege.extraktion import Steuerzeile, extrahiere

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "belege"


def _lies(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_rechnung_mit_zwei_steuersaetzen():
    e = extrahiere(_lies("rechnung_zwei_steuersaetze.txt"))
    assert e.belegnummer == "RE-2026-0042"
    assert e.belegdatum == date(2026, 3, 5)
    assert e.leistungsdatum == date(2026, 3, 3)
    assert e.lieferant_name == "Bürobedarf Müller GmbH"
    assert e.lieferant_ust_id == "DE123456789"
    assert e.iban == "DE89370400440532013000"
    assert e.zahlungsziel == date(2026, 3, 19)
    assert e.skonto_prozent == Decimal("2")
    assert e.skonto_tage == 7
    assert e.steuerzeilen == [
        Steuerzeile(Decimal("19"), Decimal("100.00"), Decimal("19.00")),
        Steuerzeile(Decimal("7"), Decimal("50.00"), Decimal("3.50")),
    ]
    assert e.netto == Decimal("150.00")
    assert e.steuer == Decimal("22.50")
    assert e.brutto == Decimal("172.50")
    assert e.rechenprobe is True


def test_quittung_mit_inklusive_steuer():
    e = extrahiere(_lies("quittung_tankstelle.txt"))
    assert e.lieferant_name == "Tankstelle Nord GmbH & Co. KG"
    assert e.belegdatum == date(2026, 3, 12)
    assert e.belegnummer == "4711"
    assert e.steuerzeilen == [
        Steuerzeile(Decimal("19"), Decimal("63.72"), Decimal("12.11"))
    ]
    assert e.brutto == Decimal("75.83")
    assert e.rechenprobe is True


def test_steuerzeile_mit_nur_einem_betrag():
    e = extrahiere(_lies("ausgangsrechnung.txt"))
    assert e.belegnummer == "2026-117"
    assert e.belegdatum == date(2026, 3, 10)
    assert e.zahlungsziel == date(2026, 3, 24)
    assert e.lieferant_ust_id == "DE999999999"
    assert e.steuerzeilen == [
        Steuerzeile(Decimal("19"), Decimal("1000.00"), Decimal("190.00"))
    ]
    assert e.brutto == Decimal("1190.00")
    assert e.rechenprobe is True


def test_rechenprobe_schlaegt_fehl():
    text = """Firma Test GmbH
Rechnung Nr. 1
Datum: 01.03.2026
Nettobetrag 100,00
zzgl. 19 % MwSt. 19,00
Gesamtbetrag 120,00"""
    e = extrahiere(text)
    assert e.rechenprobe is False


def test_unvollstaendige_rechnung():
    e = extrahiere(_lies("rechnung_unvollstaendig.txt"))
    assert e.belegnummer is None
    assert e.belegdatum is None
    assert e.lieferant_name == "Hans Beispiel"
    assert e.brutto == Decimal("450.00")
    assert e.steuerzeilen == []
    assert e.rechenprobe is None


def test_ungueltige_iban_wird_ignoriert():
    e = extrahiere("Firma\nIBAN DE00 3704 0044 0532 0130 00")
    assert e.iban is None


def test_kundennummer_ist_keine_rechnungsnummer():
    e = extrahiere("Firma GmbH\nKundennummer: 100234\nRechnung\n")
    assert e.belegnummer is None


def test_label_nimmt_den_ersten_betrag_dahinter():
    e = extrahiere("Firma GmbH\nNetto 63,72   MwSt 12,11   Brutto 75,83\n")
    assert e.netto == Decimal("63.72")
    assert e.brutto == Decimal("75.83")


def test_brutto_inklusive_steuer_und_nicht_aus_nettosumme():
    e = extrahiere(
        "Firma GmbH\nSumme netto 150,00\nGesamtbetrag inkl. 19 % MwSt 178,50\n"
    )
    assert e.brutto == Decimal("178.50")
    assert e.netto == Decimal("150.00")


# --- Gesamttest Paket C: 0 %, Hinweistexte, Vorzeichen, „ohne Abzug“ -------------

REVERSE_CHARGE = """Galerietechnik Salzburg GmbH
Getreidegasse 9 · 5020 Salzburg · Österreich
UID: ATU12345678

Galerie Muster GmbH
USt-IdNr.: DE999999999

Rechnung

Rechnungsnummer: GS-2026-044
Rechnungsdatum: 02.04.2026

Summe netto                                        600,00 €
USt 0 %                                              0,00 €
Rechnungsbetrag                                    600,00 €

Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge).
Zahlbar innerhalb von 14 Tagen ohne Abzug.
"""


def test_nullsatz_mit_hinweis_auf_13b_ist_steuerangabe():
    """B06: Die 0-%-Zeile wird nicht verworfen, der Hinweis ist das Kennzeichen."""
    e = extrahiere(REVERSE_CHARGE)
    assert e.steuerzeilen == [Steuerzeile(Decimal("0"), Decimal("600.00"), Decimal(0))]
    assert (e.netto, e.steuer, e.brutto) == (
        Decimal("600.00"),
        Decimal("0.00"),
        Decimal("600.00"),
    )
    assert e.steuerkennzeichen == "AE"
    assert e.lieferant_ust_id == "ATU12345678"
    assert e.rechenprobe is True


@pytest.mark.parametrize(
    "zeile",
    ["Umsatzsteuer (0 %) 0,00 €", "USt 0 % auf 600,00 € 0,00 €", "MwSt. 0 % 0,00"],
)
def test_nullsatz_in_verschiedenen_schreibweisen(zeile):
    e = extrahiere(
        f"Firma GmbH\nRechnung\nNettobetrag 600,00\n{zeile}\nGesamt 600,00\n"
    )
    assert e.steuerzeilen == [Steuerzeile(Decimal("0"), Decimal("600.00"), Decimal(0))]
    assert e.steuer == Decimal("0.00")


@pytest.mark.parametrize(
    ("hinweis", "kennzeichen"),
    [
        ("Gemäß § 19 Abs. 1 UStG wird keine Umsatzsteuer berechnet.", "E"),
        ("Steuerfrei nach § 4 Nr. 14 UStG.", "E"),
        ("Steuerfreie innergemeinschaftliche Lieferung.", "K"),
        ("Reverse Charge — VAT to be accounted for by the recipient", "AE"),
    ],
)
def test_hinweis_ohne_nullzeile_wird_nullsatz(hinweis, kennzeichen):
    e = extrahiere(f"Atelier Klein\nRechnung Nr. 7\nGesamtbetrag 250,00 €\n{hinweis}\n")
    assert e.steuerkennzeichen == kennzeichen
    assert e.steuerzeilen == [Steuerzeile(Decimal("0"), Decimal("250.00"), Decimal(0))]
    assert e.steuer == Decimal("0.00")


def test_hinweis_bei_besteuerter_summe_wird_kein_nullsatz():
    """Netto ≠ Brutto: eine besteuerte Rechnung, deren Steuerzeile fehlt — kein 0 %."""
    e = extrahiere(
        "Firma GmbH\nNettobetrag 100,00\nGesamtbetrag 119,00\n"
        "Hinweis: bei Lieferungen ins Ausland Reverse Charge.\n"
    )
    assert e.steuerzeilen == [] and e.steuer is None


GUTSCHRIFT = """Rahmenwerk Nord GmbH
USt-IdNr.: DE811907980

Gutschrift (Rechnungskorrektur)

Rechnungsnummer: RW-G-0012
Rechnungsdatum: 20.10.2026

Pos. Bezeichnung                 Menge  Einzelpreis   Gesamt
1    Rücknahme Bilderrahmen Eiche    -4        50,00   -200,00

Summe netto                                       -200,00 €
zzgl. 19 % USt                                     -38,00 €
Gutschriftbetrag                                  -238,00 €
"""


def test_gutschrift_behaelt_das_vorzeichen():
    """B12: Steuer −38 (nicht +38), Brutto −238 aus „Gutschriftbetrag“."""
    e = extrahiere(GUTSCHRIFT)
    assert e.steuerzeilen == [
        Steuerzeile(Decimal("19"), Decimal("-200.00"), Decimal("-38.00"))
    ]
    assert (e.netto, e.steuer, e.brutto) == (
        Decimal("-200.00"),
        Decimal("-38.00"),
        Decimal("-238.00"),
    )
    assert e.rechenprobe is True
    assert e.korrektur == "korrektur" and not e.vorzeichen_gedreht


def test_rechnungskorrektur_mit_positiven_betraegen_wird_negiert():
    positiv = GUTSCHRIFT.replace("-4 ", "4 ").replace("-2", "2").replace("-3", "3")
    e = extrahiere(positiv)
    assert (e.netto, e.steuer, e.brutto) == (
        Decimal("-200.00"),
        Decimal("-38.00"),
        Decimal("-238.00"),
    )
    assert e.vorzeichen_gedreht and e.korrektur == "korrektur"


def test_gemischte_vorzeichen_bestehen_die_rechenprobe_nicht():
    e = extrahiere("Firma GmbH\nSumme netto -200,00\nzzgl. 19 % USt 38,00\n")
    assert e.brutto == Decimal("-162.00")
    assert e.rechenprobe is False


def test_gutschrift_als_posten_einer_rechnung_ist_kein_korrekturbeleg():
    e = extrahiere(
        "Firma GmbH\nRechnung\nGutschrift vom 01.10.2026 -50,00\n"
        "Summe netto 100,00\nzzgl. 19 % USt 19,00\nGesamtbetrag 119,00\n"
    )
    assert e.korrektur is None and e.brutto == Decimal("119.00")


def test_ohne_abzug_heisst_ausdruecklich_kein_skonto():
    """B09: „ohne Abzug“ ist 0 % — nicht „unbekannt“ (sonst Kontakt-Skonto)."""
    e = extrahiere(REVERSE_CHARGE)
    assert (e.skonto_prozent, e.skonto_tage) == (Decimal("0"), 0)
    mit = extrahiere(
        "Firma GmbH\nRechnungsdatum: 01.10.2026\n"
        "Zahlbar innerhalb von 30 Tagen ohne Abzug.\n"
        "Bei Zahlung innerhalb von 10 Tagen 2 % Skonto.\n"
    )
    assert (mit.skonto_prozent, mit.skonto_tage) == (Decimal("2"), 10)
    assert mit.zahlungsziel == date(2026, 10, 31)
