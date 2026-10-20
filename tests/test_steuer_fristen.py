"""Fristen nach § 18 UStG, §§ 46 ff. UStDV, § 18a UStG; § 108 Abs. 3 AO."""

from datetime import date

import pytest

from accounti.steuer.feiertage import feiertage, naechster_werktag, ostersonntag
from accounti.steuer.fristen import (
    faellige_fristen,
    fristenkalender,
    oss_frist,
    sondervorauszahlung_frist,
    ustva_frist,
    zm_frist,
)
from accounti.steuer.zeitraum import Zeitraum


def z(text):
    return Zeitraum.lies(text)


@pytest.mark.parametrize(
    "ostern",
    [date(2019, 4, 21), date(2020, 4, 12), date(2023, 4, 9), date(2024, 3, 31),
     date(2025, 4, 20), date(2026, 4, 5), date(2038, 4, 25), date(2285, 3, 22)],
)  # fmt: skip
def test_ostersonntag(ostern):
    assert ostersonntag(ostern.year) == ostern


def test_bundeseinheitliche_feiertage_2026():
    assert feiertage(2026) == {
        date(2026, 1, 1): "Neujahr",
        date(2026, 4, 3): "Karfreitag",
        date(2026, 4, 6): "Ostermontag",
        date(2026, 5, 1): "Tag der Arbeit",
        date(2026, 5, 14): "Christi Himmelfahrt",
        date(2026, 5, 25): "Pfingstmontag",
        date(2026, 10, 3): "Tag der Deutschen Einheit",
        date(2026, 12, 25): "1. Weihnachtstag",
        date(2026, 12, 26): "2. Weihnachtstag",
    }


def test_landesfeiertage():
    bayern = feiertage(2026, "BY")
    assert bayern[date(2026, 1, 6)] == "Heilige Drei Könige"
    assert bayern[date(2026, 6, 4)] == "Fronleichnam"
    assert bayern[date(2026, 11, 1)] == "Allerheiligen"
    assert date(2026, 10, 31) not in bayern
    assert feiertage(2026, "SN")[date(2026, 11, 18)] == "Buß- und Bettag"
    assert feiertage(2026, "BE")[date(2026, 3, 8)] == "Internationaler Frauentag"
    assert feiertage(2026, "TH")[date(2026, 9, 20)] == "Weltkindertag"
    assert feiertage(2026, "NI")[date(2026, 10, 31)] == "Reformationstag"
    assert date(2026, 8, 15) in feiertage(2026, "SL")


def test_naechster_werktag_mit_landesfeiertag():
    assert naechster_werktag(date(2026, 6, 4)) == date(2026, 6, 4)
    assert naechster_werktag(date(2026, 6, 4), "BY") == date(2026, 6, 5)


@pytest.mark.parametrize(
    ("zeitraum", "faellig", "grund"),
    [
        ("2026-08", date(2026, 9, 10), None),  # Donnerstag
        ("2025-12", date(2026, 1, 12), "Samstag"),  # 10.01.2026
        ("2026-04", date(2026, 5, 11), "Sonntag"),  # 10.05.2026
        ("2026-09", date(2026, 10, 12), "Samstag"),  # 10.10.2026
        ("2023-03", date(2023, 4, 11), "Ostermontag"),  # bundeseinheitlich
        ("2020-03", date(2020, 4, 14), "Karfreitag"),  # Karfreitag … Ostermontag
        ("2026-Q1", date(2026, 4, 10), None),
        ("2026-Q3", date(2026, 10, 12), "Samstag"),
    ],
)
def test_akzeptanz_6_voranmeldung_zum_10(zeitraum, faellig, grund):
    f = ustva_frist(z(zeitraum))
    assert f.faellig_am == faellig
    assert f.grund == grund
    assert f.gesetzlich.day == 10
    assert f.verschoben is (grund is not None)


def test_dauerfristverlaengerung_einen_monat_spaeter():
    assert ustva_frist(z("2026-08"), dauerfrist=True).faellig_am == date(2026, 10, 12)
    assert ustva_frist(z("2026-09"), dauerfrist=True).faellig_am == date(2026, 11, 10)
    assert ustva_frist(z("2026-Q1"), dauerfrist=True).faellig_am == date(2026, 5, 11)
    assert ustva_frist(z("2026-12"), dauerfrist=True).faellig_am == date(2027, 2, 10)


def test_sonderfall_10_februar():
    f = sondervorauszahlung_frist(2026)
    assert (f.gesetzlich, f.faellig_am, f.grund) == (
        date(2026, 2, 10),
        date(2026, 2, 10),
        None,
    )
    assert sondervorauszahlung_frist(2024).faellig_am == date(2024, 2, 12)  # Samstag


def test_zm_zum_25_mit_feiertagen_am_sitz_des_bzst():
    assert zm_frist(z("2026-11")).faellig_am == date(2026, 12, 28)  # 25./26.12., So
    assert zm_frist(z("2026-Q3")).faellig_am == date(2026, 10, 26)  # Sonntag
    assert zm_frist(z("2026-08")).faellig_am == date(2026, 9, 25)


def test_oss_frist_wird_nicht_verschoben():
    f = oss_frist(z("2026-Q3"))
    assert f.faellig_am == date(2026, 10, 31)  # ein Samstag
    assert not f.verschoben


def test_fristenkalender():
    k = fristenkalender(2026, bundesland="BY")
    assert [f.art for f in k].count("UStVA") == 12
    assert k == sorted(k, key=lambda f: f.faellig_am)
    mit_allem = fristenkalender(
        2026, dauerfrist=True, zm="quartal", oss=True, bundesland="BY"
    )
    arten = [f.art for f in mit_allem]
    assert arten.count("Sondervorauszahlung") == 1
    assert arten.count("ZM") == 4
    assert arten.count("OSS") == 4
    quartal = fristenkalender(2026, voranmeldungszeitraum="quartal", dauerfrist=True)
    assert [f.zeitraum for f in quartal if f.art == "UStVA"] == [
        "2026-Q1",
        "2026-Q2",
        "2026-Q3",
        "2026-Q4",
    ]
    # Quartalszahler: Dauerfristverlängerung ohne Sondervorauszahlung (§ 48 UStDV),
    # der Antrag gilt fort und ist keine jährliche Frist
    assert {f.art for f in quartal} == {"UStVA"}


def test_faellige_fristen_fuer_erinnerungen():
    k = fristenkalender(2026)
    naechste = faellige_fristen(k, stichtag=date(2026, 9, 1), vorlauf_tage=14)
    assert [(f.zeitraum, f.faellig_am) for f in naechste] == [
        ("2026-08", date(2026, 9, 10))
    ]
