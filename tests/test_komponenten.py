"""Komponenten der Oberfläche als Jinja-Makros (Spec 10c A92–A95, A108–A111; Plan P1
Schritt 4, Aussehen nach L4). Jedes Makro wird über eine kleine Vorlage gerendert."""

from __future__ import annotations

import re

import pytest
from jinja2 import TemplateError

from accounti.api.vorlagen import UMGEBUNG


def render(quelle: str, **werte: object) -> str:
    vorlage = UMGEBUNG.from_string(
        '{% import "_komponenten.html" as k with context %}' + quelle
    )
    return vorlage.render(sprache=werte.pop("sprache", "de"), **werte)


def nur(html: str, tag: str) -> list[str]:
    """Alle öffnenden Tags ``<tag …>`` eines Ausschnitts."""
    return re.findall(rf"<{tag}\b[^>]*>", html)


# --- Knopf, Linkknopf, Attribute ----------------------------------------------------


def test_knopf_arten_groessen_zustaende():
    html = render('{{ k.knopf("Freigeben") }}')
    assert html.startswith('<button type="submit" class="knopf knopf-primaer">')
    assert html.endswith(">Freigeben</button>")
    for art in ("primaer", "sekundaer", "still", "gefaehrlich"):
        assert f"knopf-{art}" in render(f'{{{{ k.knopf("x", art="{art}") }}}}')
    assert 'class="knopf knopf-sekundaer knopf-klein knopf-breit"' in render(
        '{{ k.knopf("x", art="sekundaer", groesse="klein", breit=true) }}'
    )
    assert "knopf-gross" in render('{{ k.knopf("x", groesse="gross") }}')
    aus = render('{{ k.knopf("x", deaktiviert=true) }}')
    assert " disabled" in aus and "aria-disabled" not in aus
    laedt = render('{{ k.knopf("Speichert …", laedt=true) }}')
    assert 'aria-busy="true"' in laedt and "#loader-circle" in laedt
    assert "Speichert …</button>" in laedt
    mit = render(
        '{{ k.knopf("Weiter", symbol="arrow-right", taste="f", typ="button") }}'
    )
    assert 'type="button"' in mit and "#arrow-right" in mit and "<kbd>f</kbd>" in mit
    link = render('{{ k.linkknopf("Durcharbeiten", "/pruefen?a=1&b=2", taste="j") }}')
    assert link.startswith(
        '<a class="knopf knopf-sekundaer" href="/pruefen?a=1&amp;b=2">'
    )
    for falsch in ('art="bunt"', 'groesse="riesig"', 'typ="image"'):
        with pytest.raises(TemplateError):
            render(f'{{{{ k.knopf("x", {falsch}) }}}}')


def test_attribute_nur_aus_positivliste():
    html = render(
        '{{ k.knopf("x", attribute={"hx-post": "/a?b=1&c=\\"2\\"", "data-taste": "f",'
        ' "aria-controls": "liste", "formnovalidate": true, "hx-vals": none}) }}'
    )
    assert 'hx-post="/a?b=1&amp;c=&#34;2&#34;"' in html
    assert 'data-taste="f"' in html and 'aria-controls="liste"' in html
    assert " formnovalidate" in html and "hx-vals" not in html
    for name in ("onclick", "style", "href", "class", "hx-on:click", "data-x y", "a>b"):
        with pytest.raises((ValueError, TemplateError)):
            render("{{ k.knopf('x', attribute={name: 'y'}) }}", name=name)
        with pytest.raises((ValueError, TemplateError)):
            render("{{ k.linkknopf('x', '/', attribute={name: 'y'}) }}", name=name)


def test_name_direkt_vor_value():
    html = render('{{ k.knopf("Speichern", name="aktion", wert="weiter") }}')
    assert 'name="aktion" value="weiter"' in html
    assert 'name="leer" value=""' in render('{{ k.knopf("x", name="leer") }}')


# --- Status und Sicherheit ----------------------------------------------------------


def test_status_und_sicherheit_wort_und_symbol():
    zeichen = {
        "ok": "check",
        "info": "info",
        "warn": "triangle-alert",
        "fehler": "triangle-alert",
    }
    for art, symbol in zeichen.items():
        html = render(f'{{{{ k.status("{art}", "Wort") }}}}')
        assert html.startswith(f'<span class="status status-{art}">'), art
        assert f"#{symbol}" in html and "symbol-14 symbol-kraeftig" in html
        assert html.endswith("Wort</span>")
    with pytest.raises(TemplateError):
        render('{{ k.status("bunt", "x") }}')
    for stufe in ("niedrig", "mittel", "hoch"):
        html = render(f'{{{{ k.sicherheit("{stufe}") }}}}')
        assert f"sicherheit-{stufe}" in html
        assert f"Sicherheit: {stufe}" in html
        kaestchen = re.search(r'<span class="sicherheit-kaestchen"[^>]*>', html)
        assert kaestchen and 'aria-hidden="true"' in kaestchen.group(0)
        assert html.count("<span></span>") == 3
    assert "Sicherheit: mittel · KI" in render('{{ k.sicherheit("mittel", "KI") }}')
    assert "sicherheit-klein" in render('{{ k.sicherheit("hoch", klein=true) }}')
    assert "Confidence: high" in render('{{ k.sicherheit("hoch") }}', sprache="en")


def test_zaehler_betont_und_beschriftung():
    html = render('{{ k.zaehler(12, "offen") }}')
    assert (
        html == '<span class="zaehler">12<span class="unsichtbar"> offen</span></span>'
    )
    assert 'class="zaehler zaehler-betont"' in render(
        '{{ k.zaehler(3, "x", betont=true) }}'
    )
