"""HTMX-Fehlerwege (Baustein 10b, Paket 2): ohne Sitzung ``HX-Redirect`` statt 303,
CSRF-403 mit ``HX-Refresh``, Datenbank beschäftigt → 503 mit ``Retry-After``.

Der Testclient führt kein htmx aus — geprüft werden Status, Kopfzeilen und Inhalt;
dass htmx sie im Browser so behandelt, zeigte der Browser-Spike (Plan)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError
from starlette.requests import Request

from accounti.api.htmx import aktueller_pfad, ist_htmx, ist_verlaufsabruf
from accounti.models.auth import Rolle
from tests.api_hilfe import BASIS, csrf, webwelt
from tests.auth_hilfe import billige_hashes

HX = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER)
    w.person("leo", Rolle.BETRACHTER)
    return w


def test_ohne_sitzung_hx_redirect_statt_303(welt):
    r = welt.client().post(
        "/freigaben/ustva",
        data={"zeitraum": "2026-09"},
        headers={**HX, "HX-Current-URL": f"{BASIS}/freigaben?ansicht=x"},
        follow_redirects=False,
    )
    assert r.status_code == 200 and r.text == ""
    assert r.headers["hx-redirect"] == "/anmelden?weiter=/freigaben%3Fansicht%3Dx"


def test_hx_redirect_weiter_aus_current_url_nur_eigene_herkunft(welt):
    client = welt.client()
    for fremd in ("https://boese.example/freigaben", "javascript:alert(1)", "//x/y"):
        r = client.get(
            "/freigaben",
            headers={**HX, "HX-Current-URL": fremd},
            follow_redirects=False,
        )
        assert r.headers["hx-redirect"] == "/anmelden?weiter=/", fremd
    r = client.get("/freigaben", headers=HX, follow_redirects=False)
    assert r.headers["hx-redirect"] == "/anmelden?weiter=/"


def test_ohne_htmx_unveraendert_303(welt):
    client = welt.client()
    r = client.get("/freigaben", follow_redirects=False)
    assert (
        r.status_code == 303 and r.headers["location"] == "/anmelden?weiter=/freigaben"
    )
    r = client.post("/freigaben/ustva", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/anmelden?weiter=/"
    assert "hx-redirect" not in r.headers


def test_csrf_fehler_hx_refresh(welt):
    client = welt.angemeldet("jan")
    r = client.post(
        "/einstellungen/sprache", data={"csrf": "falsch", "sprache": "en"}, headers=HX
    )
    assert r.status_code == 403 and r.headers["hx-refresh"] == "true"
    r = client.post("/einstellungen/sprache", data={"csrf": "falsch", "sprache": "en"})
    assert r.status_code == 403 and "hx-refresh" not in r.headers


def test_rollen_403_ohne_hx_refresh(welt):
    client = welt.angemeldet("leo")
    r = client.post(
        "/freigaben/ustva",
        data={"csrf": csrf(client), "zeitraum": "2026-09"},
        headers=HX,
    )
    assert r.status_code == 403 and "hx-refresh" not in r.headers


def _anfrage(**kopf: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/pruefen",
            "headers": [(k.lower().encode(), v.encode()) for k, v in kopf.items()],
            "query_string": b"",
            "server": ("accounti.test", 443),
            "scheme": "https",
        }
    )


def test_verlaufsabruf_bekommt_ganze_seite():
    assert ist_htmx(_anfrage(**{"HX-Request": "true"}))
    verlauf = _anfrage(**{"HX-Request": "true", "HX-History-Restore-Request": "true"})
    assert ist_verlaufsabruf(verlauf) and not ist_htmx(verlauf)
    assert not ist_htmx(_anfrage())
    eigene = _anfrage(**{"HX-Current-URL": "https://accounti.test/pruefen?a=1"})
    assert aktueller_pfad(eigene) == "/pruefen?a=1"


def _beschaeftigt(text: str):  # noqa: ANN202
    def werfen(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise OperationalError("UPDATE …", {}, Exception(text))

    return werfen


def test_datenbank_beschaeftigt_503_mit_retry_after(welt, monkeypatch, caplog):
    from accounti.api.seiten import start

    client = welt.angemeldet("jan")
    monkeypatch.setattr(start, "kennzahlen", _beschaeftigt("database is locked"))
    r = client.get("/", headers={"Accept-Language": "en"})
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    assert "A run is currently writing" in r.text
    assert "UPDATE" not in caplog.text and "database is locked" not in caplog.text


def test_andere_operationalerror_bleiben_500(welt, monkeypatch, caplog):
    """Umgestellt (Plan P1, Schritt 11): 500 als Designseite, nicht als Klartext."""
    from accounti.api.seiten import start

    client = welt.angemeldet("jan")
    monkeypatch.setattr(start, "kennzahlen", _beschaeftigt("no such table: x"))
    r = client.get("/")
    assert r.status_code == 500 and "<h1>Interner Fehler</h1>" in r.text
    assert "no such table" not in r.text and "no such table" not in caplog.text
