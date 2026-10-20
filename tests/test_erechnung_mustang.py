import os
from datetime import UTC, datetime

import pytest
from fpdf import FPDF

from accounti.erechnung.erzeuger.cii import schreibe_cii
from accounti.erechnung.erzeuger.zugferd import schreibe_zugferd
from accounti.erechnung.mustang import (
    MustangNichtVerfuegbarError,
    MustangPruefer,
    werte_bericht_aus,
)
from tests.test_erechnung_aufbau import _bau
from tests.test_erechnung_erzeuger import FAELLE

PRUEFER = MustangPruefer()
NUR_MIT_MUSTANG = pytest.mark.skipif(
    not PRUEFER.verfuegbar() and not os.environ.get("ACCOUNTI_PRUEFWERKZEUGE_PFLICHT"),
    reason="Mustang fehlt (scripts/pruefwerkzeuge_installieren.sh)",
)
ZEIT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)

GUELTIG = """Mustang 2.26.0
<?xml version="1.0" encoding="UTF-8"?>
<validation filename="r.pdf">
  <pdf>ValidationResult [flavour=3b, assertions=[], isCompliant=true]
    <summary status="valid"/>
  </pdf>
  <xml><info><profile>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</profile></info>
    <summary status="valid"/>
  </xml>
  <summary status="valid"/>
</validation>"""

UNGUELTIG = """<?xml version="1.0" encoding="UTF-8"?>
<validation filename="r.pdf">
  <pdf>ValidationResult [flavour=3b, isCompliant=false]
    <messages><error type="17">Invalid XMP Metadata not found</error>
    <error type="23">Not a PDF/A-3</error></messages>
    <summary status="invalid"/>
  </pdf>
  <summary status="invalid"/>
</validation>"""


def test_gueltiger_bericht():
    e = werte_bericht_aus(GUELTIG)
    assert (e.gueltig, e.pdfa_konform, e.xml_gueltig) == (True, True, True)
    assert "xrechnung_3.0" in (e.profil or "")
    assert e.meldungen == []


def test_ungueltiger_bericht():
    e = werte_bericht_aus(UNGUELTIG)
    assert (e.gueltig, e.pdfa_konform, e.xml_gueltig) == (False, False, None)
    assert e.meldungen == ["Invalid XMP Metadata not found", "Not a PDF/A-3"]


def test_kein_bericht():
    with pytest.raises(RuntimeError, match="kein Prüfbericht"):
        werte_bericht_aus("java.lang.OutOfMemoryError")


def test_ohne_installation(tmp_path):
    pruefer = MustangPruefer(tmp_path)
    assert not pruefer.verfuegbar()
    with pytest.raises(
        MustangNichtVerfuegbarError, match="pruefwerkzeuge_installieren"
    ):
        pruefer.pruefe(b"%PDF")


@NUR_MIT_MUSTANG
@pytest.mark.parametrize("fall", FAELLE, ids=str)
def test_erzeugte_zugferd_pdfs_sind_konform(fall):
    """PDF/A-3b laut veraPDF und gültiges XML laut Mustang — für jeden Steuerfall."""
    r = _bau(FAELLE[fall])
    xml = schreibe_cii(r)
    e = PRUEFER.pruefe(schreibe_zugferd(r, xml, ZEIT), f"{fall}.pdf")
    assert e.gueltig, e.meldungen
    assert e.pdfa_konform and e.xml_gueltig


@NUR_MIT_MUSTANG
def test_pdf_ohne_pdfa_wird_abgelehnt():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(text="Keine PDF/A")
    pdf.embed_file(bytes=schreibe_cii(_bau(FAELLE["inland"])), basename="xrechnung.xml")
    e = PRUEFER.pruefe(bytes(pdf.output()))
    assert not e.gueltig
    assert e.pdfa_konform is False
