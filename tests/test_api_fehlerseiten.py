"""Fehler- und Statusseiten im Design (Spec 10c A9, AK48, AK58; Plan P1, Schritt 11)."""

from __future__ import annotations

import logging
import re
from typing import Annotated

import pytest
from fastapi import Depends, Request
from sqlalchemy.exc import OperationalError

from accounti.api.app import erstelle_app
from accounti.api.sicherheit import Sicherheit
from accounti.api.sitzung import Angemeldet, AngemeldetDep, erfordert
from accounti.models.auth import Recht, Rolle
from tests.api_hilfe import csrf, freigabe_hash, webwelt
from tests.auth_hilfe import billige_hashes
from tests.gesellschaft_hilfe import zahlungslauf

EN = {"Accept-Language": "en"}
VerwaltenDep = Annotated[Angemeldet, Depends(erfordert(Recht.VERWALTEN))]
HX = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER)
    w.person("leo", Rolle.BETRACHTER)
    w.person("fritz", Rolle.FREIGEBER)
    zahlungslauf(w.umgebung, "a")
    return w


def _inhalt(html: str) -> str:
    return html[html.index('<main id="inhalt"') : html.index("</main>")]


def _gesperrt(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
    raise OperationalError(
        "UPDATE auth_sitzungen …", {}, Exception("database is locked")
    )


# --- 403 -----------------------------------------------------------------------------


def test_403_nennt_recht_und_rollen(welt):
    leo = welt.angemeldet("leo")
    daten = {"csrf": csrf(leo), "zeitraum": "2026-09"}
    r = leo.post("/freigaben/ustva", data=daten)
    assert r.status_code == 403
    inhalt = _inhalt(r.text)
    assert "<h1>Keine Berechtigung</h1>" in inhalt
    assert "Ihre Rolle in Alpha Papier GmbH erlaubt das nicht" in inhalt
    assert "Nötig:" in inhalt and "Steuermeldungen freigeben" in inhalt
    assert '<span lang="de">freigeber</span>' in inhalt
    assert '<nav class="seitenleiste"' in r.text  # im Gerüst
    englisch = _inhalt(leo.post("/freigaben/ustva", data=daten, headers=EN).text)
    assert "Your role in Alpha Papier GmbH does not allow this" in englisch
    assert "approve tax returns" in englisch
    assert '<span lang="de">freigeber</span>' in englisch  # Rollenkennung bleibt
    # zusammengesetzte Prüfung (Zurückstellen: buchen oder Buchungen freigeben)
    from tests.pruefen_hilfe import Queuewelt

    b = Queuewelt(welt, welt.umgebung.wurzel).buchung()
    r = leo.post(f"/pruefen/{b.id}/zurueckstellen", data={"csrf": csrf(leo)})
    inhalt = _inhalt(r.text)
    assert r.status_code == 403 and "buchen und korrigieren" in inhalt
    assert "Buchungen freigeben" in inhalt
    for rolle in ("buchhalter", "freigeber"):
        assert f'<span lang="de">{rolle}</span>' in inhalt


def test_403_api_json_mit_dem_satz(welt):
    from accounti.api.sitzung import Verweigerung, verweigert

    client = welt.client()

    @client.app.get("/api/probe/verwalten")
    async def probe(a: VerwaltenDep) -> dict[str, str]:
        return {}

    welt.anmelden(client, "jan")
    r = client.get("/api/probe/verwalten")
    assert r.status_code == 403
    assert r.json() == {"fehler": "Ihre Rolle in Alpha Papier GmbH erlaubt das nicht"}
    fehler = verweigert(_angemeldet(welt, "jan"), Recht.VERWALTEN)
    assert isinstance(fehler.detail, Verweigerung)
    assert str(fehler.detail) == "Ihre Rolle in Alpha Papier GmbH erlaubt das nicht"
    assert fehler.detail.rechte == (Recht.VERWALTEN,)
    assert fehler.detail.rollen == (Rolle.VERWALTER,)


def _angemeldet(welt, name: str) -> Angemeldet:  # noqa: ANN001
    from accounti.api.sitzung import csrf_token

    return Angemeldet(
        benutzer=welt.personen[name].benutzer,
        sitzung=None,  # type: ignore[arg-type]
        gesellschaft=welt.dienste.gesellschaften["a"],
        gesellschaften=(welt.dienste.gesellschaften["a"],),
        rechte=frozenset({Recht.LESEN}),
        csrf=csrf_token("x"),
    )


# --- 404, 409, htmx ---------------------------------------------------------------


def test_404_im_design_mit_weg_zurueck(welt):
    jan = welt.angemeldet("jan")
    r = jan.get("/gibt/es/nicht")
    assert r.status_code == 404
    assert "<h1>Nicht gefunden</h1>" in r.text and '<nav class="seitenleiste"' in r.text
    assert re.search(r'<a href="/">Zurück</a>', _inhalt(r.text))
    r = jan.get("/pruefen/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and "Buchung nicht gefunden" in r.text
    assert '<a href="/pruefen">Zurück</a>' in _inhalt(r.text)  # Start des Bereichs
    ohne = welt.client().get("/gibt/es/nicht")
    assert ohne.status_code == 404 and '<body class="schlicht"' in ohne.text
    assert "<h1>Nicht gefunden</h1>" in ohne.text
    assert "<h1>Not found</h1>" in welt.client().get("/x", headers=EN).text


def test_404_bei_gesperrter_systemdatenbank_schlicht(welt, monkeypatch, caplog):
    from accounti.api import sitzung

    jan = welt.angemeldet("jan")
    monkeypatch.setattr(sitzung, "_lade", _gesperrt)
    r = jan.get("/gibt/es/nicht")
    assert r.status_code == 404 and '<body class="schlicht"' in r.text
    assert "database is locked" not in caplog.text and "UPDATE" not in caplog.text


def test_409_im_design(welt):
    fritz = welt.angemeldet("fritz")
    assert freigabe_hash(fritz, 1) is not None
    daten = {"csrf": csrf(fritz), "einmalcode": "000000", "freigabe_hash": "0" * 64}
    r = fritz.post("/freigaben/zahlungslauf/1", data=daten)
    assert r.status_code == 409
    inhalt = _inhalt(r.text)
    assert "<h1>Inzwischen geändert</h1>" in inhalt
    assert '<a href="/freigaben">Zurück</a>' in inhalt


def test_ueberschrift_passt_zum_fehler(welt):
    """P1 Runde 2 (gp1-bestand N2): Die Überschrift folgte nur dem Status — ein falscher
    Einmalcode oder ein fehlendes CSRF-Token hießen „Keine Berechtigung“, Fachfehler der
    Freigabe (USt-VA-Zeitraum, Lauf gesperrt) „Inzwischen geändert“. Jetzt: „Keine
    Berechtigung“ nur bei fehlender Rolle bzw. Gesellschaft, „Inzwischen geändert“ nur
    bei geänderten Daten, sonst „Nicht ausgeführt“."""
    fritz = welt.angemeldet("fritz")
    gesehen = freigabe_hash(fritz, 1)
    falsch = fritz.post(
        "/freigaben/zahlungslauf/1",
        data={"csrf": csrf(fritz), "einmalcode": "000000", "freigabe_hash": gesehen},
    )
    ohne_csrf = fritz.post(
        "/freigaben/zahlungslauf/1",
        data={"einmalcode": "000000", "freigabe_hash": gesehen},
    )
    quartal = fritz.post(
        "/freigaben/ustva",
        data={"csrf": csrf(fritz), "einmalcode": "000000", "zeitraum": "2026-Q3"},
    )
    for r, status in ((falsch, 403), (ohne_csrf, 403), (quartal, 409)):
        assert r.status_code == status, (status, r.text[:300])
        inhalt = _inhalt(r.text)
        assert "<h1>Nicht ausgeführt</h1>" in inhalt, (status, inhalt[:400])
        assert "Keine Berechtigung" not in r.text and "Inzwischen" not in r.text
    englisch = fritz.post(
        "/freigaben/zahlungslauf/1",
        data={"einmalcode": "000000", "freigabe_hash": gesehen},
        headers=EN,
    )
    assert "<h1>Not carried out</h1>" in englisch.text
    fremd = fritz.post("/gesellschaft", data={"csrf": csrf(fritz), "kuerzel": "zz"})
    assert fremd.status_code == 403 and "<h1>Keine Berechtigung</h1>" in fremd.text


def test_htmx_fehler_als_fragment(welt, monkeypatch):
    from accounti.api.seiten import start

    fritz = welt.angemeldet("fritz")
    daten = {"csrf": csrf(fritz), "einmalcode": "000000", "freigabe_hash": "0" * 64}
    antworten = {
        409: fritz.post("/freigaben/zahlungslauf/1", data=daten, headers=HX),
        422: fritz.post(
            "/freigaben/ustva", data={**daten, "zeitraum": "quatsch"}, headers=HX
        ),
        404: fritz.get("/gibt/es/nicht", headers=HX),
    }
    monkeypatch.setattr(start, "kennzahlen", _beschaeftigt)
    antworten[503] = fritz.get("/", headers=HX)
    for status, r in antworten.items():
        assert r.status_code == status, (status, r.text[:200])
        assert "<html" not in r.text and 'role="alert"' in r.text, status
        assert "hinweis-fehler" in r.text, status


def _beschaeftigt(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
    raise OperationalError("SELECT …", {}, Exception("database is locked"))


def test_statusseiten_mit_h1_je_status(welt, monkeypatch):
    from accounti.api.seiten import start

    jan = welt.client()

    @jan.app.get("/probe/zahl")
    async def zahl(a: AngemeldetDep, wert: int) -> None:
        return None

    welt.anmelden(jan, "jan")
    r = jan.get("/probe/zahl?wert=abc")  # RequestValidationError
    assert r.status_code == 422 and "<h1>Angaben prüfen</h1>" in r.text
    assert "Ungültige Angaben: wert" in r.text
    fritz = welt.angemeldet("fritz")
    daten = {"csrf": csrf(fritz), "zeitraum": "quatsch"}
    r = fritz.post("/freigaben/ustva", data=daten)  # HTTPException(422)
    assert r.status_code == 422 and "<h1>Angaben prüfen</h1>" in r.text
    monkeypatch.setattr(start, "kennzahlen", _beschaeftigt)
    r = jan.get("/")
    assert r.status_code == 503 and "<h1>Gerade beschäftigt</h1>" in r.text
    assert r.headers["retry-after"] == "5"
    gross = "x" * (welt.dienste.server.max_formular_bytes + 10)
    r = jan.post("/konto/vorlieben", data={"csrf": csrf(jan), "a": gross})
    assert r.status_code == 413 and "<h1>Zu groß</h1>" in r.text


def test_api_fehler_bleiben_json(welt):
    client = welt.client()
    r = client.get("/api/v1/gibt-es-nicht")
    assert r.status_code == 404 and r.json() == {"fehler": "Not Found"}
    r = client.get("/api/v1/ich")
    assert r.status_code == 401 and r.headers["content-type"].startswith(
        "application/json"
    )


# --- 500 --------------------------------------------------------------------------


def test_500_ohne_einzelheiten(welt, caplog):
    client = welt.angemeldet("jan")

    @client.app.get("/probe/kaputt")
    async def kaputt() -> None:
        raise RuntimeError("geheim-4711")

    with caplog.at_level(logging.ERROR):
        r = client.get("/probe/kaputt")
    assert r.status_code == 500
    assert "<h1>Interner Fehler</h1>" in r.text and '<body class="schlicht"' in r.text
    assert '<a href="/">Zur Startseite</a>' in r.text
    assert '<a class="kopf-hilfe" href="/hilfe">' in r.text
    for verboten in ("geheim-4711", "Traceback", "RuntimeError"):
        assert verboten not in r.text, verboten
    assert "RuntimeError" in caplog.text and "geheim-4711" not in caplog.text
    englisch = client.get("/probe/kaputt", headers=EN)
    assert "<h1>Internal error</h1>" in englisch.text
    assert '<html lang="en" data-theme="auto">' in englisch.text

    @client.app.get("/api/probe/kaputt")
    async def api_kaputt() -> None:
        raise RuntimeError("geheim-4711")

    api = client.get("/api/probe/kaputt")
    assert api.status_code == 500 and api.json() == {"fehler": "Interner Fehler"}


def test_500_fragt_keine_datenbank(welt):
    client = welt.angemeldet("jan")

    class KeineDatenbank:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"Datenbank gefragt: {name}")

    @client.app.get("/probe/ohne-db")
    async def ohne_db(request: Request) -> None:
        request.app.state.dienste = KeineDatenbank()
        raise RuntimeError("weg")

    r = client.get("/probe/ohne-db")
    assert r.status_code == 500 and "<h1>Interner Fehler</h1>" in r.text


def test_sicherheit_ist_die_aeusserste_middleware(welt):
    app = erstelle_app(welt.dienste)
    assert app.user_middleware[0].cls is Sicherheit


def test_ausnahme_in_innerer_middleware_gibt_designseite(welt):
    from starlette.middleware import Middleware

    class Werfer:
        def __init__(self, app) -> None:  # noqa: ANN001
            self.app = app

        async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
            if scope["type"] == "http":
                raise RuntimeError("innen")
            await self.app(scope, receive, send)

    client = welt.client()
    client.app.user_middleware.append(Middleware(Werfer))
    r = client.get("/anmelden")
    assert r.status_code == 500 and "<h1>Interner Fehler</h1>" in r.text
    assert "innen" not in r.text


def test_500_mit_hilfe_in_derselben_relativen_reihenfolge(welt):
    client = welt.client()

    @client.app.get("/probe/kaputt")
    async def kaputt() -> None:
        raise RuntimeError("x")

    kopf = client.get("/probe/kaputt").text
    kopf = kopf[kopf.index("<header") : kopf.index("</header>")]
    klassen = re.findall(r'<a class="([a-z-]+)"', kopf)
    assert klassen == ["sprunglink", "wortmarke", "kopf-hilfe"]
