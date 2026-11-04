"""Welt der Browserprobe (Plan P1, Schritt 5): jede GET-Route steht in ``probe.json``
mit Beispielwerten und liefert je Benutzer den erwarteten Status."""

from __future__ import annotations

import json

import pytest

from accounti.api.app import erstelle_app
from accounti.auth.totp import code, geheimnis_aus_base32
from tests.auth_hilfe import billige_hashes
from tests.browserprobe_welt import BENUTZER, baue
from tests.test_api_rechte_matrix import SEITEN


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture(scope="module")
def welt(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    billige_hashes(mp)
    try:
        yield baue(tmp_path_factory.mktemp("probe") / "welt")
    finally:
        mp.undo()


def test_welt_listet_jede_get_route(welt):
    app = erstelle_app(welt.web.dienste)
    get_routen = {
        e.pfad
        for e in app.state.endpunkte
        if e.methode == "GET" and not e.pfad.startswith("/api/") and e.pfad != "/gesund"
    }
    assert {s["vorlage"] for s in welt.seiten} == get_routen
    assert get_routen <= {pfad for methode, pfad in SEITEN if methode == "GET"}
    for eintrag in welt.seiten:
        assert "{" not in eintrag["pfad"], eintrag
        assert set(eintrag["erwartet"]) == set(BENUTZER)
    for name in BENUTZER:
        client = welt.web.angemeldet(name)
        for eintrag in welt.seiten:
            kopf = {"HX-Request": "true"} if eintrag["art"] == "fragment" else {}
            r = client.get(eintrag["pfad"], headers=kopf, follow_redirects=False)
            assert r.status_code == eintrag["erwartet"][name], (name, eintrag)


def test_probe_json_mit_geheimnissen_je_benutzer(welt):
    daten = json.loads(json.dumps(welt.probe("http://127.0.0.1:8473")))
    assert daten["basis"] == "http://127.0.0.1:8473"
    assert set(daten["benutzer"]) == set(BENUTZER)
    for name, eintrag in daten["benutzer"].items():
        person = welt.web.personen[name]
        geheimnis = geheimnis_aus_base32(eintrag["geheimnis"])
        assert geheimnis == person.geheimnis
        assert code(geheimnis, 1_800_000_000) == code(person.geheimnis, 1_800_000_000)
        assert eintrag["codes"] and eintrag["passwort"]
        assert eintrag["rollen"] == [r.value for r in BENUTZER[name]]


def test_ziel_muss_neu_oder_leer_sein(tmp_path):
    (tmp_path / "alt.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="nicht leer"):
        baue(tmp_path)
