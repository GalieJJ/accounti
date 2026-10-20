from datetime import date

import pytest

from accounti.steuer.zeitraum import Zeitraum, ZeitraumError


def test_monat():
    z = Zeitraum.lies("2026-08")
    assert (z.von, z.bis) == (date(2026, 8, 1), date(2026, 8, 31))
    assert z.art == "monat"
    assert z.elster_code == "08"
    assert str(z) == "2026-08"
    assert z.text == "August 2026"
    assert z.enthaelt(date(2026, 8, 31)) and not z.enthaelt(date(2026, 9, 1))


def test_quartal():
    z = Zeitraum.lies("2026-q3")
    assert (z.von, z.bis) == (date(2026, 7, 1), date(2026, 9, 30))
    assert z.elster_code == "43"
    assert str(z) == "2026-Q3"
    assert z.text == "III. Quartal 2026"
    assert [str(m) for m in z.monate()] == ["2026-07", "2026-08", "2026-09"]


def test_jahr_hat_keinen_elster_code():
    z = Zeitraum.lies("2026")
    assert (z.von, z.bis) == (date(2026, 1, 1), date(2026, 12, 31))
    with pytest.raises(ZeitraumError):
        _ = z.elster_code


def test_vorperiode_und_vorjahr():
    assert str(Zeitraum.lies("2026-01").vorperiode()) == "2025-12"
    assert str(Zeitraum.lies("2026-Q1").vorperiode()) == "2025-Q4"
    assert str(Zeitraum.lies("2026-08").vorjahr()) == "2025-08"
    assert str(Zeitraum.lies("2026-Q2").vorjahr()) == "2025-Q2"


def test_februar_schaltjahr():
    assert Zeitraum.lies("2028-02").bis == date(2028, 2, 29)


@pytest.mark.parametrize(
    "text", ["2026-13", "2026-Q5", "26-08", "August", "", "2026-00"]
)
def test_unzulaessig(text):
    with pytest.raises(ZeitraumError):
        Zeitraum.lies(text)
