"""Regelvorschau und gelernte Regeln im Browser (Spec 4.2; Baustein 10b, Paket 3)."""

from __future__ import annotations

from datetime import date

import pytest

from accounti.db.repo_kontierung import lade_kontierungsregeln
from accounti.models.auth import ROLLEN_RECHTE, Recht, Rolle
from tests.api_hilfe import csrf
from tests.auth_hilfe import billige_hashes
from tests.pruefen_hilfe import queuewelt, stand_aus

HX = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def qw(tmp_path):
    return queuewelt(tmp_path)


def vorschau(client, b, kopf=None, **felder):  # noqa: ANN001, ANN003, ANN201
    daten = {
        "csrf": csrf(client),
        "soll": "4930",
        "haben": "1200",
        "steuer": "9",
        "muster": "Bürobedarf",
        "feld": "beide",
    }
    daten.update(felder)
    return client.post(f"/pruefen/{b.id}/regelvorschau", data=daten, headers=kopf or {})


def regeln(qw, kuerzel="a"):  # noqa: ANN001, ANN201
    with qw.fabrik(kuerzel)() as s:
        return lade_kontierungsregeln(s)


def test_vorschau_fragment_und_ohne_js(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    r = vorschau(client, b, HX)
    assert r.status_code == 200 and "<html" not in r.text
    assert "Trifft 1 Ausgabe in den letzten 24 Monaten" in r.text
    assert "greift für diesen Umsatz" in r.text
    r = vorschau(client, b)  # ohne JS: ganze Seite mit Vorschau und Eingaben
    assert "<html" in r.text and "Trifft 1 Ausgabe" in r.text
    assert 'name="regel" value="1" data-taste="r" checked' in r.text
    assert regeln(qw) == []  # die Vorschau speichert nichts


def test_fokus_nach_der_vorschau(qw):
    """A104 (P1 Runde 2): htmx sperrt „Regelvorschau“ während der Anfrage
    (``hx-disabled-elt``) — ein gesperrter Knopf verliert in Chromium den Fokus an
    ``body``. Das Ergebnis trägt im Fragment ``tabindex="-1"`` und ``data-fokus``
    (accounti.js setzt den Fokus darauf), auch die Fehlermeldung; die ganze Seite ohne
    JavaScript nicht."""
    import re

    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    teil = vorschau(client, b, HX).text
    (fokus,) = re.findall(r"<div [^>]*data-fokus[^>]*>", teil)
    assert 'class="vorschau"' in fokus and 'tabindex="-1"' in fokus
    fehler = vorschau(client, b, HX, haben="4980").text
    assert re.search(r'<div tabindex="-1" data-fokus><div class="hinweis', fehler)
    assert "data-fokus" not in vorschau(client, b).text.split('id="regelvorschau"')[1]


def test_vorschau_nur_per_post(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    assert client.get(f"/pruefen/{b.id}/regelvorschau?muster=x").status_code == 405


def test_vorschau_ohne_recht_403(qw):
    b = qw.unsicher()
    for wer in ("leo", "fritz"):
        assert vorschau(qw.web.angemeldet(wer), b).status_code == 403, wer
    assert vorschau(qw.web.angemeldet("vera"), b).status_code == 200


def test_vorschau_zeigt_richtung_und_gegenrichtung(qw):
    b = qw.unsicher()
    qw.umsatz("12.00", date(2026, 9, 5), "Gutschrift", "Bürobedarf Müller GmbH")
    qw.umsatz("-20.00", date(2026, 9, 6), "Nachkauf", "Bürobedarf Müller GmbH")
    r = vorschau(qw.web.angemeldet("jan"), b, HX)
    assert "Trifft 2 Ausgaben in den letzten 24 Monaten" in r.text
    assert "Gegenrichtung (höchstens als Gegenbuchung zur Prüfung): 1" in r.text


def test_korrektur_mit_regel_ohne_recht_403_und_nichts_gespeichert(qw, monkeypatch):
    b = qw.unsicher()
    ohne = {**ROLLEN_RECHTE}
    ohne[Rolle.BUCHHALTER] = ROLLEN_RECHTE[Rolle.BUCHHALTER] - {Recht.REGELN_LERNEN}
    monkeypatch.setattr("accounti.models.auth.ROLLEN_RECHTE", ohne)
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    assert 'name="regel"' not in seite  # kein Angebot ohne Recht
    r = client.post(
        f"/pruefen/{b.id}/korrigieren",
        data={
            "csrf": csrf(client),
            "stand": stand_aus(seite),
            "soll": "4930",
            "haben": "1200",
            "steuer": "9",
            "regel": "1",
            "muster": "Bürobedarf",
        },
    )
    assert r.status_code == 403
    assert regeln(qw) == []
    (status,) = qw.sql("SELECT status FROM buchungssaetze")[0]
    assert status == "pruefung"


def test_regeln_liste_und_deaktivieren(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    r = client.post(
        f"/pruefen/{b.id}/korrigieren",
        data={
            "csrf": csrf(client),
            "stand": stand_aus(seite),
            "soll": "4930",
            "haben": "1200",
            "steuer": "9",
            "regel": "1",
            "muster": "Bürobedarf",
            "feld": "beide",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    (regel,) = regeln(qw)
    liste = client.get("/pruefen/regeln").text
    assert regel.name in liste and "Ausgabe" in liste and "jan" in liste
    assert f"/pruefen/regeln/{regel.id}/deaktivieren" in liste
    r = client.post(
        f"/pruefen/regeln/{regel.id}/deaktivieren",
        data={"csrf": csrf(client), "grund": "trifft auch Privatkäufe"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].endswith(
        "erledigt=deaktiviert"
    )
    (aus,) = regeln(qw)
    assert not aus.aktiv and aus.deaktiviert_von == "jan"
    r = client.post(
        f"/pruefen/regeln/{regel.id}/deaktivieren",
        data={"csrf": csrf(client), "grund": "nochmal"},
    )
    assert r.status_code == 409 and "schon deaktiviert" in r.text
    leer = client.post(
        f"/pruefen/regeln/{regel.id}/deaktivieren",
        data={"csrf": csrf(client), "grund": ""},
    )
    assert leer.status_code in (409, 422)


def test_verwalter_deaktiviert(qw):
    from accounti.klassifikation.lernen import lerne_regex

    with qw.fabrik()() as s:
        r = lerne_regex(s, "telekom", "telekom", "4920", "1200", 9, "jan")
        s.commit()
    vera = qw.web.angemeldet("vera")
    liste = vera.get("/pruefen/regeln").text
    assert f"/pruefen/regeln/{r.id}/deaktivieren" in liste
    antwort = vera.post(
        f"/pruefen/regeln/{r.id}/deaktivieren",
        data={"csrf": csrf(vera), "grund": "zu breit"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    leo = qw.web.angemeldet("leo")
    assert f"/pruefen/regeln/{r.id}/deaktivieren" not in leo.get("/pruefen/regeln").text
    andere = leo.post(
        f"/pruefen/regeln/{r.id}/deaktivieren", data={"csrf": csrf(leo), "grund": "x"}
    )
    assert andere.status_code == 403


def test_regel_anderer_gesellschaft_404(qw):
    from accounti.klassifikation.lernen import lerne_regex

    with qw.fabrik("b")() as s:
        r = lerne_regex(s, "telekom", "telekom", "6805", "1800", 9, "jan")
        s.commit()
    client = qw.web.angemeldet("jan")  # aktiv: a
    antwort = client.post(
        f"/pruefen/regeln/{r.id}/deaktivieren",
        data={"csrf": csrf(client), "grund": "x"},
    )
    assert antwort.status_code == 404
    assert regeln(qw, "b")[0].aktiv


def test_muster_mit_markup_escaped(qw):
    b = qw.unsicher(name="<b>Böse</b> GmbH")
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    assert "<b>Böse</b>" not in seite and "&lt;b&gt;Böse&lt;/b&gt;" in seite
    r = vorschau(client, b, HX, muster="<script>x</script>")
    assert "<script>x</script>" not in r.text and "&lt;script&gt;" in r.text


def test_standardmuster_trifft_keine_fremde_gegenpartei(qw):
    """Nachbesserung H1 (Probe P2-1): Vorbelegt ist der ganze Name der Gegenpartei
    ohne Rechtsform — die gelernte Regel bucht beim nächsten Lauf die Telekom, nicht
    die Deutsche Bahn oder die Rentenversicherung."""
    b = qw.unsicher(
        betrag="-39.95", zweck="Rechnung 10/2026", name="Deutsche Telekom AG"
    )
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    from tests.api_hilfe import formularwert

    assert formularwert(seite, "muster") == "Deutsche Telekom"
    r = client.post(
        f"/pruefen/{b.id}/korrigieren",
        data={
            "csrf": csrf(client), "stand": stand_aus(seite), "soll": "4920",
            "haben": "1200", "steuer": "9", "regel": "1",
            "muster": formularwert(seite, "muster"), "feld": "beide",
        },
        follow_redirects=False,
    )  # fmt: skip
    assert r.status_code == 303, r.text
    telekom = qw.umsatz(
        "-39.95", date(2026, 10, 20), "Rechnung 11/2026", "Deutsche Telekom AG"
    )
    bahn = qw.umsatz("-80.00", date(2026, 10, 20), "Fahrkarte", "Deutsche Bahn AG")
    from accounti.buchung.kontierung import kontiere_umsaetze
    from accounti.db.repository import lade_buchungen
    from accounti.klassifikation.engine import KlassifikationsEngine
    from accounti.klassifikation.lernen import lade_regelwerk
    from accounti.konfiguration import Buchhaltung
    from tests.pruefen_hilfe import LLMAttrappe

    with qw.fabrik()() as s:  # der nächste Lauf: gelernte Regeln vor dem LLM
        werk = lade_regelwerk(s, None, "automatisch")
        engine = KlassifikationsEngine(regelwerk=werk, llm=LLMAttrappe())  # type: ignore[arg-type]
        kontiere_umsaetze(s, engine, Buchhaltung())
        s.commit()
        neu = {x.transaktion_id: x for x in lade_buchungen(s)}
    assert neu[telekom.id].soll_konto == "4920" and neu[telekom.id].confidence == 1.0
    assert neu[bahn.id].soll_konto == "4980"  # LLM-Vorschlag, nicht die Regel


def test_breites_muster_422_mit_vorschau_und_bestaetigung(qw):
    """Nachbesserung H1: „Deutsche“ träfe die Deutsche Bahn — ohne Bestätigung 422
    mit Vorschau (andere Gegenparteien, Haken „trotzdem speichern“), nichts
    gespeichert; mit dem Haken für genau dieses Muster gespeichert."""
    qw.umsatz("-80.00", date(2026, 9, 1), "Fahrkarte 4711", "Deutsche Bahn AG")
    b = qw.unsicher(
        betrag="-39.95", zweck="Rechnung 10/2026", name="Deutsche Telekom AG"
    )
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {
        "csrf": csrf(client), "stand": stand_aus(seite), "soll": "4920",
        "haben": "1200", "steuer": "9", "regel": "1", "muster": "Deutsche",
        "feld": "beide", "ansicht": "offen",
    }  # fmt: skip
    r = client.post(f"/pruefen/{b.id}/korrigieren", data=daten, headers=HX)
    assert r.status_code == 422
    assert "Deutsche Bahn AG" in r.text and "andere Gegenparteien" in r.text
    assert 'name="regel_bestaetigt" value="Deutsche"' in r.text
    assert regeln(qw) == []
    (status,) = qw.sql("SELECT status FROM buchungssaetze WHERE id = :i", i=str(b.id))[
        0
    ]
    assert status == "pruefung"
    # ein für ein anderes Muster gesetzter Haken gilt nicht
    falsch = {**daten, "regel_bestaetigt": "Deutsch"}
    assert client.post(f"/pruefen/{b.id}/korrigieren", data=falsch).status_code == 422
    r = client.post(
        f"/pruefen/{b.id}/korrigieren",
        data={**daten, "regel_bestaetigt": "Deutsche"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    (regel,) = regeln(qw)
    assert regel.muster == "Deutsche"


def test_ohne_namen_der_gegenpartei_422_mit_vorschau_und_bestaetigung(qw):
    """Nachbesserung H-1 (Probe q1, Fall 3): Ohne Namen der Gegenpartei ist der
    Vorschlag das erste Wort des Verwendungszwecks — „Lastschrift“ träfe die
    Rentenversicherung. Ohne Bestätigung 422 mit Vorschau (der andere Umsatz mit
    seinem Verwendungszweck, Haken), mit dem Haken gespeichert."""
    qw.umsatz(
        "-450.00", date(2026, 9, 10), "Lastschrift Beitrag Rentenversicherung", None
    )
    b = qw.unsicher(betrag="-39.95", zweck="Lastschrift Fachverband 10/2026", name=None)
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    assert 'value="Lastschrift"' in seite  # Vorschlag im Formular
    daten = {
        "csrf": csrf(client), "stand": stand_aus(seite), "soll": "4920",
        "haben": "1200", "steuer": "9", "regel": "1", "muster": "Lastschrift",
        "feld": "beide", "ansicht": "offen",
    }  # fmt: skip
    r = client.post(f"/pruefen/{b.id}/korrigieren", data=daten, headers=HX)
    assert r.status_code == 422
    assert "keinen Namen der Gegenpartei" in r.text
    assert "Lastschrift Beitrag Rentenversicherung" in r.text
    assert 'name="regel_bestaetigt" value="Lastschrift"' in r.text
    assert regeln(qw) == []
    r = client.post(
        f"/pruefen/{b.id}/korrigieren",
        data={**daten, "regel_bestaetigt": "Lastschrift"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    (regel,) = regeln(qw)
    assert regel.muster == "Lastschrift"


def test_vorschau_mit_finanzkonto_ausserhalb_422(qw):
    b = qw.unsicher()
    r = vorschau(qw.web.angemeldet("jan"), b, HX, haben="4980")
    assert r.status_code == 422 and "Finanzkonto 1200" in r.text


def test_vorschau_gegenrichtung_zaehlt_ihre_eigenen_anders_gebuchten(qw):
    """gw-regeln N-1 (Probe test_s4_web::test_c): drei Ausgaben derselben
    Gegenpartei sind heute anders gebucht (LLM 4980), eine Gegenrichtung gibt es
    nicht — die Zeile der Gegenrichtung nannte trotzdem „davon … anders gebucht: 3“."""
    for i in range(3):
        qw.umsatz(betrag="-10.00", tag=date(2026, 9, 1 + i), zweck=f"RE {i}")
    qw.kontiere()
    b = qw.unsicher(tag=date(2026, 10, 2))
    r = vorschau(qw.web.angemeldet("jan"), b, HX, muster="Bürobedarf Müller")
    assert r.status_code == 200, r.text
    assert (
        "Gegenrichtung (höchstens als Gegenbuchung zur Prüfung): 0, davon heute "
        "anders gebucht: 0" in r.text
    )
    assert "3 weitere Treffer sind heute anders gebucht" in r.text
