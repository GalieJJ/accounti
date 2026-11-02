"""Migration 46371a6681c2: ``belege.steuerkennzeichen`` (Gesamttest Paket C).

Die Tests nennen feste Revisionen (``VOR``, ``REVISION``) statt ``downgrade -1`` oder
des aktuellen Kopfs: Spätere Migrationen liegen darüber, und die Revision darf in der
Kette weiterwandern (beim Zusammenführen hinter neue Köpfe gehängt).
"""

from __future__ import annotations

import sqlite3

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from accounti.db import init_db, session_factory
from tests.test_migration_belegvollstaendigkeit import WURZEL, _alembic, _ok

REVISION = "46371a6681c2"
VOR = "a14acef69fae"  # Verrechnungen (Gesamttest Debitoren), der Stand davor


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)


def _spalten(db) -> set[str]:
    with sqlite3.connect(db) as v:
        return {z[1] for z in v.execute("PRAGMA table_info(belege)")}


def _version(db) -> list[str]:
    with sqlite3.connect(db) as v:
        return [z for (z,) in v.execute("SELECT version_num FROM alembic_version")]


def test_revision_folgt_auf_die_verrechnungen():
    skripte = ScriptDirectory.from_config(Config(str(WURZEL / "alembic.ini")))
    assert skripte.get_revision(REVISION).down_revision == VOR
    assert len(skripte.get_heads()) == 1


def test_spalte_kommt_und_geht_bestand_bleibt(tmp_path):
    db = tmp_path / "alt.db"
    _ok(_alembic(db, "upgrade", VOR))
    assert "steuerkennzeichen" not in _spalten(db)
    with sqlite3.connect(db) as v:
        v.execute(
            "INSERT INTO belege (id, belegart, richtung, datei_hash, dateiname, kanal, "
            "herkunft, eingegangen_am, aufbewahren_bis, status, confidence, waehrung) "
            "VALUES ('b1', 'eingangsrechnung', 'eingang', 'h', 'r.pdf', 'upload', 'x', "
            "'2026-04-02 10:00:00', '2036-12-31', 'pruefung', 0.5, 'EUR')"
        )
    _ok(_alembic(db, "upgrade", REVISION))
    assert _version(db) == [REVISION]
    assert "steuerkennzeichen" in _spalten(db)
    with sqlite3.connect(db) as v:
        assert v.execute("SELECT steuerkennzeichen FROM belege").fetchone() == (None,)
    _ok(_alembic(db, "upgrade", "head"))
    assert "No new upgrade operations detected" in _ok(_alembic(db, "check"))
    _ok(_alembic(db, "downgrade", VOR))
    assert _version(db) == [VOR]
    assert "steuerkennzeichen" not in _spalten(db)
    with sqlite3.connect(db) as v:
        assert v.execute("SELECT count(*) FROM belege").fetchone() == (1,)
    _ok(_alembic(db, "upgrade", "head"))
    assert "steuerkennzeichen" in _spalten(db)


def test_migration_uebernimmt_die_spalte_aus_init_db(tmp_path):
    """Ein Befehl des neuen Codes legte die Datenbank an, der Vermerk steht aber auf
    dem Stand davor (z. B. von Hand gestempelt): Die Migration legt nichts doppelt
    an."""
    db = tmp_path / "a.db"
    engine, _ = session_factory(f"sqlite:///{db}")
    init_db(engine)
    engine.dispose()
    assert "steuerkennzeichen" in _spalten(db)
    _ok(_alembic(db, "stamp", VOR))
    _ok(_alembic(db, "upgrade", REVISION))
    assert _version(db) == [REVISION]
    _ok(_alembic(db, "upgrade", "head"))
    assert "No new upgrade operations detected" in _ok(_alembic(db, "check"))
