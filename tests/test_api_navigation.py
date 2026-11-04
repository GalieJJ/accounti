"""Navigation der Oberfläche (Spec 10c A1, A2, AK44; Plan P1, Schritt 6): Bereiche je
Rolle aus der Registry, Zähler über den Lesezugriff — nur für ganze Seiten."""

from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from accounti.api.geruest import Geruest
from accounti.api.registry import Bereich, Navigationspunkt
from accounti.api.sitzung import AngemeldetDep
from accounti.i18n import N_
from accounti.models import BuchungStatus
from accounti.models.auth import Recht, Rolle
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes
from tests.gesellschaft_hilfe import zahlungslauf
from tests.pruefen_hilfe import queuewelt

# Stub-Seiten für Bereiche, die es vor P2/P3/P5/10b-2 noch nicht gibt (B3)
STUBS = [
    Navigationspunkt(
        N_("Belege"), "/belege", Bereich.BELEGE, "file-text", reihenfolge=20
    ),
    Navigationspunkt(N_("Steuern"), "/steuern", Bereich.STEUERN, "calendar"),
    Navigationspunkt(
        N_("Auswertungen"), "/auswertungen", Bereich.AUSWERTUNGEN, "chart-column"
    ),
    Navigationspunkt(
        N_("Einstellungen"),
        "/einstellungen",
        Bereich.EINSTELLUNGEN,
        "settings",
        Recht.VERWALTEN,
    ),
]
OHNE_FREIGABE = ["/", "/pruefen", "/belege", "/steuern", "/auswertungen"]
MIT_FREIGABE = [*OHNE_FREIGABE, "/freigaben"]


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    for rolle in Rolle:
        w.person(rolle.value, rolle)
    return w


def _geruest(client, pfad: str = "/") -> Geruest:  # noqa: ANN001
    r = client.get(pfad)
    assert r.status_code == 200, r.text
    g = r.context["geruest"]
    assert isinstance(g, Geruest)
    return g


def _mit_stubs(welt, rolle: str):  # noqa: ANN001, ANN202
    client = welt.client()
    client.app.state.navigation = [*client.app.state.navigation, *STUBS]
    welt.anmelden(client, rolle)
    return client


@pytest.mark.parametrize(
    ("rolle", "erwartet", "einstellungen"),
    [
        ("betrachter", OHNE_FREIGABE, False),
        ("buchhalter", OHNE_FREIGABE, False),
        ("freigeber", MIT_FREIGABE, False),
        ("verwalter", OHNE_FREIGABE, True),
    ],
)
def test_bereiche_je_rolle_in_reihenfolge(welt, rolle, erwartet, einstellungen):
    g = _geruest(_mit_stubs(welt, rolle))
    assert [e.pfad for e in g.bereiche] == erwartet
    assert (g.einstellungen is not None) is einstellungen


def test_einstellungen_abgesetzt_nur_mit_verwalten(welt):
    g = _geruest(_mit_stubs(welt, "verwalter"))
    assert g.einstellungen is not None and g.einstellungen.pfad == "/einstellungen"
    assert g.einstellungen.symbol == "settings"
    assert "/einstellungen" not in [e.pfad for e in g.bereiche]
    assert _geruest(_mit_stubs(welt, "freigeber")).einstellungen is None


def test_freigaben_nur_mit_freigaberecht_seite_aber_lesbar(welt):
    for rolle in ("betrachter", "buchhalter", "verwalter"):
        client = welt.angemeldet(rolle)
        assert "/freigaben" not in [e.pfad for e in _geruest(client).bereiche]
        assert client.get("/freigaben").status_code == 200
    freigeber = _geruest(welt.angemeldet("freigeber"))
    (eintrag,) = [e for e in freigeber.bereiche if e.pfad == "/freigaben"]
    assert eintrag.symbol == "shield-check"


def test_bereich_ohne_seite_entfaellt(welt):
    g = _geruest(_mit_stubs(welt, "freigeber"))
    titel = [e.titel for e in g.bereiche]
    assert "Bank & Zahlungen" not in titel and len(titel) == len(set(titel))
    # ohne Stubs: nur die Bereiche mit Seite aus 10a/10b
    assert [e.pfad for e in _geruest(welt.angemeldet("freigeber")).bereiche] == [
        "/",
        "/pruefen",
        "/freigaben",
    ]


def test_ein_eintrag_je_bereich_mit_kleinster_reihenfolge(welt):
    client = welt.client()
    client.app.state.navigation = [
        *client.app.state.navigation,
        Navigationspunkt(
            N_("Regeln"), "/pruefen/regeln", Bereich.PRUEFEN, "check", reihenfolge=90
        ),
    ]
    welt.anmelden(client, "buchhalter")
    g = _geruest(client, "/pruefen/regeln")
    assert [e.pfad for e in g.bereiche if e.titel in ("Prüfen", "Regeln")] == [
        "/pruefen"
    ]
    (aktiv,) = [e for e in g.bereiche if e.aktiv]
    assert aktiv.pfad == "/pruefen"


def test_symbol_muss_im_sprite_stehen():
    with pytest.raises(ValueError, match="gibt-es-nicht"):
        Navigationspunkt("X", "/x", Bereich.BANK, "gibt-es-nicht")


def test_recht_als_menge_eines_genuegt():
    p = Navigationspunkt(
        "F",
        "/f",
        Bereich.FREIGABEN,
        "shield-check",
        frozenset({Recht.ZAHLUNG_FREIGEBEN, Recht.STEUER_FREIGEBEN}),
    )
    assert p.erlaubt(frozenset({Recht.LESEN, Recht.STEUER_FREIGEBEN}))
    assert not p.erlaubt(frozenset({Recht.LESEN, Recht.BUCHUNG_FREIGEBEN}))


def test_untere_leiste_und_aktiver_bereich(welt):
    g = _geruest(welt.angemeldet("freigeber"), "/pruefen")
    assert [e.pfad for e in g.unten] == ["/", "/pruefen", "/freigaben", "/menue"]
    assert [e.pfad for e in g.unten if e.aktiv] == ["/pruefen"]
    assert [e.pfad for e in g.bereiche if e.aktiv] == ["/pruefen"]
    start = _geruest(welt.angemeldet("buchhalter"), "/")
    assert [e.pfad for e in start.bereiche if e.aktiv] == ["/"]


# --- Zähler ---------------------------------------------------------------------


@pytest.fixture
def qw(tmp_path):
    q = queuewelt(tmp_path)
    q.buchung()
    q.buchung(datum=date(2026, 10, 2))
    q.buchung(status=BuchungStatus.GEPRUEFT)
    zahlungslauf(q.web.umgebung, "a")
    return q


def test_zaehler_im_geruest(qw):
    fritz = _geruest(qw.web.angemeldet("fritz"))
    zahlen = {e.pfad: (e.zaehler, e.betont) for e in fritz.bereiche}
    assert zahlen == {
        "/": (None, False),
        "/pruefen": (2, True),
        "/freigaben": (1, False),
    }
    unten = {e.pfad: e.zaehler for e in fritz.unten}
    assert unten["/pruefen"] == 2 and unten["/freigaben"] == 1
    # Gesellschaft b: eigene Datenbank, eigene Zahl
    jan = qw.web.angemeldet("jan")
    jan.post("/gesellschaft", data={"csrf": _csrf(jan), "kuerzel": "b"})
    assert {e.pfad: e.zaehler for e in _geruest(jan).bereiche}["/pruefen"] == 0


def _csrf(client) -> str:  # noqa: ANN001
    from tests.api_hilfe import csrf

    return csrf(client)


def _mit_zaehler(welt, name: str, zaehler):  # noqa: ANN001, ANN202
    client = welt.client()
    client.app.state.navigation = [
        p
        if p.pfad != "/pruefen"
        else Navigationspunkt(
            p.titel, p.pfad, p.bereich, p.symbol, p.recht, p.reihenfolge, zaehler
        )
        for p in client.app.state.navigation
    ]
    welt.anmelden(client, name)
    return client


def test_zaehler_nicht_fuer_fragmente(qw):
    aufrufe: list[int] = []

    def zaehler(s):  # noqa: ANN001, ANN202
        aufrufe.append(1)
        return 5

    client = _mit_zaehler(qw.web, "jan", zaehler)
    vorschlag = qw.buchung(datum=date(2026, 10, 3))
    r = client.get(f"/pruefen/{vorschlag.id}", headers={"HX-Request": "true"})
    assert r.status_code == 200 and "<html" not in r.text
    assert aufrufe == []
    client.get(f"/pruefen/{vorschlag.id}")
    assert aufrufe == [1]


@pytest.mark.parametrize(
    "fehler",
    [
        RuntimeError("geheim-4711"),
        OperationalError("SELECT …", {}, Exception("database is locked")),
    ],
)
def test_zaehler_fehler_laesst_nur_den_zaehler_weg(qw, fehler, caplog):
    def zaehler(s):  # noqa: ANN001, ANN202
        raise fehler

    client = _mit_zaehler(qw.web, "fritz", zaehler)
    r = client.get("/")
    assert r.status_code == 200
    zahlen = {e.pfad: e.zaehler for e in r.context["geruest"].bereiche}
    assert zahlen == {"/": None, "/pruefen": None, "/freigaben": 1}
    assert type(fehler).__name__ in caplog.text
    assert "geheim-4711" not in caplog.text and "database is locked" not in caplog.text
    assert "SELECT" not in caplog.text


def test_keine_zaehler_auf_fehlerseiten(welt):
    aufrufe: list[int] = []

    def zaehler(s):  # noqa: ANN001, ANN202
        aufrufe.append(1)
        return 5

    client = _mit_zaehler(welt, "buchhalter", zaehler)

    @client.app.get("/probe/fehler/{art}")
    async def probe(a: AngemeldetDep, art: str, zahl: int = 0) -> None:
        if art == "404":
            raise HTTPException(404)
        raise OperationalError("SELECT …", {}, Exception("database is locked"))

    assert client.get("/probe/fehler/404").status_code == 404
    assert client.get("/probe/fehler/422?zahl=abc").status_code == 422
    assert client.get("/probe/fehler/503").status_code == 503
    assert client.get("/gibt/es/nicht").status_code == 404
    assert aufrufe == []
    assert client.get("/").status_code == 200
    assert aufrufe == [1]


# --- /menue (Plan P1, Schritt 8) ---------------------------------------------------


def _gruppen(html: str) -> list[tuple[str, str]]:
    """(Etikett, Inhalt der Gruppenliste) je Abschnitt von /menue."""
    inhalt = html[html.index('<main id="inhalt"') : html.index("</main>")]
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(
            r'<h2 class="etikett"[^>]*>(.*?)</h2>\s*'
            r'<ul class="gruppenliste[^"]*">(.*?)</ul>',
            inhalt,
            re.S,
        )
    ]


def test_menue_ohne_js(qw):
    qw.web.rolle("fritz", "b", Rolle.BETRACHTER)
    html = qw.web.angemeldet("fritz").get("/menue").text
    (_, bereiche), (_, gesellschaften), (_, konto) = _gruppen(html)
    assert re.findall(r'<a href="([^"]+)"', bereiche) == ["/", "/pruefen", "/freigaben"]
    assert ">2<" in bereiche and ">1<" in bereiche  # Zähler Prüfen, Freigaben
    assert 'aria-current="page"' not in bereiche  # /menue ist kein Bereich
    assert gesellschaften.count('action="/gesellschaft"') == 1  # die andere
    assert (
        'name="csrf"' in gesellschaften and 'name="kuerzel" value="b"' in gesellschaften
    )
    assert "aktiv" in gesellschaften
    assert 'id="konto"' in html
    assert 'href="/konto"' in konto and "Hilfe" in konto
    assert 'action="/abmelden"' in konto and "Abmelden" in konto
    assert "<script" not in html[html.index("<body") :]


def test_menue_einstellungen_und_freigaben_nur_mit_recht(welt):
    stub = Navigationspunkt(
        N_("Einstellungen"),
        "/einstellungen",
        Bereich.EINSTELLUNGEN,
        "settings",
        Recht.VERWALTEN,
    )
    for name, freigaben, einstellungen in (
        ("verwalter", False, True),
        ("freigeber", True, False),
        ("buchhalter", False, False),
    ):
        client = welt.client()
        client.app.state.navigation = [*client.app.state.navigation, stub]
        welt.anmelden(client, name)
        (_, bereiche), *_ = _gruppen(client.get("/menue").text)
        assert ('href="/freigaben"' in bereiche) is freigaben, name
        assert ('href="/einstellungen"' in bereiche) is einstellungen, name


def test_menue_fragment_mit_hx_request(welt):
    client = welt.angemeldet("buchhalter")
    teil = client.get("/menue", headers={"HX-Request": "true"})
    assert teil.status_code == 200 and "<html" not in teil.text
    assert 'id="konto"' in teil.text and 'class="kopfleiste' not in teil.text
    assert "<html" in client.get("/menue").text


def test_menue_gruppen_wie_leinwand(qw):
    qw.web.rolle("fritz", "b", Rolle.BETRACHTER)
    html = qw.web.angemeldet("fritz").get("/menue").text
    etiketten = [e for e, _ in _gruppen(html)]
    assert etiketten[0] == "Bereiche" and etiketten[1] == "Gesellschaft"
    assert etiketten[2].startswith("Mein Konto") and "fritz" in etiketten[2]
    (_, _), (_, gesellschaften), _ = _gruppen(html)
    marke = r'class="marke marke-[1-6] marke-klein"[^>]*>.*?>([A-Z0-9]{2})<'
    marken = re.findall(marke, gesellschaften)
    assert marken == ["AP", "BR"]
    assert "chevron-right" in html
