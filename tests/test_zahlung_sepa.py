"""SEPA-Überweisung als pain.001.001.09 nach DK-TVS GBIC_5 (Anlage 3 DFÜ-Abkommen)."""

from datetime import date
from decimal import Decimal

from accounti.zahlung.sepa import referenz, sepa_text, verwendungszweck


def test_dk_zeichensatz_umlaute_bleiben_fremdes_wird_ersetzt():
    assert (
        sepa_text("Bürobedarf Müller & Söhne GmbH") == "Bürobedarf Müller & Söhne GmbH"
    )
    assert sepa_text("Café Žižek – «Spezial»") == "Cafe Zizek Spezial"
    assert sepa_text("  Größe: 100 %  *neu*  ") == "Größe: 100 % *neu*"
    assert sepa_text("Łódź S.A.") == "Lodz S.A."
    assert sepa_text("x" * 80, 70) == "x" * 70
    assert sepa_text("€€€") == ""


def test_referenzen_nur_latin_ohne_schraegstrich_am_rand():
    assert referenz("RE-2026/0042") == "RE-2026/0042"
    assert referenz("/RE//2026/") == "RE/2026"
    assert referenz("Müller#42_A") == "Muller42A"
    assert referenz("A" * 40) == "A" * 35
    assert referenz("###") == ""


def test_verwendungszweck():
    assert (
        verwendungszweck("RE-2026-0042", date(2026, 10, 10), Decimal("0"))
        == "RE-2026-0042 vom 10.10.2026"
    )
    assert (
        verwendungszweck("RE-200", date(2026, 10, 10), Decimal("23.80"))
        == "RE-200 vom 10.10.2026, abzgl. 23,80 EUR Skonto"
    )
    assert verwendungszweck(None, None, Decimal("0")) == "Rechnung"
    assert len(verwendungszweck("X" * 200, date(2026, 1, 1), Decimal("1"))) == 140
