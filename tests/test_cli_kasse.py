"""CLI ``accounti kasse …`` (Akzeptanz 4 über die Kommandozeile)."""

import pytest
from typer.testing import CliRunner

from accounti.cli import app

runner = CliRunner()


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


@pytest.fixture
def run(tmp_path):
    url = f"sqlite:///{(tmp_path / 'k.db').as_posix()}"
    config = str(tmp_path / "accounti.yaml")

    def _run(*args):
        return runner.invoke(app, ["kasse", *args, "--db", url, "--config", config])

    return _run


def test_kassenbuch_ueber_die_cli(run):
    r = run("anfangsbestand", "--betrag", "100", "--datum", "2026-03-01")
    assert r.exit_code == 0, r.output
    r = run(
        "buchen",
        "--betrag",
        "-24.90",
        "--text",
        "Porto",
        "--datum",
        "2026-03-02",
        "--konto",
        "4910",
    )
    assert r.exit_code == 0, r.output
    assert "Nr. 2" in _text(r) and "75,10" in _text(r)

    r = run("buchen", "--betrag", "-80", "--text", "Patronen", "--datum", "2026-03-03")
    assert r.exit_code == 1
    assert "abgelehnt" in _text(r) and "−4,90" in _text(r)

    r = run(
        "buchen",
        "--betrag",
        "50",
        "--text",
        "Barverkauf",
        "--datum",
        "2026-03-03",
        "--konto",
        "8400",
        "--steuer",
        "19",
    )
    assert r.exit_code == 0, r.output

    r = run("liste", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    assert all(w in _text(r) for w in ("Porto", "Barverkauf", "125,10"))

    r = run("bestand", "--datum", "2026-03-02", "--gezaehlt", "75,00")
    assert r.exit_code == 0, r.output
    assert "75,10" in _text(r) and "Differenz" in _text(r) and "0,10" in _text(r)

    r = run("storno", "2", "--grund", "falsch", "--datum", "2026-03-04")
    assert r.exit_code == 0, r.output
    r = run("bestand")
    assert "150,00" in _text(r)


def test_ungueltige_eingaben(run):
    r = run("buchen", "--betrag", "zwölf", "--text", "x")
    assert r.exit_code == 1 and "kein Betrag" in _text(r)
    r = run("storno", "7", "--grund", "x")
    assert r.exit_code == 1 and "gibt es nicht" in _text(r)
