import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.erechnung import lies
from accounti.erechnung.validierung import Schwere, pruefe

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "erechnung"


def _lies(name):
    return lies((FIXTURES / name).read_bytes())


def _regeln(befunde, schwere=Schwere.FEHLER):
    return {b.regel for b in befunde if b.schwere is schwere}


@pytest.mark.parametrize(
    "datei", ["xrechnung_cii.xml", "xrechnung_ubl.xml", "mit_nachlass_cii.xml"]
)
def test_gueltige_rechnungen_ohne_befund(datei):
    assert pruefe(_lies(datei)) == []


def test_falsche_rechenprobe_wird_erkannt():
    """Akzeptanz 3."""
    befunde = pruefe(_lies("fehler_rechenprobe_cii.xml"))
    assert "BR-S-09" in _regeln(befunde)
    (b,) = [b for b in befunde if b.regel == "BR-S-09"]
    assert "19" in b.text and "20.00" in b.text and "19.00" in b.text


def test_reverse_charge_ohne_kaeufer_ust_id():
    befunde = pruefe(_lies("reverse_charge_ohne_ust_id_ubl.xml"))
    assert _regeln(befunde) == {"BR-AE-02"}
    # kein XRechnung-Profil → keine Leitweg-ID-Pflicht
    assert "BR-DE-15" not in _regeln(befunde)


def test_minimum_profil_warnt_nur():
    befunde = pruefe(_lies("minimum_cii.xml"))
    assert _regeln(befunde) == set()
    assert "PROFIL" in _regeln(befunde, Schwere.WARNUNG)


def test_xrechnung_ohne_leitweg_id():
    r = dataclasses.replace(_lies("xrechnung_cii.xml"), kaeufer_referenz=None)
    assert "BR-DE-15" in _regeln(pruefe(r))


@pytest.mark.parametrize(
    ("feld", "regel"),
    [
        ("nummer", "BR-02"),
        ("datum", "BR-03"),
        ("typ", "BR-04"),
        ("waehrung", "BR-05"),
        ("zeilen", "BR-16"),
    ],
)
def test_pflichtangaben(feld, regel):
    r = _lies("xrechnung_cii.xml")
    leer = [] if feld == "zeilen" else None
    assert regel in _regeln(pruefe(dataclasses.replace(r, **{feld: leer})))


def test_verkaeufer_ohne_name_und_steuerkennung():
    r = _lies("xrechnung_cii.xml")
    r.verkaeufer.name = None
    r.verkaeufer.ust_id = None
    regeln = _regeln(pruefe(r))
    assert {"BR-06", "UStG-14-2"} <= regeln


def test_positionssumme_muss_stimmen():
    r = _lies("xrechnung_cii.xml")
    r.zeilen[0].netto = Decimal("86.00")
    regeln = _regeln(pruefe(r))
    assert "BR-CO-10" in regeln
    assert "BR-S-08" in regeln


def test_brutto_muss_netto_plus_steuer_sein():
    r = _lies("xrechnung_cii.xml")
    r.summen.brutto = Decimal("172.00")
    assert {"BR-CO-15", "BR-CO-16"} <= _regeln(pruefe(r))


def test_unplausibler_steuersatz_fuer_das_land():
    r = _lies("xrechnung_cii.xml")
    for z in r.zeilen[:2]:
        z.steuersatz = Decimal("16")
    r.steuern[0].satz = Decimal("16")
    r.steuern[0].betrag = Decimal("16.00")
    r.summen.steuer = Decimal("19.50")
    r.summen.brutto = r.summen.zahlbetrag = Decimal("169.50")
    befunde = pruefe(r)
    assert _regeln(befunde) == set()
    assert "SATZ-LAND" in _regeln(befunde, Schwere.WARNUNG)


def test_fehlender_leistungszeitpunkt_ist_warnung():
    r = dataclasses.replace(_lies("xrechnung_cii.xml"), leistungsdatum=None)
    assert "UStG-14-6" in _regeln(pruefe(r), Schwere.WARNUNG)


def test_rundungsdifferenz_unter_einem_euro_ist_nur_warnung():
    r = _lies("xrechnung_cii.xml")
    r.steuern[0].betrag = Decimal("19.01")
    r.summen.steuer = Decimal("22.51")
    r.summen.brutto = r.summen.zahlbetrag = Decimal("172.51")
    befunde = pruefe(r)
    assert _regeln(befunde) == set()
    assert "BR-S-09" in _regeln(befunde, Schwere.WARNUNG)


def test_befreiungsgrund_als_code_genuegt():
    r = _lies("reverse_charge_ohne_ust_id_ubl.xml")
    r.steuern[0].befreiungsgrund = None
    r.kaeufer.ust_id = "DE999999999"
    assert _regeln(pruefe(r)) == set()


def test_nicht_steuerbar_ohne_satz():
    r = _lies("reverse_charge_ohne_ust_id_ubl.xml")
    r.kaeufer.ust_id = "DE999999999"
    for z in r.zeilen:
        z.steuerkategorie, z.steuersatz = "O", None
    r.steuern[0].kategorie, r.steuern[0].satz = "O", None
    assert _regeln(pruefe(r)) == set()


def test_extension_zahlbetrag_mit_drittzahlungen_ist_nur_warnung():
    r = _lies("xrechnung_cii.xml")
    r.spezifikation += "#conformant#urn:xeinkauf.de:kosit:extension:xrechnung_3.0"
    r.summen.zahlbetrag = Decimal("200.00")
    befunde = pruefe(r)
    assert "BR-CO-16" not in _regeln(befunde)
    assert "BR-CO-16" in _regeln(befunde, Schwere.WARNUNG)


def test_lieferanschrift_braucht_ort_und_plz():
    from accounti.erechnung.modell import Anschrift

    r = dataclasses.replace(
        _lies("xrechnung_cii.xml"), lieferanschrift=Anschrift(land="DE")
    )
    assert {"BR-DE-10", "BR-DE-11"} <= _regeln(pruefe(r))
