from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app

runner = CliRunner()
BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "beispiel_sparkasse.csv"


def test_import_classify_export(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    runner.invoke(app, ["db", "init", "--db", url])
    runner.invoke(app, ["import", "bank", str(BEISPIEL), "--db", url])
    c = runner.invoke(app, ["classify", "--db", url, "--no-llm"])
    assert c.exit_code == 0
    out = tmp_path / "export"
    e = runner.invoke(
        app,
        [
            "export",
            "datev",
            "--db",
            url,
            "--berater",
            "23426",
            "--mandant",
            "40005",
            "--output",
            str(out),
        ],
    )
    assert e.exit_code == 0
    dateien = list(out.glob("EXTF_*.csv"))
    assert len(dateien) == 1


def test_zweiter_classify_lauf_bucht_nichts_doppelt(tmp_path):
    import sqlite3

    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    runner.invoke(app, ["db", "init", "--db", url])
    runner.invoke(app, ["import", "bank", str(BEISPIEL), "--db", url])
    erst = runner.invoke(app, ["classify", "--db", url, "--no-llm"])
    zweit = runner.invoke(app, ["classify", "--db", url, "--no-llm"])
    assert zweit.exit_code == 0, zweit.output
    assert "0 kontiert" in zweit.output
    verbindung = sqlite3.connect(tmp_path / "a.db")
    doppelt = verbindung.execute(
        "select count(*) from (select transaktion_id from buchungssaetze "
        "group by transaktion_id having count(*) > 1)"
    ).fetchone()[0]
    assert doppelt == 0
    # Amazon-, PayPal- und eBay-Auszahlung bleiben für den Marktplatz-Abgleich offen
    # (Gesamttest Steuer B2) — vorher als Erlös 8400 mit Umsatzsteuer gebucht
    assert "5 kontiert" in erst.output and "3 offen" in erst.output
    assert "Marktplatz" in erst.output and "marktplatz import" in erst.output
