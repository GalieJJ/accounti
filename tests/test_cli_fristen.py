from typer.testing import CliRunner

from accounti.cli import app

runner = CliRunner()


def text(ergebnis):
    """Ausgabe ohne Zeilenumbrüche und Tabellenrahmen."""
    return " ".join(ergebnis.output.replace("│", " ").split())


def test_fristenkalender_aus_der_konfiguration(tmp_path):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "elster:\n  dauerfristverlaengerung: true\n  bundesland: BY\n", encoding="utf-8"
    )
    r = runner.invoke(app, ["fristen", "--jahr", "2026", "--config", str(konfig)])
    assert r.exit_code == 0, r.output
    ausgabe = text(r)
    assert "Fristenkalender 2026" in ausgabe
    assert "Bayern" in ausgabe
    assert "10.02.2026" in ausgabe  # Sondervorauszahlung
    # August mit Dauerfristverlängerung: 10.10.2026 ist ein Samstag
    assert "12.10.2026" in ausgabe and "statt 10.10.2026 (Samstag)" in ausgabe


def test_optionen_ueberschreiben_konfiguration(tmp_path):
    r = runner.invoke(
        app,
        [
            "fristen",
            "--jahr",
            "2026",
            "--quartal",
            "--zm",
            "quartal",
            "--oss",
            "--config",
            str(tmp_path / "fehlt.yaml"),
        ],
    )
    assert r.exit_code == 0, r.output
    ausgabe = text(r)
    assert "2026-Q3" in ausgabe
    assert "26.10.2026 ZM 2026-Q3 statt 25.10.2026 (Sonntag)" in ausgabe
    assert "31.10.2026 OSS 2026-Q3" in ausgabe
    assert "ZM = Zusammenfassende Meldung" in ausgabe
    assert "bundeseinheitliche Feiertage" in ausgabe


def test_unbekanntes_bundesland(tmp_path):
    r = runner.invoke(
        app,
        ["fristen", "--jahr", "2026", "--bundesland", "XY", "--config", "fehlt.yaml"],
    )
    assert r.exit_code == 2
    assert "XY" in r.output
