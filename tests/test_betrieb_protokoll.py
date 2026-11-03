"""Protokollierung ohne personenbezogene Inhalte (Spec 4.6, Teststrategie)."""

import io
import json
import logging

import pytest

from accounti.betrieb.protokoll import richte_protokoll_ein, schwaerze
from accounti.models.auth import Rolle, TokenRecht
from tests.api_hilfe import melde_an, webwelt
from tests.auth_hilfe import PASSWORT, billige_hashes
from tests.pdf_hilfe import pdf_mit_text

IBAN = "DE89 3704 0044 0532 0130 00"


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def ausgabe():
    puffer = io.StringIO()
    wurzel = logging.getLogger()
    vorher = (wurzel.handlers[:], wurzel.level)
    richte_protokoll_ein("DEBUG", "text", puffer)
    yield puffer
    wurzel.handlers, stufe = vorher
    wurzel.setLevel(stufe)


@pytest.mark.parametrize(
    ("roh", "darf_nicht"),
    [
        (f"Zahlung an {IBAN} geprüft", "3704"),
        ("IBAN DE89370400440532013000", "370400440532013000"),
        ("Mail an erika.muster@galerie.example", "erika.muster"),
        ("Authorization: Bearer abc.def-ghi", "abc.def-ghi"),
        ("Token accounti_api_Zx9-geheim_123", "Zx9-geheim"),
        ("postgresql+psycopg://accounti:sehr-geheim@db/acc", "sehr-geheim"),
        ("GET /x?passwort=hunter2&einmalcode=123456", "hunter2"),
        ("GET /x?token=abcdef", "abcdef"),
        # Runde 6 (g5w-konten N1): Zugangsdaten jeder URL, auch unkodiert oder
        # vom Zeilenumbruch (Rich, 80 Zeichen) zerschnitten
        ("Webhook https://alarm:Kassel#2026@hooks.example.invalid/hook", "Kassel"),
        ("Webhook https://alarm:Wint3r?Sonne@hooks.example.invalid/hook", "Wint3r"),
        ("Webhook https://alarm:Wint3r%3FSonne@hooks.example.invalid/x", "Wint3r"),
        ("https://accounti:sehr-geheim@hooks.example/x", "accounti:"),
        ("Webhook https://alarm:Kassel/… nicht zustellbar", "Kassel"),
        (
            "Webhook https://accounti:github_pat_11ABCDEFG0123456789_abcdefghijkl"
            " mnopqrstuvwxyzABCDEF0123456789abcd@hooks.example.invalid/…",
            "github_pat_11",
        ),
        # Runde 7 (g6w B-2): Ziffern vor „#“ sind kein Port, auch ohne Schema
        ("Webhook https://alarm:4711#Sonne@hooks.example.invalid/hook", "4711"),
        ("Webhook https://alarm:4711#Sonne@hooks.example.invalid/hook", "alarm"),
        ("Webhook https://alarm:4711#Sonne nicht zustellbar", "4711"),
        ("Webhook https://alarm:4711#Sonne nicht zustellbar", "Sonne"),
        ("Webhook https://alarm:1234?abc@hooks.example/x", "1234"),
        ("Rest alarm:4711#Sonne@hooks.example.invalid/hook", "4711"),
        ("Rest alarm:4711#Sonne@hooks.example.invalid/hook", "alarm"),
        ("Token ghp_abcdefghijklmnopqrstuvwxyz0123456789", "abcdefghijklmnop"),
        ("passwort: hunter2", "hunter2"),
        ("Password = hunter2", "hunter2"),
        ("PIN=12345 falsch", "12345"),
        ("PIN: 12345 falsch", "12345"),
        ("TAN 123456 abgelaufen", "123456"),
    ],
)
def test_schwaerzung(roh, darf_nicht):
    assert darf_nicht not in schwaerze(roh)


@pytest.mark.parametrize(
    "roh",
    [
        "GET https://hooks.example:8443/services → 200",
        "http://127.0.0.1:8080/x",
        "Buchung 4fec6038 an 1200, Kz 81: 500,00",
        "sha256 fa34e1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e",
        "Pin-Liste geladen",
    ],
)
def test_schwaerzung_laesst_harmloses(roh):
    assert schwaerze(roh) == roh


def test_filter_gilt_fuer_alle_logger_und_ausnahmen(ausgabe):
    logging.getLogger("accounti.irgendwas").info("Konto %s", IBAN)
    try:
        raise ValueError(f"kaputt bei {IBAN}")
    except ValueError:
        logging.getLogger("uvicorn.error").exception("Fehler")
    text = ausgabe.getvalue()
    assert "3704" not in text
    assert "[IBAN]" in text and "ValueError" in text


def test_json_format():
    puffer = io.StringIO()
    wurzel = logging.getLogger()
    vorher = (wurzel.handlers[:], wurzel.level)
    try:
        richte_protokoll_ein("INFO", "json", puffer)
        logging.getLogger("accounti.test").info("an %s", "x@y.example")
        zeile = json.loads(puffer.getvalue().strip())
    finally:
        wurzel.handlers, stufe = vorher
        wurzel.setLevel(stufe)
    assert zeile["logger"] == "accounti.test"
    assert zeile["text"] == "an [E-Mail]"


def test_durchlauf_ohne_personenbezogene_inhalte_im_protokoll(tmp_path, ausgabe):
    """Anmeldung, Seiten, API mit Namen, IBAN, Token, Passwort — nichts davon im Log."""
    welt = webwelt(tmp_path)
    welt.person("erika.muster", Rolle.FREIGEBER)
    token = welt.token("a", TokenRecht.OPOS_LESEN, TokenRecht.BELEGE_SCHREIBEN)
    client = welt.client()
    melde_an(client, "erika.muster", "falsches Passwort!", "000000")
    welt.anmelden(client, "erika.muster")
    client.get("/", params={"suche": "Alpha Papier GmbH", "iban": IBAN})
    client.get("/freigaben")
    kopf = {"Authorization": f"Bearer {token}"}
    client.get(
        "/api/v1/offene-posten", headers=kopf, params={"kontakt": "Alpha Papier"}
    )
    client.post(
        "/api/v1/belege",
        headers={
            **kopf,
            "X-Dateiname": "rechnung-alpha.pdf",
            "X-Absender": "erika.muster@galerie.example",
        },
        content=pdf_mit_text(f"Rechnung Alpha Papier GmbH IBAN {IBAN}"),
    )
    text = ausgabe.getvalue()
    assert "GET /freigaben 200" in text  # es wird protokolliert …
    for geheim in (
        "erika",
        "Alpha",
        "3704",
        token,
        token[-10:],
        PASSWORT,
        "falsches Passwort",
        "rechnung-alpha",
        "galerie.example",
        "suche=",
        "testclient",  # Client-Adresse
    ):
        assert geheim not in text, geheim


def test_zugriffsprotokoll_mit_routenvorlage_statt_pfad(tmp_path, ausgabe):
    """Befund A-N1: der dekodierte Pfad unbekannter Anfragen kam wörtlich ins
    Protokoll — Namen und per ``%0A`` gefälschte Zeilen. Jetzt die Vorlage der Route
    (``/freigaben/zahlungslauf/{nr}``), unbekannte Pfade nur als ``(unbekannt)``."""
    welt = webwelt(tmp_path)
    client = welt.client()
    client.get(
        "/api/v1/kunden/Max%20Mustermann%0A2026-10-21 09:00:00,000 INFO "
        "accounti.zugriff: POST /freigaben/zahlungslauf/1 303 5 ms"
    )
    client.post("/freigaben/zahlungslauf/4711", follow_redirects=False)
    client.get("/statisch/accounti.css")
    zeilen = [z for z in ausgabe.getvalue().splitlines() if "accounti.zugriff" in z]
    text = "\n".join(zeilen)
    assert len(zeilen) == 3, text
    assert "Mustermann" not in text and "4711" not in text
    assert "GET (unbekannt) 404" in text
    assert "POST /freigaben/zahlungslauf/{nr} 303" in text
    assert "GET /statisch/accounti.css 200" in text


def test_datenbankfehler_ohne_werte_im_protokoll(tmp_path, ausgabe):
    """Befund B-M7/A-N2: SQLAlchemy hängt ``[parameters: …]`` an die Meldung —
    Engines verbergen die Werte, und die App protokolliert unbehandelte Ausnahmen
    nur mit ihrer Art (500 ohne Traceback)."""
    from datetime import date, datetime

    from fastapi.testclient import TestClient
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError

    from accounti.api.app import erstelle_app
    from accounti.db import session_factory
    from accounti.db.repository import speichere_beleg
    from accounti.db.tabellen import BelegRow
    from accounti.models import Beleg
    from tests.api_hilfe import BASIS

    welt = webwelt(tmp_path)
    beleg = Beleg(
        datei_hash="0" * 64,
        dateiname="Rechnung Max Mustermann Zahnarzt.pdf",
        kanal="api",
        herkunft="API-Token erp von Erika Musterfrau",
        eingegangen_am=datetime(2026, 1, 1),
        aufbewahren_bis=date(2036, 12, 31),
    )
    with welt.dienste.datenbank("a") as s:
        speichere_beleg(s, beleg)
        s.commit()
        zeile = {
            c.name: getattr(s.get(BelegRow, str(beleg.id)), c.key)
            for c in BelegRow.__table__.columns
        }
    # 1. die Meldung der Datenbank selbst enthält keine Werte mehr
    engine, fabrik = session_factory(welt.umgebung.db["a"])
    with fabrik() as s:
        try:
            s.execute(insert(BelegRow), [zeile])
            s.commit()
        except IntegrityError as fehler:
            meldung = str(fehler)
        else:  # pragma: no cover
            pytest.fail("doppelter Schlüssel ohne Fehler")
    engine.dispose()
    assert "Mustermann" not in meldung and "Musterfrau" not in meldung
    # 2. eine fehlschlagende Anfrage: 500, im Protokoll nur die Art
    app = erstelle_app(welt.dienste)

    def kaputt() -> None:
        with welt.dienste.datenbank("a") as s:
            s.execute(insert(BelegRow), [zeile])

    app.add_api_route("/kaputt", kaputt)
    r = TestClient(app, base_url=BASIS).get("/kaputt")
    assert r.status_code == 500
    assert "Mustermann" not in r.text
    text = ausgabe.getvalue()
    assert "IntegrityError" in text
    for geheim in ("Mustermann", "Zahnarzt", "Musterfrau", "INSERT INTO"):
        assert geheim not in text, geheim


def test_queue_belege_ohne_belegtexte_im_protokoll(tmp_path, ausgabe, monkeypatch):
    """Baustein 10b (PR 10b-1: Queue und Belege; die Auswertungen folgen mit 10b-2):
    Durchlauf mit unverwechselbaren Markern in Verwendungszweck, Lieferant,
    Begründung, Belegdatei, E-Rechnung, Regelmuster, Rückfrage und Einmalcode — die
    Protokollausgabe enthält keinen davon, auch nicht bei 409/404/422/503/500; im
    Zugriffsprotokoll stehen Routenvorlagen."""
    from pathlib import Path

    from sqlalchemy.exc import OperationalError

    from accounti.db.repo_kontierung import speichere_kontierungsgrund
    from accounti.models import BuchungStatus
    from tests.api_hilfe import csrf, formularwert
    from tests.pruefen_hilfe import pdf, queuewelt, stand_aus

    qw = queuewelt(tmp_path)
    marker = "QXZ"
    b = qw.unsicher(name=f"{marker}lieferant GmbH", zweck=f"{marker}zweck 4711")
    with qw.fabrik()() as s:
        speichere_kontierungsgrund(
            s, b.id, quelle="llm", begruendung=f"{marker}begruendung"
        )
        s.commit()
    beleg = qw.beleg(pdf(f"{marker}inhalt"), dateiname=f"{marker}datei.pdf")
    xml = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "erechnung"
        / "xrechnung_ubl.xml"
    ).read_text(encoding="utf-8")
    erechnung = qw.beleg(
        xml.replace("Lieferant", f"{marker}erechnung").encode(), ".xml"
    )
    frei = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=qw_tag())
    jan = qw.web.angemeldet("jan")
    seite = jan.get(f"/pruefen/{b.id}").text
    for pfad in (
        f"/belege/{beleg.id}",
        f"/belege/{beleg.id}/datei",
        f"/belege/{erechnung.id}",
    ):
        jan.get(pfad)
    jan.post(
        f"/pruefen/{b.id}/regelvorschau",
        data={"csrf": csrf(jan), "muster": f"{marker}muster", "soll": "4930"},
    )
    jan.post(  # 422: Sachkontowechsel ohne Steuerangabe
        f"/pruefen/{b.id}/korrigieren",
        data={
            "csrf": csrf(jan),
            "stand": stand_aus(seite),
            "soll": "4360",
            "haben": "1200",
        },
    )
    jan.post(  # 409: veralteter Stand
        f"/pruefen/{b.id}/freigeben", data={"csrf": csrf(jan), "stand": "veraltet"}
    )
    jan.post(
        f"/pruefen/{b.id}/zurueckstellen",
        data={
            "csrf": csrf(jan),
            "stand": stand_aus(seite),
            "text": f"{marker}rueckfrage",
        },
    )
    seite = jan.get(f"/buchungen/{frei.id}").text
    jan.post(  # 403: falscher Einmalcode
        f"/buchungen/{frei.id}/stornieren",
        data={
            "csrf": csrf(jan),
            "stand": formularwert(seite, "stand"),
            "grund": f"{marker}grund",
            "einmalcode": f"{marker}123",
        },
    )
    from uuid import uuid4

    assert jan.get(f"/belege/{uuid4()}").status_code == 404
    from accounti.api.seiten import pruefen as seite_pruefen

    def beschaeftigt(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise OperationalError(
            f"UPDATE {marker}sql", {}, Exception("database is locked")
        )

    monkeypatch.setattr(seite_pruefen, "lade_pruefschlange", beschaeftigt)
    assert jan.get("/pruefen").status_code == 503
    monkeypatch.setattr(
        seite_pruefen,
        "lade_pruefschlange",
        lambda *a, **k: (_ for _ in ()).throw(ValueError(f"{marker}fehler")),
    )
    assert jan.get("/pruefen").status_code == 500
    text = ausgabe.getvalue()
    assert "POST /pruefen/{buchung_id:uuid}/korrigieren 422" in text
    assert "POST /pruefen/{buchung_id:uuid}/freigeben 409" in text
    assert "GET /pruefen 503" in text and "GET /pruefen 500" in text
    assert marker not in text and marker.lower() not in text, text
    assert str(b.id) not in text and str(beleg.id) not in text


def qw_tag():  # noqa: ANN201
    from datetime import date

    return date(2026, 10, 2)


# --- Runde 8 (g7w): lange Eingaben, Überschwärzung, „/“ im Passwort ----------------


@pytest.mark.parametrize("laenge", [15_000, 40_000])
def test_langer_statischer_pfad_haelt_den_server_nicht_an(tmp_path, ausgabe, laenge):
    """DoS-1 (g7w, schon auf main): ``GET /statisch/<15 000 Zeichen>`` ohne Anmeldung
    schrieb den Pfad ganz ins Zugriffsprotokoll; die Schwärzung brauchte dafür im
    Event-Loop 5 s (40 000 Zeichen: 36 s), jede andere Anfrage wartete. Jetzt steht der
    Pfad gekürzt im Protokoll, und die Anfrage dauert nicht länger als sonst."""
    import time

    client = webwelt(tmp_path).client()
    client.get("/statisch/accounti.css")
    beginn = time.perf_counter()
    r = client.get("/statisch/" + "a" * laenge)
    dauer = time.perf_counter() - beginn
    assert r.status_code == 404
    (zeile,) = [z for z in ausgabe.getvalue().splitlines() if " 404 " in z]
    assert "GET /statisch/aaaa" in zeile and "…" in zeile, zeile
    assert len(zeile) < 400, len(zeile)
    assert dauer < 0.5, dauer  # vorher 5 s bzw. 36 s


@pytest.mark.parametrize(
    "folge",
    ["a", "a.", "#", "a%", "a@", "@a.", "a:", "a:a@", "a1", "https://a", "x://", "-"],
)
def test_schwaerzungsmuster_ohne_quadratische_laufzeit(folge):
    """DoS-1: Die Muster probierten jede Stelle einer langen Zeichenfolge ohne Leerraum
    und liefen dort bis zum Ende — quadratisch (15 000 × „a“: 5 s). Jedes Muster für
    sich, ohne die Kürzung in ``schwaerze``: 100 000 Zeichen, ohne und mit „@“."""
    import time

    from accounti.betrieb.protokoll import _MUSTER

    text = "GET /statisch/" + (folge * 100_000)[:100_000] + " 404 1 ms"
    for muster, ersatz in _MUSTER:
        beginn = time.perf_counter()
        muster.sub(ersatz, text)
        dauer = time.perf_counter() - beginn
        assert dauer < 0.25, (muster.pattern, dauer)  # gemessen: ~10 ms


def test_schwaerzung_kuerzt_ueberlange_zeilen_vor_den_mustern():
    """Zweite Ebene gegen DoS-1: Eine Zeile über ``ZEILE_HOECHSTENS`` Zeichen verliert
    ihre Mitte, bevor ein Muster sie sieht — Anfang und Ende bleiben, der Rest der
    Meldung (andere Zeilen) auch."""
    import time

    from accounti.betrieb.protokoll import ZEILE_HOECHSTENS

    lang = "Anfang " + "x" * 200_000 + " Ende"
    beginn = time.perf_counter()
    text = schwaerze(f"erste Zeile\n{lang}\nletzte Zeile an a@b.example")
    assert time.perf_counter() - beginn < 0.5
    erste, mitte, letzte = text.split("\n")
    assert erste == "erste Zeile" and letzte == "letzte Zeile an [E-Mail]"
    assert mitte.startswith("Anfang") and mitte.endswith("Ende"), mitte[:80]
    assert "gekürzt" in mitte and len(mitte) <= ZEILE_HOECHSTENS


@pytest.mark.parametrize(
    ("geheimnis", "darf_nicht"),
    [
        (IBAN, "3704"),
        ("Bearer " + "eyJ" + "k" * 3000, "kkkkkkkk"),
        ("https://accounti:sehr-geheim@hooks.example/x", "sehr-geheim"),
        ("passwort=hunter2", "hunter2"),
        ("PIN: 12345", "12345"),
    ],
    ids=["iban", "bearer", "url", "parameter", "pin"],
)
def test_kuerzung_laesst_kein_halbes_geheimnis_stehen(geheimnis, darf_nicht):
    """Erst kürzen, dann schwärzen: Ein Geheimnis an einer Schnittstelle fällt ganz weg
    (sonst bliebe ein angeschnittener Rest stehen, den kein Muster mehr erkennt — etwa
    „DE89 3704“ oder das Ende eines Tokens ohne „Bearer“ davor)."""
    from accounti.betrieb.protokoll import ZEILE_HOECHSTENS

    for stelle in range(0, ZEILE_HOECHSTENS + 1, 25):
        zeile = "w " * (stelle // 2) + geheimnis + " z" * ZEILE_HOECHSTENS
        assert darf_nicht not in schwaerze(zeile), stelle
        zeile = "w " * ZEILE_HOECHSTENS + geheimnis + " z" * (stelle // 2)
        assert darf_nicht not in schwaerze(zeile), stelle
