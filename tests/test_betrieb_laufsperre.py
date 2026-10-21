"""Befund A-M3: je Gesellschaft und Art höchstens ein Lauf — auch über Prozesse.

Der Compose-Dienst ``lauf`` startet ``bank lauf`` als eigenen Prozess, die App
stößt denselben Lauf über ``POST /api/v1/laeufe/bank`` an. Ein ``threading.Lock``
im App-Prozess sieht den anderen nicht — gesperrt wird in der Datenbank
(PostgreSQL: Advisory-Lock) bzw. neben der SQLite-Datei (Dateisperre).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import accounti
from accounti.betrieb.laufsperre import LaufLaeuftError, laufsperre
from accounti.cli import app
from accounti.models.auth import TokenRecht
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes
from tests.pg_hilfe import mit_postgresql

HALTER = """
import sys
from accounti.betrieb.laufsperre import laufsperre
with laufsperre(sys.argv[1], sys.argv[2]):
    print("gesperrt", flush=True)
    sys.stdin.readline()
"""


class AndererProzess:
    """Hält die Laufsperre in einem eigenen Prozess, bis ``frei()``."""

    def __init__(self, db: str, art: str = "bank") -> None:
        umgebung = {
            **os.environ,
            "PYTHONPATH": str(Path(accounti.__file__).resolve().parents[1]),
        }
        self.prozess = subprocess.Popen(  # noqa: S603 - feste Argumente
            [sys.executable, "-c", HALTER, db, art],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=umgebung,
        )
        assert self.prozess.stdout is not None
        assert self.prozess.stdout.readline().strip() == "gesperrt"

    def frei(self) -> None:
        assert self.prozess.stdin is not None
        self.prozess.stdin.write("\n")
        self.prozess.stdin.flush()
        assert self.prozess.wait(timeout=30) == 0


def _pruefe_sperre(db: str) -> None:
    halter = AndererProzess(db)
    try:
        with pytest.raises(LaufLaeuftError, match="bank"), laufsperre(db, "bank"):
            pass
        with laufsperre(db, "aufgaben"):  # andere Art bleibt frei
            pass
    finally:
        halter.frei()
    with laufsperre(db, "bank"):  # nach dem Ende wieder frei
        pass


def test_sperre_gilt_ueber_prozesse_sqlite(tmp_path):
    _pruefe_sperre(f"sqlite:///{tmp_path / 'a.db'}")


@mit_postgresql
def test_sperre_gilt_ueber_prozesse_postgresql(pg_datenbank):
    _pruefe_sperre(pg_datenbank())


def test_sperre_im_selben_prozess(tmp_path):
    for db in (f"sqlite:///{tmp_path / 'a.db'}", "sqlite:///:memory:"):
        with (
            laufsperre(db, "bank"),
            pytest.raises(LaufLaeuftError),
            laufsperre(db, "bank"),
        ):
            pass


def test_rest_lauf_bekommt_409_wenn_der_dienst_lauf_schon_laeuft(tmp_path, monkeypatch):
    billige_hashes(monkeypatch)
    w = webwelt(tmp_path)
    token = w.token("a", TokenRecht.LAEUFE_STARTEN)
    client = w.client()
    halter = AndererProzess(w.umgebung.db["a"])
    try:
        r = client.post(
            "/api/v1/laeufe/bank", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 409, r.text
        assert "läuft schon" in r.json()["fehler"]
    finally:
        halter.frei()
    r = client.post("/api/v1/laeufe/bank", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


def test_cli_bank_lauf_wartet_nicht_auf_einen_laufenden(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT"):
        monkeypatch.delenv(name, raising=False)
    db = f"sqlite:///{tmp_path / 'a.db'}"
    halter = AndererProzess(db)
    try:
        r = CliRunner().invoke(app, ["bank", "lauf", "--db", db, "--no-llm"])
        assert r.exit_code == 1, r.output
        assert "läuft schon" in r.output
    finally:
        halter.frei()
    r = CliRunner().invoke(app, ["bank", "lauf", "--db", db, "--no-llm"])
    assert r.exit_code == 0, r.output
