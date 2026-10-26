"""Migration 46371a6681c2: ``belege.steuerkennzeichen`` (Gesamttest Paket C)."""

from __future__ import annotations

import sqlite3

import pytest

from tests.test_migration_belegvollstaendigkeit import _alembic, _ok

VOR = "ddc9a184ddb4"  # Baustein 7, der Stand vor dem Steuerkennzeichen


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)


def _spalten(db) -> set[str]:
    with sqlite3.connect(db) as v:
        return {z[1] for z in v.execute("PRAGMA table_info(belege)")}


def test_spalte_kommt_und_geht_bestand_bleibt(tmp_path):
    db = tmp_path / "alt.db"
    _ok(_alembic(db, "upgrade", VOR))
    with sqlite3.connect(db) as v:
        v.execute(
            "INSERT INTO belege (id, belegart, richtung, datei_hash, dateiname, kanal, "
            "herkunft, eingegangen_am, aufbewahren_bis, status, confidence, waehrung) "
            "VALUES ('b1', 'eingangsrechnung', 'eingang', 'h', 'r.pdf', 'upload', 'x', "
            "'2026-04-02 10:00:00', '2036-12-31', 'pruefung', 0.5, 'EUR')"
        )
    _ok(_alembic(db, "upgrade", "head"))
    assert "steuerkennzeichen" in _spalten(db)
    with sqlite3.connect(db) as v:
        assert v.execute("SELECT steuerkennzeichen FROM belege").fetchone() == (None,)
    assert "No new upgrade operations detected" in _ok(_alembic(db, "check"))
    _ok(_alembic(db, "downgrade", VOR))
    assert "steuerkennzeichen" not in _spalten(db)
    with sqlite3.connect(db) as v:
        assert v.execute("SELECT count(*) FROM belege").fetchone() == (1,)
    _ok(_alembic(db, "upgrade", "head"))
