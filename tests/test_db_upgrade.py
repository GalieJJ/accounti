"""Upgrade-Weg für Datenbanken aus ``db init``/``init_db`` (Befund Betrieb B2).

``init_db`` stempelt eine neue Datenbank auf den Kopf der Migrationen; ``accounti db
upgrade`` leitet bei Datenbanken ohne Vermerk den Stand aus dem Schema ab.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import SCHEMA_STAND, init_db, session_factory

WURZEL = Path(__file__).resolve().parents[1]
VOR_BAUSTEIN_7 = "a684d10751de"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)


def _alembic(db: Path, *args: str) -> str:
    umgebung = {
        **os.environ,
        "ACCOUNTI_DB": f"sqlite:///{db}",
        "PYTHONPATH": str(WURZEL / "src"),
    }
    e = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(WURZEL / "alembic.ini"), *args],
        cwd=db.parent,
        env=umgebung,
        capture_output=True,
        text=True,
        check=False,
    )
    assert e.returncode == 0, e.stdout + e.stderr
    return e.stdout + e.stderr


def _version(db: Path) -> list[str]:
    with sqlite3.connect(db) as v:
        return [z for (z,) in v.execute("SELECT version_num FROM alembic_version")]


def _spalten(db: Path, tabelle: str) -> set[str]:
    with sqlite3.connect(db) as v:
        return {z[1] for z in v.execute(f"PRAGMA table_info('{tabelle}')")}


def test_schema_stand_ist_der_kopf_der_migrationen():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    skripte = ScriptDirectory.from_config(Config(str(WURZEL / "alembic.ini")))
    assert skripte.get_heads() == [SCHEMA_STAND]


def test_db_init_stempelt_und_alembic_upgrade_laeuft(tmp_path):
    """Der dokumentierte Weg: ``db init``, später ``alembic upgrade head``."""
    db = tmp_path / "neu.db"
    r = runner.invoke(app, ["db", "init", "--db", f"sqlite:///{db}"])
    assert r.exit_code == 0, r.output
    assert _version(db) == [SCHEMA_STAND]
    _alembic(db, "upgrade", "head")
    assert "No new upgrade operations detected" in _alembic(db, "check")
    # ein zweites init_db ändert nichts
    engine, _ = session_factory(f"sqlite:///{db}")
    init_db(engine)
    engine.dispose()
    assert _version(db) == [SCHEMA_STAND]


def test_vorhandene_datenbank_ohne_vermerk_wird_nicht_gestempelt(tmp_path):
    """Die Tabellen einer alten Datenbank zeigen nicht den Stand dieses Codes."""
    db = tmp_path / "alt.db"
    with sqlite3.connect(db) as v:
        v.execute("CREATE TABLE transaktionen (id VARCHAR(36) PRIMARY KEY)")
    engine, _ = session_factory(f"sqlite:///{db}")
    init_db(engine)
    engine.dispose()
    with sqlite3.connect(db) as v:
        tabellen = {n for (n,) in v.execute("SELECT name FROM sqlite_master")}
    assert "alembic_version" not in tabellen


def _alte_datenbank_ohne_vermerk(db: Path) -> None:
    """Wie ``db init`` vor Baustein 7: Schema von a684d10751de, kein Vermerk — und
    danach hat schon ein Befehl des neuen Codes ``init_db`` aufgerufen (neue Tabellen
    da, neue Spalten an alten Tabellen nicht)."""
    _alembic(db, "upgrade", VOR_BAUSTEIN_7)
    with sqlite3.connect(db) as v:
        v.execute("DROP TABLE alembic_version")
    engine, _ = session_factory(f"sqlite:///{db}")
    init_db(engine)
    engine.dispose()
    assert "storniert_durch" not in _spalten(db, "buchungssaetze")


def test_db_upgrade_leitet_den_stand_aus_dem_schema_ab(tmp_path):
    db = tmp_path / "alt.db"
    _alte_datenbank_ohne_vermerk(db)
    r = runner.invoke(
        app, ["db", "upgrade", "--db", f"sqlite:///{db}"], env={"COLUMNS": "250"}
    )
    assert r.exit_code == 0, r.output
    assert f"abgeleitet: {VOR_BAUSTEIN_7}" in r.output
    assert "journal uebernehmen" in r.output
    assert _version(db) == [SCHEMA_STAND]
    assert {"storniert_durch", "storno_von"} <= _spalten(db, "buchungssaetze")
    assert "No new upgrade operations detected" in _alembic(db, "check")


def test_db_upgrade_mit_vermerk_und_leer(tmp_path):
    mit = tmp_path / "mit.db"
    _alembic(mit, "upgrade", VOR_BAUSTEIN_7)
    r = runner.invoke(app, ["db", "upgrade", "--db", f"sqlite:///{mit}"])
    assert r.exit_code == 0, r.output
    assert "abgeleitet" not in r.output
    assert _version(mit) == [SCHEMA_STAND]
    leer = tmp_path / "leer.db"
    r = runner.invoke(app, ["db", "upgrade", "--db", f"sqlite:///{leer}"])
    assert r.exit_code == 0, r.output
    assert _version(leer) == [SCHEMA_STAND]
    assert "No new upgrade operations detected" in _alembic(leer, "check")


def test_db_upgrade_erkennt_fremde_datenbank(tmp_path):
    db = tmp_path / "fremd.db"
    with sqlite3.connect(db) as v:
        v.execute("CREATE TABLE kunden (id INTEGER PRIMARY KEY)")
    r = runner.invoke(app, ["db", "upgrade", "--db", f"sqlite:///{db}"])
    assert r.exit_code == 1
    assert "Keine Tabellen von accounti" in r.output
