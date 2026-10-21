"""App-Fabrik, Router-Registry und Grundlayout (Schnittstelle der Web-Oberfläche)."""

import importlib
import sys

import pytest

from accounti.api.registry import endpunkte, navigation, routermodule
from accounti.models.auth import Recht, Rolle
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def paket(tmp_path, monkeypatch):
    """Ein Paket mit zwei Seitenmodulen — eines mit router, eines ohne."""
    wurzel = tmp_path / "probe_seiten"
    wurzel.mkdir()
    (wurzel / "__init__.py").write_text("", encoding="utf-8")
    (wurzel / "pruefen.py").write_text(
        "from fastapi import APIRouter\n"
        "from accounti.api.registry import Navigationspunkt\n"
        "from accounti.models.auth import Recht\n"
        "router = APIRouter()\n"
        "NAVIGATION = [Navigationspunkt('Prüfen', '/pruefen', Recht.BUCHEN, 10)]\n"
        "@router.get('/pruefen')\n"
        "def pruefen() -> dict[str, str]:\n"
        "    return {}\n",
        encoding="utf-8",
    )
    (wurzel / "hilfe.py").write_text("X = 1\n", encoding="utf-8")
    (wurzel / "_privat.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield importlib.import_module("probe_seiten")
    for name in [n for n in sys.modules if n.startswith("probe_seiten")]:
        del sys.modules[name]


def test_registry_findet_router_module(paket):
    module = routermodule(paket)
    assert [m.__name__ for m in module] == ["probe_seiten.pruefen"]
    assert [(e.methode, e.pfad) for e in endpunkte(module, "/x")] == [
        ("GET", "/x/pruefen")
    ]
    assert [p.titel for p in navigation(module)] == ["Prüfen"]


def test_navigation_nur_mit_recht(tmp_path):
    from accounti.api import seiten
    from accounti.api.registry import Navigationspunkt

    welt = webwelt(tmp_path)
    welt.person("jan", Rolle.BETRACHTER)
    app_punkte = navigation(routermodule(seiten))
    assert ("Übersicht", "/") in [(p.titel, p.pfad) for p in app_punkte]
    client = welt.client()
    client.app.state.navigation = [
        *app_punkte,
        Navigationspunkt("Nur Buchhaltung", "/geheim", Recht.BUCHEN),
    ]
    welt.anmelden(client, "jan")
    seite = client.get("/").text
    assert 'href="/freigaben"' in seite
    assert "/geheim" not in seite


def test_vorlagen_escapen(tmp_path):
    from accounti.db.repo_auth import speichere_benutzer

    welt = webwelt(tmp_path)
    p = welt.person("jan", Rolle.BETRACHTER)

    with welt.system() as s:
        speichere_benutzer(
            s, p.benutzer.model_copy(update={"anzeigename": "<script>x()</script>"})
        )
        s.commit()
    client = welt.client()
    welt.anmelden(client, "jan")
    seite = client.get("/").text
    assert "<script>x()</script>" not in seite
    assert "&lt;script&gt;" in seite
