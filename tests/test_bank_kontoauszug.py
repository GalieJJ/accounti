from pathlib import Path

import pytest

from accounti.importers.kontoauszug import (
    Auszug,
    KontoauszugError,
    erkenne_auszugsformat,
    lies_kontoauszug,
)
from accounti.importers.profil import waehle_importer
from tests.test_cli_opos import KOPF

DATEN = Path(__file__).parent / "daten" / "bank"


@pytest.mark.parametrize(
    ("datei", "format"),
    [
        ("auszug.sta", "mt940"),
        ("camt053_v08.xml", "camt"),
        ("camt053_v02.xml", "camt"),
        ("camt052_v08.xml", "camt"),
    ],
)
def test_formaterkennung_am_inhalt(datei, format):
    assert erkenne_auszugsformat((DATEN / datei).read_bytes()) == format


@pytest.mark.parametrize(
    "daten",
    [
        b"",
        b"kein Kontoauszug",
        KOPF.encode(),
        b'<?xml version="1.0"?><Invoice xmlns="urn:x"/>',
        b"\xef\xbb\xbf:20:nur ein Feld",
    ],
)
def test_kein_kontoauszug(daten):
    assert erkenne_auszugsformat(daten) is None
    with pytest.raises(KontoauszugError):
        lies_kontoauszug(daten)


def test_lies_kontoauszug_waehlt_den_parser():
    assert len(lies_kontoauszug((DATEN / "auszug.sta").read_bytes())) == 2
    assert len(lies_kontoauszug((DATEN / "camt053_v08.xml").read_bytes())) == 1


@pytest.mark.parametrize(
    ("konto", "iban", "erwartet"),
    [
        ("DE02120300000000202051", "DE02120300000000202051", True),
        ("DE02 1203 0000 0000 2020 51", "DE02120300000000202051", True),
        ("DE89370400440532013000", "DE02120300000000202051", False),
        ("12030000/0000202051", "DE02120300000000202051", True),
        ("12030000/202051", "DE02120300000000202051", True),
        ("12030000/202051EUR", "DE02120300000000202051", True),
        ("37040044/0532013000", "DE02120300000000202051", False),
        ("COBADEFFXXX/DE02120300000000202051", "DE02120300000000202051", True),
        (None, "DE02120300000000202051", True),  # unbekannt: nicht ausschließen
        ("12030000/0000202051", "VISA1234", True),  # Karte ohne IBAN
        ("DE02120300000000202051", "VISA1234", False),  # Giro-Auszug, keine Karte
        ("visa 1234", "VISA1234", True),
        ("irgendwas", "DE02120300000000202051", True),
    ],
)
def test_gehoert_zu(konto, iban, erwartet):
    assert Auszug(konto=konto).gehoert_zu(iban) is erwartet


def test_waehle_importer_auto_erkennt_mt940_und_camt(tmp_path):
    sta = tmp_path / "auszug.sta"
    sta.write_bytes((DATEN / "auszug.sta").read_bytes())
    xml = tmp_path / "auszug.xml"
    xml.write_bytes((DATEN / "camt053_v08.xml").read_bytes())
    leer = tmp_path / "leer.yaml"
    assert waehle_importer(sta, "auto", eigene=leer).name == "mt940"
    assert waehle_importer(xml, "auto", eigene=leer).name == "camt"
    assert waehle_importer(xml, "camt", eigene=leer).name == "camt"
