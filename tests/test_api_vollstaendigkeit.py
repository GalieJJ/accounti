"""Vollständigkeitslisten der Oberfläche (Spec 10c A113, A115; Plan P1, Schritt 0).

``GLEICHLAUF``: jeder POST-Endpunkt nennt den Test, der Browser und CLI gleich laufen
lässt, oder eine ausdrücklich benannte Ausnahme nach A113 (Anmeldung, Sitzung,
Anzeige-Vorlieben). POST-Endpunkte aus 10a/10b ohne eigenen Gleichlauftest stehen als
``Bestand`` mit dem Plan des Bausteins, der den Weg über dieselbe Fachfunktion festlegt.

``HTMX_FORMEN``: jede Route der Seiten (ohne die REST-API) hat genau eine Form —
``fragment`` (mit ``HX-Request`` ein Teil der Seite, sonst die ganze Seite bzw. 303),
``neu_laden`` (``HX-Refresh``), ``weiterleitung`` (303) oder ``ganze_seite`` — mit
Grund.
Die GET-Seiten aus 10a/10b sind ``ganze_seite`` mit Grund „Bestand“. Wer eine Route
anlegt, trägt sie im selben Schritt hier ein; das Verhalten prüft
``test_htmx_formen_wirken`` (Schritt 13).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from accounti.api.app import erstelle_app
from tests.api_hilfe import webwelt

WURZEL = Path(__file__).resolve().parents[1]
PLAN_10A = "docs/plans/2026-10-26-auth-gesellschaften-betrieb-api.md"
PLAN_10B = "docs/plans/2026-10-27-web-oberflaeche.md"


@dataclass(frozen=True)
class Ausnahme:
    """Keine Fachaktion mit CLI-Befehl (A113)."""

    grund: str


@dataclass(frozen=True)
class Bestand:
    """POST aus 10a/10b: dieselbe Fachfunktion wie die CLI, festgelegt im Plan."""

    plan: str


# (Methode, Pfad) → Gleichlauftest („datei::test“), Bestand oder Ausnahme
GLEICHLAUF: dict[tuple[str, str], str | Bestand | Ausnahme] = {
    ("POST", "/anmelden"): Ausnahme("Sitzung im Browser; die CLI prüft je Befehl"),
    ("POST", "/abmelden"): Ausnahme("Sitzung im Browser beenden"),
    ("POST", "/gesellschaft"): Ausnahme("Sitzungszustand; CLI: --gesellschaft"),
    ("POST", "/einstellungen/sprache"): Ausnahme("308 auf /konto/vorlieben (A87)"),
    ("POST", "/konto/vorlieben"): Ausnahme("Anzeige-Vorliebe (A87, A113)"),
    ("POST", "/freigaben/zahlungslauf/{nr}"): Bestand(PLAN_10A),
    ("POST", "/freigaben/ustva"): Bestand(PLAN_10A),
    ("POST", "/pruefen/{buchung_id:uuid}/freigeben"): (
        "tests/test_akzeptanz_web.py::"
        "test_akzeptanz_1_unsichere_buchung_pruefen_korrigieren_freigeben"
    ),
    ("POST", "/pruefen/{buchung_id:uuid}/korrigieren"): (
        "tests/test_akzeptanz_web.py::"
        "test_akzeptanz_1_unsichere_buchung_pruefen_korrigieren_freigeben"
    ),
    ("POST", "/pruefen/{buchung_id:uuid}/zurueckstellen"): Bestand(PLAN_10B),
    ("POST", "/pruefen/{buchung_id:uuid}/regelvorschau"): Ausnahme(
        "Vorschau ohne Änderung (liest nur)"
    ),
    ("POST", "/pruefen/regeln/{regel_id:uuid}/deaktivieren"): Bestand(PLAN_10B),
    ("POST", "/buchungen/{buchung_id:uuid}/korrigieren"): (
        "tests/test_api_buchungen.py::"
        "test_freigegebene_buchung_korrigieren_ist_storno_und_neubuchung"
    ),
    ("POST", "/buchungen/{buchung_id:uuid}/stornieren"): (
        "tests/test_akzeptanz_web.py::test_akzeptanz_1_freigegebene_buchung_per_storno"
    ),
}

BESTAND = "Bestand"  # GET-Seite aus 10a/10b: ganze Seite auch mit HX-Request
FORMEN = {"fragment", "neu_laden", "weiterleitung", "ganze_seite"}

# (Methode, Pfad) → (Form, Grund)
HTMX_FORMEN: dict[tuple[str, str], tuple[str, str]] = {
    ("GET", "/anmelden"): ("ganze_seite", BESTAND),
    ("POST", "/anmelden"): ("weiterleitung", "303 auf weiter"),
    ("POST", "/abmelden"): ("weiterleitung", "303 auf /anmelden"),
    ("POST", "/gesellschaft"): ("weiterleitung", "303 auf /"),
    ("POST", "/einstellungen/sprache"): ("weiterleitung", "308 auf /konto/vorlieben"),
    ("GET", "/"): ("ganze_seite", BESTAND),
    ("GET", "/freigaben"): ("ganze_seite", BESTAND),
    # Ergebnis als Seite (meldung.html); Fehler als Seite, mit htmx als Fragment
    ("POST", "/freigaben/zahlungslauf/{nr}"): ("ganze_seite", "Ergebnis als Seite"),
    ("POST", "/freigaben/ustva"): ("ganze_seite", "Ergebnis als Seite"),
    ("GET", "/pruefen"): ("ganze_seite", BESTAND),
    ("GET", "/pruefen/regeln"): ("ganze_seite", BESTAND),
    ("GET", "/pruefen/{buchung_id:uuid}"): ("fragment", "Arbeitsfläche (10b)"),
    ("POST", "/pruefen/{buchung_id:uuid}/freigeben"): ("fragment", "Arbeitsfläche"),
    ("POST", "/pruefen/{buchung_id:uuid}/korrigieren"): ("fragment", "Arbeitsfläche"),
    ("POST", "/pruefen/{buchung_id:uuid}/zurueckstellen"): (
        "fragment",
        "Arbeitsfläche",
    ),
    ("POST", "/pruefen/{buchung_id:uuid}/regelvorschau"): ("fragment", "Regelvorschau"),
    ("POST", "/pruefen/regeln/{regel_id:uuid}/deaktivieren"): (
        "weiterleitung",
        "303 auf /pruefen/regeln",
    ),
    ("GET", "/buchungen/{buchung_id:uuid}"): ("ganze_seite", BESTAND),
    # Ergebnis und Fehler als die Buchungsseite (Bestand 10b)
    ("POST", "/buchungen/{buchung_id:uuid}/korrigieren"): (
        "ganze_seite",
        "Ergebnis als Seite",
    ),
    ("POST", "/buchungen/{buchung_id:uuid}/stornieren"): (
        "ganze_seite",
        "Ergebnis als Seite",
    ),
    ("GET", "/belege/{beleg_id:uuid}"): ("ganze_seite", BESTAND),
    ("GET", "/belege/{beleg_id:uuid}/datei"): ("ganze_seite", "Datei, kein HTML"),
    ("GET", "/belege/{beleg_id:uuid}/seite/{n}.png"): ("ganze_seite", "Bild"),
    ("GET", "/belege/{beleg_id:uuid}/download"): ("ganze_seite", "Datei, kein HTML"),
    # Baustein 10c P1
    ("GET", "/muster"): ("fragment", "neue Seite: Block inhalt"),
    ("GET", "/muster/beispiel"): ("fragment", "Austausch; ohne htmx 303"),
    ("GET", "/menue"): ("fragment", "neue Seite: Block inhalt"),
    ("GET", "/gesellschaft"): ("fragment", "neue Seite: Block inhalt"),
    ("GET", "/konto"): ("fragment", "neue Seite: Block inhalt"),
    ("POST", "/konto/vorlieben"): ("neu_laden", "HX-Refresh; ohne htmx 303 auf weiter"),
    ("GET", "/hilfe"): ("fragment", "neue Seite: Block inhalt"),
    ("GET", "/hilfe/{thema}"): ("fragment", "neue Seite: Block inhalt"),
}


@pytest.fixture(scope="module")
def routen(tmp_path_factory) -> set[tuple[str, str]]:
    w = webwelt(tmp_path_factory.mktemp("vollstaendigkeit"))
    app = erstelle_app(w.dienste)
    return {
        (e.methode, e.pfad)
        for e in app.state.endpunkte
        if not e.pfad.startswith("/api/") and e.pfad != "/gesund"
    }


def test_jeder_post_hat_gleichlauf_oder_ausnahme(routen):
    assert set(GLEICHLAUF) == {r for r in routen if r[0] == "POST"}
    for eintrag in GLEICHLAUF.values():
        if isinstance(eintrag, Ausnahme):
            assert eintrag.grund
        elif isinstance(eintrag, Bestand):
            assert (WURZEL / eintrag.plan).is_file(), eintrag.plan


def test_jeder_gleichlauftest_existiert():
    for eintrag in GLEICHLAUF.values():
        if not isinstance(eintrag, str):
            continue
        datei, name = eintrag.split("::")
        assert (WURZEL / datei).is_file(), datei
        modul = importlib.import_module(datei.removesuffix(".py").replace("/", "."))
        assert callable(getattr(modul, name, None)), eintrag


def test_jede_route_hat_eine_htmx_form(routen):
    assert set(HTMX_FORMEN) == routen
    for form, grund in HTMX_FORMEN.values():
        assert form in FORMEN and grund


HX = {"HX-Request": "true"}


def _wirkt(form: str, methode: str, pfad: str, ohne, mit) -> None:  # noqa: ANN001
    """Die Form einer Route an zwei Antworten (ohne und mit ``HX-Request``)."""
    wo = (methode, pfad, ohne.status_code, mit.status_code)
    html = "text/html" in mit.headers.get("content-type", "")
    if form == "fragment" and methode == "GET":
        assert mit.status_code == 200 and "<html" not in mit.text, wo
        if pfad == "/muster/beispiel":
            assert ohne.status_code == 303, wo
        else:
            assert ohne.status_code == 200 and "<html" in ohne.text, wo
    elif form == "fragment":  # Aktionen der Arbeitsfläche
        assert "<html" not in mit.text, wo
        assert mit.status_code in (200, 409, 422), wo
        assert ohne.status_code == 303 or "<html" in ohne.text, wo
    elif form == "ganze_seite":
        if methode == "GET":
            assert mit.status_code == ohne.status_code == 200, wo
        for r in (ohne, mit):  # Ergebnis als ganze Seite (Fehler mit htmx: Fragment)
            if r.status_code == 200 and html:
                assert "<html" in r.text, wo
        assert ohne.status_code == 200 or "<html" in ohne.text, wo
    elif form == "neu_laden":
        assert mit.status_code == 200 and mit.headers.get("hx-refresh") == "true", wo
        assert ohne.status_code == 303, wo
    else:  # weiterleitung: 303/308; ein Fehler (etwa ein zweiter Versuch) als Seite
        assert ohne.status_code in (303, 308), wo
        assert mit.status_code in (303, 308) or mit.status_code >= 400, wo


def test_htmx_formen_wirken(tmp_path, monkeypatch):
    """AK58, A99, A115 (Plan P1, Schritt 13): jede Route mit und ohne ``HX-Request`` —
    Fragment ohne ``<html``, ``HX-Refresh``, 303 bzw. ganze Seite; jede neue GET-Route
    liefert mit ``HX-Request`` ein Fragment."""
    from accounti.models.auth import Rolle, rechte_der_rollen
    from tests.api_hilfe import melde_an
    from tests.auth_hilfe import PASSWORT, billige_hashes
    from tests.gesellschaft_hilfe import zahlungslauf
    from tests.test_api_rechte_matrix import (
        ANGEMELDET,
        OFFEN,
        SEITEN,
        EinesVon,
        anfrage,
        fachdaten,
    )

    billige_hashes(monkeypatch)
    welt = webwelt(tmp_path)  # wie die Welt der Rechte-Matrix
    for rolle in Rolle:
        welt.person(rolle.value, rolle)
    zahlungslauf(welt.umgebung, "a")
    welt.daten = fachdaten(welt, tmp_path)  # type: ignore[attr-defined]
    clients: dict[Rolle, object] = {}

    def wer(recht: object) -> Rolle:
        for rolle in Rolle:
            rechte = rechte_der_rollen([rolle])
            if (
                recht in (OFFEN, ANGEMELDET)
                or (isinstance(recht, EinesVon) and recht & rechte)
                or recht in rechte
            ):
                return rolle
        raise AssertionError(recht)

    geprueft = set()
    for (methode, pfad), (form, _) in sorted(
        HTMX_FORMEN.items(), key=lambda x: (x[0][1] == "/abmelden", x[0])
    ):
        if (methode, pfad) == ("POST", "/anmelden"):
            code = welt.code("buchhalter")
            ohne = melde_an(welt.client(), "buchhalter", PASSWORT, code)
            welt.uhr.weiter(30)
            client = welt.client()
            client.headers.update(HX)
            mit = melde_an(client, "buchhalter", PASSWORT, welt.code("buchhalter"))
            welt.uhr.weiter(30)
        elif pfad == "/abmelden":  # je Aufruf eine eigene Sitzung
            b = Rolle.BETRACHTER
            ohne = anfrage(welt, welt.angemeldet(b.value), b, methode, pfad)
            mit = anfrage(welt, welt.angemeldet(b.value), b, methode, pfad, HX)
        else:
            rolle = wer(SEITEN[(methode, pfad)])
            if rolle not in clients:
                clients[rolle] = welt.angemeldet(rolle.value)
            client = clients[rolle]
            ohne = anfrage(welt, client, rolle, methode, pfad)
            mit = anfrage(welt, client, rolle, methode, pfad, HX)
        _wirkt(form, methode, pfad, ohne, mit)
        geprueft.add((methode, pfad))
    assert geprueft == set(HTMX_FORMEN)
