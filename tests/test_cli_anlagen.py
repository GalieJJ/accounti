"""CLI ``accounti anlagen …``."""

import pytest
from typer.testing import CliRunner

from accounti.cli import app

runner = CliRunner()


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


@pytest.fixture
def run(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    config = str(tmp_path / "accounti.yaml")  # fehlt: Standards gelten

    def _run(*args):
        return runner.invoke(app, ["anlagen", *args, "--db", url, "--config", config])

    return _run


def test_tabelle(run):
    r = run("tabelle")
    assert r.exit_code == 0, r.output
    assert "Personenkraftwagen" in _text(r) and "4.2.1" in _text(r)


def test_anlegen_afa_spiegel_abgang(run, tmp_path):
    r = run(
        "anlegen",
        "--bezeichnung",
        "Schreibtisch",
        "--datum",
        "15.09.2026",
        "--kosten",
        "3.600,00",
        "--nutzungsdauer",
        "3",
        "--konto",
        "0420",
    )
    assert r.exit_code == 0, r.output
    assert "Nr. 1" in _text(r) and "linear" in _text(r)

    r = run("plan", "1")
    assert r.exit_code == 0, r.output
    assert "400,00" in _text(r) and "4/36" in _text(r)

    r = run("afa", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    assert "400,00" in _text(r) and "zur Prüfung" in _text(r)
    r = run("afa", "--jahr", "2026")
    assert "nichts zu buchen" in _text(r)

    r = run("freigeben", "--jahr", "2026", "--von", "pruefer")
    assert r.exit_code == 0 and "1 AfA-Buchung freigegeben" in _text(r)

    r = run("liste", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    assert "Schreibtisch" in _text(r) and "3.200,00" in _text(r)

    r = run("afa", "--jahr", "2027", "--bis-monat", "4")
    assert "400,00" in _text(r)
    r = run(
        "abgang",
        "1",
        "--datum",
        "2027-05-20",
        "--erloes",
        "3000",
        "--gegenkonto",
        "1200",
    )
    assert r.exit_code == 0, r.output
    assert "Buchgewinn" in _text(r) and "2315" in _text(r)

    datei = tmp_path / "spiegel.csv"
    r = run("spiegel", "--jahr", "2027", "--csv", str(datei))
    assert r.exit_code == 0, r.output
    assert "Summe" in _text(r)
    assert "Summe" in datei.read_text(encoding="utf-8")


def test_regelverstoss_und_unbekanntes(run):
    r = run(
        "anlegen",
        "--bezeichnung",
        "Sessel",
        "--datum",
        "2026-02-01",
        "--kosten",
        "900",
        "--art",
        "gwg",
    )
    assert r.exit_code == 1
    assert "800,00" in _text(r)
    r = run("plan", "99")
    assert r.exit_code == 1 and "nicht gefunden" in _text(r)
    r = run("afa", "--jahr", "2026", "--bis-monat", "13")
    assert r.exit_code == 1


def test_vorschlaege_ohne_treffer(run):
    r = run("vorschlaege", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    assert "Keine" in _text(r)
