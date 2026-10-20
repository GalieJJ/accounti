"""Vordruck USt 1 A 2026.

BMF-Schreiben vom 29.12.2025, III C 3 - S 7344/00039/007/036.
"""

from decimal import Decimal

import pytest

from accounti.steuer.umsatzsteuer import DATEV_BU_SCHLUESSEL, UStBerechner
from accounti.steuer.voranmeldung import (
    KENNZIFFERN_2026,
    Art,
    UStVoranmeldung,
)

D = Decimal

# Kennziffer → Zeile laut Vordruckmuster 2026 (Seiten 1–3)
ZEILEN_2026 = {
    10: 10, 22: 11, 70: 12,
    81: 13, 86: 14, 87: 15, 35: 16, 36: 16, 77: 17, 76: 18, 80: 18,
    41: 19, 44: 20, 49: 21, 43: 22, 48: 23,
    91: 24, 89: 25, 93: 26, 90: 27, 95: 28, 98: 28, 94: 29, 96: 29,
    46: 30, 47: 30, 73: 31, 74: 31, 84: 32, 85: 32,
    42: 33, 60: 34, 21: 35, 45: 36,
    66: 38, 61: 39, 62: 40, 67: 41, 63: 42, 59: 43, 64: 44,
    65: 46, 69: 47, 39: 49, 83: 50, 50: 51, 37: 52,
    29: 53, 26: 54, 500: 55,
}  # fmt: skip


def test_alle_kennziffern_des_vordrucks_2026_mit_zeile():
    assert {kz: k.zeile for kz, k in KENNZIFFERN_2026.items()} == ZEILEN_2026
    assert 23 not in KENNZIFFERN_2026  # 2026 durch Kz 500 ersetzt


def test_steuer_wird_bei_81_86_89_93_aus_der_bemessungsgrundlage_berechnet():
    satz = {kz: k.satz for kz, k in KENNZIFFERN_2026.items() if k.satz is not None}
    assert satz == {
        81: D("19"),
        86: D("7"),
        87: D("0"),
        89: D("19"),
        93: D("7"),
        90: D("0"),
    }
    paare = {kz: k.steuer_kz for kz, k in KENNZIFFERN_2026.items() if k.steuer_kz}
    assert paare == {35: 36, 76: 80, 95: 98, 94: 96, 46: 47, 73: 74, 84: 85}
    assert KENNZIFFERN_2026[46].bezeichnung.startswith("Sonstige Leistungen nach § 3a")
    assert KENNZIFFERN_2026[66].art is Art.STEUER
    assert KENNZIFFERN_2026[10].art is Art.MERKER


def _va(**werte: str) -> UStVoranmeldung:
    va = UStVoranmeldung(zeitraum="2026-08")
    for kz, betrag in werte.items():
        va.addiere(int(kz.removeprefix("kz")), D(betrag))
    return va


def test_volle_euro_und_kz83():
    va = _va(
        kz81="10000.75",
        kz86="2000.40",
        kz41="5000.99",
        kz21="300.50",
        kz45="800.00",
        kz66="1234.56",
    )
    assert va.bmg(81) == D("10000")
    assert va.steuer(81) == D("1900.00")  # 10.000 € × 19 %, nicht 10.000,75 € × 19 %
    assert va.steuer(86) == D("140.00")
    assert va.umsatzsteuer == D("2040.00")  # Zeile 37
    assert va.vorsteuer == D("1234.56")  # Zeilen 38–44
    assert va.kz83 == D("805.44")
    assert va.formularwerte() == {
        21: D("300"),
        41: D("5000"),
        45: D("800"),
        66: D("1234.56"),
        81: D("10000"),
        83: D("805.44"),
        86: D("2000"),
    }


def test_negative_bemessungsgrundlage_wird_gegen_null_abgeschnitten():
    va = _va(kz81="-50.75")
    assert va.bmg(81) == D("-50")
    assert va.steuer(81) == D("-9.50")
    assert va.kz83 == D("-9.50")


def test_reverse_charge_ist_neutral_und_ig_erwerb_7_prozent():
    va = _va(kz46="1000.00", kz47="190.00", kz67="190.00", kz93="100.00", kz61="7.00")
    assert va.umsatzsteuer == D("197.00")
    assert va.vorsteuer == D("197.00")
    assert va.kz83 == D("0.00")
    assert va.formularwerte()[93] == D("100")


def test_sondervorauszahlung_und_andere_steuerbetraege():
    va = _va(kz81="1000", kz65="10.00", kz69="5.00", kz39="100.00")
    # 190,00 + 10,00 + 5,00 − 100,00
    assert va.vorauszahlung_vor_abzug == D("205.00")  # Zeile 48
    assert va.kz83 == D("105.00")


def test_erstattung_und_berichtigung():
    va = _va(kz81="100", kz66="500.00")
    va.berichtigt = True
    assert va.kz83 == D("-481.00")
    assert va.ist_erstattung
    assert va.formularwerte()[10] == D("1")


def test_unbekannte_kennziffer():
    va = UStVoranmeldung(zeitraum="2026-08")
    with pytest.raises(KeyError):
        va.addiere(23, D("1"))


def test_zusammenfassung_nennt_zeilen_und_ergebnis():
    text = _va(kz81="1000", kz66="50.00").zusammenfassung()
    assert "Kz 81" in text and "Zeile 13" in text
    assert "190,00" in text
    assert "Kz 83" in text and "140,00" in text


def test_oss_umsatz_gehoert_in_kz_45():
    pos = UStBerechner().berechne_ust(D("100.00"), "FR")
    assert pos.kennziffer_ust_va == 45


def test_datev_schluessel_ig_erwerb_und_13b():
    assert DATEV_BU_SCHLUESSEL["ig_erwerb_19"] == 19
    assert DATEV_BU_SCHLUESSEL["ig_erwerb_7"] == 18
    assert DATEV_BU_SCHLUESSEL["reverse_charge"] == 94
