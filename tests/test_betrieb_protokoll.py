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
