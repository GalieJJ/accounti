"""Bindung im Web ohne Datenbank-Aufbau (Baustein 10c P4a, Prüfung sicher-3).

``angemeldet`` bindet jede Anfrage an die aktive Gesellschaft (D4). Die Bindung legt
dabei keine Engine samt ``init_db`` an und hält keine globale Sperre über einen
Verbindungsaufbau; ist die Datenbank nicht lesbar, merkt sich der Schnappschuss den
Fehler. So bleiben ``/gesellschaft``, der Wechsel, ``/konto`` und das Abmelden auch
dann erreichbar (P1, B14), und nur eine Seite, die einen Datenbank-Abschnitt liest,
scheitert — fail-closed, nie still die Datei.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event

from accounti.api.app import erstelle_app
from accounti.api.sitzung import AngemeldetDep
from accounti.konfiguration import lade_buchhaltung
from accounti.models.auth import Rolle
from tests.api_hilfe import BASIS, Webwelt, csrf, webwelt
from tests.auth_hilfe import billige_hashes


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("eva", Rolle.BUCHHALTER, gesellschaft="a")
    w.rolle("eva", "b", Rolle.BUCHHALTER)
    return w


def _datenbank_von_a(w: Webwelt, url: str) -> None:
    """Die Datenbank von a liegt jetzt unter ``url`` — wie nach einem Neustart (keine
    Engine im Prozess)."""
    g = w.dienste.gesellschaften["a"]
    w.dienste.gesellschaften["a"] = dataclasses.replace(g, datenbank=url)
    w.dienste._engines.pop(g.datenbank, None)


def _client(w: Webwelt) -> TestClient:
    """Mit einer Probe-Route, die einen Datenbank-Abschnitt liest."""

    def buchhaltung(a: AngemeldetDep) -> dict[str, str]:
        rahmen = lade_buchhaltung(a.gesellschaft.konfiguration).kontenrahmen
        return {"gesellschaft": a.gesellschaft.kuerzel, "rahmen": rahmen}

    app = erstelle_app(w.dienste)
    app.get("/test/buchhaltung")(buchhaltung)
    client = TestClient(app, base_url=BASIS)
    antwort = w.anmelden(client, "eva")
    assert antwort.status_code == 303, antwort.text
    return client


def test_nicht_erreichbare_aktive_gesellschaft_wechseln_und_abmelden(welt, tmp_path):
    """Probe sicher-3: das Verzeichnis der SQLite-Datei fehlt — vorher 500 auf
    ``/gesellschaft``, ``/konto``, ``POST /gesellschaft`` und ``POST /abmelden``."""
    client = _client(welt)
    weg = f"sqlite:///{(tmp_path / 'gibt' / 'es' / 'nicht' / 'a.db').as_posix()}"
    _datenbank_von_a(welt, weg)
    r = client.get("/gesellschaft")
    assert r.status_code == 200, r.text
    assert "nicht erreichbar" in r.text
    assert client.get("/konto").status_code == 200
    token = csrf(client, "/gesellschaft")
    r = client.post(
        "/gesellschaft",
        data={"csrf": token, "kuerzel": "b"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    b = {"gesellschaft": "b", "rahmen": "SKR04"}
    assert client.get("/test/buchhaltung").json() == b
    r = client.post("/abmelden", data={"csrf": token}, follow_redirects=False)
    assert r.status_code == 303, r.text
    assert not (tmp_path / "gibt").exists()  # keine Datei, kein Verzeichnis angelegt
    assert weg not in welt.dienste._engines


def test_unlesbare_datenbank_fail_closed_nur_beim_lesen(welt, tmp_path, caplog):
    """Keine Datenbank, sondern Unsinn: ``/gesellschaft`` und ``/konto`` gehen, die
    Seite mit einem Datenbank-Abschnitt scheitert (500), statt still die Datei zu
    nehmen."""
    client = _client(welt)
    kaputt = tmp_path / "kaputt.db"
    kaputt.write_bytes(b"keine Datenbank " * 512)
    _datenbank_von_a(welt, f"sqlite:///{kaputt.as_posix()}")
    assert client.get("/gesellschaft").status_code == 200
    assert client.get("/konto").status_code == 200
    with caplog.at_level(logging.ERROR, logger="accounti"):
        r = client.get("/test/buchhaltung")
    assert r.status_code == 500
    assert "EinstellungenNichtLesbar" in caplog.text
    assert "Sitzung nicht lesbar" not in caplog.text


def test_binden_ohne_init_db_und_ohne_globale_sperre(welt):
    """Die Bindung legt keine Engine der Gesellschaft an (``Dienste._fabrik`` mit
    ``init_db``) und verbindet nie unter ``Dienste._sperre``."""
    client = _client(welt)
    url = welt.dienste.gesellschaften["a"].datenbank
    welt.dienste._engines.pop(url, None)
    unter_sperre: list[bool] = []

    def verbunden(*_: object) -> None:
        unter_sperre.append(welt.dienste._sperre.locked())

    event.listen(Engine, "connect", verbunden)
    try:
        assert client.get("/gesellschaft").status_code == 200
        a = {"gesellschaft": "a", "rahmen": "SKR03"}
        assert client.get("/test/buchhaltung").json() == a
    finally:
        event.remove(Engine, "connect", verbunden)
    assert url not in welt.dienste._engines
    assert unter_sperre and not any(unter_sperre)


def test_seite_ohne_einstellungen_oeffnet_die_datenbank_nicht(welt):
    """Die Bindung öffnet die Datenbank der Gesellschaft nicht — eine Seite ohne
    Datenbank-Abschnitt (``/konto``) verbindet sich nie mit ihr, auch nicht hinter
    einer Sperre; erst das Lesen eines Abschnitts nimmt den Schnappschuss, einmal je
    Anfrage."""
    client = _client(welt)
    url = welt.dienste.gesellschaften["a"].datenbank
    verbindungen: list[str] = []

    def verbunden(verbindung: object) -> None:
        adresse = verbindung.engine.url  # type: ignore[attr-defined]
        verbindungen.append(adresse.render_as_string(hide_password=False))

    event.listen(Engine, "engine_connect", verbunden)
    try:
        assert client.get("/konto").status_code == 200
        assert url not in verbindungen
        a = {"gesellschaft": "a", "rahmen": "SKR03"}
        assert client.get("/test/buchhaltung").json() == a
    finally:
        event.remove(Engine, "engine_connect", verbunden)
    assert verbindungen.count(url) == 1


def test_fehlende_sqlite_datei_wird_nicht_angelegt(welt, tmp_path):
    """Eine fehlende Datei der aktiven Gesellschaft ist leer (keine Versionen) — die
    Bindung legt sie nicht an; das tut erst der Zugriff auf ihre Daten."""
    client = _client(welt)
    neu = Path(tmp_path / "neu.db")
    _datenbank_von_a(welt, f"sqlite:///{neu.as_posix()}")
    a = {"gesellschaft": "a", "rahmen": "SKR03"}
    assert client.get("/test/buchhaltung").json() == a
    assert not neu.exists()
