"""Musterseite ``/muster`` (Spec 10c A101, A92, AK51, AK58; Plan P1 Schritt 4, L9)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from accounti.models.auth import Rolle
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes

VORLAGEN = Path(__file__).resolve().parents[1] / "src" / "accounti" / "api" / "vorlagen"
HX = {"HX-Request": "true"}
ETIKETTEN = (
    "Farben",
    "Schrift",
    "Knöpfe",
    "Status und Sicherheit",
    "Felder",
    "Hinweise",
    "Tabelle und leerer Zustand",
)


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("leo", Rolle.BETRACHTER)
    return w


@pytest.fixture
def leo(welt):
    return welt.angemeldet("leo")


def _inhalt(html: str) -> str:
    """Der Inhalt der Musterseite (Block ``inhalt``) ohne Kopf und Navigation des
    Gerüsts."""
    anfang = html.index('<div class="muster">')
    return html[anfang : html.index("</main>", anfang)]


def _rahmen(html: str) -> list[str]:
    teile = re.split(r'<section class="thema(?: thema-(?:hell|dunkel))?"', html)
    return teile[1:]


def test_fragment_mit_hx_request(leo):
    teil = leo.get("/muster", headers=HX)
    assert teil.status_code == 200
    assert "<html" not in teil.text and 'class="kopfleiste' not in teil.text
    assert 'class="seitenleiste"' not in teil.text.split("muster-rahmen")[0]
    assert "<h1>Bausteine</h1>" in teil.text
    assert 'class="knopf knopf-primaer"' in teil.text  # Makros gerendert
    assert teil.headers["Vary"] == "Accept-Language"
    verlauf = leo.get("/muster", headers={**HX, "HX-History-Restore-Request": "true"})
    assert "<html" in verlauf.text
    ganz = leo.get("/muster")
    assert "<html" in ganz.text and "<h1>Bausteine</h1>" in ganz.text


def test_jedes_makro_auf_der_musterseite():
    """AK51: jedes öffentliche Makro aus ``_komponenten.html`` steht auf der Seite."""
    makros = set(
        re.findall(
            r"{%-?\s*macro\s+([a-z]\w*)\(",
            (VORLAGEN / "_komponenten.html").read_text(encoding="utf-8"),
        )
    )
    muster = (VORLAGEN / "muster.html").read_text(encoding="utf-8")
    aufgerufen = set(re.findall(r"\bk\.([a-z]\w*)\(", muster))
    assert makros, "keine Makros gefunden"
    assert makros - aufgerufen == set()
    assert aufgerufen - makros == set()


def test_ohne_parameter_hell_und_dunkel_nebeneinander(leo):
    html = leo.get("/muster").text
    assert html.count('<section class="thema thema-hell"') == 1
    assert html.count('<section class="thema thema-dunkel"') == 1
    hell, dunkel = _rahmen(_inhalt(html))
    for rahmen in (hell, dunkel):
        stellen = [rahmen.index(f">{e}</h3>") for e in ETIKETTEN]
        assert stellen == sorted(stellen)
        for text in (
            "Fehler:</strong> Die PLZ hat 5 Ziffern.",
            "Die PLZ hat 5 Ziffern.",
            "652,31 €",
            "Nichts zu prüfen.",
            "Nächster Bankabruf: heute 14:00.",
            "accounti berät nicht steuerlich.",
            "Code falsch oder schon benutzt.",
            "freigegeben",
            "überfällig",
            "Sicherheit: mittel",
        ):
            assert text in rahmen, text
    assert "Ruhig, hell und dunkel, Systemschrift" in html
    assert '<html lang="de" data-theme="auto">' in html


def test_theme_parameter_zeigt_einen_rahmen(leo):
    for wahl, schema in (("dunkel", "dark"), ("hell", "light"), ("auto", "light dark")):
        html = leo.get(f"/muster?theme={wahl}").text
        assert f'<html lang="de" data-theme="{wahl}">' in html
        assert f'<meta name="color-scheme" content="{schema}">' in html
        assert html.count('<section class="thema"') == 1
        assert "thema-hell" not in _inhalt(html) and "thema-dunkel" not in _inhalt(html)
        assert (
            'aria-current="page">'
            + {
                "dunkel": "dunkel",
                "hell": "hell",
                "auto": "automatisch",
            }[wahl]
            in html
        )


def test_theme_parameter_nur_bekannte_werte(leo):
    r = leo.get("/muster?theme=%3Cxyz%3E")
    assert r.status_code == 200
    assert "xyz" not in r.text
    assert '<html lang="de" data-theme="auto">' in r.text
    assert r.text.count('<section class="thema thema-') == 2


def test_ids_eindeutig_trotz_zwei_rahmen(leo):
    for pfad in ("/muster", "/muster?theme=dunkel"):
        html = leo.get(pfad).text
        ids = re.findall(r'\sid="([^"]+)"', html)
        doppelt = [i for i, n in Counter(ids).items() if n > 1]
        assert doppelt == [], (pfad, doppelt)
        verweise = re.findall(r'\s(?:for|aria-labelledby)="([^"]+)"', html)
        for liste in re.findall(r'\saria-describedby="([^"]+)"', html):
            verweise += liste.split()
        verweise += re.findall(r'<a href="#([^"]+)">', html)
        assert set(verweise) - set(ids) == set(), pfad
    beide = leo.get("/muster").text
    assert 'id="hell-iban"' in beide and 'id="dunkel-iban"' in beide


def test_zustaende_gezeigt(leo):
    html = _inhalt(leo.get("/muster?theme=hell").text)
    for merkmal in (
        " disabled",  # deaktiviert
        'aria-busy="true"',  # lädt
        'class="htmx-request"',  # Ladeanzeige im Rahmen einer Anfrage
        'aria-invalid="true"',  # Fehler
        'aria-current="page"',  # aktiv
        'aria-current="step"',
        "zeige-fokus",  # Fokus ohne echten Fokus
        "zeile-gewaehlt",
        " checked",
        "feld-warnung",
        "feld-meldung-ok",
        "layout-zweispaltig",
        "layout-karten",
        "layout-einstellungen",
        "layout-formular",
    ):
        assert merkmal in html, merkmal


def test_verlangt_anmeldung_und_steht_nicht_in_der_navigation(welt, leo):
    for pfad in ("/muster", "/muster/beispiel"):
        r = welt.client().get(pfad, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/anmelden")
    assert 'href="/muster"' not in leo.get("/").text
    app = welt.client().app
    punkte = [p.pfad for p in app.state.navigation]  # type: ignore[attr-defined]
    assert "/muster" not in punkte


def test_keine_daten_der_gesellschaft(welt, leo):
    inhalt = _inhalt(leo.get("/muster").text)
    for g in welt.dienste.gesellschaften.values():
        assert g.name not in inhalt
        assert f'data-gesellschaft="{g.kuerzel}"' not in inhalt
    teil = leo.get("/muster", headers=HX).text
    assert all(g.name not in teil for g in welt.dienste.gesellschaften.values())


def test_beispielfragment_mit_data_fokus(leo):
    r = leo.get("/muster/beispiel", headers=HX)
    assert r.status_code == 200 and "<html" not in r.text
    assert len(re.findall(r"\sdata-fokus[\s>=]", r.text)) == 1
    ohne = leo.get("/muster/beispiel", follow_redirects=False)
    assert ohne.status_code == 303 and ohne.headers["location"] == "/muster#austausch"
    seite = leo.get("/muster").text
    assert 'id="austausch"' in seite and 'hx-get="/muster/beispiel"' in seite
    assert 'hx-target="#austausch-ziel"' in seite and 'id="austausch-ziel"' in seite
