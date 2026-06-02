from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app

runner = CliRunner()
BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "beispiel_sparkasse.csv"


def test_import_bank_meldet_anzahl(tmp_path):
    url = f"sqlite:///{(tmp_path / 'accounti.db').as_posix()}"
    runner.invoke(app, ["db", "init", "--db", url])
    res = runner.invoke(app, ["import", "bank", str(BEISPIEL), "--db", url])
    assert res.exit_code == 0
    assert "8" in res.stdout
