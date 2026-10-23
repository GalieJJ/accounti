"""CSRF über die Registry (Baustein 10b): jeder POST-Endpunkt der Oberfläche ohne
oder mit falschem Token → 403, nichts geändert."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from accounti.api.app import erstelle_app
from accounti.db import session_factory
from accounti.models.auth import Rolle
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes
from tests.test_api_rechte_matrix import anfrage, fachdaten  # noqa: F401

STAND_ABFRAGEN = {
    "a": (
        "SELECT count(*) FROM journal",
        "SELECT group_concat(status || soll_konto, ',') FROM buchungssaetze",
        "SELECT count(*) FROM kontierungsregeln WHERE aktiv",
        "SELECT count(*) FROM aufgaben",
        "SELECT count(*) FROM zahlungslauf_protokoll",
    ),
    "system": (
        "SELECT group_concat(name || coalesce(sprache, '-'), ',') FROM auth_benutzer",
        "SELECT count(*) FROM auth_sitzungen WHERE beendet_am IS NULL",
    ),
}


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


def zustand(welt) -> list[object]:  # noqa: ANN001
    werte: list[object] = []
    for ziel, abfragen in STAND_ABFRAGEN.items():
        url = welt.umgebung.system if ziel == "system" else welt.umgebung.db[ziel]
        engine, fabrik = session_factory(url)
        with fabrik() as s:
            werte += [s.execute(text(a)).scalar() for a in abfragen]
        engine.dispose()
    return werte


def test_jeder_post_ohne_csrf_403_und_nichts_geaendert(tmp_path):
    from tests.gesellschaft_hilfe import zahlungslauf

    welt = webwelt(tmp_path)
    for rolle in Rolle:
        welt.person(rolle.value, rolle)
    welt.rolle("buchhalter", "a", Rolle.FREIGEBER)
    welt.rolle("buchhalter", "a", Rolle.VERWALTER)
    zahlungslauf(welt.umgebung, "a")
    welt.daten = fachdaten(welt, tmp_path)  # type: ignore[attr-defined]
    client = welt.angemeldet("buchhalter")
    posts = sorted(
        e.pfad
        for e in erstelle_app(welt.dienste).state.endpunkte
        if e.methode == "POST" and not e.pfad.startswith(("/api/", "/anmelden"))
    )
    assert "/pruefen/{buchung_id:uuid}/korrigieren" in posts
    vorher = zustand(welt)
    original = client.post

    def mit_token(token: str | None):  # noqa: ANN202
        def senden(url, data=None, **kw):  # noqa: ANN001, ANN003, ANN202
            daten = dict(data or {})
            daten.pop("csrf", None)
            if token is not None:
                daten["csrf"] = token
            return original(url, data=daten, **kw)

        return senden

    for pfad in posts:
        for token in (None, "falsch"):
            client.post = mit_token(token)  # type: ignore[method-assign]
            try:
                r = anfrage(welt, client, Rolle.BUCHHALTER, "POST", pfad)
            finally:
                client.post = original  # type: ignore[method-assign]
            assert r.status_code == 403, (pfad, token, r.status_code)
            assert "CSRF" in r.text, pfad
    assert zustand(welt) == vorher
