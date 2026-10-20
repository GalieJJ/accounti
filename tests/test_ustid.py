import json
from datetime import date, datetime

import pytest

from accounti.kontakte.ustid import (
    UstIdError,
    baue_anfrage,
    bewerte,
    normalisiere,
    werte_aus,
)
from accounti.models import UstIdPruefart

EIGENE = "DE123456789"
JETZT = datetime(2026, 10, 20, 15, 36, 40)


def _qualifiziert(**kw):
    werte = {
        "firmenname": "Musterhaus GmbH & Co KG",
        "strasse": "Musterstrasse 22",
        "plz": "12345",
        "ort": "musterort",
    }
    werte.update(kw)
    return baue_anfrage(EIGENE, "ATU12345678", **werte)


def _antwort(anfrage=None, http=200, **felder):
    body = {
        "id": "5115f6e9699c329f",
        "anfrageZeitpunkt": "2026-10-20T15:36:40.883983695+02:00",
        **felder,
    }
    return werte_aus(anfrage or _qualifiziert(), http, json.dumps(body), None, JETZT)


ALLES_A = {"ergFirmenname": "A", "ergStrasse": "A", "ergPlz": "A", "ergOrt": "A"}


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        (" atu 123.456-78 ", "ATU12345678"),
        ("GR123456789", "EL123456789"),
        ("el 123456789", "EL123456789"),
        ("XI123456789", "XI123456789"),
    ],
)
def test_schreibweise(roh, erwartet):
    assert normalisiere(roh) == erwartet


def test_qualifizierte_anfrage_hat_die_feldnamen_der_api():
    a = _qualifiziert()
    assert a.art is UstIdPruefart.QUALIFIZIERT
    assert json.loads(a.als_json()) == {
        "anfragendeUstid": "DE123456789",
        "angefragteUstid": "ATU12345678",
        "firmenname": "Musterhaus GmbH & Co KG",
        "strasse": "Musterstrasse 22",
        "plz": "12345",
        "ort": "musterort",
    }


def test_ohne_ort_wird_einfach_angefragt():
    a = baue_anfrage(EIGENE, "ATU12345678", firmenname="Musterhaus", ort=None)
    assert a.art is UstIdPruefart.EINFACH
    assert json.loads(a.als_json()) == {
        "anfragendeUstid": "DE123456789",
        "angefragteUstid": "ATU12345678",
    }


def test_einfach_laesst_firmendaten_weg():
    a = baue_anfrage(EIGENE, "ATU12345678", firmenname="X", ort="Y", einfach=True)
    assert a.art is UstIdPruefart.EINFACH
    assert set(json.loads(a.als_json())) == {"anfragendeUstid", "angefragteUstid"}


@pytest.mark.parametrize(
    ("eigene", "angefragt", "grund"),
    [
        ("ATU12345678", "FR12345678901", "eigene"),
        (None, "ATU12345678", "eigene"),
        (EIGENE, "DE987654321", "inländisch"),
        (EIGENE, "US123456789", "Länderkennzeichen"),
        (EIGENE, "", "fehlt"),
        (EIGENE, None, "fehlt"),
    ],
)
def test_unzulaessige_anfragen_gehen_nicht_raus(eigene, angefragt, grund):
    with pytest.raises(UstIdError, match=grund):
        baue_anfrage(eigene, angefragt)


def test_qualifiziert_bestaetigt():
    p = _antwort(status="evatr-0000", **ALLES_A)
    assert (p.status, p.http_status) == ("evatr-0000", 200)
    assert p.bzst_id == "5115f6e9699c329f"
    assert p.bzst_zeitpunkt == "2026-10-20T15:36:40.883983695+02:00"
    assert (p.erg_firmenname, p.erg_strasse, p.erg_plz, p.erg_ort) == ("A",) * 4
    assert p.ust_id == "ATU12345678" and p.eigene_ust_id == EIGENE
    assert p.zeitpunkt == JETZT
    assert p.aufbewahren_bis == date(2036, 12, 31)
    assert json.loads(p.antwort)["status"] == "evatr-0000"
    b = bewerte(p)
    assert (b.bestaetigt, b.gueltig, b.hinweise) == (True, True, ())
    assert "qualifiziert bestätigt" in b.grund


def test_einfache_bestaetigung_reicht_nicht():
    p = _antwort(baue_anfrage(EIGENE, "ATU12345678"), status="evatr-0000")
    b = bewerte(p)
    assert (b.bestaetigt, b.gueltig) == (False, True)
    assert "einfach" in b.grund


def test_ungueltig_mit_zeitraum():
    p = _antwort(status="evatr-2006", gueltigAb="2019-01-01", gueltigBis="2024-12-31")
    b = bewerte(p)
    assert (b.bestaetigt, b.gueltig) == (False, False)
    assert "nicht gültig" in b.grund
    assert "01.01.2019" in b.grund and "31.12.2024" in b.grund
    assert "evatr-2006" in b.grund


def test_nicht_vergeben_kommt_als_404_mit_json():
    p = _antwort(http=404, status="evatr-2001")
    b = bewerte(p)
    assert (p.http_status, b.gueltig, b.bestaetigt) == (404, False, False)
    assert "nicht vergeben" in b.grund


def test_name_stimmt_nicht():
    p = _antwort(status="evatr-0000", **{**ALLES_A, "ergFirmenname": "B"})
    b = bewerte(p)
    assert (b.bestaetigt, b.gueltig) == (False, True)
    assert "Firmenname" in b.grund


def test_ort_stimmt_nicht():
    p = _antwort(status="evatr-0000", **{**ALLES_A, "ergOrt": "B"})
    b = bewerte(p)
    assert not b.bestaetigt
    assert "Ort" in b.grund


def test_strasse_weicht_ab_ist_nur_ein_hinweis():
    p = _antwort(status="evatr-0000", **{**ALLES_A, "ergStrasse": "B"})
    b = bewerte(p)
    assert b.bestaetigt
    assert any("Straße" in h for h in b.hinweise)


def test_nicht_mitgeteilte_angaben_werden_akzeptiert():
    nicht_mitgeteilt = {**ALLES_A, "ergFirmenname": "D", "ergOrt": "D"}
    p = _antwort(status="evatr-0000", **nicht_mitgeteilt)
    b = bewerte(p)
    assert b.bestaetigt
    assert any("nicht mitgeteilt" in h for h in b.hinweise)


def test_besonderheit_2008_ist_keine_bestaetigung():
    b = bewerte(_antwort(status="evatr-2008"))
    assert (b.bestaetigt, b.gueltig) == (False, True)
    assert "BZSt" in b.grund


def test_stoerung_ist_keine_aussage():
    b = bewerte(_antwort(http=503, status="evatr-1001"))
    assert (b.bestaetigt, b.gueltig) == (False, None)
    assert "zurzeit nicht möglich" in b.grund


def test_keine_verbindung():
    p = werte_aus(_qualifiziert(), None, None, "URLError: timed out", JETZT)
    assert (p.http_status, p.status, p.antwort) == (None, None, None)
    b = bewerte(p)
    assert (b.bestaetigt, b.gueltig) == (False, None)
    assert "timed out" in b.grund


def test_unlesbare_antwort():
    p = werte_aus(_qualifiziert(), 502, "<html>Bad Gateway</html>", None, JETZT)
    assert p.antwort == "<html>Bad Gateway</html>"
    assert "nicht lesbar" in (p.fehler or "")
    assert bewerte(p).gueltig is None


def test_unbekannter_status_wird_roh_genannt():
    b = bewerte(_antwort(http=500, status="evatr-9999"))
    assert b.gueltig is None
    assert "evatr-9999" in b.grund
