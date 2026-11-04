"""Mein Konto: Anzeige-Vorlieben (Spec 10c A6, A87, AK45; Plan P1, Schritt 9)."""

from __future__ import annotations

import re

import pytest

from accounti.models.auth import Rolle
from tests.api_hilfe import csrf, webwelt
from tests.auth_hilfe import billige_hashes

HX = {"HX-Request": "true"}
DE = {"Accept-Language": "de"}


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    for rolle in Rolle:
        w.person(rolle.value, rolle)
    return w


def _speichern(client, **felder):  # noqa: ANN001, ANN003, ANN202
    kopf = felder.pop("kopf", None)
    daten = {"csrf": csrf(client), **felder}
    return client.post(
        "/konto/vorlieben", data=daten, headers=kopf or {}, follow_redirects=False
    )


def _gewaehlt(html: str, name: str) -> str:
    m = re.search(
        rf'name="{name}" value="([^"]*)" checked', html[html.index("<main") :]
    )
    assert m, name
    return m.group(1)


def test_konto_fuer_jede_rolle(welt):
    for rolle in Rolle:
        r = welt.angemeldet(rolle.value).get("/konto")
        assert r.status_code == 200, rolle
        inhalt = r.text[r.text.index("<main") :]
        assert '<form method="post" action="/konto/vorlieben"' in inhalt
        for name, wert in (
            ("sprache", "auto"),
            ("darstellung", "auto"),
            ("fachansicht", "aus"),
            ("betraege_verbergen", "aus"),
            ("tastenkuerzel", "an"),
        ):
            assert _gewaehlt(r.text, name) == wert, (rolle, name)
        assert inhalt.count("<fieldset") >= 5 and 'type="checkbox"' not in inhalt
        assert "Speichern" in inhalt


def test_vorlieben_ohne_js_303_und_wirkung(welt):
    client = welt.angemeldet("buchhalter")
    r = _speichern(client, darstellung="dunkel", weiter="/pruefen")
    assert r.status_code == 303 and r.headers["location"] == "/pruefen"
    seite = client.get("/pruefen").text
    assert '<html lang="de" data-theme="dunkel">' in seite
    assert '<meta name="color-scheme" content="dark">' in seite
    neu = welt.angemeldet("buchhalter")  # neue Anmeldung, anderes „Gerät“
    assert 'data-theme="dunkel"' in neu.get("/").text
    assert _gewaehlt(neu.get("/konto").text, "darstellung") == "dunkel"


def test_teilformular_aendert_nur_gesendete_felder(welt):
    client = welt.angemeldet("buchhalter")
    _speichern(client, darstellung="hell", sprache="en", fachansicht="an")
    r = _speichern(client, tastenkuerzel="aus")
    assert r.status_code == 303
    html = client.get("/konto", headers=DE).text
    assert _gewaehlt(html, "darstellung") == "hell"
    assert _gewaehlt(html, "sprache") == "en"
    assert _gewaehlt(html, "fachansicht") == "an"
    assert _gewaehlt(html, "tastenkuerzel") == "aus"
    assert _gewaehlt(html, "betraege_verbergen") == "aus"


def test_ungueltige_wahl_422_mit_fehlerliste(welt):
    client = welt.angemeldet("buchhalter")
    r = _speichern(client, darstellung="lila", fachansicht="vielleicht", sprache="en")
    assert r.status_code == 422
    inhalt = r.text[r.text.index("<main") :]
    liste = re.search(
        r'<div class="hinweis hinweis-fehler fehlerliste" role="alert".*?</ul>',
        inhalt,
        re.S,
    )
    assert liste
    ziele = re.findall(r'<a href="#([^"]+)"', liste.group(0))
    assert ziele == ["darstellung-auto", "fachansicht-an"]
    for ziel in ziele:
        assert f'id="{ziel}"' in inhalt
    assert 'aria-describedby="darstellung-fehler"' in inhalt
    assert _gewaehlt(r.text, "sprache") == "en"  # gültige Eingaben bleiben
    assert "lila" not in inhalt  # nichts gespiegelt
    assert (
        _gewaehlt(client.get("/konto").text, "darstellung") == "auto"
    )  # nichts gespeichert


def test_mit_htmx_hx_refresh(welt):
    client = welt.angemeldet("buchhalter")
    r = _speichern(client, darstellung="dunkel", kopf=HX)
    assert r.status_code == 200 and r.headers["hx-refresh"] == "true" and r.text == ""
    assert 'data-theme="dunkel"' in client.get("/").text


def test_weiter_nur_relativ(welt):
    client = welt.angemeldet("buchhalter")
    for weiter in ("https://evil.example/x", "//evil.example/x", "\\\\evil"):
        r = _speichern(client, darstellung="hell", weiter=weiter)
        assert r.headers["location"] == "/", weiter
    assert _speichern(client, darstellung="hell").headers["location"] == "/konto"


def test_alter_sprachpfad_308_und_wirkt(welt):
    client = welt.angemeldet("buchhalter")
    daten = {"csrf": csrf(client), "sprache": "en", "weiter": "/freigaben"}
    r = client.post("/einstellungen/sprache", data=daten, follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/konto/vorlieben"
    r = client.post("/einstellungen/sprache", data=daten)  # Browser folgt mit Körper
    assert r.status_code == 200 and r.url.path == "/freigaben"
    assert '<html lang="en" ' in client.get("/", headers=DE).text
    daten["sprache"] = ""  # „automatisch“ wie im alten Formular
    client.post("/einstellungen/sprache", data=daten)
    assert '<html lang="de" ' in client.get("/", headers=DE).text


def test_tastenkuerzel_als_data_attribut(welt):
    client = welt.angemeldet("buchhalter")
    assert re.search(r'<body [^>]*data-tastenkuerzel="an"', client.get("/").text)
    _speichern(client, tastenkuerzel="aus")
    assert re.search(r'<body [^>]*data-tastenkuerzel="aus"', client.get("/").text)


def test_konto_fragment_mit_hx_request(welt):
    client = welt.angemeldet("betrachter")
    teil = client.get("/konto", headers=HX)
    assert teil.status_code == 200 and "<html" not in teil.text
    assert 'action="/konto/vorlieben"' in teil.text and "<h1>" in teil.text
    assert "<html" in client.get("/konto").text


def test_vorlieben_ohne_ereignis(welt):
    from tests.api_hilfe import zaehle

    client = welt.angemeldet("buchhalter")
    vorher = zaehle(welt.umgebung.system, "SELECT count(*) FROM auth_ereignisse")
    _speichern(client, darstellung="dunkel", sprache="en", tastenkuerzel="aus")
    nachher = zaehle(welt.umgebung.system, "SELECT count(*) FROM auth_ereignisse")
    assert nachher == vorher
