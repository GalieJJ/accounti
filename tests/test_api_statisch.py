"""Statische Dateien und CSP-Regeln der Oberfläche (Baustein 10b, Paket 2).

htmx liegt lokal und unverändert bei (Prüfsumme), ist ohne ``eval``, ohne Skripte aus
Antworten und ohne Indikatorstil konfiguriert; keine Seite und keine Vorlage enthält
Inline-Skripte, ``<style>``, ``style=`` oder ``on…=``-Attribute (CSP aus 10a bleibt);
eigene Dateien tragen einen Versionsanhang (``/statisch`` wird zwischengespeichert).
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

import pytest

from accounti import __version__
from accounti.models.auth import Rolle
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes

STATISCH = Path(__file__).resolve().parents[1] / "src" / "accounti" / "api" / "statisch"
VORLAGEN = STATISCH.parent / "vorlagen"
HTMX_SHA256 = "d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717"


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER)
    w.rolle("jan", "a", Rolle.FREIGEBER)
    return w


def seiten_html(welt) -> list[str]:  # noqa: ANN001
    """Jede GET-Seite ohne Pfadparameter (angemeldet) plus die Anmeldeseite."""
    client = welt.angemeldet("jan")
    from accounti.api.app import erstelle_app

    pfade = sorted(
        {
            e.pfad
            for e in erstelle_app(welt.dienste).state.endpunkte
            if e.methode == "GET"
            and "{" not in e.pfad
            and not e.pfad.startswith("/api")
        }
    )
    texte = [welt.client().get("/anmelden").text]
    for pfad in pfade:
        r = client.get(pfad)
        assert r.status_code == 200, (pfad, r.status_code)
        texte.append(r.text)
    return texte


def test_htmx_pruefsumme_und_lizenz():
    datei = STATISCH / "htmx-2.0.11.min.js"
    assert hashlib.sha256(datei.read_bytes()).hexdigest() == HTMX_SHA256
    lizenz = (STATISCH / "LIZENZ-htmx.txt").read_text(encoding="utf-8")
    assert "Zero-Clause BSD" in lizenz and HTMX_SHA256 in lizenz
    assert "2.0.11" in lizenz
    dritte = (STATISCH.parents[3] / "THIRD-PARTY.md").read_text(encoding="utf-8")
    assert "htmx 2.0.11" in dritte and "0BSD" in dritte


def test_htmx_wird_ausgeliefert(welt):
    r = welt.client().get(f"/statisch/htmx-2.0.11.min.js?v={__version__}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        ("text/javascript", "application/javascript")
    )
    assert r.headers["x-content-type-options"] == "nosniff"
    assert hashlib.sha256(r.content).hexdigest() == HTMX_SHA256


def test_htmx_konfiguration(welt):
    seite = welt.client().get("/anmelden").text
    treffer = re.search(r'<meta name="htmx-config" content="([^"]*)">', seite)
    assert treffer, "htmx-config fehlt"
    konfig = json.loads(html.unescape(treffer.group(1)))
    assert konfig["allowEval"] is False and konfig["allowScriptTags"] is False
    assert konfig["includeIndicatorStyles"] is False
    assert konfig["historyCacheSize"] == 0 and konfig["selfRequestsOnly"] is True
    # htmx überträgt beim Einschwingen kein ``style`` (CSP style-src 'self')
    assert "style" not in konfig["attributesToSettle"]
    regeln = konfig["responseHandling"]
    codes = [r["code"] for r in regeln]
    eingetauscht = regeln[codes.index("409|422")]
    assert eingetauscht == {"code": "409|422", "swap": True, "error": False}
    assert codes.index("409|422") < codes.index("[45]..")
    assert regeln[codes.index("[45]..")]["swap"] is False
    assert 'hx-history="false"' in seite


INLINE = [
    (re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.I), "Inline-Skript"),
    (re.compile(r"<style\b", re.I), "<style>"),
    (re.compile(r"\sstyle\s*=", re.I), "style="),
    (re.compile(r"\son[a-z]+\s*=", re.I), "on…="),
    (re.compile(r"\bhx-on[:-]", re.I), "hx-on"),
    (re.compile(r"\bjs:", re.I), "js:"),
    (re.compile(r"javascript:", re.I), "javascript:"),
]


def fachseiten_html(tmp_path) -> list[str]:  # noqa: ANN001
    """Arbeitsfläche, Buchung und Beleg mit Inhalt (Seiten mit Pfadparametern)."""
    from tests.pruefen_hilfe import pdf, queuewelt

    (tmp_path / "queue").mkdir(exist_ok=True)
    qw = queuewelt(tmp_path / "queue")
    beleg = qw.beleg(pdf())
    b = qw.unsicher()
    mit_beleg = qw.buchung(beleg_id=beleg.id)
    client = qw.web.angemeldet("jan")
    texte = []
    for pfad in (
        f"/pruefen/{b.id}",
        f"/pruefen/{mit_beleg.id}",
        f"/buchungen/{b.id}",
        f"/belege/{beleg.id}",
        "/pruefen/regeln",
    ):
        r = client.get(pfad)
        assert r.status_code == 200, pfad
        texte.append(r.text)
    return texte


def test_keine_inline_skripte_stile_oder_ereignisattribute(welt, tmp_path):
    quellen = {str(p): p.read_text(encoding="utf-8") for p in VORLAGEN.rglob("*.html")}
    quellen |= {f"seite {i}": t for i, t in enumerate(seiten_html(welt))}
    quellen |= {f"fach {i}": t for i, t in enumerate(fachseiten_html(tmp_path))}
    for name, text in quellen.items():
        for muster, art in INLINE:
            assert not muster.search(text), (name, art, muster.search(text))


def test_eigenes_skript_ohne_eval_und_innerhtml():
    for datei in STATISCH.glob("*.js"):
        if datei.name.startswith("htmx-"):
            continue
        text = datei.read_text(encoding="utf-8")
        for verboten in (
            "eval(",
            "innerHTML",
            "outerHTML",
            "new Function",
            "document.write",
            "insertAdjacentHTML",
            'setTimeout("',
            'setInterval("',
        ):
            assert verboten not in text, (datei.name, verboten)


def test_eigene_dateien_mit_versionsanhang(welt):
    for text in seiten_html(welt):
        verweise = re.findall(r'(?:src|href)="(/statisch/[^"]+)"', text)
        assert verweise, "keine statischen Dateien eingebunden"
        for verweis in verweise:
            # Symbole: ``<use href="/statisch/symbole.svg?v=…#name">`` — versioniert ist
            # der Teil vor dem Fragment (Plan P1, Schritt 2)
            datei, _, fragment = verweis.partition("#")
            assert datei.endswith(f"?v={__version__}"), verweis
            assert not fragment or datei.startswith("/statisch/symbole.svg?"), verweis
        assert f"/statisch/accounti.css?v={__version__}" in text


def test_tasten_in_markup_und_skript_gleich(tmp_path):
    """Jede Taste der Prüfseite ist im Skript bekannt — und umgekehrt."""
    texte = fachseiten_html(tmp_path)
    im_markup = set(re.findall(r'data-taste="([^"]+)"', "".join(texte)))
    skript = (STATISCH / "pruefen.js").read_text(encoding="utf-8")
    liste = re.search(r"var TASTEN = \[([^\]]*)\]", skript)
    assert liste, "TASTEN fehlt"
    im_skript = set(re.findall(r'"([^"]+)"', liste.group(1)))
    assert im_markup | {"?"} == im_skript, (im_markup, im_skript)
    # Strg+Enter löst den Hauptknopf aus, nicht den ersten Absendeknopf
    assert 'querySelector("button.hauptknopf")' in skript
    hilfe = re.search(r'<details id="tastenhilfe".*?</details>', texte[0], re.S)
    assert hilfe is not None
    for taste in im_skript:
        assert f"<kbd>{taste}</kbd>" in hilfe.group(0), taste
