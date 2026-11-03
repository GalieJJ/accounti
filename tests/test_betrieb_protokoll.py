"""Protokollierung ohne personenbezogene Inhalte (Spec 4.6, Teststrategie)."""

import io
import json
import logging
import re

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


# --- Folgepaket F, Runde 2 (gf-betrieb F-B1): langer Pfad mit jeder Methode ---------


def _scope(app, methode: str, pfad: str, route=None):  # noqa: ANN001, ANN202
    scope = {
        "type": "http",
        "method": methode,
        "path": pfad,
        "raw_path": pfad.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "app": app,
        "scheme": "http",
        "server": ("accounti.test", 80),
    }
    if route is not None:
        scope["route"] = route
    return scope


def test_ansichtspfad_eines_langen_pfads_ohne_quadratische_laufzeit(tmp_path):
    """F-B1 (gf-betrieb, schon auf main): Nach einem POST suchte ``ansichtspfad`` für
    jeden Abschnitt des Pfads alle Routen ab und baute den Pfad neu — quadratisch, im
    Event-Loop, auch für die 404-Seite (8000 Abschnitte: 1 s). Ohne Route (404) gilt
    gleich „/“, mit Route höchstens ``ABSCHNITTE`` Abschnitte; der Weg einer Route
    nach oben bleibt (``/pruefen/{id}/korrigieren`` → ``/pruefen/{id}``)."""
    import time
    from types import SimpleNamespace
    from uuid import uuid4

    from starlette.requests import Request

    from accounti.api.vorlagen import ansichtspfad

    app = webwelt(tmp_path).client().app
    # wie ``scope["route"]`` beim Bearbeiten der Anfrage (gefundene Route)
    route = SimpleNamespace(path="/pruefen/{buchung_id:uuid}/korrigieren")
    for pfad, mit in (("/x" * 20_000, None), ("/pruefen/1" + "/x" * 20_000, route)):
        beginn = time.perf_counter()
        assert ansichtspfad(Request(_scope(app, "POST", pfad, mit))) == "/"
        dauer = time.perf_counter() - beginn
        assert dauer < 0.01, dauer  # vorher mehrere Sekunden
    nr = uuid4()
    anfrage = Request(_scope(app, "POST", f"/pruefen/{nr}/korrigieren", route))
    assert ansichtspfad(anfrage) == f"/pruefen/{nr}"
    assert ansichtspfad(Request(_scope(app, "GET", "/x" * 20_000))) == "/x" * 20_000


@pytest.mark.parametrize(
    "methode", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS", "PROPFIND", "GET", "HEAD"]
)
def test_langer_pfad_haelt_den_server_mit_keiner_methode_an(tmp_path, methode):
    """F-B1: ``POST /x/x/…`` (40 000 Zeichen) ohne Anmeldung hielt den Server an —
    die 404-Seite rechnete ``ansichtspfad`` quadratisch (echter serve: jede andere
    Anfrage wartete 3,7 s). Jede Methode außer GET war betroffen; jetzt sind alle so
    schnell wie GET, angemeldet wie unangemeldet."""
    import time

    welt = webwelt(tmp_path)
    welt.person("jan", Rolle.BUCHHALTER)
    for client in (welt.client(), welt.angemeldet("jan")):
        client.get("/anmelden")
        beginn = time.perf_counter()
        r = client.request(methode, "/x" * 20_000)
        dauer = time.perf_counter() - beginn
        assert r.status_code == 404, r.status_code
        assert dauer < 0.5, dauer  # vorher mehrere Sekunden


def test_lange_sprachangabe_haelt_den_server_nicht_an(tmp_path):
    """Gefunden bei der Suche nach weiteren Stellen wie F-B1 (schon auf main): Das
    Muster für ``Accept-Language`` probierte für jeden Teil jede Aufteilung einer
    Leerraumfolge (16 000 Leerzeichen: 1,2 s, im Event-Loop) — jede Seite, auch
    ``/anmelden`` und die 404-Seite ohne Anmeldung, liest den Kopf."""
    import time

    client = webwelt(tmp_path).client()
    client.get("/anmelden")
    for pfad in ("/anmelden", "/gibt/es/nicht"):
        for kopf in ("de" + " " * 40_000 + ";q=1 x", "en" + "\t" * 40_000 + "x"):
            beginn = time.perf_counter()
            r = client.get(pfad, headers={"Accept-Language": kopf})
            dauer = time.perf_counter() - beginn
            assert r.status_code in (200, 404), r.status_code
            assert '<html lang="de" ' in r.text
            assert dauer < 0.5, (pfad, dauer)  # vorher mehrere Sekunden


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


# Geheimnisse mit kurzen Werten — jeder Wert enthält Ziffern, der Fülltext keine
KANTE = [
    ("bearer", "Authorization: Bearer eyJtok4711geheim"),
    ("passwort", "passwort: hunter4711"),
    ("kennwort", "Kennwort = Sonne4711"),
    ("pin", "PIN: 471147"),
    ("tan", "TAN 123456"),
    ("secret", "secret: s3cr3t4711"),
    ("iban", IBAN),
    ("url", "https://accounti:sehr4711@hooks.example/x"),
]


@pytest.mark.parametrize("geheimnis", [g for _, g in KANTE], ids=[n for n, _ in KANTE])
def test_kuerzung_laesst_kein_halbes_geheimnis_stehen(geheimnis):
    """Erst kürzen, dann schwärzen: Ein Geheimnis an einer Schnittkante fällt ganz weg
    oder erscheint geschwärzt — an **jeder** Lage der vorderen und der hinteren Kante,
    Zeichen für Zeichen (Folgepaket F, g8w B8-1: Die hintere Kante trennte „Bearer“,
    „passwort:“, „PIN“ … von ihrem Wert, der dann ungeschwärzt stand; der Test ging in
    Schritten von 25 und mit einem 3000 Zeichen langen Token vor)."""
    from accounti.betrieb.protokoll import _RAND

    lage = range(-len(geheimnis) - 40, len(geheimnis) + 40)
    for versatz in lage:
        # vordere Kante: das Geheimnis beginnt um „versatz“ vor bzw. hinter ihr
        zeile = ("w " * _RAND)[: _RAND + versatz] + " " + geheimnis + " z" * 3000
        text = schwaerze(zeile)
        assert not re.search(r"\d", text), ("vorn", versatz, text[1300:1700])
        # hintere Kante: ebenso von hinten gezählt
        zeile = "w " * 2500 + geheimnis + (" z" * _RAND)[: _RAND - versatz]
        text = schwaerze(zeile)
        assert not re.search(r"\d", text), ("hinten", versatz, text[-1700:-1300])
    assert "accounti:" not in schwaerze("w " * 2500 + KANTE[-1][1] + " z" * 700)


@pytest.mark.parametrize("wort", ["PIN", "TAN", "passwort", "Kennwort", "Bearer"])
@pytest.mark.parametrize("leer", ["\n", " ", "\t"])
def test_schluesselwort_mit_langer_leerraumfolge_ohne_quadratische_laufzeit(wort, leer):
    """B8-1 (Hinweis g8w): „PIN“ und 8000 Zeilenumbrüche brauchten 0,71 s — das
    PIN/TAN-Muster probierte jede Aufteilung der Leerraumfolge auf zwei ``\\s*``. Der
    Abstand zwischen Schlüsselwort und Wert ist possessiv (``\\s*+``, F Runde 2:
    F-B2), jedes Muster linear — 100 000 Zeichen, auch „PIN “ davor."""
    import time

    from accounti.betrieb.protokoll import _MUSTER

    for text in (
        wort + leer * 100_000,
        wort + ":" + leer * 100_000 + "4711",
        "PIN " + leer * 100_000,
        wort + leer * 100_000 + "4711",
    ):
        for muster, ersatz in _MUSTER:
            beginn = time.perf_counter()
            muster.sub(ersatz, text)
            dauer = time.perf_counter() - beginn
            assert dauer < 0.25, (muster.pattern, dauer)  # vorher 4–5 s (PIN, TAN)


def test_schluesselwort_und_wert_mit_abstand_bleiben_geschwaerzt():
    """Übliche Schreibweisen (Tabulator, Ausrichtung mit Leerzeichen,
    Zeilenumbruch)."""
    for roh in (
        "passwort:\t\thunter4711",
        "Kennwort      =      Sonne4711",
        "PIN\n471147",
        "TAN :  123456",
        "Authorization: Bearer\n  eyJtok4711",
        "secret:" + " " * 30 + "s3cr3t4711",
    ):
        assert not re.search(r"\d", schwaerze(roh)), roh


@pytest.mark.parametrize("anzahl", [41, 300, 5000])
def test_schluesselwort_und_wert_mit_langem_abstand_bleiben_geschwaerzt(anzahl):
    """F-B2 (gf-betrieb k3_port.py, aus F 61e2a5d): Hinter mehr als 40
    Leerraumzeichen zwischen Schlüsselwort und Wert erkannte kein Muster den Wert mehr
    („PIN“ + 41 Leerzeichen + Zahl, „Passwort:“ + 41 Tabs, „Bearer“ + 41 × „\\n“, „TAN“
    + 40 × „\\r\\n“) — d36ac77 schwärzte sie. Jetzt beliebig lang, auch wenn die Zeile
    dadurch gekürzt wird (5000 Leerzeichen)."""
    for roh in (
        "PIN" + " " * anzahl + "471147",
        "Passwort:" + "\t" * anzahl + "hunter4711",
        "Authorization: Bearer" + "\n" * anzahl + "eyJtok4711",
        "TAN" + "\r\n" * anzahl + "123456",
        "Kennwort" + " " * anzahl + "=" + " " * anzahl + "Sonne4711",
        "PIN:" + " " * anzahl + "4711",
    ):
        text = schwaerze(roh)
        assert not re.search(r"\d", text), (roh[:12], text[-40:])


@pytest.mark.parametrize("anzahl", [41, 260, 600, 1600])
@pytest.mark.parametrize(
    "wort",
    ["PIN", "Passwort:", "Bearer", "Kennwort ="],
    ids=["pin", "pw", "bearer", "kw"],
)
def test_langer_abstand_an_der_schnittkante_bleibt_geschwaerzt(wort, anzahl):
    """F-B2 mit der Kürzung langer Zeilen: Ein Abstand über die hintere bzw. vordere
    Kante hinaus trennt den Wert nicht von seinem Schlüsselwort — der Vorlauf des
    Endes reicht über den ganzen Abstand (Lage um die Kante in Schritten von 7)."""
    from accounti.betrieb.protokoll import _RAND

    geheim = wort + " " * anzahl + ("471147" if wort == "PIN" else "hunter4711")
    for versatz in range(-len(geheim) - 30, 40, 7):
        zeile = "w " * 2500 + geheim + (" z" * _RAND)[: _RAND - versatz]
        text = schwaerze(zeile)
        assert not re.search(r"\d", text), ("hinten", versatz, text[-300:])
        zeile = ("w " * _RAND)[: _RAND + versatz] + " " + geheim + " z" * 3000
        text = schwaerze(zeile)
        assert not re.search(r"\d", text), ("vorn", versatz, text[1300:1800])


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        # Port vor einer Abfrage (Runde 7 machte Port und Abfrage zu „***“) — hinter
        # einem Rechner mit Punkt bzw. localhost (Folgepaket F, g8w B8-2)
        ("https://rechner.example:8443?x=1", "https://rechner.example:8443?x=1"),
        ("http://localhost:8000?next=/", "http://localhost:8000?next=/"),
        ("http://localhost:8000?", "http://localhost:8000?"),
        ("https://rechner.example:8443#/start", "https://rechner.example:8443#/start"),
        # das Wort vor „:“ gehört nicht zur E-Mail-Adresse
        ("Empfänger:max@firma.de", "Empfänger:[E-Mail]"),
        ("Kontakt: mailto:info@galerie.example", "Kontakt: mailto:[E-Mail]"),
        ("Konto 4711:Bürobedarf@Lieferant.de", "Konto 4711:[E-Mail]"),
        ("Uhrzeit 10:30@buero.example", "Uhrzeit 10:[E-Mail]"),
        ("Zeit 12:00:00@x.de", "Zeit 12:00:[E-Mail]"),
        ("Benutzer jan:Rolle@admin.example", "Benutzer jan:[E-Mail]"),
    ],
)
def test_schwaerzung_ohne_ueberschwaerzung(roh, erwartet):
    """B7-3 (g7w, Runde 7): Port und Abfrage verschwanden, ein Wort vor „:“ wurde Teil
    von [E-Mail]. Zugangsdaten bleiben geschwärzt (``test_schwaerzung``)."""
    assert schwaerze(roh) == erwartet


@pytest.mark.parametrize(
    "roh",
    [
        "a" * 37 + "https://u:pw4711@h",
        "Datenbankverbindungsfehlermeldungskontextpostgresql://u:pw4711@h/db",
        "Datenbankverbindungsfehlermeldungskontextpostgresql://u:pw4711",
        "x-" + "a" * 45 + "://u:pw4711@h",
        "a" * 5000 + "https://u:pw4711@h",
        "ä" * 50 + "https://u:pw4711/x@h",
    ],
    ids=[
        "37_buchstaben",
        "wort",
        "wort_abgeschnitten",
        "langes_schema",
        "5000",
        "pfad",
    ],
)
def test_zugangsdaten_hinter_jedem_schema(roh):
    """B8-3 (g8w): Ein Schema hinter 42 oder mehr Buchstaben ohne Trenner fand kein
    Muster (``(?<![A-Za-z])…{0,40}://``) — die Zugangsdaten blieben stehen. Die Muster
    beginnen jetzt an „://“, gleich, was davor steht; linear wie bisher."""
    import time

    assert "pw4711" not in schwaerze(roh)
    text = "a" * 100_000 + "://u:pw4711@h"
    beginn = time.perf_counter()
    assert "pw4711" not in schwaerze(text)
    assert time.perf_counter() - beginn < 0.25


@pytest.mark.parametrize(
    "roh",
    [
        "Fehler https://alarm:4711?",
        "Fehler https://alarm:4711#\nSonne@hooks.example/x",
        "Fehler https://alarm:4711?#Sonne",
        "Fehler https://alarm:4711?x=Sonne",
        "Fehler https://alarm:4711? nicht zustellbar",
        "Fehler https://alarm:4711#/",
        "Fehler https://alarm:4711/",
        "Fehler https://alarm:4711",
        # Zahl über 65535 ist kein Port, auch hinter einem Rechner
        "Fehler https://rechner.example:99999?x=1",
        "Fehler https://localhost:0?",
    ],
)
def test_port_nur_hinter_einem_rechner(roh):
    """B8-2 (g8w): Die Port-Ausnahme (B7-3) ließ eine abgeschnittene Adresse mit
    Ziffern-Passwort vor ?/# stehen. „:Ziffern“ ist jetzt nur ein Port, wenn der Teil
    davor wie ein Rechner aussieht (Punkt, localhost, IPv4) und die Zahl höchstens
    65535 ist — sonst ein Passwort: „alarm:***“ (Sicherheit vor Bequemlichkeit)."""
    text = schwaerze(roh)
    assert ":***" in text, text
    assert "4711" not in text and "99999" not in text and "Sonne" not in text, text


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        ("https://rechner.example:8443?x=1", "https://rechner.example:8443?x=1"),
        ("https://localhost:8443#/a", "https://localhost:8443#/a"),
        ("http://127.0.0.1:8080?x=1", "http://127.0.0.1:8080?x=1"),
        ("https://hooks.example:65535/x", "https://hooks.example:65535/x"),
        # Grenze: ein Rechner ohne Punkt ist von „benutzer:4711“ nicht zu trennen
        ("https://host:8443?x=1", "https://host:***"),
        ("https://host:8443/pfad", "https://host:***/pfad"),
    ],
)
def test_port_hinter_einem_rechner_bleibt_lesbar(roh, erwartet):
    assert schwaerze(roh) == erwartet


@pytest.mark.parametrize(
    ("roh", "darf_nicht"),
    [
        ("Fehler: https://alarm:4711/Sonne@hooks.example.invalid/hook", "4711"),
        ("Fehler: https://alarm:4711/Sonne@hooks.example.invalid/hook", "alarm"),
        ("Fehler: https://alarm:4711/Sonne@hooks.example.invalid/hook", "Sonne"),
        ("Fehler: https://alarm:4711/Sonne@hooks.example.invalid", "4711"),
        ("https://host:4711#Sonne nicht zustellbar", "Sonne"),
        ("https://alarm:4711?Sonne nicht zustellbar", "Sonne"),
        ("Rest alarm:4711#Sonne@hooks.example.invalid/hook", "alarm"),
        ("Rest alarm:Wint3r%3FSonne@hooks.example.invalid/hook", "alarm"),
    ],
)
def test_schwaerzung_mit_schraegstrich_im_passwort(roh, darf_nicht):
    """B7-2 (g7w): Ein unkodiertes „/“ im Passwort mit Ziffern davor ließ „alarm:4711“
    als Rechner und Port stehen. Ein „@“ im ersten Pfadabschnitt hinter
    „benutzer:…“ gilt als Ende der Zugangsdaten."""
    assert darf_nicht not in schwaerze(roh)


@pytest.mark.parametrize(
    "roh",
    [
        "https://mastodon.example:443/@kanal",
        "https://hooks.example:8443/pfad/@user",
        "https://outlook.office.com/webhook/a1b2-c3@d4e5-f6/IncomingWebhook/abc",
    ],
)
def test_schwaerzung_laesst_at_im_pfad(roh):
    assert schwaerze(roh) == roh
