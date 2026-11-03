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
