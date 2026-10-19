from datetime import date
from decimal import Decimal

import pytest

from accounti.belege.zahlen import parse_betrag, parse_datum


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("1.234,56", "1234.56"),
        ("1234,56", "1234.56"),
        ("-23,99", "-23.99"),
        ("23,99-", "-23.99"),
        ("1.234,56 €", "1234.56"),
        ("EUR 12,00", "12.00"),
        ("12,5", "12.50"),
        ("1.000", "1000.00"),
        ("+5,00", "5.00"),
    ],
)
def test_parse_betrag(text, erwartet):
    assert parse_betrag(text) == Decimal(erwartet)


@pytest.mark.parametrize("text", ["", "abc", "12.34.56"])
def test_parse_betrag_ungueltig(text):
    assert parse_betrag(text) is None


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("05.03.2026", date(2026, 3, 5)),
        ("5.3.26", date(2026, 3, 5)),
        ("5. März 2026", date(2026, 3, 5)),
        ("05. Maerz 2026", date(2026, 3, 5)),
        ("2026-03-05", date(2026, 3, 5)),
        ("31.12.2025", date(2025, 12, 31)),
    ],
)
def test_parse_datum(text, erwartet):
    assert parse_datum(text) == erwartet


@pytest.mark.parametrize("text", ["32.01.2026", "29.02.2026", "", "morgen"])
def test_parse_datum_ungueltig(text):
    assert parse_datum(text) is None
