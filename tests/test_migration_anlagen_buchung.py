"""Migration 2f7c7043043e — ``anlagegueter.buchung_id`` (Gesamttest Abschluss B11)."""

from __future__ import annotations

import sqlite3

from tests.test_migration_belegvollstaendigkeit import (  # noqa: F401
    _alembic,
    _ok,
    _umgebung,
)

VOR = "6d38d11fc348"  # Token je Gesellschaft, der Stand davor


def _spalten(db) -> set[str]:
    with sqlite3.connect(db) as v:
        return {z[1] for z in v.execute("PRAGMA table_info(anlagegueter)")}


def test_upgrade_downgrade_mit_bestand(tmp_path):
    db = tmp_path / "a.db"
    _ok(_alembic(db, "upgrade", VOR))
    with sqlite3.connect(db) as v:
        v.execute(
            "INSERT INTO anlagegueter (id, nr, bezeichnung, konto, anschaffungsdatum, "
            "anschaffungskosten, afa_art, wechsel_linear, immateriell, erstellt_am) "
            "VALUES ('a1', 1, 'Regal', '0420', '2025-03-01', 600, 'linear', 1, 0, "
            "'2025-03-01 10:00:00')"
        )
    assert "buchung_id" not in _spalten(db)
    _ok(_alembic(db, "upgrade", "head"))
    assert "buchung_id" in _spalten(db)
    assert "No new upgrade operations detected" in _ok(_alembic(db, "check"))
    _ok(_alembic(db, "downgrade", "-1"))
    assert "buchung_id" not in _spalten(db)
    _ok(_alembic(db, "upgrade", "head"))
    with sqlite3.connect(db) as v:
        assert v.execute("SELECT nr, buchung_id FROM anlagegueter").fetchall() == [
            (1, None)
        ]
