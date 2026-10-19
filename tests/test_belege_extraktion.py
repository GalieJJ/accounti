from datetime import date
from decimal import Decimal
from pathlib import Path

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
