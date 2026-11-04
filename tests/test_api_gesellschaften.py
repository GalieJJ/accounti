"""Mehrere Gesellschaften im Browser und in der API (Spec 4.4, Akzeptanz 5)."""

import pytest

from accounti.api.app import erstelle_app
from accounti.models.auth import Rolle, TokenRecht
from tests.api_hilfe import csrf, webwelt
from tests.auth_hilfe import billige_hashes


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    w.person("jan", Rolle.BUCHHALTER, gesellschaft="a")
    w.rolle("jan", "b", Rolle.BUCHHALTER)
    w.person("ole", Rolle.FREIGEBER, gesellschaft="a")  # nur Gesellschaft A
    return w


def seiten_ohne_parameter(app):
    return [
        e.pfad
        for e in app.state.endpunkte
        if e.methode == "GET"
        and "{" not in e.pfad
        and not e.pfad.startswith("/api/")
        and e.pfad != "/anmelden"
    ]


def test_akzeptanz_5_wechsel_aendert_alle_ansichten(welt):
    from tests.gesellschaft_hilfe import zahlungslauf

    zahlungslauf(welt.umgebung, "a")
    zahlungslauf(welt.umgebung, "b")
    client = welt.angemeldet("jan")
    seite = client.get("/freigaben").text  # Befund B-N2: die Daten, nicht nur der Kopf
    assert "A-RE-1" in seite and "111,00" in seite and "B-RE-7" not in seite
    start = client.get("/")
    assert "Alpha Papier GmbH" in start.text and "111,00" in start.text
    # umgestellt (Plan P1, Schritt 7): gewechselt wird über /gesellschaft — der Kopf
    # zeigt die aktive Gesellschaft als Link dorthin, die andere steht nicht im Kopf
    assert (
        '<a class="kopf-gesellschaft" href="/gesellschaft" data-gesellschaft="a"'
        in (start.text)
    )
    assert "Beta Rahmen KG" not in start.text
    assert "Beta Rahmen KG" in client.get("/gesellschaft").text  # dort die Auswahl
    r = client.post(
        "/gesellschaft",
        data={"csrf": csrf(client), "kuerzel": "b"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    pfade = seiten_ohne_parameter(erstelle_app(welt.dienste))
    assert {"/", "/freigaben"} <= set(pfade)
    for pfad in pfade:
        seite = client.get(pfad)
        assert seite.status_code == 200, pfad
        # umgestellt: statt der Zeile „Gesellschaft: …“ Kennzeichen im Kopf und Titel
        assert 'data-gesellschaft="b"' in seite.text, pfad
        assert " · Beta Rahmen KG · accounti</title>" in seite.text, pfad
    start = client.get("/")
    assert "777,00" in start.text and "111,00" not in start.text
    seite = client.get("/freigaben").text
    assert "B-RE-7" in seite and "777,00" in seite and "Beta Rahmen KG" in seite
    assert "A-RE-1" not in seite and "Alpha Papier GmbH" not in seite.split("<main")[-1]


def test_benutzer_von_a_sieht_b_nicht(welt):
    client = welt.angemeldet("ole")
    start = client.get("/")
    assert "Beta Rahmen KG" not in start.text  # kein Wechsler, keine Daten
    r = client.post("/gesellschaft", data={"csrf": csrf(client), "kuerzel": "b"})
    assert r.status_code == 403
    start = client.get("/")
    assert "Alpha Papier GmbH" in start.text and "777,00" not in start.text


def test_rolle_entzogen_wirkt_sofort(welt):
    from accounti.auth.dienst import entferne_rolle

    client = welt.angemeldet("jan")
    client.post("/gesellschaft", data={"csrf": csrf(client), "kuerzel": "b"})
    with welt.system() as s:
        entferne_rolle(
            s, welt.personen["jan"].benutzer, "b", Rolle.BUCHHALTER, welt.uhr(), "t"
        )
        s.commit()
    # Rollenänderung beendet die Sitzung — neu anmelden landet in A
    assert client.get("/", follow_redirects=False).status_code == 303
    client = welt.angemeldet("jan")
    assert "Beta Rahmen KG" not in client.get("/").text


def test_token_sieht_nur_seine_gesellschaft(welt):
    client = welt.client()
    a = welt.token("a", TokenRecht.OPOS_LESEN, name="erp-a")
    b = welt.token("b", TokenRecht.OPOS_LESEN, name="erp-b")
    posten_a = client.get(
        "/api/v1/offene-posten", headers={"Authorization": f"Bearer {a}"}
    ).json()
    posten_b = client.get(
        "/api/v1/offene-posten", headers={"Authorization": f"Bearer {b}"}
    ).json()
    assert [p["belegnummer"] for p in posten_a["offene_posten"]] == ["A-RE-1"]
    assert [p["belegnummer"] for p in posten_b["offene_posten"]] == ["B-RE-7"]


def test_eigene_konfiguration_je_gesellschaft(welt):
    from accounti.konfiguration import lade_buchhaltung
    from tests.api_hilfe import freigabe_hash
    from tests.gesellschaft_hilfe import zahlungslauf

    g = welt.dienste.gesellschaften
    assert lade_buchhaltung(g["a"].konfiguration).kontenrahmen == "SKR03"
    assert lade_buchhaltung(g["b"].konfiguration).kontenrahmen == "SKR04"
    assert g["a"].archiv != g["b"].archiv and g["a"].datenbank != g["b"].datenbank
    # Befund B-N2: die Konfiguration wirkt im Browser je Gesellschaft —
    # Vier-Augen nur in B
    pfad = welt.umgebung.config["b"]
    pfad.write_text(
        pfad.read_text(encoding="utf-8").replace(
            "zahlung:\n", "zahlung:\n  vier_augen: true\n"
        ),
        encoding="utf-8",
    )
    zahlungslauf(welt.umgebung, "a")
    zahlungslauf(welt.umgebung, "b")
    welt.person("chef", Rolle.FREIGEBER, gesellschaft="a")
    welt.rolle("chef", "b", Rolle.FREIGEBER)
    client = welt.angemeldet("chef")
    for kuerzel, erwartet in (("a", "freigegeben von chef"), ("b", "zweite Person")):
        client.post("/gesellschaft", data={"csrf": csrf(client), "kuerzel": kuerzel})
        daten = {
            "csrf": csrf(client),
            "einmalcode": welt.personen["chef"].codes.pop(),
            "freigabe_hash": freigabe_hash(client, 1),
        }
        r = client.post("/freigaben/zahlungslauf/1", data=daten)
        assert r.status_code == 200, r.text
        assert erwartet in r.text, kuerzel


# --- /gesellschaft (Plan P1, Schritt 8) -------------------------------------------


def _zeilen(html: str) -> dict[str, str]:
    """Kürzel → HTML der Zeile in der Liste der Gesellschaften."""
    import re

    liste = html[html.index('<ul class="gruppenliste gesellschaften"') :]
    liste = liste[: liste.index("</ul>")]
    return {
        m.group(1): m.group(0)
        for m in re.finditer(
            r'<li data-gesellschaft="([a-z0-9_-]+)">.*?</li>', liste, re.S
        )
    }


def _vorschlaege(welt, kuerzel: str, anzahl: int) -> None:  # noqa: ANN001
    from datetime import date

    from tests.pruefen_hilfe import Queuewelt

    qw = Queuewelt(welt, welt.umgebung.wurzel)
    for tag in range(1, anzahl + 1):
        qw.buchung(kuerzel=kuerzel, datum=date(2026, 10, tag))


def test_gesellschaftsseite_nur_mit_rolle(welt):
    jan = welt.angemeldet("jan")
    zeilen = _zeilen(jan.get("/gesellschaft").text)
    assert set(zeilen) == {"a", "b"}
    assert "aktiv" in zeilen["a"] and 'action="/gesellschaft"' in zeilen["b"]
    assert 'name="kuerzel" value="b"' in zeilen["b"]
    ole = welt.angemeldet("ole")
    html = ole.get("/gesellschaft").text
    assert set(_zeilen(html)) == {"a"} and "Beta Rahmen KG" not in html
    assert welt.client().get("/gesellschaft", follow_redirects=False).status_code == 303


def test_zeile_schmal_name_vor_den_zaehlern(welt):
    """P1 Runde 2 („Mehr“ bei 390 px): „aktiv“ und die Zähler stehen in einer Gruppe,
    die unter den Namen rückt, wenn die Breite nicht reicht — der Name bricht nicht
    mehr dreizeilig um und überlagert nichts."""
    from tests.design_hilfe import css, selektoren, stilregeln

    zeilen = _zeilen(welt.angemeldet("jan").get("/gesellschaft").text)
    for kuerzel, vorne in (("a", "aktiv"), ("b", "0 zu prüfen")):
        gruppe = zeilen[kuerzel].split('<span class="gruppenliste-zahlen">', 1)[1]
        assert gruppe.startswith(f'<span class="gruppenliste-neben">{vorne}<'), gruppe
    werte: dict[str, dict[str, str]] = {}
    for s in stilregeln(css()):
        for sel in selektoren(s.regel.kopf):
            werte.setdefault(sel, {}).update(dict(s.regel.deklarationen))
    assert werte[".gesellschaften .gruppenliste-aktiv"]["flex-wrap"] == "wrap"
    assert werte[".gesellschaften button"]["flex-wrap"] == "wrap"
    assert werte[".gesellschaften .gruppenliste-text"]["flex"] == "1 1 10rem"
    assert werte[".gruppenliste-zahlen"]["margin-left"] == "auto"


def test_zaehler_je_gesellschaft(welt):
    _vorschlaege(welt, "a", 2)
    _vorschlaege(welt, "b", 3)
    zeilen = _zeilen(welt.angemeldet("jan").get("/gesellschaft").text)
    assert "2 zu prüfen" in zeilen["a"] and "3 zu prüfen" in zeilen["b"]


def test_freigaben_zahl_nur_mit_freigaberecht(welt):
    from tests.gesellschaft_hilfe import zahlungslauf

    zahlungslauf(welt.umgebung, "a")
    zahlungslauf(welt.umgebung, "b")
    welt.rolle("ole", "b", Rolle.BETRACHTER)  # in b ohne Freigaberecht
    zeilen = _zeilen(welt.angemeldet("ole").get("/gesellschaft").text)
    assert "1 Freigabe" in zeilen["a"] and "Freigabe" not in zeilen["b"]
    assert "0 zu prüfen" in zeilen["b"]
    jan = _zeilen(welt.angemeldet("jan").get("/gesellschaft").text)
    assert "Freigabe" not in jan["a"] + jan["b"]


def test_nicht_erreichbare_gesellschaft_bricht_die_seite_nicht(
    welt, monkeypatch, caplog
):
    from accounti.api import geruest

    echte = geruest.zaehle

    async def kaputt(lesezugriff, url, funktionen, frist=None):  # noqa: ANN001, ANN202
        if url == welt.umgebung.db["b"]:
            raise RuntimeError("geheim-4711")
        return await echte(lesezugriff, url, funktionen, frist)

    monkeypatch.setattr(geruest, "zaehle", kaputt)
    r = welt.angemeldet("jan").get("/gesellschaft")
    assert r.status_code == 200
    zeilen = _zeilen(r.text)
    assert "nicht erreichbar" in zeilen["b"] and "nicht erreichbar" not in zeilen["a"]
    assert "geheim-4711" not in caplog.text


def test_haengende_gesellschaft_haelt_die_seite_nicht_auf(welt, monkeypatch):
    import threading
    import time

    from accounti.api import lesezugriff
    from accounti.buchung import pruefschlange

    frei = threading.Event()
    echte = pruefschlange.anzahl_offen

    def haengt(s):  # noqa: ANN001, ANN202
        if "b.db" in str(s.get_bind().url):
            frei.wait(10)
        return echte(s)

    monkeypatch.setattr(lesezugriff, "FRIST", 0.5)
    jan = welt.angemeldet("jan")
    jan.app.state.navigation = [
        p if p.zaehler is not pruefschlange.anzahl_offen else _mit(p, haengt)
        for p in jan.app.state.navigation
    ]
    try:
        beginn = time.monotonic()
        r = jan.get("/gesellschaft")
        dauer = time.monotonic() - beginn
    finally:
        frei.set()
    assert r.status_code == 200 and dauer < 3
    zeilen = _zeilen(r.text)
    assert "nicht erreichbar" in zeilen["b"] and "0 zu prüfen" in zeilen["a"]


def _mit(punkt, zaehler):  # noqa: ANN001, ANN202
    from dataclasses import replace

    return replace(punkt, zaehler=zaehler)


def test_fehlende_datenbankdatei_wird_nicht_angelegt(welt):
    from pathlib import Path

    datei = Path(welt.umgebung.db["b"].removeprefix("sqlite:///"))
    datei.unlink()
    r = welt.angemeldet("jan").get("/gesellschaft")
    assert r.status_code == 200
    assert "nicht erreichbar" in _zeilen(r.text)["b"]
    assert not datei.exists()


@pytest.mark.parametrize("fall", ["keine_sqlite_datei", "tabellen_fehlen"])
def test_kaputte_datenbank_ist_nicht_erreichbar(welt, fall):
    """P1 Runde 2 (gp1-sicherheit N2): Ist die Datei keine SQLite-Datenbank oder fehlen
    die Tabellen, scheiterte jeder Zähler einzeln — die Zeile zeigte still nichts.
    Scheitern alle Zähler einer Gesellschaft, gilt sie als „nicht erreichbar“."""
    import sqlite3
    from pathlib import Path

    datei = Path(welt.umgebung.db["b"].removeprefix("sqlite:///"))
    if fall == "keine_sqlite_datei":
        datei.write_bytes(b"kaputt" * 1000)
    else:
        v = sqlite3.connect(datei)
        v.execute("DROP TABLE buchungssaetze")
        v.execute("DROP TABLE zahlungslaeufe")
        v.commit()
        v.close()
    zeilen = _zeilen(welt.angemeldet("jan").get("/gesellschaft").text)
    assert "nicht erreichbar" in zeilen["b"], zeilen["b"]
    assert "nicht erreichbar" not in zeilen["a"] and "0 zu prüfen" in zeilen["a"]


@pytest.mark.parametrize("pfad", ["/gesellschaft", "/menue"])
def test_aktive_gesellschaft_nur_einmal_gezaehlt(welt, monkeypatch, pfad):
    """P1 Runde 2 (gp1-sicherheit N1): /gesellschaft und /menue zählten die aktive
    Gesellschaft zweimal nacheinander (Liste, dann Navigation) — gesperrt hieß das zwei
    Fristen (4–6 s). Die Navigation übernimmt jetzt die Zahlen der Liste: jede
    Datenbank wird je Seite einmal gefragt, die Seite wartet höchstens eine Frist."""
    from accounti.api import geruest

    echte = geruest.zaehle
    gefragt: list[str] = []

    async def zaehlt(lesezugriff, url, funktionen, frist=None):  # noqa: ANN001, ANN202
        gefragt.append(url)
        return await echte(lesezugriff, url, funktionen, frist)

    monkeypatch.setattr(geruest, "zaehle", zaehlt)
    _vorschlaege(welt, "a", 2)
    r = welt.angemeldet("jan").get(pfad)
    assert r.status_code == 200
    assert sorted(gefragt) == sorted(welt.umgebung.db[k] for k in ("a", "b")), gefragt
    assert '<span class="zaehler zaehler-betont">2<' in r.text  # Navigation wie bisher


def test_gesellschaft_fragment_mit_hx_request(welt):
    jan = welt.angemeldet("jan")
    teil = jan.get("/gesellschaft", headers={"HX-Request": "true"})
    assert teil.status_code == 200 and "<html" not in teil.text
    assert "<h1>" in teil.text and 'class="gruppenliste gesellschaften"' in teil.text
    assert "<html" in jan.get("/gesellschaft").text


def test_wechsel_per_post(welt):
    jan = welt.angemeldet("jan")
    r = jan.post(
        "/gesellschaft",
        data={"csrf": csrf(jan), "kuerzel": "b"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert 'data-gesellschaft="b"' in jan.get("/").text
    fremd = welt.angemeldet("ole")
    r = fremd.post("/gesellschaft", data={"csrf": csrf(fremd), "kuerzel": "b"})
    assert r.status_code == 403
