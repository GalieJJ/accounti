"""CLI ``accounti sicherung`` und ``accounti betrieb aufbewahrung``."""

import pytest
from typer.testing import CliRunner

from accounti.bank.tresor import neuer_schluessel
from accounti.cli import app
from tests.gesellschaft_hilfe import zwei_gesellschaften
from tests.test_betrieb_sicherung import befuelle, url

runner = CliRunner()


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_ARCHIV", "ACCOUNTI_GESELLSCHAFT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ACCOUNTI_SICHERUNG_SCHLUESSEL", neuer_schluessel())
    return tmp_path


def test_sichern_pruefen_wiederherstellen(umgebung):
    db, archiv = befuelle(umgebung)
    ordner = umgebung / "sicherungen"  # gibt es noch nicht: „/“ am Ende = Ordner
    r = runner.invoke(
        app,
        [
            "sicherung",
            "erstellen",
            "--ziel",
            f"{ordner}/",
            "--db",
            db,
            "--archiv",
            str(archiv),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "3 Buchungen" in r.output and "4 Belege" in r.output
    (datei,) = ordner.glob("accounti-standard-*.sicherung")
    r = runner.invoke(app, ["sicherung", "pruefen", str(datei)])
    assert r.exit_code == 0, r.output
    assert "vollständig und unverändert" in r.output
    neu = url(umgebung / "neu.db")
    r = runner.invoke(
        app,
        ["sicherung", "wiederherstellen", str(datei), "--db", neu]
        + ["--archiv", str(umgebung / "neu-archiv")],
    )
    assert r.exit_code == 0, r.output
    assert "Wiederhergestellt" in r.output
    # die Ansichten zeigen dasselbe
    vorher = runner.invoke(app, ["opos", "liste", "--db", db]).output
    nachher = runner.invoke(app, ["opos", "liste", "--db", neu]).output
    assert vorher == nachher and "RE-1" in nachher
    # ein zweites Mal geht nicht: Ziel nicht mehr leer
    r = runner.invoke(
        app,
        ["sicherung", "wiederherstellen", str(datei), "--db", neu]
        + ["--archiv", str(umgebung / "x")],
    )
    assert r.exit_code == 1 and "nicht leer" in r.output


def test_ohne_schluessel_wird_nichts_geschrieben(umgebung, monkeypatch):
    db, archiv = befuelle(umgebung)
    monkeypatch.delenv("ACCOUNTI_SICHERUNG_SCHLUESSEL")
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL", raising=False)
    ziel = umgebung / "s.sicherung"
    r = runner.invoke(
        app,
        [
            "sicherung",
            "erstellen",
            "--ziel",
            str(ziel),
            "--db",
            db,
            "--archiv",
            str(archiv),
        ],
    )
    assert r.exit_code == 1 and "fehlt" in r.output
    assert not ziel.exists()


def test_mit_gesellschaft(umgebung, monkeypatch):
    u = zwei_gesellschaften(umgebung)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    ziel = umgebung / "b.sicherung"
    r = runner.invoke(app, ["-g", "b", "sicherung", "erstellen", "--ziel", str(ziel)])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["sicherung", "pruefen", str(ziel)])
    assert "1 Belege" in r.output


def test_schluessel(umgebung):
    r = runner.invoke(app, ["sicherung", "schluessel"])
    assert r.exit_code == 0
    assert len(r.output.splitlines()[0].strip()) == 44


def test_aufbewahrung(umgebung):
    db, _ = befuelle(umgebung)
    r = runner.invoke(
        app,
        ["betrieb", "aufbewahrung", "--db", db, "--stichtag", "2026-10-20"],
        env={"COLUMNS": "200"},
    )
    assert r.exit_code == 0, r.output
    assert "Buchungen" in r.output and "10 Jahre" in r.output
    assert "8 Jahre" in r.output and "Nichts wird automatisch gelöscht" in r.output
