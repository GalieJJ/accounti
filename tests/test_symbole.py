"""Symbole als lokales SVG-Sprite aus lucide-static 1.55.0 (Spec 10c A96, A98, A99;
Plan P1 Schritt 2 und L6)."""

from __future__ import annotations

import importlib.util
import re
import sys

import pytest

from accounti import __version__
from tests.design_hilfe import CSS, STATISCH, WURZEL, css, stilregeln

SPRITE = STATISCH / "symbole.svg"
LIZENZ = STATISCH / "LIZENZ-lucide.txt"


def _erzeuger():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location(
        "symbole_erzeuger", WURZEL / "scripts" / "symbole.py"
    )
    assert spec and spec.loader
    modul = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    return modul


ERZEUGER = _erzeuger()

BEISPIEL = """<!-- @license lucide-static v1.55.0 - ISC -->
<svg
  class="lucide lucide-{name}"
  xmlns="http://www.w3.org/2000/svg"
  width="24"
  height="24"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
>
{formen}
</svg>
"""


def test_erzeuger_wandelt_symbol(tmp_path):
    paket = tmp_path / "package"
    (paket / "icons").mkdir(parents=True)
    formen = {
        "check": '  <path d="M20 6 9 17l-5-5" />',
        "info": '  <circle cx="12" cy="12" r="10" />\n  <path d="M12 16v-4" />',
    }
    for name, inhalt in formen.items():
        (paket / "icons" / f"{name}.svg").write_text(
            BEISPIEL.format(name=name, formen=inhalt), encoding="utf-8"
        )
    sprite = ERZEUGER.sprite(paket, ("check", "info"))
    assert (
        '<symbol id="check" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></symbol>'
        in (sprite)
    )
    assert (
        '<symbol id="info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/>'
        '<path d="M12 16v-4"/></symbol>'
    ) in sprite
    for wurzelattribut in ("stroke-width", "width=", "class=", "fill=", "lucide-"):
        assert wurzelattribut not in sprite.split("-->", 1)[1], wurzelattribut
    # Unerwartetes scheitert, statt still ins Sprite zu gelangen
    for falsch in (
        '<path d="M1 1" onload="x()" />',
        '<use href="#a" />',
        '<path d="M1 1" style="fill:red" />',
        "<script>alert(1)</script>",
    ):
        (paket / "icons" / "x.svg").write_text(
            BEISPIEL.format(name="x", formen=falsch), encoding="utf-8"
        )
        with pytest.raises(ERZEUGER.SymbolError):
            ERZEUGER.sprite(paket, ("x",))


def test_erzeuger_prueft_version_und_integritaet(tmp_path):
    paket = tmp_path / "package"
    paket.mkdir()
    (paket / "package.json").write_text('{"version": "1.61.0"}', encoding="utf-8")
    with pytest.raises(ERZEUGER.SymbolError, match="1.61.0"):
        ERZEUGER.pruefe_paket(paket, None)
    (paket / "package.json").write_text('{"version": "1.55.0"}', encoding="utf-8")
    falsch = tmp_path / "lucide-static-1.55.0.tgz"
    falsch.write_bytes(b"kein Tarball")
    with pytest.raises(ERZEUGER.SymbolError, match="Integrität"):
        ERZEUGER.pruefe_paket(paket, falsch)


def _ids() -> list[str]:
    return re.findall(r'<symbol id="([^"]+)"', SPRITE.read_text(encoding="utf-8"))


def test_sprite_budget_und_ids():
    assert SPRITE.stat().st_size <= 15_360
    assert _ids() == list(ERZEUGER.SYMBOLE)
    assert len(ERZEUGER.SYMBOLE) == 36 == len(set(ERZEUGER.SYMBOLE))


def test_sprite_ohne_skript_und_verweise():
    text = SPRITE.read_text(encoding="utf-8")
    assert (
        re.search(r"<script|\son\w+=|href=|style=|url\(|<foreignObject", text) is None
    )
    assert re.findall(r"https?://[^\"' ]+", text) == ["http://www.w3.org/2000/svg"]


def test_lizenz_isc_und_mit_beigelegt():
    text = LIZENZ.read_text(encoding="utf-8")
    for teil in (
        "ISC License",
        "Cole Bemis",
        "The MIT License",
        "1.55.0",
        ERZEUGER.INTEGRITAET,
    ):
        assert teil in text, teil
    for neu, alt in {
        "triangle-alert": "alert-triangle",
        "circle-help": "help-circle",
        "circle-x": "x-circle",
        "circle-alert": "alert-circle",
    }.items():
        assert f"{neu} ← {alt}" in text
    assert "(MIT-Teil unten, 22)" in text
    dritte = (WURZEL / "THIRD-PARTY.md").read_text(encoding="utf-8")
    assert "lucide-static 1.55.0" in dritte and "LIZENZ-lucide.txt" in dritte


def test_symbole_wie_leinwand():
    """Fassung 4 (L6): die Formen der Leinwand für Navigation, Status, Hinweis,
    Feldmeldung, gesperrt und Vorschlag; die alten Namen aus Fassung 3 sind weg."""
    ids = set(_ids())
    leinwand = {
        "house",
        "square-check-big",
        "file-text",
        "calendar",
        "chart-column",
        "shield-check",
        "settings",
        "menu",
        "circle-help",
        "check",
        "info",
        "triangle-alert",
        "circle-x",
        "circle-alert",
        "lock",
        "arrow-right",
        "chevron-down",
        "chevron-right",
        "chevron-left",
        "external-link",
        "loader-circle",
    }
    assert leinwand <= ids
    entfallen = {
        "list-checks",
        "calculator",
        "stamp",
        "ellipsis",
        "gauge",
        "circle-user",
        "building-2",
        "circle-check",
    }
    assert not entfallen & ids


# --- Makro und symbol_url -----------------------------------------------------------


def _render(quelle: str) -> str:
    from accounti.api.vorlagen import UMGEBUNG

    vorlage = UMGEBUNG.from_string(
        '{% import "_komponenten.html" as k with context %}' + quelle
    )
    return vorlage.render(sprache="de")


def test_symbol_url_mit_versionsanhang():
    from accounti.api.symbole import symbol_url

    assert symbol_url("check") == f"/statisch/symbole.svg?v={__version__}#check"


def test_unbekanntes_symbol_scheitert():
    from accounti.api.symbole import symbol_url

    for name in ("stamp", "check#x", "../x", ""):
        with pytest.raises(ValueError):
            symbol_url(name)
    with pytest.raises(ValueError):
        _render('{{ k.symbol("gibt-es-nicht") }}')
    with pytest.raises(ValueError):
        _render('{{ k.symbol("check", groesse=17) }}')


def test_symbol_dekorativ_aria_hidden():
    html = _render('{{ k.symbol("check") }}')
    assert html == (
        '<svg class="symbol symbol-18" aria-hidden="true" focusable="false">'
        f'<use href="/statisch/symbole.svg?v={__version__}#check"></use></svg>'
    )


def test_symbol_mit_beschriftung_role_img():
    html = _render('{{ k.symbol("lock", beschriftung="gesperrt <b>") }}')
    assert 'role="img" aria-label="gesperrt &lt;b&gt;"' in html
    assert "aria-hidden" not in html


def test_symbol_groesse_und_strich_als_klasse():
    html = _render('{{ k.symbol("info", groesse=14, kraeftig=true) }}')
    assert 'class="symbol symbol-14 symbol-kraeftig"' in html
    assert re.search(r"\s(width|height|style|stroke-width)=", html) is None
    klassen = {
        k
        for s in stilregeln(css(CSS))
        for k in re.findall(r"\.(symbol-[\w-]+)", s.regel.kopf)
    }
    assert {f"symbol-{n}" for n in (14, 16, 18, 22, 28, 40)} | {
        "symbol-kraeftig"
    } <= klassen


def test_sprite_wird_ausgeliefert(tmp_path):
    """Das Sprite kommt aus /statisch (eigene Herkunft, ``default-src 'self'``)."""
    from tests.api_hilfe import webwelt

    r = webwelt(tmp_path).client().get(f"/statisch/symbole.svg?v={__version__}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.content == SPRITE.read_bytes()
