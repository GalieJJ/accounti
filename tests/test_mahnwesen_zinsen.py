"""Verzugszinsen nach § 288 BGB gegen handgerechnete Werte.

Formel je Abschnitt: Kapital × (Basiszinssatz + 9 bzw. 5) / 100 × Tage / 365,
kaufmännisch auf Cent gerundet; die Zinsen sind die Summe der Abschnitte.
"""

from datetime import date
from decimal import Decimal

import pytest

from accounti.mahnwesen.basiszins import BasiszinsUnbekanntError
from accounti.mahnwesen.zinsen import summe, verzugszinsen

D = Decimal


def test_b2b_ein_abschnitt():
    # 1190 × 10,52 % × 31 / 365 = 10,632405… → 10,63
    (a,) = verzugszinsen(D("1190.00"), [], date(2026, 8, 1), date(2026, 8, 31), True)
    assert (a.von, a.bis, a.tage) == (date(2026, 8, 1), date(2026, 8, 31), 31)
    assert (a.basiszins, a.satz, a.kapital) == (D("1.52"), D("10.52"), D("1190.00"))
    assert a.zinsen == D("10.63")


def test_b2c_fuenf_prozentpunkte():
    # 1190 × 6,52 % × 31 / 365 = 6,589665… → 6,59
    abschnitte = verzugszinsen(
        D("1190.00"), [], date(2026, 8, 1), date(2026, 8, 31), False
    )
    assert abschnitte[0].satz == D("6.52")
    assert summe(abschnitte) == D("6.59")


def test_ueber_den_wechsel_des_basiszinssatzes_am_1_juli_2026():
    # 16.–30.06.: 1190 × 10,27 % × 15 / 365 = 5,022445… → 5,02
    # 01.–15.07.: 1190 × 10,52 % × 15 / 365 = 5,144712… → 5,14
    abschnitte = verzugszinsen(
        D("1190.00"), [], date(2026, 6, 16), date(2026, 7, 15), True
    )
    assert [(a.von, a.bis, a.tage, a.satz, a.zinsen) for a in abschnitte] == [
        (date(2026, 6, 16), date(2026, 6, 30), 15, D("10.27"), D("5.02")),
        (date(2026, 7, 1), date(2026, 7, 15), 15, D("10.52"), D("5.14")),
    ]
    assert summe(abschnitte) == D("10.16")


def test_teilzahlung_im_verzug_senkt_das_kapital_ab_dem_zahltag():
    # Rest heute 190, am 11.08. kamen 1000: bis 10.08. auf 1190, ab 11.08. auf 190
    # 1190 × 10,52 % × 10 / 365 = 3,429808… → 3,43
    #  190 × 10,52 % × 21 / 365 = 1,149994… → 1,15
    abschnitte = verzugszinsen(
        D("190.00"),
        [(date(2026, 8, 11), D("1000.00")), (date(2026, 7, 1), D("50.00"))],
        date(2026, 8, 1),
        date(2026, 8, 31),
        True,
    )
    assert [(a.tage, a.kapital, a.zinsen) for a in abschnitte] == [
        (10, D("1190.00"), D("3.43")),
        (21, D("190.00"), D("1.15")),
    ]
    assert summe(abschnitte) == D("4.58")


def test_zahlung_nach_dem_stichtag_zaehlt_noch_zum_kapital():
    (a,) = verzugszinsen(
        D("0.00"),
        [(date(2026, 9, 5), D("1190.00"))],
        date(2026, 8, 1),
        date(2026, 8, 31),
        True,
    )
    assert a.kapital == D("1190.00") and a.zinsen == D("10.63")


def test_kein_verzug_keine_zinsen():
    assert verzugszinsen(D("100"), [], date(2026, 8, 2), date(2026, 8, 1), True) == []
    assert summe([]) == D("0.00")


def test_unbekannter_basiszins_bricht_ab():
    with pytest.raises(BasiszinsUnbekanntError):
        verzugszinsen(D("100"), [], date(2026, 12, 1), date(2027, 1, 15), True)
