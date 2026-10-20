"""Mehrere Gesellschaften im Browser und in der API (Spec 4.4, Akzeptanz 5)."""

import pytest

from accounti.api.app import erstelle_app
from accounti.models.auth import Rolle, TokenRecht
from tests.api_hilfe import csrf, webwelt
from tests.auth_hilfe import billige_hashes


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER, gesellschaft="a")
    w.rolle("jan", "b", Rolle.BUCHHALTER)
    w.person("ole", Rolle.FREIGEBER, gesellschaft="a")  # nur Gesellschaft A
    return w


def seiten_ohne_parameter(app):
    return [
        e.pfad
        for e in app.state.endpunkte
        if e.methode == "GET"
        and "{" not in e.pfad
        and not e.pfad.startswith("/api/")
        and e.pfad != "/anmelden"
    ]


def test_akzeptanz_5_wechsel_aendert_alle_ansichten(welt):
    client = welt.angemeldet("jan")
    start = client.get("/")
    assert "Alpha Papier GmbH" in start.text and "111,00" in start.text
    assert "Beta Rahmen KG" in start.text  # nur als Auswahl im Wechsler
    r = client.post(
        "/gesellschaft",
        data={"csrf": csrf(client), "kuerzel": "b"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    pfade = seiten_ohne_parameter(erstelle_app(welt.dienste))
    assert {"/", "/freigaben"} <= set(pfade)
    for pfad in pfade:
        seite = client.get(pfad)
        assert seite.status_code == 200, pfad
        assert "Gesellschaft: <strong>Beta Rahmen KG</strong>" in seite.text, pfad
    start = client.get("/")
    assert "777,00" in start.text and "111,00" not in start.text


def test_benutzer_von_a_sieht_b_nicht(welt):
    client = welt.angemeldet("ole")
    start = client.get("/")
    assert "Beta Rahmen KG" not in start.text  # kein Wechsler, keine Daten
    r = client.post("/gesellschaft", data={"csrf": csrf(client), "kuerzel": "b"})
    assert r.status_code == 403
    start = client.get("/")
    assert "Alpha Papier GmbH" in start.text and "777,00" not in start.text


def test_rolle_entzogen_wirkt_sofort(welt):
    from accounti.auth.dienst import entferne_rolle

    client = welt.angemeldet("jan")
    client.post("/gesellschaft", data={"csrf": csrf(client), "kuerzel": "b"})
    with welt.system() as s:
        entferne_rolle(
            s, welt.personen["jan"].benutzer, "b", Rolle.BUCHHALTER, welt.uhr(), "t"
        )
        s.commit()
    # Rollenänderung beendet die Sitzung — neu anmelden landet in A
    assert client.get("/", follow_redirects=False).status_code == 303
    client = welt.angemeldet("jan")
    assert "Beta Rahmen KG" not in client.get("/").text


def test_token_sieht_nur_seine_gesellschaft(welt):
    client = welt.client()
    a = welt.token("a", TokenRecht.OPOS_LESEN, name="erp-a")
    b = welt.token("b", TokenRecht.OPOS_LESEN, name="erp-b")
    posten_a = client.get(
        "/api/v1/offene-posten", headers={"Authorization": f"Bearer {a}"}
    ).json()
    posten_b = client.get(
        "/api/v1/offene-posten", headers={"Authorization": f"Bearer {b}"}
    ).json()
    assert [p["belegnummer"] for p in posten_a["offene_posten"]] == ["A-RE-1"]
    assert [p["belegnummer"] for p in posten_b["offene_posten"]] == ["B-RE-7"]


def test_eigene_konfiguration_je_gesellschaft(welt):
    from accounti.konfiguration import lade_buchhaltung

    g = welt.dienste.gesellschaften
    assert lade_buchhaltung(g["a"].konfiguration).kontenrahmen == "SKR03"
    assert lade_buchhaltung(g["b"].konfiguration).kontenrahmen == "SKR04"
    assert g["a"].archiv != g["b"].archiv and g["a"].datenbank != g["b"].datenbank
