"""Bindung der Einstellungen im Web (Baustein 10c P4, Schritt 3; D4, D5, G-N1).

Die Middleware ``Einstellungsstand`` legt je Anfrage einen neuen, ungebundenen Stand an;
``angemeldet`` (Sitzung) und ``api_zugang`` (Token) binden ihn an die Gesellschaft —
streng: Ohne Bindung oder mit einer anderen Konfiguration liest keine Anfrage einen
Datenbank-Abschnitt (500), Betriebsabschnitte gehen immer.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool

from accounti.api.app import erstelle_app
from accounti.api.einstellungsstand import Einstellungsstand
from accounti.api.rest import ZugangDep
from accounti.api.sicherheit import Sicherheit
from accounti.api.sitzung import AngemeldetDep
from accounti.db import session_factory
from accounti.db.repo_einstellungen import fuege_version_an
from accounti.einstellungen.leser import (
    DatenbankQuelle,
    EinstellungsquelleFehlt,
    aktueller_stand,
    lies_abschnitt,
)
from accounti.konfiguration import lade_buchhaltung
from accounti.models.auth import Rolle, TokenRecht
from tests.api_hilfe import BASIS, csrf, webwelt
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


def version(url: str, abschnitt: str, daten: dict) -> None:
    engine, fabrik = session_factory(url)
    try:
        with fabrik() as s:
            fuege_version_an(
                s, abschnitt, daten, person="erika", grund="Probe", quelle="cli"
            )
            s.commit()
    finally:
        engine.dispose()


def _client(welt, *routen) -> TestClient:  # noqa: ANN001
    app = erstelle_app(welt.dienste)
    for pfad, funktion in routen:
        app.get(pfad)(funktion)
    return TestClient(app, base_url=BASIS)


def _angemeldet(welt, client: TestClient, name: str = "eva") -> TestClient:  # noqa: ANN001
    antwort = welt.anmelden(client, name)
    assert antwort.status_code == 303, antwort.text
    return client


def test_sicherheit_ist_die_aeusserste_middleware(welt, caplog):
    """G-N1: Sicherheit außen (500-Seite, Kopfzeilen), ``Einstellungsstand`` innen."""

    def boese() -> None:
        raise EinstellungsquelleFehlt("Probe")

    app = erstelle_app(welt.dienste)
    assert app.user_middleware[0].cls is Sicherheit
    assert app.user_middleware[1].cls is Einstellungsstand
    app.get("/test/boese")(boese)
    client = TestClient(app, base_url=BASIS)
    with caplog.at_level(logging.ERROR, logger="accounti"):
        r = client.get("/test/boese")
    assert r.status_code == 500
    assert "content-security-policy" in r.headers
    assert "EinstellungsquelleFehlt" in caplog.text
    assert "Probe" not in r.text


def test_ungebunden_fail_closed(welt, caplog):
    """D5: Eine Route ohne Anmeldung liest einen Datenbank-Abschnitt → 500."""
    from accounti.elster.konfiguration import lade_elster

    pfad = welt.umgebung.config["a"]

    def ohne_anmeldung() -> dict[str, str]:
        return {"zeitraum": lade_elster(pfad).voranmeldungszeitraum}

    client = _client(welt, ("/test/ungebunden", ohne_anmeldung))
    with caplog.at_level(logging.ERROR, logger="accounti"):
        r = client.get("/test/ungebunden")
    assert r.status_code == 500
    assert "EinstellungsquelleFehlt" in caplog.text


def test_betriebsabschnitte_ohne_bindung(welt):
    from accounti.auth.einstellungen import lade_auth

    pfad = welt.umgebung.registry

    def betrieb() -> dict[str, object]:
        return {
            "auth": lade_auth(pfad).passwort_mindestlaenge,
            "gesellschaften": sorted(
                lies_abschnitt(pfad, "gesellschaften")["eintraege"]
            ),
            "gebunden": aktueller_stand().gebunden,  # type: ignore[union-attr]
        }

    r = _client(welt, ("/test/betrieb", betrieb)).get("/test/betrieb")
    assert r.status_code == 200, r.text
    assert r.json()["gesellschaften"] == ["a", "b"] and r.json()["gebunden"] is False


def test_schnappschuss_je_anfrage(welt):
    """A54: In einer Anfrage ein Stand — die nächste Anfrage sieht die neue Version."""
    db = welt.umgebung.db["a"]
    version(db, "buchhaltung", {"kontenrahmen": "SKR03", "bank_konto": "1800"})

    def zweimal(a: AngemeldetDep) -> dict[str, str]:
        vorher = lade_buchhaltung(a.gesellschaft.konfiguration).bank_konto
        version(db, "buchhaltung", {"kontenrahmen": "SKR03", "bank_konto": "1210"})
        nachher = lade_buchhaltung(a.gesellschaft.konfiguration).bank_konto
        return {"vorher": vorher, "nachher": nachher}

    client = _angemeldet(welt, _client(welt, ("/test/zweimal", zweimal)))
    assert client.get("/test/zweimal").json() == {"vorher": "1800", "nachher": "1800"}
    assert client.get("/test/zweimal").json()["vorher"] == "1210"


def test_gesellschaften_getrennt(welt):
    """Sitzung in a, Version nur in b: a liest seine Datei, nach dem Wechsel nach b
    gilt die Version von b."""
    version(welt.umgebung.db["b"], "buchhaltung", {"bank_konto": "1810"})

    async def bank(a: AngemeldetDep) -> dict[str, str]:
        # auch im Threadpool (kopierter Kontext) derselbe gebundene Stand
        konto = await run_in_threadpool(
            lambda: lade_buchhaltung(a.gesellschaft.konfiguration).bank_konto
        )
        return {"gesellschaft": a.gesellschaft.kuerzel, "konto": konto}

    client = _angemeldet(welt, _client(welt, ("/test/bank", bank)))
    assert client.get("/test/bank").json() == {"gesellschaft": "a", "konto": "1200"}
    r = client.post(
        "/gesellschaft",
        data={"csrf": csrf(client), "kuerzel": "b"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert client.get("/test/bank").json() == {"gesellschaft": "b", "konto": "1810"}


def test_anderer_pfad_fail_closed(welt, caplog):
    """D5: Angemeldet in a, die Route liest die Konfiguration von b → 500."""
    andere = welt.umgebung.config["b"]

    def fremd(a: AngemeldetDep) -> dict[str, str]:
        return {"rahmen": lade_buchhaltung(andere).kontenrahmen}

    client = _angemeldet(welt, _client(welt, ("/test/fremd", fremd)))
    with caplog.at_level(logging.ERROR, logger="accounti"):
        r = client.get("/test/fremd")
    assert r.status_code == 500
    assert "EinstellungsquelleFehlt" in caplog.text


def test_rest_token_bindet_seine_gesellschaft(welt, monkeypatch):
    """``POST /api/v1/laeufe/bank`` mit ``buchhaltung.bank_konto`` aus der Version der
    Gesellschaft des Tokens (Pilot ``lade_buchhaltung``)."""
    import accounti.bank.lauf as lauf

    version(
        welt.umgebung.db["b"],
        "buchhaltung",
        {"kontenrahmen": "SKR04", "bank_konto": "1810"},
    )
    gesehen: list[tuple[str, str]] = []

    def bank_lauf(s, engine, buchhaltung, **_):  # noqa: ANN001, ANN003, ANN202
        gesehen.append((buchhaltung.kontenrahmen, buchhaltung.bank_konto))
        raise RuntimeError("nur bis hierher")

    monkeypatch.setattr(lauf, "bank_lauf", bank_lauf)
    for kuerzel in ("a", "b"):
        token = welt.token(kuerzel, TokenRecht.LAEUFE_STARTEN, name=f"erp-{kuerzel}")
        welt.client().post(
            "/api/v1/laeufe/bank", headers={"Authorization": f"Bearer {token}"}
        )
    assert gesehen == [("SKR03", "1200"), ("SKR04", "1810")]

    def ich(zugang: ZugangDep) -> dict[str, object]:
        stand = aktueller_stand()
        assert stand is not None
        return {"gebunden": stand.gebunden, "kuerzel": stand.kuerzel}

    token = welt.token("b", TokenRecht.LAEUFE_STARTEN, name="erp-ich")
    r = _client(welt, ("/api/v1/test/ich", ich)).get(
        "/api/v1/test/ich", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.json() == {"gebunden": True, "kuerzel": "b"}


def test_dienste_quelle_nutzt_die_engine_der_gesellschaft(welt):
    q = welt.dienste.quelle("b")
    assert isinstance(q, DatenbankQuelle)
    assert q is welt.dienste.quelle("b")
    version(welt.umgebung.db["b"], "kasse", {"konto": "1610"})
    assert q.schnappschuss().versionen["kasse"].daten == {"konto": "1610"}


def test_datenbank_wert_wirkt_in_freigaben(tmp_path):
    """AK78: ``elster.voranmeldungszeitraum: quartal`` nur als Version — die
    USt-VA-Freigabe für 2026-Q3 im Browser ist kein Fachfehler mehr."""
    from accounti.api.dienste import Dienste, einzelne_gesellschaft
    from tests import test_cli_ustva as ustva
    from tests.api_hilfe import Uhr, Webwelt
    from tests.auth_hilfe import SCHLUESSEL

    url, konfig = ustva.umgebung(tmp_path)
    uhr = Uhr(datetime(2026, 10, 20, 9, 0))
    g = einzelne_gesellschaft(url, str(tmp_path / "archiv"), konfig)
    dienste = Dienste(url, {g.kuerzel: g}, schluessel=lambda: SCHLUESSEL, uhr=uhr)
    welt = Webwelt(None, dienste, uhr)  # type: ignore[arg-type]
    welt.person("chef", Rolle.FREIGEBER, gesellschaft="standard")
    chef = welt.angemeldet("chef")

    def freigeben() -> object:
        daten = {
            "csrf": csrf(chef),
            "zeitraum": "2026-Q3",
            "einmalcode": welt.code("chef"),
        }
        antwort = chef.post("/freigaben/ustva", data=daten)
        welt.uhr.weiter(30)
        return antwort

    r = freigeben()
    assert r.status_code == 409 and "kein Voranmeldungszeitraum" in r.text, r.text
    version(
        url,
        "elster",
        {
            "bundesland": "BY",
            "finanzamt": {"name": "Finanzamt München"},
            "voranmeldungszeitraum": "quartal",
        },
    )
    r = freigeben()
    assert r.status_code == 200, r.text
    assert "2026-Q3 freigegeben von chef" in r.text


def test_rechte_haengen_nicht_an_der_bindung(welt):
    """Die Bindung ändert keine Rechte: ohne Anmeldung weiter zur Anmeldung."""
    r = welt.client().get("/freigaben", follow_redirects=False)
    assert r.status_code == 303 and "/anmelden" in r.headers["location"]
