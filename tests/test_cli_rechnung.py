from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app
from tests.pdf_hilfe import pdf_mit_anhang, pdf_mit_text

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "erechnung"


def test_gueltige_xrechnung():
    r = runner.invoke(app, ["rechnung", "pruefen", str(FIXTURES / "xrechnung_ubl.xml")])
    assert r.exit_code == 0, r.output
    assert "RE-2026-0042" in r.output
    assert "Bürobedarf Müller GmbH" in r.output
    assert "172.50" in r.output
    assert "xrechnung" in r.output.lower()
    assert "Keine Befunde" in r.output


def test_fehlerhafte_rechnung_endet_mit_exit_1():
    datei = FIXTURES / "fehler_rechenprobe_cii.xml"
    r = runner.invoke(app, ["rechnung", "pruefen", str(datei)])
    assert r.exit_code == 1
    assert "BR-S-09" in r.output


def test_zugferd_pdf(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(
        pdf_mit_anhang("factur-x.xml", (FIXTURES / "minimum_cii.xml").read_bytes())
    )
    r = runner.invoke(app, ["rechnung", "pruefen", str(pdf)])
    assert r.exit_code == 0, r.output
    assert "MIN-2026-9" in r.output
    assert "PROFIL" in r.output


def test_pdf_ohne_erechnung(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(pdf_mit_text("Rechnung"))
    r = runner.invoke(app, ["rechnung", "pruefen", str(pdf)])
    assert r.exit_code == 1
    assert "keine E-Rechnung" in r.output
