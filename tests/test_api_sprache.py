"""Oberfläche auf Deutsch und Englisch (Spec 4.5; Baustein 10b, Paket 2)."""

from __future__ import annotations

import pytest

from accounti import i18n
from accounti.models.auth import Rolle
from tests.api_hilfe import csrf, webwelt
from tests.auth_hilfe import billige_hashes

EN = {"Accept-Language": "en-GB,en;q=0.9"}
DE = {"Accept-Language": "de-DE,de;q=0.9"}


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER)
    w.person("leo", Rolle.BETRACHTER)
    return w


def test_html_lang_und_navigation_englisch(welt):
    client = welt.angemeldet("jan")
    seite = client.get("/", headers=EN).text
    assert '<html lang="en" ' in seite
    assert "Company: <strong>Alpha Papier GmbH</strong>" in seite
    # umgestellt (Plan P1, B9): jan ist buchhalter — Freigaben sieht nur, wer freigeben
    # darf; „Navigation englisch“ prüft Übersicht und Prüfen bzw. Freigaben für fritz
    assert ">Overview<" in seite and ">Review<" in seite and "Sign out" in seite
    assert ">Approvals<" not in seite
    welt.person("fritz", Rolle.FREIGEBER)
    assert ">Approvals<" in welt.angemeldet("fritz").get("/", headers=EN).text
    seite = client.get("/", headers=DE).text
    assert '<html lang="de" ' in seite
    assert "Gesellschaft: <strong>Alpha Papier GmbH</strong>" in seite


def test_anmeldeseite_nach_accept_language(welt):
    client = welt.client()
    assert "<h1>Sign in</h1>" in client.get("/anmelden", headers=EN).text
    assert "<h1>Anmelden</h1>" in client.get("/anmelden", headers=DE).text
    assert "<h1>Anmelden</h1>" in client.get("/anmelden").text  # Standard: de


def test_fehlerseite_uebersetzt(welt):
    client = welt.angemeldet("leo")
    daten = {"csrf": csrf(client), "zeitraum": "2026-09"}
    r = client.post("/freigaben/ustva", data=daten, headers=EN)
    assert r.status_code == 403
    assert "Your role in Alpha Papier GmbH does not allow this" in r.text
    r = client.post("/freigaben/ustva", data=daten, headers=DE)
    assert "Ihre Rolle in Alpha Papier GmbH erlaubt das nicht" in r.text


def test_vary_accept_language(welt):
    assert welt.client().get("/anmelden").headers["vary"] == "Accept-Language"
    client = welt.angemeldet("jan")
    assert "Accept-Language" in client.get("/").headers["vary"]


def test_sprache_leckt_nicht_in_die_naechste_anfrage(welt):
    client = welt.angemeldet("jan")
    assert '<html lang="en" ' in client.get("/", headers=EN).text
    assert i18n.aktive_sprache.get() == "de"
    assert '<html lang="de" ' in client.get("/", headers=DE).text
    assert '<html lang="de" ' in client.get("/").text


def _waehle(client, sprache: str, mit_csrf: bool = True):  # noqa: ANN001, ANN202
    daten = {"sprache": sprache, "weiter": "/freigaben"}
    if mit_csrf:
        daten["csrf"] = csrf(client)
    return client.post("/einstellungen/sprache", data=daten, follow_redirects=False)


def test_sprache_wechseln_braucht_csrf(welt):
    client = welt.angemeldet("jan")
    r = _waehle(client, "en", mit_csrf=False)
    assert r.status_code == 403
    assert '<html lang="de" ' in client.get("/", headers=DE).text
    r = _waehle(client, "en")
    assert r.status_code == 303 and r.headers["location"] == "/freigaben"
    assert '<html lang="en" ' in client.get("/", headers=DE).text
    assert _waehle(client, "fr").status_code == 422


def test_sprache_bleibt_nach_neuer_anmeldung(welt):
    client = welt.angemeldet("jan")
    _waehle(client, "en")
    client.post("/abmelden", data={"csrf": csrf(client)})
    neu = welt.angemeldet("jan")
    seite = neu.get("/", headers=DE).text
    assert '<html lang="en" ' in seite
    assert '<option value="en" lang="en" selected>' in seite


def test_automatisch_folgt_wieder_dem_browser(welt):
    client = welt.angemeldet("jan")
    _waehle(client, "en")
    _waehle(client, "")
    assert '<html lang="de" ' in client.get("/", headers=DE).text
    assert '<html lang="en" ' in client.get("/", headers=EN).text


def test_jede_seite_in_beiden_sprachen(welt):
    from accounti.api.app import erstelle_app

    pfade = sorted(
        {
            e.pfad
            for e in erstelle_app(welt.dienste).state.endpunkte
            if e.methode == "GET"
            and "{" not in e.pfad
            and not e.pfad.startswith(("/api", "/anmelden"))
        }
    )
    client = welt.angemeldet("jan")
    for pfad in pfade:
        for kopf, lang, firma in (
            (DE, "de", "Gesellschaft: <strong>Alpha Papier GmbH</strong>"),
            (EN, "en", "Company: <strong>Alpha Papier GmbH</strong>"),
        ):
            r = client.get(pfad, headers=kopf)
            assert r.status_code == 200, (pfad, lang)
            assert f'<html lang="{lang}" ' in r.text and firma in r.text, (pfad, lang)
