import pytest

from accounti.belege.kanaele.pruefung import (
    DateiAbgelehntError,
    Dateipruefung,
    erkenne_dateityp,
    sicherer_dateiname,
)
from tests.pdf_hilfe import pdf_mit_text

CII = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b"<rsm:CrossIndustryInvoice "
    b'xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100">'
    b"</rsm:CrossIndustryInvoice>"
)


@pytest.mark.parametrize(
    ("inhalt", "typ"),
    [
        (pdf_mit_text("Rechnung"), "pdf"),
        (b"\xef\xbb\xbf\n%PDF-1.7\n", "pdf"),
        (CII, "xml"),
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", "jpeg"),
        (b"\x89PNG\r\n\x1a\n\x00\x00", "png"),
        (b"II*\x00\x08\x00", "tiff"),
        (b"MM\x00*\x00\x08", "tiff"),
    ],
)
def test_belegtypen_werden_am_inhalt_erkannt(inhalt, typ):
    assert erkenne_dateityp(inhalt) == typ


@pytest.mark.parametrize(
    "inhalt",
    [
        b"Rechnung Nr. 1 - nur Text",
        b"PK\x03\x04\x14\x00 docx oder zip",
        b"<!DOCTYPE html><html><body>Rechnung</body></html>",
        b"<html><head><title>x</title></head></html>",
        b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>',
        b"<kaputt",
        b"GIF89a\x01\x00",
        b"",
    ],
)
def test_andere_typen_werden_nicht_erkannt(inhalt):
    assert erkenne_dateityp(inhalt) is None


def test_pruefung_gibt_sicheren_dateinamen_zurueck():
    p = Dateipruefung()
    assert p.pruefe("Rechnung.pdf", b"%PDF-1.4 x") == "Rechnung.pdf"
    assert p.pruefe("../../etc/passwd", b"%PDF-1.4 x") == "passwd.pdf"
    assert p.pruefe("C:\\Users\\a\\scan.JPG", b"\xff\xd8\xff\xe0") == "scan.JPG"
    assert p.pruefe(None, b"\x89PNG\r\n\x1a\n") == "beleg.png"
    assert p.pruefe("rechnung.txt", b"%PDF-1.4") == "rechnung.txt.pdf"
    assert p.pruefe("a\x00b\nc.xml", CII) == "abc.xml"


def test_leere_zu_grosse_und_fremde_dateien_werden_abgelehnt():
    p = Dateipruefung(max_bytes=10)
    with pytest.raises(DateiAbgelehntError) as leer:
        p.pruefe("a.pdf", b"")
    assert leer.value.art == "leer"
    with pytest.raises(DateiAbgelehntError) as gross:
        p.pruefe("a.pdf", b"%PDF-1.4 " + b"x" * 10)
    assert gross.value.art == "groesse"
    assert "höchstens" in str(gross.value)
    with pytest.raises(DateiAbgelehntError) as fremd:
        p.pruefe("a.zip", b"PK\x03\x04")
    assert fremd.value.art == "typ"
    assert "ZIP" in str(fremd.value)


def test_typauswahl_aus_der_konfiguration():
    p = Dateipruefung(typen=frozenset({"pdf"}))
    assert p.pruefe("a.pdf", b"%PDF-1.4") == "a.pdf"
    with pytest.raises(DateiAbgelehntError, match="jpeg"):
        p.pruefe("a.jpg", b"\xff\xd8\xff\xe0")


def test_sicherer_dateiname_kuerzt_und_ersetzt():
    lang = "x" * 300 + ".pdf"
    assert len(sicherer_dateiname(lang, "pdf")) <= 200
    assert sicherer_dateiname(lang, "pdf").endswith(".pdf")
    assert sicherer_dateiname("   ", "xml") == "beleg.xml"
    assert sicherer_dateiname(".versteckt", "pdf") == "versteckt.pdf"
