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
    # Fehlerseiten (Schritt 11): 404 mit und ohne Anmeldung, 403, 409, 422
    assert alle.get("/gibt/es/nicht").text.count("<h1") == 1
    assert probe.web.client().get("/gibt/es/nicht").text.count("<h1") == 1
    leo = probe.web.angemeldet("leo")
    daten = {"csrf": _csrf(leo), "zeitraum": "2026-09"}
    assert leo.post("/freigaben/ustva", data=daten).text.count("<h1") == 1
    falsch = {"csrf": _csrf(alle), "einmalcode": "0", "freigabe_hash": "0" * 64}
    r = alle.post("/freigaben/zahlungslauf/1", data=falsch)
    assert r.status_code == 409 and r.text.count("<h1") == 1
    r = alle.post("/freigaben/ustva", data={"csrf": _csrf(alle), "zeitraum": "x"})
    assert r.status_code == 422 and r.text.count("<h1") == 1


def _csrf(client) -> str:  # noqa: ANN001
    from tests.api_hilfe import csrf

    return csrf(client)


def test_brotkrumen_unterhalb_eines_bereichs(probe, alle):
    vorschlag = probe.ids["vorschlag"]
    for pfad, titel in (
        (f"/pruefen/{vorschlag}", None),
        ("/pruefen/regeln", "Gelernte Regeln"),
    ):
        html = _main(alle.get(pfad).text)
        nav = re.search(
            r'<nav class="brotkrumen" aria-label="Brotkrumen"><ol>(.*?)</ol></nav>',
            html,
        )
        assert nav, pfad
        assert '<a href="/pruefen">Prüfen</a>' in nav.group(1)
        letzte = re.findall(r'<span aria-current="page">([^<]*)</span>', nav.group(1))
        assert len(letzte) == 1 and letzte[0].strip(), pfad
        if titel:
            assert letzte[0] == titel
    englisch = alle.get("/pruefen/regeln", headers=EN).text
    assert '<nav class="brotkrumen" aria-label="Breadcrumbs">' in englisch
    assert '<a href="/pruefen">Review</a>' in englisch
    for pfad in ("/pruefen", "/", "/freigaben"):
        assert 'class="brotkrumen"' not in alle.get(pfad).text, pfad


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
        seiten = [client.get(p).text for p in ("/", "/pruefen", "/pruefen/regeln")]
        seiten += [client.get(p).text for p in ("/freigaben", "/muster", "/menue")]
        # Fehlerseiten im Gerüst (Schritt 11): 404, 403 bzw. 422, 503
        seiten.append(client.get("/gibt/es/nicht").text)
        daten = {"csrf": _csrf(client), "zeitraum": "quatsch"}
        r = client.post("/freigaben/ustva", data=daten)
        assert r.status_code == (422 if name == "fritz" else 403)
        seiten.append(r.text)
        with pytest.MonkeyPatch.context() as mp:
            from accounti.api.seiten import start

            mp.setattr(start, "kennzahlen", _beschaeftigt)
            r = client.get("/")
            assert r.status_code == 503
            seiten.append(r.text)
        for html in seiten:
            pfad = re.search(r"<title>([^<]*)</title>", html).group(1)
            stelle, namen = _hilfe_stelle(html)
            stellen.add(stelle)
            vorn = [n for n in namen if n in reihenfolge]
            erwartet = [n for n in reihenfolge if n in vorn]
            assert vorn[: len(erwartet)] == erwartet, (name, pfad, namen)
            assert namen[stelle + 1] == "benutzermenue-ausloeser", (name, pfad, namen)
        assert len(stellen) == 1, (name, stellen)
    _, namen = _hilfe_stelle(welt.client().get("/anmelden").text)
    assert namen[:3] == ["sprunglink", "wortmarke", "kopf-hilfe"]


def _beschaeftigt(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
    from sqlalchemy.exc import OperationalError

    raise OperationalError("SELECT …", {}, Exception("database is locked"))


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


def test_seitentitel_schmal_ohne_informationsverlust(welt):
    """P1 Runde 2 (D-M1, WCAG 1.4.10): unter 64rem steht der Seitentitel nur dann im
    Kopf (und das ``h1`` ist nur für Screenreader da), wenn er in zwei Zeilen der
    Kopfleiste passt; er bricht dort um, statt mit Ellipse abgeschnitten zu werden. Ein
    längerer
    Titel (Gesellschaft wechseln, Belegnummer, Fehlerseiten) bleibt als ``h1`` im
    Inhalt sichtbar."""
    from accounti.api.vorlagen import passt_in_den_kopf

    c = welt.angemeldet("jan")
    assert '<body class="geruest mit-kopftitel"' in c.get("/pruefen").text
    assert '<body class="geruest mit-kopftitel"' in c.get("/konto").text
    lang = c.get("/gesellschaft").text
    assert '<body class="geruest"' in lang and "<h1>Gesellschaft wechseln</h1>" in lang
    for titel in ("Prüfen", "Gelernte Regeln", "Buchung f3fa55d2", "Hilfe: Freigaben"):
        assert passt_in_den_kopf(titel), titel
    for titel in (
        "Gesellschaft wechseln",
        "Beleg RE-2026-000123",
        "Keine Berechtigung",
        "Ergebnis der Freigabe",
        "",
    ):
        assert not passt_in_den_kopf(titel), titel
    kopf = _deklarationen(".kopf-titel", SCHMAL) | _deklarationen(
        ".mit-kopftitel .kopf-titel", SCHMAL
    )
    assert "text-overflow" not in kopf and kopf.get("white-space") != "nowrap"
    assert kopf.get("overflow-wrap") == "anywhere" and "overflow" not in kopf
    assert _deklarationen(".kopf-titel", SCHMAL).get("display") != "block"


def test_druck_schwarz_auf_weiss_mit_tabellenkopf():
    """A97 (P1 Runde 2, gp1-design B3/B4): Im Hochformat (A4 ≤ 816 px) griff die
    Kartenform unter 64rem auch im Druck — Tabellen ohne Kopf, das h1 versteckt, die
    Reiter gedruckt; im Dunkelmodus blieben die dunklen Token (Karten #1a1d21). Der
    Druck
    setzt jetzt die hellen Werte schwarz auf weiß, zeigt Tabellen als Tabelle mit
    wiederholtem Kopf und das h1, und blendet jede Navigation aus."""
    token = _deklarationen(":root", "print")
    assert _deklarationen(".thema-dunkel", "print") == token
    for name, wert in (("--text", "#000"), ("--text-2", "#000"), ("--grund", "#fff")):
        assert token.get(name) == wert, (name, token.get(name))
    assert token.get("--flaeche") == "#fff" and token.get("--akzent") == "#000"
    assert _deklarationen("nav", "print").get("display") == "none"
    kopf = _deklarationen(".tabelle thead", "print")
    assert kopf.get("display") == "table-header-group"
    assert kopf.get("position") == "static" and kopf.get("clip-path") == "none"
    assert _deklarationen(".tabelle tr", "print").get("display") == "table-row"
    assert _deklarationen(".tabelle td", "print").get("display") == "table-cell"
    assert _deklarationen(".tabelle td::before", "print").get("content") == "none"
    h1 = _deklarationen("#inhalt h1:not(.unsichtbar)", "print")
    assert h1.get("position") == "static" and h1.get("clip-path") == "none"


def test_forced_colors_nur_der_aktive_reiter_unterstrichen():
    """P1 Runde 2 (gp1-design B5): Im Kontrastmodus wird der transparente Strich der
    inaktiven Reiter sichtbar — jeder Reiter sah aktiv aus. Er bekommt dort die Farbe
    der Fläche (``Canvas``)."""
    inaktiv = _deklarationen(
        '.reiter > a:not([aria-current="page"])', "(forced-colors: active)"
    )
    assert inaktiv.get("border-bottom-color") == "Canvas"


def test_druckkopf(welt):
    html = welt.angemeldet("jan").get("/pruefen").text
    druck = re.search(r'<div class="druckkopf">(.*?)</div>', html, re.S)
    assert druck
    text = druck.group(1)
    assert "Alpha Papier GmbH" in text and "Prüfen" in text and "jan" in text
    assert "20.10.2026" in text  # dienste.uhr() der Welt
    gedruckt = _deklarationen(".druckkopf", "print")
    assert gedruckt["display"] == "block"
    assert _deklarationen(".druckkopf")["display"] == "none"


def test_statusbereich_role_status(welt):
    for client, pfad in ((welt.angemeldet("jan"), "/"), (welt.client(), "/anmelden")):
        html = client.get(pfad).text
        status = '<div id="status" role="status" aria-live="polite" class="unsichtbar">'
        assert status + "</div>" in html, pfad


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


def _marke_im_kopf(html: str) -> tuple[str, str]:
    m = re.search(
        r'class="kopf-gesellschaft"[^>]*><span class="marke (marke-[1-6])"'
        r' aria-hidden="true">([A-Z0-9ÄÖÜ]{2})<',
        html,
    )
    assert m
    return m.group(1), m.group(2)


def _marke_in_liste(html: str, kuerzel: str) -> tuple[str, str]:
    zeile = html[html.index(f'<li data-gesellschaft="{kuerzel}">') :]
    m = re.search(
        r'class="marke (marke-[1-6]) marke-klein"[^>]*>'
        r'<span class="marke-monogramm" aria-hidden="true">([A-Z0-9ÄÖÜ]{2})<',
        zeile,
    )
    assert m
    return m.group(1), m.group(2)


def test_kennfarbe_gleich_fuer_alle_benutzer(welt):
    """Zwei Benutzer mit Rollen in verschiedenen Gesellschaften sehen die gemeinsame
    Gesellschaft b in derselben Farbe (die Farben rechnen über die ganze Registry)."""
    welt.rolle("jan", "b", Rolle.BUCHHALTER)
    welt.person("bea", Rolle.BETRACHTER, gesellschaft="b")  # nur b
    bea = _marke_im_kopf(welt.angemeldet("bea").get("/").text)
    jan = _marke_in_liste(welt.angemeldet("jan").get("/gesellschaft").text, "b")
    assert bea[0] == jan[0]


def test_monogramm_gleich_fuer_alle_benutzer(welt):
    welt.rolle("jan", "b", Rolle.BUCHHALTER)
    welt.person("bea", Rolle.BETRACHTER, gesellschaft="b")
    bea = _marke_im_kopf(welt.angemeldet("bea").get("/").text)
    jan = _marke_in_liste(welt.angemeldet("jan").get("/menue").text, "b")
    assert bea[1] == jan[1] == "BR"


def test_lang_je_sprache_auf_jeder_seite(probe, alle):
    """AK57, A112: ``<html lang>`` folgt der Sprache auf jeder HTML-Seite (angemeldet
    und ohne Anmeldung)."""
    for pfad in [*_html_seiten(probe), "/gibt/es/nicht"]:
        client = probe.web.client() if pfad == "/anmelden" else alle
        for sprache in ("de", "en"):
            r = client.get(pfad, headers={"Accept-Language": sprache})
            assert f'<html lang="{sprache}" ' in r.text, (pfad, sprache)
    for sprache in ("de", "en"):
        r = probe.web.client().get("/hilfe", headers={"Accept-Language": sprache})
        assert f'<html lang="{sprache}" ' in r.text, sprache
