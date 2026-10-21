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
    ],
)
def test_schwaerzung(roh, darf_nicht):
    assert darf_nicht not in schwaerze(roh)


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
