from datetime import date
from decimal import Decimal

import pytest

from accounti.konfiguration import KonfigurationError
from accounti.mahnwesen.basiszins import basiszins_am
from accounti.mahnwesen.konfiguration import lade_mahnwesen


def test_standards_wie_im_spec_beispiel(tmp_path):
    e = lade_mahnwesen(tmp_path / "fehlt.yaml")
    assert [(s.name, s.ab_tagen, s.gebuehr, s.verzugszinsen) for s in e.stufen] == [
        ("Zahlungserinnerung", 5, Decimal("0.00"), False),
        ("1. Mahnung", 14, Decimal("5.00"), True),
        ("2. Mahnung", 28, Decimal("10.00"), True),
    ]
    assert e.mindestbetrag == Decimal("10.00") and e.karenztage == 3
    assert e.stufenabstand_tage == 7 and e.zahlungsfrist_tage == 10
    assert e.verzug_nach_tagen == 0 and e.unbekannt_als == "verbraucher"
    assert e.pauschale_b2b == Decimal("40.00") and e.pauschale_anrechnen is True
    assert basiszins_am(date(2026, 7, 1), e.basiszinstabelle()).satz == Decimal("1.52")


def test_eigene_stufen_und_basiszinssaetze(tmp_path):
    pfad = tmp_path / "a.yaml"
    pfad.write_text(
        "mahnwesen:\n"
        "  karenztage: 0\n"
        "  stufen:\n"
        "    - {name: Erinnerung, ab_tagen: 7, gebuehr: 0, verzugszinsen: false}\n"
        "    - name: Letzte Mahnung\n"
        "      ab_tagen: 21\n"
        "      gebuehr: 2.50\n"
        "      verzugszinsen: true\n"
        "      text: 'Rechnung {nummer}: bitte {summe} € bis {frist}.'\n"
        "  basiszinssaetze:\n"
        "    - {ab: 2027-01-01, satz: 1.77}\n",
        encoding="utf-8",
    )
    e = lade_mahnwesen(pfad)
    assert [s.name for s in e.stufen] == ["Erinnerung", "Letzte Mahnung"]
    assert e.stufen[1].text.startswith("Rechnung {nummer}")
    assert basiszins_am(date(2027, 5, 1), e.basiszinstabelle()).satz == Decimal("1.77")


@pytest.mark.parametrize(
    ("abschnitt", "meldung"),
    [
        ("stufen: []", "mindestens eine Stufe"),
        (
            "stufen: [{name: A, ab_tagen: 14}, {name: B, ab_tagen: 7}]",
            "ab_tagen muss von Stufe zu Stufe steigen",
        ),
        ("stufen: [{name: A, ab_tagen: 5, text: 'Hallo {kunde_xy}'}]", "kunde_xy"),
        ("basiszinssaetze: [{ab: 2027-02-01, satz: 1}]", "1. Januar und 1. Juli"),
        ("unbekannt_als: jemand", "unbekannt_als"),
    ],
)
def test_fehler_mit_klarer_meldung(tmp_path, abschnitt, meldung):
    pfad = tmp_path / "a.yaml"
    pfad.write_text(f"mahnwesen:\n  {abschnitt}\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match=meldung):
        lade_mahnwesen(pfad)
