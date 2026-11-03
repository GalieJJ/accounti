"""Gerüst der Oberfläche (Spec 10c A3–A7, A89; Plan P1 Schritte 1 und 7)."""

from __future__ import annotations

import re
from datetime import date

import pytest

from accounti.api.registry import Bereich, Navigationspunkt
from accounti.i18n import N_
from accounti.models.auth import Rolle
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes
from tests.browserprobe_welt import baue
from tests.design_hilfe import css, selektoren, stilregeln


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


# --- Schritt 7: Gerüst ---------------------------------------------------------------


EN = {"Accept-Language": "en"}
FOKUSSIERBAR = re.compile(
    r'<(a\s[^>]*href=|summary\b|button\b|select\b|textarea\b|input\b(?![^>]*type="hidden"))'
)


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """Bestand mit jeder GET-Seite samt Beispiel-IDs (die Welt der Browserprobe)."""
    mp = pytest.MonkeyPatch()
    billige_hashes(mp)
    try:
        yield baue(tmp_path_factory.mktemp("geruest") / "welt")
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def alle(probe):
    return probe.web.angemeldet("alle")


def _html_seiten(probe):  # noqa: ANN001, ANN202
    return [s["pfad"] for s in probe.seiten if s["art"] == "html"]


def _kopf(html: str) -> str:
    return html[html.index('<header class="kopfleiste') : html.index("</header>")]


def _main(html: str) -> str:
    return html[html.index('<main id="inhalt"') : html.index("</main>")]


def test_titel_seite_gesellschaft_accounti(welt):
    jan = welt.angemeldet("jan")
    assert (
        "<title>Übersicht · Alpha Papier GmbH · accounti</title>" in jan.get("/").text
    )
    assert (
        "<title>Overview · Alpha Papier GmbH · accounti</title>"
        in jan.get("/", headers=EN).text
    )
    assert "<title>Anmelden · accounti</title>" in welt.client().get("/anmelden").text
    assert (
        "<title>Sign in · accounti</title>"
        in welt.client().get("/anmelden", headers=EN).text
    )


def test_kennfarbe_und_kuerzel_auf_jeder_seite(probe, alle):
    for pfad in [p for p in _html_seiten(probe) if p != "/anmelden"]:  # schlicht
        r = alle.get(pfad)
        assert r.status_code == 200, pfad
        kopf = _kopf(r.text)
        chip = re.search(
            r'<(a|span) class="kopf-gesellschaft"[^>]*data-gesellschaft="a"[^>]*>'
            r'<span class="marke marke-([1-6])" aria-hidden="true">'
            r"([A-ZÄÖÜ0-9]{2})</span>",
            kopf,
        )
        assert chip, pfad
        assert "Alpha Papier GmbH" in kopf, pfad
        assert not re.search(r"<span\b[^>]*aria-label=", r.text), pfad


def test_keine_zeile_gesellschaft_im_inhalt(probe, alle):
    for pfad in _html_seiten(probe):
        inhalt = _main(alle.get(pfad).text)
        assert "Gesellschaft: <strong>" not in inhalt, pfad
        assert "aktive-gesellschaft" not in inhalt, pfad


def test_genau_ein_h1(probe, alle):
    for pfad in [*_html_seiten(probe), "/muster?theme=dunkel"]:
        assert alle.get(pfad).text.count("<h1") == 1, pfad
    assert probe.web.client().get("/anmelden").text.count("<h1") == 1


def test_sprunglink_ist_erstes_ziel(welt):
    for client, pfad in ((welt.client(), "/anmelden"), (welt.angemeldet("jan"), "/")):
        html = client.get(pfad).text
        koerper = html[html.index("<body") :]
        erstes = FOKUSSIERBAR.search(koerper)
        assert erstes and koerper[erstes.start() :].startswith(
            '<a class="sprunglink" href="#inhalt">'
        ), pfad
        assert '<main id="inhalt" tabindex="-1"' in html


def _hilfe_stelle(html: str) -> tuple[int, list[str]]:
    kopf = _kopf(html)
    ziele = [
        kopf[m.start() : kopf.index(">", m.start()) + 1]
        for m in FOKUSSIERBAR.finditer(kopf)
    ]
    namen = []
    for z in ziele:
        klasse = re.search(r'class="([^"]+)"', z)
        namen.append(
            klasse.group(1).split()[0] if klasse else z[1:].split()[0].strip(">")
        )
    return namen.index("kopf-hilfe"), namen


def test_hilfe_link_gleiche_stelle(welt):
    welt.person("fritz", Rolle.FREIGEBER)
    welt.rolle("jan", "b", Rolle.BUCHHALTER)  # jan: zwei Gesellschaften, fritz: eine
    reihenfolge = ["sprunglink", "wortmarke", "kopf-gesellschaft", "kopf-hilfe"]
    for name in ("jan", "fritz"):
        client = welt.angemeldet(name)
        stellen = set()
        for pfad in ("/", "/pruefen", "/pruefen/regeln", "/freigaben", "/muster"):
            stelle, namen = _hilfe_stelle(client.get(pfad).text)
            stellen.add(stelle)
            vorn = [n for n in namen if n in reihenfolge]
            erwartet = [n for n in reihenfolge if n in vorn]
            assert vorn[: len(erwartet)] == erwartet, (name, pfad, namen)
            assert namen[stelle + 1] == "benutzermenue-ausloeser", (name, pfad, namen)
        assert len(stellen) == 1, (name, stellen)
    _, namen = _hilfe_stelle(welt.client().get("/anmelden").text)
    assert namen[:3] == ["sprunglink", "wortmarke", "kopf-hilfe"]


def test_benutzermenue_breit_und_symbol_schmal(welt):
    kopf = _kopf(welt.angemeldet("jan").get("/").text)
    menue = kopf[
        kopf.index('<details class="benutzermenue">') : kopf.index("</details>")
    ]
    assert '<summary class="benutzermenue-ausloeser">' in menue
    assert '<span class="avatar" aria-hidden="true">JA</span>' in menue
    assert 'href="/konto"' in menue and "Mein Konto" in menue
    assert 'action="/konto/vorlieben"' in menue
    assert 'name="sprache"' in menue and 'name="darstellung"' in menue
    assert 'name="weiter" value="/"' in menue and "Übernehmen" in menue
    assert 'class="menue-eintrag" href="/hilfe' in menue
    assert 'action="/abmelden"' in menue and "Abmelden" in menue
    assert re.search(r'<a class="kopf-konto" href="/menue#konto">', kopf)


def test_untere_leiste_ziele(welt):
    belege = Navigationspunkt(N_("Belege"), "/belege", Bereich.BELEGE, "file-text")
    welt.person("fritz", Rolle.FREIGEBER)
    for name, erwartet in (
        ("jan", ["/", "/pruefen", "/belege", "/menue"]),
        ("fritz", ["/", "/pruefen", "/belege", "/freigaben", "/menue"]),
    ):
        client = welt.client()
        client.app.state.navigation = [*client.app.state.navigation, belege]
        welt.anmelden(client, name)
        html = client.get("/pruefen").text
        leiste = html[html.index('<nav class="untere-leiste"') :]
        leiste = leiste[: leiste.index("</nav>")]
        ziele = re.findall(r'<a class="leisten-ziel" href="([^"]+)"', leiste)
        assert ziele == erwartet and len(ziele) <= 5, name
        assert re.findall(r'href="([^"]+)" aria-current="page"', leiste) == ["/pruefen"]
        seitenleiste = html[html.index('<nav class="seitenleiste"') :]
        assert (
            'href="/pruefen" aria-current="page"'
            in seitenleiste[: seitenleiste.index("</nav>")]
        )


def test_zaehler_in_seitenleiste_und_unterer_leiste(tmp_path):
    from tests.gesellschaft_hilfe import zahlungslauf
    from tests.pruefen_hilfe import queuewelt

    qw = queuewelt(tmp_path)
    qw.buchung()
    qw.buchung(datum=date(2026, 10, 2))
    zahlungslauf(qw.web.umgebung, "a")
    html = qw.web.angemeldet("fritz").get("/").text
    seitenleiste = html[html.index('<nav class="seitenleiste"') :]
    seitenleiste = seitenleiste[: seitenleiste.index("</nav>")]
    assert re.search(
        r'href="/pruefen".*?<span class="zaehler zaehler-betont">2<', seitenleiste
    )
    assert re.search(r'href="/freigaben".*?<span class="zaehler">1<', seitenleiste)
    leiste = html[html.index('<nav class="untere-leiste"') :]
    assert '<span class="leisten-zahl">2</span>' in leiste[: leiste.index("</nav>")]


def _regeln(selektor: str, medien: str | None = None):  # noqa: ANN202
    return [
        s
        for s in stilregeln(css())
        if selektor in selektoren(s.regel.kopf)
        and (medien is None or any(medien in m for m in s.medien))
        and (medien is not None or not s.medien)
    ]


def _deklarationen(selektor: str, medien: str | None = None) -> dict[str, str]:
    werte: dict[str, str] = {}
    for s in _regeln(selektor, medien):
        werte.update(dict(s.regel.deklarationen))
    return werte


SCHMAL = "not all and (min-width: 64rem)"


def test_safe_area_im_kopf_und_in_der_leiste():
    kopf = _deklarationen(".kopfleiste", SCHMAL)
    for seite in ("top", "left", "right"):
        assert f"env(safe-area-inset-{seite})" in " ".join(kopf.values()), seite
    leiste = _deklarationen(".untere-leiste")
    assert "env(safe-area-inset-bottom)" in leiste["padding-bottom"]
    assert (
        "env(safe-area-inset-bottom)"
        in _deklarationen("body.geruest", SCHMAL)["padding-bottom"]
    )


def test_masse_des_geruests():
    from tests.design_hilfe import token

    masse = token().masse
    assert masse["--kopfhoehe"] == "3.5rem" and masse["--leistenhoehe"] == "4rem"
    assert masse["--seitenleiste"] == "14.5rem"
    assert _deklarationen(".kopfleiste")["height"] == "var(--kopfhoehe)"
    assert (
        _deklarationen(".geruest-rumpf > .seitenleiste")["flex"]
        == "0 0 var(--seitenleiste)"
    )
    assert _deklarationen(".geruest-rumpf > .seitenleiste", SCHMAL)["display"] == "none"
    assert _deklarationen("body > .untere-leiste")["display"] == "none"
    assert _deklarationen("body > .untere-leiste", SCHMAL)["display"] == "grid"
    # 64 px mit der Linie oben (L10: untere Leiste 64 px ohne Safe Area)
    ziel = _deklarationen(".leisten-ziel")["min-height"]
    assert ziel == "calc(var(--leistenhoehe) - 1px)"


def test_data_theme_aus_der_wahl(welt):
    from accounti.auth.dienst import Vorlieben, setze_vorlieben

    jan = welt.angemeldet("jan")
    for wahl, schema in (("dunkel", "dark"), ("hell", "light"), ("auto", "light dark")):
        with welt.system() as s:
            setze_vorlieben(
                s, welt.personen["jan"].benutzer.id, Vorlieben(darstellung=wahl)
            )
            s.commit()
        html = jan.get("/").text
        assert f'<html lang="de" data-theme="{wahl}">' in html, wahl
        assert f'<meta name="color-scheme" content="{schema}">' in _html_kopf(html)
    assert 'data-tastenkuerzel="an"' in jan.get("/").text
    with welt.system() as s:
        setze_vorlieben(
            s, welt.personen["jan"].benutzer.id, Vorlieben(tastenkuerzel=False)
        )
        s.commit()
    assert re.search(r'<body [^>]*data-tastenkuerzel="aus"', jan.get("/").text)
    assert 'data-tastenkuerzel="an"' in welt.client().get("/anmelden").text


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
