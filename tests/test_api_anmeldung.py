"""Anmeldung im Browser, Sitzung, CSRF und Sicherheitskopfzeilen (Spec 4.1, Akz. 4)."""

import pytest

from accounti.db.repo_auth import lade_ereignisse
from accounti.models.auth import Rolle
from tests.api_hilfe import csrf, melde_an, webwelt
from tests.auth_hilfe import PASSWORT, billige_hashes


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER)
    w.person("eva", Rolle.BUCHHALTER, mit_2fa=False)
    return w


def sitzungscookie(client):
    return client.cookies.get("__Host-accounti_sitzung")


def test_ohne_anmeldung_zur_anmeldeseite(welt):
    client = welt.client()
    r = client.get("/freigaben", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/anmelden?weiter=/freigaben"
    r = client.get("/api/v1/ich")
    assert r.status_code == 401


def test_akzeptanz_4_anmeldung_ohne_zweiten_faktor_scheitert(welt):
    client = welt.client()
    # richtiges Passwort, kein Code
    r = melde_an(client, "jan", PASSWORT, "")
    assert r.status_code == 401
    assert "Anmeldung fehlgeschlagen" in r.text
    assert sitzungscookie(client) is None
    # richtiges Passwort, falscher Code
    r = melde_an(client, "jan", PASSWORT, "000000")
    assert r.status_code == 401 and sitzungscookie(client) is None
    # Benutzer ohne eingerichteten zweiten Faktor
    r = melde_an(client, "eva", PASSWORT, "123456")
    assert r.status_code == 401 and sitzungscookie(client) is None
    # ohne Sitzung keine Seite
    assert client.get("/", follow_redirects=False).status_code == 303
    # mit beidem
    r = welt.anmelden(client, "jan")
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert sitzungscookie(client)
    seite = client.get("/")
    assert seite.status_code == 200
    assert "Alpha Papier GmbH" in seite.text


def test_sitzungscookie_attribute(welt):
    client = welt.client()
    r = welt.anmelden(client, "jan")
    kopf = r.headers["set-cookie"].lower()
    assert kopf.startswith("__host-accounti_sitzung=")
    for attribut in ("secure", "httponly", "samesite=strict", "path=/"):
        assert attribut in kopf
    assert "domain=" not in kopf


def test_anmeldeformular_gegen_login_csrf(welt):
    client = welt.client()
    r = client.post(
        "/anmelden",
        data={"benutzer": "jan", "passwort": PASSWORT, "einmalcode": welt.code("jan")},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert sitzungscookie(client) is None


def test_weiterleitung_nur_relativ(welt):
    for ziel, erwartet in (
        ("/freigaben", "/freigaben"),
        ("//boese.example/x", "/"),
        ("https://boese.example", "/"),
        ("/\\boese.example", "/"),
    ):
        client = welt.client()
        r = melde_an(client, "jan", PASSWORT, welt.code("jan"), weiter=ziel)
        welt.uhr.weiter(30)
        assert r.status_code == 303, r.text
        assert r.headers["location"] == erwartet


def test_abmelden_beendet_die_sitzung_serverseitig(welt):
    client = welt.client()
    welt.anmelden(client, "jan")
    alt = sitzungscookie(client)
    # ohne CSRF-Token kein Abmelden (und kein anderes POST)
    assert client.post("/abmelden", follow_redirects=False).status_code == 403
    r = client.post("/abmelden", data={"csrf": csrf(client)}, follow_redirects=False)
    assert r.status_code == 303
    assert sitzungscookie(client) is None
    # das alte Cookie taugt nichts mehr
    fremd = welt.client()
    fremd.cookies.set("__Host-accounti_sitzung", alt, domain="accounti.test")
    assert fremd.get("/", follow_redirects=False).status_code == 303
    with welt.system() as s:
        assert any(e.art == "abmeldung" for e in lade_ereignisse(s))


def test_csrf_falsch_oder_fremde_seite(welt):
    client = welt.client()
    welt.anmelden(client, "jan")
    token = csrf(client)
    r = client.post("/gesellschaft", data={"csrf": "falsch", "kuerzel": "a"})
    assert r.status_code == 403
    r = client.post(
        "/gesellschaft",
        data={"csrf": token, "kuerzel": "a"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert r.status_code == 403
    r = client.post(
        "/gesellschaft",
        data={"kuerzel": "a"},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_leerlauf_beendet_die_sitzung(welt):
    client = welt.client()
    welt.anmelden(client, "jan")
    welt.uhr.weiter(29 * 60)
    assert client.get("/", follow_redirects=False).status_code == 200
    welt.uhr.weiter(31 * 60)
    assert client.get("/", follow_redirects=False).status_code == 303


def test_sperre_nach_fehlversuchen_auch_im_browser(tmp_path):
    w = webwelt(tmp_path, sperre_nach_fehlversuchen=3)
    w.person("jan", Rolle.BUCHHALTER)
    client = w.client()
    for _ in range(3):
        assert (
            melde_an(client, "jan", "falsch falsch falsch", "000000").status_code == 401
        )
    r = w.anmelden(client, "jan")
    assert r.status_code == 401  # gesperrt, obwohl jetzt alles stimmt


def test_sicherheitskopfzeilen(welt):
    client = welt.client()
    r = client.get("/anmelden")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["referrer-policy"] == "same-origin"
    css = client.get("/statisch/accounti.css")
    assert css.status_code == 200
    assert css.headers.get("cache-control") != "no-store"


def test_gesund(welt):
    r = welt.client().get("/gesund")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_benutzer_ohne_gesellschaft_kommt_nicht_hinein(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER, gesellschaft="gibtsnicht")
    r = w.anmelden(w.client(), "jan")
    assert r.status_code == 401
