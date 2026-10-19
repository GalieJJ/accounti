from pathlib import Path

import pytest

from accounti.belege.erkennung import (
    ErkennungError,
    Format,
    erkenne_belegart,
    erkenne_format,
    hole_text,
)
from accounti.belege.extraktion import extrahiere
from accounti.belege.kanaele import RohBeleg
from accounti.belege.ocr import OCREngine
from accounti.models import Belegart
from tests.pdf_hilfe import pdf_mit_anhang, pdf_mit_bild, pdf_mit_text

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "belege"

CII = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:'
    b'CrossIndustryInvoice:100"></rsm:CrossIndustryInvoice>'
)
UBL = (
    b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">'
    b"</Invoice>"
)


def _roh(inhalt, name):
    return RohBeleg(dateiname=name, inhalt=inhalt, kanal="upload", herkunft=name)


class FakeOCR(OCREngine):
    name = "fake"

    def __init__(self, text="OCR-Text"):
        self.text = text
        self.bilder = []

    def erkenne(self, bild):
        self.bilder.append(bild)
        return self.text


# --- Format ----------------------------------------------------------------


def test_format_xrechnung_cii_und_ubl():
    assert erkenne_format(_roh(CII, "r.xml")).format is Format.ERECHNUNG_XML
    befund = erkenne_format(_roh(UBL, "r.xml"))
    assert befund.format is Format.ERECHNUNG_XML
    assert befund.syntax == "UBL"


def test_format_zugferd_anhang():
    befund = erkenne_format(_roh(pdf_mit_anhang("factur-x.xml", CII), "r.pdf"))
    assert befund.format is Format.ZUGFERD_PDF
    assert befund.syntax == "CII"


def test_pdf_mit_anderem_anhang_ist_normales_pdf():
    pdf = pdf_mit_anhang("notiz.txt", b"hallo")
    assert erkenne_format(_roh(pdf, "r.pdf")).format is Format.PDF


def test_format_pdf_bild_text_unbekannt():
    assert erkenne_format(_roh(pdf_mit_text("x"), "r.pdf")).format is Format.PDF
    assert erkenne_format(_roh(b"\xff\xd8\xff\xe0", "scan.jpg")).format is Format.BILD
    assert erkenne_format(_roh(b"\x89PNG\r\n\x1a\n", "scan.png")).format is Format.BILD
    assert erkenne_format(_roh(b"Rechnung", "r.txt")).format is Format.TEXT
    assert erkenne_format(_roh(b"\x00\x01\x02", "r.bin")).format is Format.UNBEKANNT


def test_kaputtes_xml_ist_keine_erechnung():
    assert erkenne_format(_roh(b"<Invoice", "r.xml")).format is Format.UNBEKANNT


# --- Text ------------------------------------------------------------------


def test_text_aus_pdf_textebene_ohne_ocr():
    ocr = FakeOCR()
    roh = _roh(
        pdf_mit_text("Bürobedarf Müller GmbH\nRechnungsbetrag 172,50 €"), "r.pdf"
    )
    text, quelle = hole_text(roh, erkenne_format(roh), ocr)
    assert "Bürobedarf Müller GmbH" in text
    assert "172,50" in text
    assert quelle == "pdf"
    assert ocr.bilder == []


def test_gescanntes_pdf_geht_an_ocr():
    ocr = FakeOCR("Rechnung aus dem Scan")
    roh = _roh(pdf_mit_bild(b"\xff\xd8\xff\xe0SCAN"), "scan.pdf")
    text, quelle = hole_text(roh, erkenne_format(roh), ocr)
    assert text == "Rechnung aus dem Scan"
    assert quelle == "ocr"
    assert ocr.bilder == [b"\xff\xd8\xff\xe0SCAN"]


def test_bild_geht_an_ocr():
    ocr = FakeOCR("Quittung")
    roh = _roh(b"\xff\xd8\xff\xe0FOTO", "foto.jpg")
    assert hole_text(roh, erkenne_format(roh), ocr) == ("Quittung", "ocr")


def test_ohne_ocr_engine_ist_scan_ein_fehler():
    roh = _roh(b"\xff\xd8\xff\xe0FOTO", "foto.jpg")
    with pytest.raises(ErkennungError, match="OCR"):
        hole_text(roh, erkenne_format(roh), None)


def test_unbekanntes_format_ist_ein_fehler():
    roh = _roh(b"\x00\x01", "x.bin")
    with pytest.raises(ErkennungError, match="Format"):
        hole_text(roh, erkenne_format(roh), FakeOCR())


# --- Belegart --------------------------------------------------------------


@pytest.mark.parametrize(
    ("datei", "art"),
    [
        ("rechnung_zwei_steuersaetze.txt", Belegart.EINGANGSRECHNUNG),
        ("rechnung_unvollstaendig.txt", Belegart.EINGANGSRECHNUNG),
        ("quittung_tankstelle.txt", Belegart.QUITTUNG),
        ("kontoauszug.txt", Belegart.KONTOAUSZUG),
        ("kreditkarte_12_umsaetze.txt", Belegart.KONTOAUSZUG),
        ("vertrag.txt", Belegart.VERTRAG),
        ("sonstiges.txt", Belegart.SONSTIGES),
        ("ausgangsrechnung.txt", Belegart.EINGANGSRECHNUNG),
    ],
)
def test_belegart_per_regel(datei, art):
    text = (FIXTURES / datei).read_text(encoding="utf-8")
    ergebnis = erkenne_belegart(text, extrahiere(text))
    assert ergebnis.belegart is art
    assert ergebnis.begruendung


def test_eigene_ust_id_macht_ausgangsrechnung():
    text = (FIXTURES / "ausgangsrechnung.txt").read_text(encoding="utf-8")
    ergebnis = erkenne_belegart(text, extrahiere(text), eigene_ust_ids={"DE999999999"})
    assert ergebnis.belegart is Belegart.AUSGANGSRECHNUNG


def test_sonstiges_hat_niedrige_confidence():
    text = (FIXTURES / "sonstiges.txt").read_text(encoding="utf-8")
    assert erkenne_belegart(text, extrahiere(text)).confidence < 0.5
