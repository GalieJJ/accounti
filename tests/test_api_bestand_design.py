"""Querschnitt der Seiten im neuen Design (Spec 10c A121, AK49, AK52–AK54; Plan P1,
Schritt 12).

``UMGESTELLT`` nennt die Seiten (Routenvorlage wie in ``probe.json`` der Browserprobe),
die schon im neuen Design stehen; jede Seite kommt mit ihrem Commit hinein und macht die
Tests für sich erst rot, dann grün. Am Ende von Schritt 12 sind es alle HTML-Seiten der
Registry (``test_alle_seiten_im_querschnitt``). Geprüft wird das gerenderte HTML des
Bestands der Browserprobe (``tests.browserprobe_welt``) für den Benutzer ``alle`` (alle
Rollen, also jedes Formular), die Anmeldung ohne Sitzung.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

import pytest

from accounti.models import BuchungStatus
from accounti.models.auth import Rolle
from tests.api_hilfe import csrf, webwelt
from tests.auth_hilfe import billige_hashes
from tests.browserprobe_welt import baue
from tests.pruefen_hilfe import queuewelt, stand_aus

# Seiten im neuen Design (Routenvorlagen); Reihenfolge wie in Schritt 12
UMGESTELLT: list[str] = [
    "/anmelden",
    "/",
    "/freigaben",
    "/pruefen",
    "/pruefen/{buchung_id:uuid}",
    "/pruefen/regeln",
    "/buchungen/{buchung_id:uuid}",
    "/belege/{beleg_id:uuid}",
    # die neuen Seiten aus P1 halten dieselben Regeln
    "/menue",
    "/gesellschaft",
    "/konto",
    "/hilfe",
    "/hilfe/{thema}",
    "/muster",
]

# Seiten mit Codefeld (A109) und der Hauptaktion je Seite (AK49 I12): Text des Knopfs
CODESEITEN = {"/anmelden", "/freigaben", "/buchungen/{buchung_id:uuid}"}
HAUPTAKTION = {
    "/anmelden": ["Anmelden"],
    "/freigaben": ["Freigeben", "Werte freigeben"],
    "/pruefen/{buchung_id:uuid}": ["Freigeben"],
    "/buchungen/{buchung_id:uuid}": ["Korrigieren"],
}
# Listen mit leerem Zustand (AK54): Seite → Pfade mit leerer Datenbank
LEERE_LISTEN = {
    "/": ["/"],
    "/freigaben": ["/freigaben"],
    "/pruefen": ["/pruefen", "/pruefen?ansicht=zurueckgestellt"],
    "/pruefen/regeln": ["/pruefen/regeln"],
}
LEERE = {
    # leeres Element ohne Kinder in HTML
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


@dataclass(eq=False)
class Element:
    tag: str
    attrs: dict[str, str]
    eltern: tuple[Element, ...]
    text: list[str] = field(default_factory=list)

    @property
    def klassen(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def in_tag(self, tag: str) -> Element | None:
        for e in reversed(self.eltern):
            if e.tag == tag:
                return e
        return None

    @property
    def versteckt(self) -> bool:
        return any(
            "unsichtbar" in e.klassen or "hidden" in e.attrs
            for e in (*self.eltern, self)
        )


class Baum(HTMLParser):
    """Alle Elemente einer Seite mit ihren Vorfahren (für die Querschnittsprüfungen)."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.elemente: list[Element] = []
        self._stapel: list[Element] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        e = Element(tag, {k: v or "" for k, v in attrs}, tuple(self._stapel))
        self.elemente.append(e)
        if tag not in LEERE:
            self._stapel.append(e)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stapel) - 1, -1, -1):
            if self._stapel[i].tag == tag:
                del self._stapel[i:]
                return

    def handle_data(self, data: str) -> None:
        for e in self._stapel:
            e.text.append(data)

    def alle(self, tag: str) -> list[Element]:
        return [e for e in self.elemente if e.tag == tag]


def text(e: Element) -> str:
    return " ".join("".join(e.text).split())


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    billige_hashes(mp)
    try:
        yield baue(tmp_path_factory.mktemp("bestand") / "welt")
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def alle(probe):
    return probe.web.angemeldet("alle")


def pfad_von(probe, vorlage: str) -> str:  # noqa: ANN001
    (eintrag,) = [s for s in probe.seiten if s["vorlage"] == vorlage]
    return eintrag["pfad"]


def html_von(probe, alle, vorlage: str, anhang: str = "") -> str:  # noqa: ANN001
    client = probe.web.client() if vorlage == "/anmelden" else alle
    r = client.get(pfad_von(probe, vorlage) + anhang)
    assert r.status_code == 200, (vorlage, r.status_code)
    return r.text


def _codefelder(baum: Baum) -> list[Element]:
    return [e for e in baum.alle("input") if e.attrs.get("name") == "einmalcode"]


def _labels(baum: Baum) -> dict[str, list[Element]]:
    labels: dict[str, list[Element]] = {}
    for label in baum.alle("label"):
        labels.setdefault(label.attrs.get("for", ""), []).append(label)
    return labels


@pytest.mark.parametrize("vorlage", UMGESTELLT)
def test_codefelder_mit_sichtbarem_label_und_ein_feld(probe, alle, vorlage):
    """AK49 (I10), AK53: jedes Codefeld mit sichtbarem Label, eines je Formular."""
    baum = Baum(html_von(probe, alle, vorlage))
    felder = _codefelder(baum)
    if vorlage in CODESEITEN:
        assert felder, vorlage
    labels = _labels(baum)
    je_formular: dict[int, int] = {}
    for feld in felder:
        ident = feld.attrs.get("id")
        assert ident and "placeholder" not in feld.attrs, (vorlage, feld.attrs)
        assert "aria-label" not in feld.attrs, (vorlage, feld.attrs)
        sichtbar = [lb for lb in labels.get(ident, []) if not lb.versteckt]
        assert sichtbar, (vorlage, ident)
        # /muster zeigt beide Varianten; sonst ist Ziffern der Standard
        erlaubt = ("numeric", "text") if vorlage == "/muster" else ("numeric",)
        assert feld.attrs.get("inputmode") in erlaubt, (vorlage, ident)
        formular = feld.in_tag("form")
        if formular is None:  # Beispiele auf /muster stehen ohne Formular
            assert vorlage == "/muster", (vorlage, ident)
            continue
        je_formular[id(formular)] = je_formular.get(id(formular), 0) + 1
    assert all(n == 1 for n in je_formular.values()), (vorlage, je_formular)


@pytest.mark.parametrize("vorlage", [v for v in UMGESTELLT if v in HAUPTAKTION])
def test_hauptaktion_ist_primaerknopf(probe, alle, vorlage):
    """AK49 (I12): die Hauptaktion der Seite ist ein primärer Knopf."""
    baum = Baum(html_von(probe, alle, vorlage))
    knoepfe = baum.alle("button")
    for name in HAUPTAKTION[vorlage]:
        treffer = [k for k in knoepfe if text(k) in (name, f"{name}f", f"{name} f")]
        assert treffer, (vorlage, name, [text(k) for k in knoepfe])
        for knopf in treffer:
            assert "knopf-primaer" in knopf.klassen, (vorlage, name)


def test_hauptaktion_korrigieren_wenn_freigeben_gesperrt(tmp_path):
    """Ist Freigeben wegen der Prüfregel ausgeblendet, ist Korrigieren primär."""
    if "/pruefen/{buchung_id:uuid}" not in UMGESTELLT:
        pytest.skip("Arbeitsfläche noch nicht umgestellt")
    qw = queuewelt(tmp_path)
    b = qw.buchung(soll_konto="1800", haben_konto="1200", steuer_schluessel=9)
    baum = Baum(qw.web.angemeldet("jan").get(f"/pruefen/{b.id}").text)
    knoepfe = {text(e).split(" ")[0]: e for e in baum.alle("button")}
    assert "Freigeben" not in knoepfe
    assert "knopf-primaer" in knoepfe["Korrigieren"].klassen


@pytest.mark.parametrize("vorlage", UMGESTELLT)
def test_jedes_sichtbare_feld_mit_label_for(probe, alle, vorlage):
    """AK53: jedes sichtbare Feld hat ein sichtbares ``label for`` — kein Feld nur mit
    Platzhalter oder ``aria-label``."""
    baum = Baum(html_von(probe, alle, vorlage))
    labels = _labels(baum)
    for e in baum.elemente:
        if e.tag not in ("input", "select", "textarea") or e.versteckt:
            continue
        if e.attrs.get("type") in ("hidden", "submit", "button", "reset"):
            continue
        ident = e.attrs.get("id")
        assert ident, (vorlage, e.attrs)
        assert "aria-label" not in e.attrs, (vorlage, ident)
        sichtbar = [lb for lb in labels.get(ident, []) if not lb.versteckt]
        assert sichtbar and text(sichtbar[0]), (vorlage, ident)


@pytest.mark.parametrize("vorlage", UMGESTELLT)
def test_jede_tabelle_mit_caption_und_rollen(probe, alle, vorlage):
    """AK52: jede Tabelle mit ``caption`` und ausdrücklichen Rollen (Kartenform)."""
    baum = Baum(html_von(probe, alle, vorlage))
    tabellen = baum.alle("table")
    mit_caption = {id(c.in_tag("table")) for c in baum.alle("caption")}
    rollen = {"tr": "row", "th": "columnheader", "td": "cell"}
    for t in tabellen:
        assert id(t) in mit_caption, (vorlage, t.attrs)
        assert t.attrs.get("role") == "table", (vorlage, t.attrs)
    for e in baum.elemente:
        if e.tag in rollen and e.in_tag("table") is not None:
            assert e.attrs.get("role") == rollen[e.tag], (vorlage, e.tag, e.attrs)
        if e.tag in ("thead", "tbody", "tfoot"):
            assert e.attrs.get("role") == "rowgroup", (vorlage, e.tag)


@pytest.mark.parametrize("vorlage", UMGESTELLT)
def test_jede_tabelle_im_benannten_scrollrahmen(probe, alle, vorlage):
    """A93/A107 (P1 Runde 2, D-H1): eine Tabelle, die breiter ist als ihr Platz, wird
    nie abgeschnitten — sie scrollt in ihrem Rahmen, und der Rahmen ist per Tastatur
    erreichbar und benannt (``role="region"``, ``aria-label`` = Beschriftung,
    ``tabindex="0"``; axe ``scrollable-region-focusable``)."""
    baum = Baum(html_von(probe, alle, vorlage))
    captions = {id(c.in_tag("table")): text(c) for c in baum.alle("caption")}
    for t in baum.alle("table"):
        rahmen = t.eltern[-1]
        assert "tabelle-rahmen" in rahmen.klassen, (vorlage, rahmen.attrs)
        assert rahmen.attrs.get("role") == "region", (vorlage, rahmen.attrs)
        assert rahmen.attrs.get("tabindex") == "0", (vorlage, rahmen.attrs)
        assert rahmen.attrs.get("aria-label") == captions[id(t)], (vorlage, rahmen.attrs)


@pytest.mark.parametrize("vorlage", UMGESTELLT)
def test_beschreibungslisten_sind_komponente(probe, alle, vorlage):
    """I11: jede Beschreibungsliste ist die Komponente ``angaben``."""
    baum = Baum(html_von(probe, alle, vorlage))
    for dl in baum.alle("dl"):
        assert "angaben" in dl.klassen, (vorlage, dl.attrs)


VERWEISE = ("for", "aria-describedby", "aria-controls", "aria-labelledby")


def _pruefe_ids(html: str, wo: str) -> None:
    baum = Baum(html)
    ids = [e.attrs["id"] for e in baum.elemente if "id" in e.attrs]
    doppelt = {i for i in ids if ids.count(i) > 1}
    assert not doppelt, (wo, doppelt)
    vorhanden = set(ids)
    for e in baum.elemente:
        for name in VERWEISE:
            for ziel in e.attrs.get(name, "").split():
                assert ziel in vorhanden, (wo, name, ziel)
        href = e.attrs.get("href", "")
        if e.tag == "a" and href.startswith("#") and len(href) > 1:
            assert href[1:] in vorhanden, (wo, href)


@pytest.mark.parametrize("vorlage", UMGESTELLT)
def test_ids_je_seite_eindeutig(probe, alle, vorlage):
    """B16: jede id einmal; jeder Verweis (``for``, ``aria-*``, ``#…``) trifft."""
    _pruefe_ids(html_von(probe, alle, vorlage), vorlage)
    if vorlage in CODESEITEN:
        _pruefe_ids(
            html_von(probe, alle, vorlage, "?code=wiederherstellung"), vorlage + "?code"
        )


def _fehlerfall_arbeitsflaeche(tmp_path) -> tuple[str, str, list[str]]:  # noqa: ANN001
    """Korrektur ohne Steuerangabe → 422 mit Link auf ``#steuer``."""
    qw = queuewelt(tmp_path)
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": stand_aus(seite),
        "ansicht": "offen",
        "soll": "4360",
        "haben": "1200",
        "grund": "Eingabe bleibt",
    }
    r = client.post(f"/pruefen/{b.id}/korrigieren", data=daten)
    assert r.status_code == 422, r.text
    return r.text, "steuer", ["Eingabe bleibt", 'value="4360"']


def _fehlerfall_buchung(tmp_path) -> tuple[str, str, list[str]]:  # noqa: ANN001
    """Storno ohne Grund → 422 mit Link auf ``#grund-s``."""
    from datetime import date

    qw = queuewelt(tmp_path)
    b = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 1))
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": stand_aus(seite),
        "einmalcode": qw.web.personen["jan"].codes[-1],
        "grund": " ",
        "datum": "2026-10-02",
    }
    r = client.post(f"/buchungen/{b.id}/stornieren", data=daten)
    assert r.status_code == 422, r.text
    return r.text, "grund-s", ['value="2026-10-02"']


FEHLERFAELLE = {
    "/pruefen/{buchung_id:uuid}": _fehlerfall_arbeitsflaeche,
    "/buchungen/{buchung_id:uuid}": _fehlerfall_buchung,
}


@pytest.mark.parametrize("vorlage", [v for v in UMGESTELLT if v in FEHLERFAELLE])
def test_422_mit_fehlerliste_und_aria(tmp_path, vorlage):
    """AK53: 422 mit Fehlerliste (``role="alert"``, Link aufs Feld), am Feld
    ``aria-invalid`` und ``aria-describedby``; Eingaben außer Codes bleiben."""
    html, feld, bleibt = FEHLERFAELLE[vorlage](tmp_path)
    baum = Baum(html)
    (liste,) = [e for e in baum.elemente if "fehlerliste" in e.klassen]
    assert liste.attrs.get("role") == "alert"
    links = [
        e for e in baum.alle("a") if any("fehlerliste" in x.klassen for x in e.eltern)
    ]
    assert f"#{feld}" in [a.attrs["href"] for a in links], links
    (eingabe,) = [e for e in baum.elemente if e.attrs.get("id") == feld]
    assert eingabe.attrs.get("aria-invalid") == "true"
    beschreibung = eingabe.attrs.get("aria-describedby", "").split()
    assert f"{feld}-fehler" in beschreibung, eingabe.attrs
    for wert in bleibt:
        assert wert in html, wert
    for code in _codefelder(baum):
        assert code.attrs.get("value", "") == ""
    _pruefe_ids(html, vorlage + " 422")


@pytest.fixture(scope="module")
def leer(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    billige_hashes(mp)
    try:
        w = webwelt(tmp_path_factory.mktemp("leer"))
        w.person("alle", *Rolle)
        from tests.test_api_app import _leere_posten

        _leere_posten(w)  # die Welt bringt einen offenen Posten mit
        yield w.angemeldet("alle")
    finally:
        mp.undo()


@pytest.mark.parametrize("vorlage", [v for v in UMGESTELLT if v in LEERE_LISTEN])
def test_jede_liste_mit_leerem_zustand(leer, vorlage):
    """AK54: mit leerer Datenbank ein Satz und ein Link zur nächsten Aktion, ohne
    ``role`` (kein neues Ereignis)."""
    for pfad in LEERE_LISTEN[vorlage]:
        r = leer.get(pfad)
        assert r.status_code == 200, pfad
        baum = Baum(r.text)
        leere = [e for e in baum.elemente if "leer" in e.klassen]
        assert leere, pfad
        for zustand in leere:
            assert "role" not in zustand.attrs, pfad
            inhalt = [e for e in baum.elemente if zustand in e.eltern]
            assert not any("role" in e.attrs for e in inhalt), pfad
            aktionen = [e for e in inhalt if e.tag == "a" and e.attrs.get("href")]
            assert aktionen, pfad


@pytest.mark.parametrize("vorlage", [v for v in UMGESTELLT if v in CODESEITEN])
def test_code_parameter_je_seite(probe, alle, vorlage):
    """A109: ``?code=wiederherstellung`` schaltet **alle** Codefelder der Seite auf die
    Textvariante mit Rückweg; ein anderer Wert wird ignoriert (200, ungespiegelt)."""
    baum = Baum(html_von(probe, alle, vorlage, "?code=wiederherstellung"))
    felder = _codefelder(baum)
    assert felder, vorlage
    labels = _labels(baum)
    for feld in felder:
        assert feld.attrs.get("inputmode") == "text", (vorlage, feld.attrs)
        (label,) = labels[feld.attrs["id"]]
        assert text(label) == "Wiederherstellungscode", vorlage
    rueckwege = [e for e in baum.alle("a") if text(e) == "Code aus der App verwenden"]
    assert len(rueckwege) == len(felder), vorlage
    html = html_von(probe, alle, vorlage, "?code=xyzzy")
    assert "xyzzy" not in html, vorlage
    felder = _codefelder(Baum(html))
    assert felder and all(f.attrs.get("inputmode") == "numeric" for f in felder)


def test_alle_seiten_im_querschnitt(probe):
    """Am Ende von Schritt 12: alle HTML-Seiten der Registry (GET, mit Beispiel-IDs)
    stehen im neuen Design."""
    seiten = {s["vorlage"] for s in probe.seiten if s["art"] == "html"}
    assert set(UMGESTELLT) == seiten
    assert len(UMGESTELLT) == len(set(UMGESTELLT))


def test_hilfe_hat_die_sprungziele_der_leeren_zustaende(leer):
    """Die Links der leeren Zustände zeigen auf vorhandene Abschnitte der Hilfe."""
    pfade = [p for v in UMGESTELLT for p in LEERE_LISTEN.get(v, [])]
    texte = "".join(leer.get(p).text for p in pfade)
    for ziel in sorted(set(re.findall(r'href="(/hilfe/[a-z]+)#([a-z-]+)"', texte))):
        hilfe = leer.get(ziel[0]).text
        assert f'id="{ziel[1]}"' in hilfe, ziel


def test_ergebnis_einer_freigabe_mit_h1_und_hinweis(tmp_path, monkeypatch):
    """B8: die Seite nach einer Freigabe (``meldung.html``) hat ein ``h1``, die Meldung
    als neuen Hinweis (``role="status"``) und den Weg zurück."""
    if "/freigaben" not in UMGESTELLT:
        pytest.skip("Freigaben noch nicht umgestellt")
    from tests.api_hilfe import freigabe_hash
    from tests.gesellschaft_hilfe import zahlungslauf

    billige_hashes(monkeypatch)
    w = webwelt(tmp_path)
    w.person("fritz", Rolle.FREIGEBER)
    zahlungslauf(w.umgebung, "a")
    client = w.angemeldet("fritz")
    daten = {
        "csrf": csrf(client),
        "einmalcode": w.personen["fritz"].codes[0],
        "freigabe_hash": freigabe_hash(client, 1),
    }
    r = client.post("/freigaben/zahlungslauf/1", data=daten)
    assert r.status_code == 200, r.text
    assert r.text.count("<h1") == 1 and "<h1>Ergebnis der Freigabe</h1>" in r.text
    assert '<div class="hinweis hinweis-ok" role="status">' in r.text
    assert "Zahlungslauf 1 freigegeben von fritz" in r.text
    assert '<a href="/freigaben">Zurück</a>' in r.text
