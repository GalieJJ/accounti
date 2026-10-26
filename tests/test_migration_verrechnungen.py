"""Migration a14acef69fae (Gesamttest Debitoren): Tabelle ``verrechnungen`` nur anfügen.

Wie Journal und USt-IdNr.-Protokoll sperren auf SQLite Trigger auch rohes SQL — nach
der Migration ebenso wie nach ``init_db`` (Nachprüfung N6).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from accounti.db import init_db, session_factory
from tests.test_migration_belegvollstaendigkeit import WURZEL, _alembic, _ok

REVISION = "a14acef69fae"
VOR = "2f7c7043043e"  # Anlagen-Buchung (Gesamttest Abschluss), der Stand davor
TRIGGER = {"verrechnungen_kein_update", "verrechnungen_kein_delete"}


def test_revision_folgt_auf_die_anlagen_buchung():
    skripte = ScriptDirectory.from_config(Config(str(WURZEL / "alembic.ini")))
    assert skripte.get_revision(REVISION).down_revision == VOR


def _trigger(db: Path) -> set[str]:
    with sqlite3.connect(db) as v:
        return {
            n
            for (n,) in v.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND tbl_name='verrechnungen'"
            )
        }


def _roh_aendern(db: Path) -> None:
    with sqlite3.connect(db) as v:
        v.execute(
            "INSERT INTO verrechnungen (id, kontakt_id, posten_id, gegen_posten_id, "
            "betrag, datum, erstellt_am) VALUES ('v', 'k', 'p', 'g', 10, "
            "'2026-03-06', '2026-03-06 10:00:00')"
        )
        v.execute("UPDATE verrechnungen SET betrag = 1")


def test_migration_legt_die_trigger_an_und_nimmt_sie_zurueck(tmp_path):
    db = tmp_path / "a.db"
    _ok(_alembic(db, "upgrade", "head"))
    assert _trigger(db) == TRIGGER
    with pytest.raises(sqlite3.DatabaseError, match="unveränderbar"):
        _roh_aendern(db)
    _ok(_alembic(db, "downgrade", VOR))
    assert _trigger(db) == set()
    _ok(_alembic(db, "upgrade", "head"))
    assert _trigger(db) == TRIGGER


def test_migration_nach_init_db(tmp_path):
    # Ein Befehl des neuen Codes lief vor der Migration: Tabelle und Trigger gibt es
    # schon — die Migration übernimmt sie
    db = tmp_path / "a.db"
    engine, _ = session_factory(f"sqlite:///{db}")
    init_db(engine)
    engine.dispose()
    assert _trigger(db) == TRIGGER
    _ok(_alembic(db, "stamp", VOR))
    _ok(_alembic(db, "upgrade", "head"))
    assert _trigger(db) == TRIGGER
