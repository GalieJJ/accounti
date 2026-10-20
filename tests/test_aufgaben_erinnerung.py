"""Erinnerungsstufen und Eskalation gegen feste Stichtage."""

from datetime import date

import pytest

from accounti.aufgaben.einstellungen import AufgabenEinstellungen, Erinnerungsplan
from accounti.aufgaben.erinnerung import faellige_erinnerungen, stufe_am
from accounti.models.aufgaben import Aufgabe, AufgabenStatus

FAELLIG = date(2026, 10, 20)


def _aufgabe(**kw):
    werte = {
        "nr": 1,
        "art": "beleg_fehlt",
        "titel": "Beleg fehlt",
        "objekt_typ": "transaktion",
        "objekt_id": "tx1",
        "faellig_am": FAELLIG,
    }
    werte.update(kw)
    return Aufgabe(**werte)


@pytest.mark.parametrize(
    ("stichtag", "stufe"),
    [
        (date(2026, 10, 19), 0),
        (date(2026, 10, 20), 1),  # am Fälligkeitstag
        (date(2026, 10, 22), 1),
        (date(2026, 10, 23), 2),  # 3 Tage danach: 1. Erinnerung
        (date(2026, 10, 26), 2),
        (date(2026, 10, 27), 3),  # 7 Tage danach: letzte Stufe
        (date(2027, 1, 1), 3),
    ],
)
def test_stufe_gegen_feste_stichtage(stichtag, stufe):
    assert stufe_am(_aufgabe(), Erinnerungsplan(), stichtag) == stufe


def test_ohne_faelligkeit_keine_stufe():
    assert stufe_am(_aufgabe(faellig_am=None), Erinnerungsplan(), FAELLIG) == 0


def test_nur_neue_stufen_werden_gemeldet():
    e = AufgabenEinstellungen()
    gemeldet = _aufgabe(erinnerungsstufe=1)
    assert faellige_erinnerungen([gemeldet], e, date(2026, 10, 22)) == []
    (er,) = faellige_erinnerungen([gemeldet], e, date(2026, 10, 23))
    assert (er.stufe, er.ueberfaellig_tage, er.eskaliert_an) == (2, 3, None)
    assert er.bezeichnung == "1. Erinnerung · 3 Tage überfällig"
    (er,) = faellige_erinnerungen([_aufgabe()], e, FAELLIG)
    assert er.bezeichnung == "fällig heute"


def test_verpasster_lauf_meldet_einmal_die_hoechste_stufe():
    """Fiel der Lauf eine Woche aus, gibt es eine Meldung, nicht drei."""
    (er,) = faellige_erinnerungen(
        [_aufgabe()], AufgabenEinstellungen(), date(2026, 10, 30)
    )
    assert er.stufe == 3 and er.ueberfaellig_tage == 10


def test_erledigte_und_hinfaellige_werden_nicht_erinnert():
    e = AufgabenEinstellungen()
    for status in (AufgabenStatus.ERLEDIGT, AufgabenStatus.HINFAELLIG):
        assert faellige_erinnerungen([_aufgabe(status=status)], e, FAELLIG) == []
    wartet = _aufgabe(status=AufgabenStatus.WARTET)
    assert len(faellige_erinnerungen([wartet], e, FAELLIG)) == 1


def test_eskalation_auf_der_letzten_stufe_je_art():
    e = AufgabenEinstellungen.model_validate(
        {
            "erinnerung": {
                "stufen": [0, 3, 7],
                "eskalation_an": "@leitung",
                "arten": {"beleg_fehlt": {"stufen": [0, 14]}},
            }
        }
    )
    beleg = _aufgabe(erinnerungsstufe=1)
    kontierung = _aufgabe(nr=2, art="kontierung_pruefen", erinnerungsstufe=2)
    stichtag = date(2026, 10, 27)
    (er,) = faellige_erinnerungen([beleg, kontierung], e, stichtag)
    assert er.aufgabe.nr == 2 and er.stufe == 3 and er.eskaliert_an == "@leitung"
    assert er.bezeichnung == "eskaliert an @leitung · 7 Tage überfällig"
    (er,) = faellige_erinnerungen([beleg], e, date(2026, 11, 3))
    assert er.stufe == 2 and er.eskaliert_an == "@leitung"


def test_schon_eskaliert_wird_nicht_wieder_eskaliert():
    e = AufgabenEinstellungen.model_validate({"erinnerung": {"eskalation_an": "chef"}})
    assert (
        faellige_erinnerungen([_aufgabe(erinnerungsstufe=3)], e, date(2027, 1, 1)) == []
    )
