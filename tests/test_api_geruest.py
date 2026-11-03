"""Gerüst der Oberfläche (Spec 10c A3–A7, A89; Plan P1 Schritte 1 und 7)."""

from __future__ import annotations

import re

import pytest

from accounti.models.auth import Rolle
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER)
    return w


def _html_kopf(text: str) -> str:
    return text[: text.index("</head>")]


def test_html_traegt_theme_und_color_scheme(welt):
    """E16, A89: ``data-theme`` an ``<html>`` (bis zur Wahl am Benutzer „auto“), dazu
    ``<meta name="color-scheme">`` passend zur Wahl — vor dem Laden der CSS-Datei
    blitzt nichts auf — und ``viewport-fit=cover`` für die Safe Area."""
    for client, pfad in ((welt.client(), "/anmelden"), (welt.angemeldet("jan"), "/")):
        r = client.get(pfad)
        assert r.status_code == 200
        assert re.search(r'<html lang="de" data-theme="auto">', r.text)
        kopf = _html_kopf(r.text)
        assert '<meta name="color-scheme" content="light dark">' in kopf
        viewport = re.search(r'<meta name="viewport" content="([^"]+)">', kopf)
        assert viewport and "viewport-fit=cover" in viewport.group(1)
        assert "width=device-width" in viewport.group(1)


# --- Kennfarbe und Monogramm (Regeln; Plan P1 Schritt 8, vorgezogen) ----------------


def test_kennfarbe_stabil_je_kuerzel():
    from accounti.api.geruest import kennfarben

    eins = kennfarben(["muster", "tochter", "a"])
    assert eins == kennfarben(["tochter", "a", "muster"])  # Reihenfolge egal
    assert set(eins) == {"muster", "tochter", "a"}
    assert all(1 <= f <= 6 for f in eins.values())


def test_kennfarben_ohne_dopplung_bis_sechs():
    from accounti.api.geruest import kennfarben

    for n in range(1, 7):
        farben = kennfarben([f"g{i}" for i in range(n)])
        assert len(set(farben.values())) == n, farben
    sieben = kennfarben([f"g{i}" for i in range(7)])
    assert set(sieben.values()) == {1, 2, 3, 4, 5, 6}  # ab sieben wiederholt


def test_gewaehlte_farbe_geht_vor():
    from accounti.api.geruest import kennfarben

    frei = kennfarben(["a", "b"])
    farben = kennfarben(["a", "b"], gewaehlt={"b": frei["a"]})
    assert farben["b"] == frei["a"] and farben["a"] != farben["b"]


def test_monogramm_aus_dem_namen():
    from accounti.api.geruest import monogramme

    assert monogramme(
        {
            "gd": "Galerie Demo GmbH",
            "ku": "Kunsthandel UG",
            "b": "Beta Rahmen KG",
            "x": "Atelier",
            "u": "über-Galerie",
        }
    ) == {"gd": "GD", "ku": "KU", "b": "BR", "x": "AT", "u": "ÜG"}


def test_monogramm_eindeutig_je_registry():
    from accounti.api.geruest import monogramme

    # vergeben wird in alphabetischer Reihenfolge der Kürzel: a, mu, muster, z
    m = monogramme(
        {
            "muster": "Galerie Dorn KG",  # GD und MU vergeben → G2
            "a": "Galerie Demo GmbH",  # GD
            "z": "Grün Dunkel",  # GD vergeben, Kürzel zu kurz, G2 vergeben → G3
            "mu": "Galerie Dach OHG",  # GD vergeben → Registry-Kürzel MU
        }
    )
    assert m == {"a": "GD", "mu": "MU", "muster": "G2", "z": "G3"}
    assert all(len(w) == 2 and w == w.upper() for w in m.values())


def test_marken_aus_registry(welt):
    from accounti.api.geruest import marken

    alle = marken(welt.dienste.gesellschaften)
    assert {k: (m.name, m.monogramm) for k, m in alle.items()} == {
        "a": ("Alpha Papier GmbH", "AP"),
        "b": ("Beta Rahmen KG", "BR"),
    }
    assert alle["a"].farbe != alle["b"].farbe
