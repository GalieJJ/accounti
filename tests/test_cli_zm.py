"""CLI ``accounti zm`` — Zusammenfassende Meldung als Portaldatei."""

from typer.testing import CliRunner

from accounti.cli import app
from tests.test_cli_ustva import text, umgebung

runner = CliRunner()


def zm(url, konfig, *extra):
    return runner.invoke(
        app, ["zm", "--period", "2026-08", "--db", url, "--config", konfig, *extra]
    )


def test_zm_mit_bestaetigter_ustid_als_csv(tmp_path):
    url, konfig = umgebung(tmp_path)
    datei = tmp_path / "zm.csv"
    r = zm(url, konfig, "--csv", str(datei))
    assert r.exit_code == 0, r.output
    assert "ATU12345678" in text(r) and "5.000" in text(r)
    assert "bis 25.09.2026" in text(r)
    assert datei.read_text(encoding="utf-8") == (
        "#v3.0\n#ve3.2.1\n"
        "Umsatzsteuer-Identifikationsnummer (USt-IdNr.),Summe (Euro),Art der Leistung\n"
        "ATU12345678,5000,L\n"
    )


def test_akzeptanz_7_zm_ohne_bestaetigte_ustid_wird_bemaengelt(tmp_path):
    url, konfig = umgebung(tmp_path, bestaetigt=False)
    datei = tmp_path / "zm.csv"
    r = zm(url, konfig, "--csv", str(datei))
    assert r.exit_code == 1
    assert "USt-IdNr. ATU12345678 nicht bestätigt" in text(r)
    assert not datei.exists()


def test_zeitraum_ohne_eu_umsaetze(tmp_path):
    url, konfig = umgebung(tmp_path)
    r = runner.invoke(
        app, ["zm", "--period", "2026-07", "--db", url, "--config", konfig]
    )
    assert r.exit_code == 0, r.output
    assert "keine Zusammenfassende Meldung nötig" in text(r)
