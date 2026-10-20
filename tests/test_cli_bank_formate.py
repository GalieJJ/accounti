"""MT940 und CAMT über die Kommandozeile — Akzeptanz 2 und 6 für die neuen Formate."""

from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_transaktionen

runner = CliRunner()
DATEN = Path(__file__).parent / "daten" / "bank"


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


def test_import_bank_mt940_zweimal_ohne_dubletten(tmp_path):
    url = f"sqlite:///{(tmp_path / 'f.db').as_posix()}"
    datei = tmp_path / "maerz.sta"
    datei.write_bytes((DATEN / "auszug.sta").read_bytes())
    r = runner.invoke(app, ["import", "bank", str(datei), "--db", url])
    assert r.exit_code == 0, r.output
    assert "6 Transaktionen importiert" in _text(r)
    r = runner.invoke(app, ["import", "bank", str(datei), "--db", url])
    assert "0 Transaktionen importiert, 6 Dubletten übersprungen" in _text(r)


def test_import_bank_camt_mit_festem_format(tmp_path):
    url = f"sqlite:///{(tmp_path / 'f.db').as_posix()}"
    datei = tmp_path / "auszug.xml"
    datei.write_bytes((DATEN / "camt053_v08.xml").read_bytes())
    r = runner.invoke(
        app, ["import", "bank", str(datei), "--format", "camt", "--db", url]
    )
    assert r.exit_code == 0, r.output
    engine, make_session = session_factory(url)
    init_db(engine)
    with make_session() as s:
        betraege = sorted(str(t.betrag) for t in lade_transaktionen(s))
    engine.dispose()
    # zwei gleiche Parkgebühren mit verschiedener Bankreferenz bleiben zwei
    assert betraege == ["-5.00", "-5.00", "-59.50", "1190.00"]


def test_formate_werden_aufgelistet():
    r = runner.invoke(app, ["import", "banken"])
    assert r.exit_code == 0, r.output
    assert "mt940" in r.output and "camt" in r.output
