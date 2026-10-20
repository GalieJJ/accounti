"""CLI ``accounti elster`` — PIN und Protokoll."""

import sqlite3

from typer.testing import CliRunner

from accounti.bank.tresor import neuer_schluessel
from accounti.cli import app
from accounti.elster.pin import lade_pin
from tests.test_cli_ustva import befehl, mit_attrappe, protokoll, umgebung

runner = CliRunner()


def test_pin_wird_verschluesselt_abgelegt(tmp_path, monkeypatch):
    schluessel = neuer_schluessel()
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", schluessel)
    pin_datei = tmp_path / "geheim" / "elster-pin.enc"
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        f"elster:\n  eric:\n    pin_datei: {pin_datei}\n", encoding="utf-8"
    )
    r = runner.invoke(
        app, ["elster", "pin", "--config", str(konfig)], input="654321\n654321\n"
    )
    assert r.exit_code == 0, r.output
    assert "654321" not in r.output
    assert lade_pin(pin_datei, schluessel) == "654321"


def test_pin_ohne_schluessel_oder_ohne_pfad(tmp_path, monkeypatch):
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL", raising=False)
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text("elster:\n  eric:\n    pin_datei: pin.enc\n", encoding="utf-8")
    r = runner.invoke(app, ["elster", "pin", "--config", str(konfig)], input="1\n1\n")
    assert r.exit_code == 2 and "ACCOUNTI_SCHLUESSEL" in r.output
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", neuer_schluessel())
    r = runner.invoke(app, ["elster", "pin", "--config", str(tmp_path / "fehlt.yaml")])
    assert r.exit_code == 2 and "elster.eric.pin_datei" in r.output


def test_protokoll_meldet_manipulation(tmp_path):
    url, konfig = umgebung(tmp_path)
    mit_attrappe(konfig)
    assert befehl(url, konfig, tmp_path, "uebermitteln", "--test").exit_code == 0
    datei = url.removeprefix("sqlite:///")
    verbindung = sqlite3.connect(datei)
    verbindung.execute("DROP TRIGGER steuermeldung_protokolle_kein_update")
    verbindung.execute("UPDATE steuermeldung_protokolle SET ticket = 'gefälscht'")
    verbindung.commit()
    verbindung.close()
    r = protokoll(url, tmp_path)
    assert r.exit_code == 1
    assert "Eintrag 1: Inhalt verändert" in r.output
