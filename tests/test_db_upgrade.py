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
from tests.pg_hilfe import mit_postgresql

WURZEL = Path(__file__).resolve().parents[1]
VOR_BAUSTEIN_7 = "a684d10751de"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)


def _alembic(db: Path, *args: str, ok: bool = True) -> str:
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
    assert (e.returncode == 0) is ok, e.stdout + e.stderr
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
    leer.touch()  # vorhanden, aber leer (eine fehlende Datei lehnt db upgrade ab)
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


def test_db_upgrade_scheitert_mit_meldung_statt_traceback(tmp_path):
    """Nachprüfung N4: Verträgt eine Migration eine schon vorhandene Tabelle nicht
    (hier: ``api_tokens`` vor a684d10751de), endete ``db upgrade`` mit einem
    Traceback. Jetzt Meldung mit dem erreichten Stand und Exit 1."""
    from sqlalchemy.exc import SQLAlchemyError

    db = tmp_path / "alt.db"
    _alembic(db, "upgrade", "33d478b807fc")
    with sqlite3.connect(db) as v:
        v.execute("CREATE TABLE api_tokens (id VARCHAR(36) PRIMARY KEY)")
    r = runner.invoke(
        app, ["db", "upgrade", "--db", f"sqlite:///{db}"], env={"COLUMNS": "250"}
    )
    assert r.exit_code == 1, r.output
    assert not isinstance(r.exception, SQLAlchemyError), r.exception
    assert "Upgrade abgebrochen" in r.output and "33d478b807fc" in r.output
    assert "api_tokens" in r.output


def test_db_upgrade_legt_keine_neue_sqlite_datei_an(tmp_path):
    """Nachprüfung N4: Ein Tippfehler in ``--db`` legte eine neue Datenbank an und
    migrierte sie — die echte blieb alt. Neu anlegen ist ``db init``."""
    db = tmp_path / "tippfehler.db"
    r = runner.invoke(
        app, ["db", "upgrade", "--db", f"sqlite:///{db}"], env={"COLUMNS": "250"}
    )
    assert r.exit_code == 1, r.output
    assert "gibt es nicht" in r.output and "db init" in r.output
    assert not db.exists()


def test_migration_token_je_gesellschaft(tmp_path):
    """Befund Betrieb B9: Index ``uq_api_token_aktiv`` auf (gesellschaft, name)."""
    db = tmp_path / "t.db"
    _alembic(db, "upgrade", "ddc9a184ddb4")
    zeile = (
        "INSERT INTO api_tokens (id, name, token_hash, gesellschaft, rechte, "
        "angelegt_von, angelegt_am) VALUES (?, 'erp', ?, ?, '[]', 'x', "
        "'2026-10-01 00:00:00')"
    )
    with sqlite3.connect(db) as v:
        v.execute(zeile, ("1", "h1", "a"))
    _alembic(db, "upgrade", "head")
    with sqlite3.connect(db) as v:
        v.execute(zeile, ("2", "h2", "b"))
        with pytest.raises(sqlite3.IntegrityError):
            v.execute(zeile, ("3", "h3", "b"))
    assert "No new upgrade operations detected" in _alembic(db, "check")
    with sqlite3.connect(db) as v:
        v.execute("DELETE FROM api_tokens WHERE id = '2'")
    _alembic(db, "downgrade", "-1")
    _alembic(db, "upgrade", "head")
    assert _alembic(db, "heads").count("(head)") == 1


def _token_index(db: Path) -> list[str]:
    with sqlite3.connect(db) as v:
        return [
            z[2]
            for z in v.execute("PRAGMA index_info('uq_api_token_aktiv')").fetchall()
        ]


def test_downgrade_token_index_bricht_vor_dem_loeschen_ab(tmp_path):
    """Nachprüfung N3: Mit zwei aktiven „erp“ (a und b) scheiterte das Downgrade erst
    beim Anlegen des alten Index — unter SQLite war der neue da schon gelöscht."""
    db = tmp_path / "t.db"
    _alembic(db, "upgrade", "head")
    zeile = (
        "INSERT INTO api_tokens (id, name, token_hash, gesellschaft, rechte, "
        "angelegt_von, angelegt_am) VALUES (?, 'erp', ?, ?, '[]', 'x', "
        "'2026-10-01 00:00:00')"
    )
    with sqlite3.connect(db) as v:
        v.execute(zeile, ("1", "h1", "a"))
        v.execute(zeile, ("2", "h2", "b"))
    ausgabe = _alembic(db, "downgrade", "-1", ok=False)
    assert "Downgrade abgebrochen" in ausgabe and "erp" in ausgabe, ausgabe
    assert _token_index(db) == ["gesellschaft", "name"]
    assert _version(db) == [SCHEMA_STAND]


def _alembic_url(url: str, cwd: Path, *args: str, ok: bool = True) -> str:
    umgebung = {**os.environ, "ACCOUNTI_DB": url, "PYTHONPATH": str(WURZEL / "src")}
    e = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(WURZEL / "alembic.ini"), *args],
        cwd=cwd,
        env=umgebung,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (e.returncode == 0) is ok, e.stdout + e.stderr
    return e.stdout + e.stderr


@mit_postgresql
def test_postgresql_migration_und_db_upgrade(pg_datenbank, tmp_path):
    """PostgreSQL: Token-Index je Gesellschaft (B9) und ``db upgrade`` ohne Vermerk
    (B2) — die Merkmale stammen aus der Wegwerf-SQLite, verglichen wird mit PG."""
    from sqlalchemy import create_engine, text

    url = pg_datenbank()
    _alembic_url(url, tmp_path, "upgrade", VOR_BAUSTEIN_7)
    engine = create_engine(url)
    with engine.begin() as v:
        v.execute(text("DROP TABLE alembic_version"))
    engine.dispose()
    engine, _ = session_factory(url)
    init_db(engine)  # neuer Code vor der Migration: kein Vermerk, Spalten fehlen
    engine.dispose()
    r = runner.invoke(app, ["db", "upgrade", "--db", url], env={"COLUMNS": "250"})
    assert r.exit_code == 0, r.output
    assert f"abgeleitet: {VOR_BAUSTEIN_7}" in r.output
    assert "No new upgrade operations detected" in _alembic_url(url, tmp_path, "check")
    zeile = text(
        "INSERT INTO api_tokens (id, name, token_hash, gesellschaft, rechte, "
        "angelegt_von, angelegt_am) VALUES (:id, 'erp', :h, :g, '[]', 'x', "
        "'2026-10-01 00:00:00')"
    )
    engine = create_engine(url)
    with engine.begin() as v:
        v.execute(zeile, {"id": "1", "h": "h1", "g": "a"})
        v.execute(zeile, {"id": "2", "h": "h2", "g": "b"})
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), engine.begin() as v:
        v.execute(zeile, {"id": "3", "h": "h3", "g": "b"})
    # Nachprüfung N3: das Downgrade bricht vorher ab, der Index bleibt
    ausgabe = _alembic_url(url, tmp_path, "downgrade", "-1", ok=False)
    assert "Downgrade abgebrochen" in ausgabe, ausgabe
    with pytest.raises(IntegrityError), engine.begin() as v:
        v.execute(zeile, {"id": "3", "h": "h3", "g": "b"})
    with engine.begin() as v:
        v.execute(text("DELETE FROM api_tokens WHERE id = '2'"))
        stand = v.execute(text("SELECT version_num FROM alembic_version")).all()
    engine.dispose()
    assert stand == [(SCHEMA_STAND,)]
    _alembic_url(url, tmp_path, "downgrade", "-1")
    _alembic_url(url, tmp_path, "upgrade", "head")
