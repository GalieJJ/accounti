"""Migrationen von Baustein 10b — Alembic als eigener Prozess wie im Container.

``d5a849692843`` (Kontierung: ``kontierungsgruende``, ``kontierungsregeln``) hängt an
``ddc9a184ddb4`` (Baustein 7), ``SPRACHE`` (``auth_benutzer.sprache``) daran. Beide
übernehmen, was ``init_db`` schon anlegte, und laufen gegen jede Datenbank (System-
und Gesellschaftsdatenbank — ``auth_benutzer`` liegt wegen der gemeinsamen Metadaten
in jeder).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.pg_hilfe import mit_postgresql
from tests.pg_hilfe import pg_datenbank as pg_datenbank  # noqa: F401 (Fixture)

WURZEL = Path(__file__).resolve().parents[1]
SIEBEN = "ddc9a184ddb4"  # Baustein 7
KONTIERUNG = "d5a849692843"
BUCHUNG = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)


def alembic(db: Path | str, *args: str) -> subprocess.CompletedProcess[str]:
    url = db if isinstance(db, str) else f"sqlite:///{db}"
    umgebung = {**os.environ, "ACCOUNTI_DB": url, "PYTHONPATH": str(WURZEL / "src")}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(WURZEL / "alembic.ini"), *args],
        cwd=WURZEL,
        env=umgebung,
        capture_output=True,
        text=True,
        check=False,
    )


def ok(ergebnis: subprocess.CompletedProcess[str]) -> str:
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    return ergebnis.stdout + ergebnis.stderr


def bestand(db: Path) -> None:
    """Datenbank auf dem Stand von Baustein 7 mit einer Buchung zur Prüfung."""
    ok(alembic(db, "upgrade", SIEBEN))
    with sqlite3.connect(db) as v:
        v.execute(
            "INSERT INTO buchungssaetze (id, transaktion_id, beleg_id, datum, "
            "soll_konto, haben_konto, betrag_netto, steuer_schluessel, steuer_betrag, "
            "buchungstext, beleg_nummer, status, confidence, geprueft_von, "
            "beleg_position_id) VALUES (?, NULL, NULL, '2026-06-01', '4980', '1200', "
            "50.00, 9, 9.50, 'Bürobedarf', NULL, 'pruefung', 0.62, NULL, NULL)",
            (BUCHUNG,),
        )


def schema(db: Path) -> tuple[set[str], set[str], set[str]]:
    with sqlite3.connect(db) as v:
        tabellen = {
            n for (n,) in v.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        trigger = {
            n
            for (n,) in v.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        spalten = {z[1] for z in v.execute("PRAGMA table_info('auth_benutzer')")}
    return tabellen, trigger, spalten


NEU = {"kontierungsgruende", "kontierungsregeln"}
TRIGGER = {"kontierungsgruende_kein_update", "kontierungsgruende_kein_delete"}


def test_ein_kopf_nach_ddc9a184ddb4(tmp_path):
    db = tmp_path / "x.db"
    kopf = ok(alembic(db, "heads"))
    assert kopf.count("(head)") == 1 and KONTIERUNG in kopf
    verlauf = ok(alembic(db, "history", "-r", "a684d10751de:head"))
    assert f"{SIEBEN} -> {KONTIERUNG} (head)" in verlauf
    assert f"a684d10751de -> {SIEBEN}" in verlauf


def test_upgrade_auf_bestand(tmp_path):
    db = tmp_path / "alt.db"
    bestand(db)
    ok(alembic(db, "upgrade", "head"))
    tabellen, trigger, spalten = schema(db)
    assert tabellen >= NEU and trigger >= TRIGGER
    assert "No new upgrade operations detected" in ok(alembic(db, "check"))
    with sqlite3.connect(db) as v:
        assert v.execute("SELECT count(*) FROM buchungssaetze").fetchone() == (1,)
        v.execute(
            "INSERT INTO kontierungsgruende VALUES ('g1', ?, 'llm', NULL, NULL, "
            "'x', '2026-06-01 10:00:00')",
            (BUCHUNG,),
        )
        with pytest.raises(sqlite3.DatabaseError, match="unveränderbar"):
            v.execute("UPDATE kontierungsgruende SET begruendung = 'y'")
        v.rollback()


def test_migration_uebernimmt_was_init_db_schon_anlegte(tmp_path):
    from accounti.db import init_db, session_factory

    db = tmp_path / "alt.db"
    bestand(db)
    engine, _ = session_factory(f"sqlite:///{db}")
    init_db(engine)  # neue Tabellen samt Triggern, aber keine neue Spalte
    engine.dispose()
    tabellen, trigger, spalten = schema(db)
    assert tabellen >= NEU and trigger >= TRIGGER
    ok(alembic(db, "upgrade", "head"))
    assert "No new upgrade operations detected" in ok(alembic(db, "check"))


def test_downgrade_und_wieder_hinauf(tmp_path):
    db = tmp_path / "alt.db"
    bestand(db)
    ok(alembic(db, "upgrade", "head"))
    ok(alembic(db, "downgrade", "-1"))
    tabellen, trigger, spalten = schema(db)
    assert not tabellen & NEU and not trigger & TRIGGER
    with sqlite3.connect(db) as v:  # der Bestand bleibt
        assert v.execute("SELECT count(*) FROM buchungssaetze").fetchone() == (1,)
    ok(alembic(db, "upgrade", "head"))
    assert "No new upgrade operations detected" in ok(alembic(db, "check"))
    assert ok(alembic(db, "heads")).count("(head)") == 1


@mit_postgresql
def test_postgresql_rundlauf(pg_datenbank):  # noqa: F811
    """Gegen frische PostgreSQL-Datenbanken (System und Gesellschaft): hinauf, check,
    zurück auf Baustein 7, wieder hinauf."""
    for _ in ("system", "gesellschaft"):
        url = pg_datenbank()
        ok(alembic(url, "upgrade", SIEBEN))
        ok(alembic(url, "upgrade", "head"))
        assert "No new upgrade operations detected" in ok(alembic(url, "check"))
        ok(alembic(url, "downgrade", SIEBEN))
        ok(alembic(url, "upgrade", "head"))
        assert "No new upgrade operations detected" in ok(alembic(url, "check"))
