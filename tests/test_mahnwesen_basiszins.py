"""Basiszinssatz nach § 247 BGB — datiert, mit Gültigkeitszeitraum."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from accounti.mahnwesen.basiszins import (
    BASISZINSSAETZE,
    Basiszins,
    BasiszinsUnbekanntError,
    basiszins_am,
    tabelle,
)


def test_tabelle_lueckenlos_halbjaehrlich_und_aktuell():
    saetze = list(BASISZINSSAETZE)
    assert saetze[0] == Basiszins(date(2002, 7, 1), date(2002, 12, 31), Decimal("2.47"))
    assert saetze[-1] == Basiszins(
        date(2026, 7, 1), date(2026, 12, 31), Decimal("1.52")
    )
    for vorher, nachher in zip(saetze, saetze[1:], strict=False):
        assert vorher.bis + timedelta(days=1) == nachher.ab
    assert all(s.ab.day == 1 and s.ab.month in (1, 7) for s in saetze)
    assert len(saetze) == 49


@pytest.mark.parametrize(
    ("tag", "satz"),
    [
        (date(2026, 7, 1), "1.52"),
        (date(2026, 6, 30), "1.27"),
        (date(2026, 1, 1), "1.27"),
        (date(2025, 6, 30), "2.27"),
        (date(2024, 3, 1), "3.62"),
        (date(2023, 1, 1), "1.62"),
        (date(2022, 12, 31), "-0.88"),
        (date(2016, 6, 30), "-0.83"),
        (date(2013, 1, 1), "-0.13"),
        (date(2011, 7, 1), "0.37"),
        (date(2008, 1, 1), "3.32"),
    ],
)
def test_satz_am_stichtag(tag, satz):
    assert basiszins_am(tag).satz == Decimal(satz)


def test_ohne_bekannten_satz_klare_meldung():
    with pytest.raises(BasiszinsUnbekanntError, match=r"01\.01\.2027.*basiszinssaetze"):
        basiszins_am(date(2027, 1, 1))
    with pytest.raises(BasiszinsUnbekanntError):
        basiszins_am(date(2002, 6, 30))


def test_ergaenzung_und_korrektur_aus_der_konfiguration():
    saetze = tabelle(
        [
            Basiszins(date(2027, 1, 1), date(2027, 6, 30), Decimal("1.77")),
            Basiszins(date(2026, 7, 1), date(2026, 12, 31), Decimal("1.60")),
        ]
    )
    assert basiszins_am(date(2027, 3, 1), saetze).satz == Decimal("1.77")
    assert basiszins_am(date(2026, 8, 1), saetze).satz == Decimal("1.60")
    with pytest.raises(BasiszinsUnbekanntError):
        basiszins_am(date(2027, 7, 1), saetze)
    with pytest.raises(ValueError, match="überschneid"):
        tabelle([Basiszins(date(2026, 10, 1), date(2027, 3, 31), Decimal("2"))])
