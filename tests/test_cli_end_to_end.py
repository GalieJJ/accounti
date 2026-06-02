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
