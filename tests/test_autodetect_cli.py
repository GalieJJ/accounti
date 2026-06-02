from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app
from accounti.importers.profil import EINGEBAUTE_PROFILE, erkenne_profil

runner = CliRunner()
BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "beispiel_sparkasse.csv"


def test_erkennt_sparkasse():
    header = (
        "Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;"
        "Begünstigter/Zahlungspflichtiger;Kontonummer;BLZ;Betrag;Währung;Info"
    )
    profil = erkenne_profil(header, EINGEBAUTE_PROFILE)
    assert profil is not None
    assert profil.name == "sparkasse"


def test_erkennt_dkb_nicht_als_sparkasse():
    header = (
        "Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;"
        "Verwendungszweck;Betrag (EUR)"
    )
    profil = erkenne_profil(header, EINGEBAUTE_PROFILE)
    assert profil is not None
    assert profil.name == "dkb"


def test_unbekannt_gibt_none():
    assert erkenne_profil("Foo;Bar;Baz", EINGEBAUTE_PROFILE) is None


def test_cli_import_auto(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    runner.invoke(app, ["db", "init", "--db", url])
    res = runner.invoke(
        app, ["import", "bank", str(BEISPIEL), "--db", url, "--format", "auto"]
    )
    assert res.exit_code == 0
    assert "8" in res.stdout


def test_cli_banken_liste():
    res = runner.invoke(app, ["import", "banken"])
    assert res.exit_code == 0
    assert "sparkasse" in res.stdout
    assert "dkb" in res.stdout
