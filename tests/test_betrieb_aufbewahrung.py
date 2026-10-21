"""Aufbewahrungsfristen (§ 147 AO, § 14b UStG, BEG IV) und Bericht ohne Löschen."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from accounti.betrieb.aufbewahrung import (
    Unterlage,
    aussonderbar_ab,
    bericht,
    frist,
    frist_ende,
)
from accounti.db import init_db, session_factory
from accounti.db.repository import speichere_beleg, speichere_buchung
from accounti.models import Beleg, Buchungssatz


@pytest.mark.parametrize(
    ("unterlage", "jahre"),
    [
        (Unterlage.BUCH, 10),
        (Unterlage.JAHRESABSCHLUSS, 10),
        (Unterlage.BUCHUNGSBELEG, 8),  # seit BEG IV
        (Unterlage.RECHNUNG, 8),  # § 14b UStG
        (Unterlage.HANDELSBRIEF, 6),
        (Unterlage.SONSTIGE, 6),
    ],
)
def test_fristen(unterlage, jahre):
    assert frist(unterlage).jahre == jahre


def test_frist_beginnt_mit_dem_jahresende():
    # Beleg vom 2.1.2018 und vom 30.12.2018: gleiche Frist bis 31.12.2026
    assert frist_ende(Unterlage.BUCHUNGSBELEG, date(2018, 1, 2)) == date(2026, 12, 31)
    assert frist_ende(Unterlage.BUCHUNGSBELEG, date(2018, 12, 30)) == date(2026, 12, 31)
    assert aussonderbar_ab(Unterlage.BUCHUNGSBELEG, date(2018, 6, 1)) == date(
        2027, 1, 1
    )
    assert frist_ende(Unterlage.BUCH, date(2018, 6, 1)) == date(2028, 12, 31)


def test_institute_behalten_zehn_jahre():
    assert frist(Unterlage.BUCHUNGSBELEG, institut=True).jahre == 10
    assert "19a" in frist(Unterlage.BUCHUNGSBELEG, institut=True).grundlage
    assert frist_ende(Unterlage.BUCHUNGSBELEG, date(2018, 6, 1), True) == date(
        2028, 12, 31
    )


def test_bericht_zeigt_nur_was_abgelaufen_ist(tmp_path):
    engine, fabrik = session_factory(f"sqlite:///{tmp_path / 'a.db'}")
    init_db(engine)
    with fabrik() as s:
        for jahr in (2015, 2016, 2018, 2025):
            speichere_buchung(
                s,
                Buchungssatz(
                    datum=date(jahr, 6, 1),
                    soll_konto="4930",
                    haben_konto="1200",
                    betrag_netto=Decimal("1.00"),
                    buchungstext="x",
                ),
            )
            speichere_beleg(
                s,
                Beleg(
                    datei_hash=f"{jahr:064d}",
                    dateiname=f"{jahr}.pdf",
                    kanal="ordner",
                    herkunft="t",
                    eingegangen_am=datetime(jahr, 6, 1),
                    aufbewahren_bis=date(jahr + 10, 12, 31),
                ),
            )
        s.commit()
        zeilen = {z.bezeichnung: z for z in bericht(s, date(2026, 10, 20))}
        institut = {z.bezeichnung: z for z in bericht(s, date(2026, 10, 20), True)}
    engine.dispose()
    # Buchungen 10 Jahre: 2015 ist am 1.1.2026 frei, 2016 erst 2027
    assert zeilen["Buchungen"].aussonderbar == 1
    assert zeilen["Buchungen"].gesamt == 4
    assert zeilen["Buchungen"].aeltester == date(2015, 6, 1)
    # Belege 8 Jahre: 2015, 2016 und 2018 (bis 31.12.2026? nein: 2018 + 8 = 2026)
    assert zeilen["Belege"].aussonderbar == 2  # 2015 und 2016
    assert institut["Belege"].aussonderbar == 1  # Institute: 10 Jahre
    # nichts wurde gelöscht
    assert zeilen["Belege"].gesamt == 4
