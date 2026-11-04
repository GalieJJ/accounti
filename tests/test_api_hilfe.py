"""Hilfe je Bereich (Spec 10c A8, AK47, AK57; Plan P1, Schritt 10)."""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from accounti.api import seiten
from accounti.api.registry import Bereich, Navigationspunkt, navigation, routermodule
from accounti.i18n import N_
from accounti.models.auth import Recht, Rolle
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes

HX = {"HX-Request": "true"}
SPEC = (
    Path(__file__).resolve().parents[1]
    / "docs/specs/2026-10-26-oberflaeche-einrichtung.md"
)


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER)
    return w


def _text(seite: str) -> str:
    inhalt = seite[seite.index('<main id="inhalt"') : seite.index("</main>")]
    return html.unescape(re.sub(r"<[^>]+>", " ", inhalt))


def test_jeder_bereich_hat_eine_hilfeseite(welt):
    from accounti.api.hilfe_inhalt import HILFE, Hilfethema

    bereiche = {p.bereich for p in navigation(routermodule(seiten))}
    assert bereiche == {Bereich.UEBERSICHT, Bereich.PRUEFEN, Bereich.FREIGABEN}
    client = welt.client()
    for bereich in bereiche:
        assert Hilfethema(bereich.value) in HILFE, bereich
        r = client.get(f"/hilfe/{bereich.value}")
        assert r.status_code == 200, bereich
        assert r.text.count("<h1") == 1
    for thema in ("anmeldung", "konto"):
        assert client.get(f"/hilfe/{thema}").status_code == 200, thema


def test_fehlende_hilfe_wird_gemeldet():
    from accounti.api.hilfe_inhalt import fehlende_hilfe

    stubs = [
        Navigationspunkt(N_("Belege"), "/belege", Bereich.BELEGE, "file-text"),
        Navigationspunkt(N_("Steuern"), "/steuern", Bereich.STEUERN, "calendar"),
        Navigationspunkt(
            N_("Auswertungen"), "/a", Bereich.AUSWERTUNGEN, "chart-column"
        ),
        Navigationspunkt(
            N_("Einstellungen"),
            "/e",
            Bereich.EINSTELLUNGEN,
            "settings",
            Recht.VERWALTEN,
        ),
    ]
    punkte = [*navigation(routermodule(seiten)), *stubs]
    assert fehlende_hilfe(punkte) == [
        Bereich.BELEGE,
        Bereich.STEUERN,
        Bereich.AUSWERTUNGEN,
        Bereich.EINSTELLUNGEN,
    ]
    assert fehlende_hilfe(navigation(routermodule(seiten))) == []


def test_ohne_anmeldung_ohne_daten_der_gesellschaft(welt):
    client = welt.client()
    for pfad in ("/hilfe", "/hilfe/pruefen", "/hilfe/anmeldung", "/hilfe/freigaben"):
        r = client.get(pfad)
        assert r.status_code == 200, pfad
        assert '<body class="schlicht"' in r.text, pfad
        assert 'class="seitenleiste"' not in r.text
        assert "Alpha Papier" not in r.text and "Beta Rahmen" not in r.text
        assert "A-RE-1" not in r.text


def test_angemeldet_mit_geruest(welt):
    r = welt.angemeldet("jan").get("/hilfe/pruefen")
    assert r.status_code == 200
    assert '<nav class="seitenleiste"' in r.text and 'data-gesellschaft="a"' in r.text
    assert "<title>Hilfe: Prüfen · Alpha Papier GmbH · accounti</title>" in r.text
    assert '<a class="kopf-hilfe" href="/hilfe">' in r.text  # Hilfe kein Bereich


def test_keine_links_auf_fremde_hosts(welt):
    from accounti.api.hilfe_inhalt import HILFE

    client = welt.angemeldet("jan")
    for pfad in ["/hilfe", *(f"/hilfe/{t.value}" for t in HILFE)]:
        seite = client.get(pfad).text
        for ziel in re.findall(r'(?:href|src|action)="([^"]*)"', seite):
            assert ziel.startswith(("/", "#")) and not ziel.startswith("//"), (
                pfad,
                ziel,
            )


def _anhang_b() -> list[str]:
    text = SPEC.read_text(encoding="utf-8")
    teil = text[text.index("## Anhang B") : text.index("## Anhang C")]
    zeilen = [z for z in teil.splitlines() if z.startswith("| ")][1:]
    return [z.split("|")[1].strip() for z in zeilen]


def test_begriffe_aus_anhang_b(welt):
    """AK57: jeder Begriff aus Anhang B steht auf /hilfe — klare Sprache, Fachbegriff,
    Erklärung, in beiden Sprachen."""
    from accounti.api.hilfe_inhalt import BEGRIFFE

    zeilen = _anhang_b()
    assert len(zeilen) == 17
    # „%“ steht in den msgids als „%%“ (Newstyle-gettext formatiert)
    assert [b.fach.replace("%%", "%") for b in BEGRIFFE] == zeilen
    client = welt.client()
    seite = _text(client.get("/hilfe").text)
    englisch = _text(client.get("/hilfe", headers={"Accept-Language": "en"}).text)
    for b in BEGRIFFE:
        for teil in (b.klar, b.fach, b.erklaerung):
            text = " ".join(teil.replace("%%", "%").split())
            assert text in " ".join(seite.split()), teil
    assert "Looks right – approve" in englisch and "Passt – freigeben" not in englisch


def test_tasten_aus_einer_quelle(welt):
    from accounti.api.hilfe_inhalt import HILFE, TASTEN_PRUEFEN, Hilfethema

    assert HILFE[Hilfethema.PRUEFEN].tasten == TASTEN_PRUEFEN
    seite = welt.client().get("/hilfe/pruefen").text
    for taste, text in TASTEN_PRUEFEN:
        assert f"<kbd>{taste}</kbd>" in seite and text in html.unescape(seite), taste


def test_unbekanntes_thema_404(welt):
    client = welt.client()
    for pfad in ("/hilfe/xyz", "/hilfe/belege", "/hilfe/EINSTELLUNGEN", "/hilfe/%00"):
        assert client.get(pfad).status_code == 404, pfad
    assert welt.angemeldet("jan").get("/hilfe/belege").status_code == 404


def test_abschnitt_zahlungslauf(welt):
    seite = welt.client().get("/hilfe/freigaben").text
    abschnitt = re.search(r'<section id="zahlungslauf".*?</section>', seite, re.S)
    assert abschnitt and "accounti zahlung vorschlag" in abschnitt.group(0)


def test_hilfe_fragment_mit_hx_request(welt):
    client = welt.angemeldet("jan")
    for pfad in ("/hilfe", "/hilfe/pruefen"):
        teil = client.get(pfad, headers=HX)
        assert teil.status_code == 200 and "<html" not in teil.text, pfad
        assert "<h1>" in teil.text
        assert "<html" in client.get(pfad).text


def test_hilfe_bei_gesperrter_systemdatenbank_schlicht(welt, monkeypatch, caplog):
    from accounti.api import sitzung

    client = welt.angemeldet("jan")

    def gesperrt(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise OperationalError(
            "UPDATE auth_sitzungen …", {}, Exception("database is locked")
        )

    monkeypatch.setattr(sitzung, "_lade", gesperrt)
    r = client.get("/hilfe/pruefen")
    assert r.status_code == 200 and '<body class="schlicht"' in r.text
    assert "OperationalError" in caplog.text
    assert "database is locked" not in caplog.text and "UPDATE" not in caplog.text


def test_hilfe_link_im_kopf_je_bereich(welt):
    client = welt.angemeldet("jan")
    for pfad, ziel in (
        ("/", "/hilfe/uebersicht"),
        ("/pruefen", "/hilfe/pruefen"),
        ("/pruefen/regeln", "/hilfe/pruefen"),
        ("/konto", "/hilfe/konto"),
        ("/menue", "/hilfe"),
    ):
        assert f'<a class="kopf-hilfe" href="{ziel}">' in client.get(pfad).text, pfad
    anmelden = welt.client().get("/anmelden").text
    assert '<a class="kopf-hilfe" href="/hilfe/anmeldung">' in anmelden
