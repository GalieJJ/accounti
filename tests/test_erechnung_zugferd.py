import io
from datetime import UTC, datetime
from decimal import Decimal

from pypdf import PdfReader

from accounti.belege.erkennung import Format, erkenne_format
from accounti.belege.kanaele import RohBeleg
from accounti.erechnung import lies
from accounti.erechnung.erzeuger.cii import schreibe_cii
from accounti.erechnung.erzeuger.zugferd import ANHANG, schreibe_zugferd
from tests.test_erechnung_aufbau import FIRMA, _bau, entwurf, kunde, pos
from tests.test_erechnung_erzeuger import FAELLE

ZEIT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def _pdf(fall="inland", rechnung=None):
    r = rechnung or _bau(FAELLE[fall])
    xml = schreibe_cii(r)
    return r, xml, schreibe_zugferd(r, xml, ZEIT)


def _text(pdf):
    return "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(pdf)).pages)


def test_xml_ist_unveraendert_eingebettet():
    _, xml, pdf = _pdf()
    reader = PdfReader(io.BytesIO(pdf))
    assert pdf.startswith(b"%PDF-")
    assert dict(reader.attachments) == {ANHANG: [xml]}
    assert ANHANG == "xrechnung.xml"


def test_pdfa_und_factur_x_metadaten():
    _, _, pdf = _pdf()
    reader = PdfReader(io.BytesIO(pdf))
    xmp = reader.trailer["/Root"]["/Metadata"].get_object().get_data().decode()
    assert "<pdfaid:part>3</pdfaid:part>" in xmp
    assert "<pdfaid:conformance>B</pdfaid:conformance>" in xmp
    assert "<fx:ConformanceLevel>XRECHNUNG</fx:ConformanceLevel>" in xmp
    assert f"<fx:DocumentFileName>{ANHANG}</fx:DocumentFileName>" in xmp
    katalog = reader.trailer["/Root"]
    (af,) = katalog["/AF"]
    assert af.get_object()["/AFRelationship"] == "/Alternative"
    assert "/OutputIntents" in katalog


def test_eigener_erkenner_sieht_zugferd():
    _, xml, pdf = _pdf()
    befund = erkenne_format(
        RohBeleg(dateiname="r.pdf", inhalt=pdf, kanal="t", herkunft="t")
    )
    assert befund.format is Format.ZUGFERD_PDF
    assert befund.xml == xml
    assert lies(befund.xml).nummer == "2026-0001"


def test_lesbare_ansicht():
    r, _, pdf = _pdf()
    text = _text(pdf)
    for erwartet in (
        "Rechnung",
        "2026-0001",
        "10.03.2026",
        "Galerie Muster GmbH",
        "Atelier Kundin GmbH",
        "Kundenstraße 8",
        "Bilderrahmen Eiche",
        "1.216,75",
        "190,00",
        "1,75",
        "DE999999999",
        "DE89 3704 0044 0532 0130 00",
        "PO-77",
        "2,00 % Skonto",
        "24.03.2026",
    ):
        assert erwartet in text, erwartet
    assert "#SKONTO#" not in text


def test_reverse_charge_hinweis_im_pdf():
    _, _, pdf = _pdf("reverse_charge")
    text = _text(pdf)
    assert "Steuerschuldnerschaft des Leistungsempfängers" in text
    assert "ATU12345678" in text
    assert "720,00" in text


def test_deterministisch():
    _, _, a = _pdf()
    _, _, b = _pdf()
    assert a == b


def test_viele_positionen_ueber_mehrere_seiten():
    r = _bau(entwurf(kunde(), *[pos(f"Rahmen Nr. {i}", "10") for i in range(1, 61)]))
    _, _, pdf = _pdf(rechnung=r)
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 2
    text = _text(pdf)
    assert "Rahmen Nr. 1" in text and "Rahmen Nr. 60" in text
    assert "Seite 2 von" in text


def test_sonderzeichen_in_metadaten():
    firma = FIRMA.model_copy(update={"name": "Müller & Söhne <Rahmen>"})
    from accounti.erechnung.erzeuger.aufbau import baue_rechnung

    r = baue_rechnung(
        entwurf(kunde(), pos("Rahmen", "100")), firma, "2026-0009", ZEIT.date()
    )
    _, _, pdf = _pdf(rechnung=r)
    reader = PdfReader(io.BytesIO(pdf))
    xmp = reader.trailer["/Root"]["/Metadata"].get_object().get_data().decode()
    assert "Müller &amp; Söhne &lt;Rahmen&gt;" in xmp
    assert "<rdf:li>Müller &amp; Söhne &lt;Rahmen&gt;</rdf:li>" in xmp
    assert r.summen.brutto == Decimal("119.00")
