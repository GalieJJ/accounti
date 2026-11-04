"""Migration ``REV`` (Baustein 10c P4a): Einstellungen, Anträge, Geheimnisse.

Alembic als eigener Prozess wie im Container. Alle Tests hängen an der eigenen
Revision ``REV`` und an ihrem Vorgänger ``VOR`` aus dem ``ScriptDirectory`` — nie an
einem relativen Downgrade oder am aktuellen Kopf (Wächter
``tests/test_migration_regeln.py``, Plan G-M1). So bleiben sie grün, wenn sich eine
spätere Migration daran kettet.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from tests.pg_hilfe import mit_postgresql
from tests.pg_hilfe import pg_datenbank as pg_datenbank  # noqa: F401 (Fixture)
from tests.test_migration_web import WURZEL, alembic, bestand, ok

# Baustein 10c P4a: einstellungen, einstellungsantraege, geheimnisse
REV = "83dfa5750c7f"
NEU = {"einstellungen", "einstellungsantraege", "geheimnisse"}
TRIGGER = {"einstellungen_kein_update", "einstellungen_kein_delete"}
runner = CliRunner()


def _skripte():  # noqa: ANN202
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(str(WURZEL / "alembic.ini")))


def _vor() -> str:
    vor = _skripte().get_revision(REV).down_revision
    assert isinstance(vor, str)
    return vor


VOR = _vor()


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)


def _schema(db: Path) -> tuple[set[str], set[str]]:
    with sqlite3.connect(db) as v:
        tabellen = {
            n for (n,) in v.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        trigger = {
            n
            for (n,) in v.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND tbl_name='einstellungen'"
            )
        }
    return tabellen, trigger


def _version_einfuegen(v: sqlite3.Connection) -> None:
    v.execute(
        "INSERT INTO einstellungen (abschnitt, version, daten, schema_version, "
        "vollstaendig, fehlend, person, grund, quelle, erstellt_am, hash, "
        "vorgaenger_hash) VALUES ('mandant', 1, '{}', 1, 1, '[]', 'erika', 'Probe', "
        "'cli', '2026-11-04 10:00:00', ?, ?)",
        ("a" * 64, "0" * 64),
    )


def test_ein_kopf(tmp_path):
    """Genau ein Kopf, er ist ``SCHEMA_STAND``; ``REV`` steht in der Kette hinter
    ``VOR`` — welche Revision gerade der Kopf ist, nimmt der Test nicht an."""
    from accounti.db import SCHEMA_STAND

    assert ok(alembic(tmp_path / "x.db", "heads")).count("(head)") == 1
    skripte = _skripte()
    assert skripte.get_heads() == [SCHEMA_STAND]
    vorfahren = [r.revision for r in skripte.iterate_revisions(SCHEMA_STAND, "base")]
    assert REV in vorfahren
    assert vorfahren.index(VOR) == vorfahren.index(REV) + 1


def test_upgrade_auf_bestand(tmp_path):
    db = tmp_path / "alt.db"
    bestand(db)  # Baustein 7 mit einer Buchung
    ok(alembic(db, "upgrade", VOR))
    assert not _schema(db)[0] & NEU
    ok(alembic(db, "upgrade", REV))
    tabellen, trigger = _schema(db)
    assert tabellen >= NEU and trigger == TRIGGER
    with sqlite3.connect(db) as v:
        assert v.execute("SELECT count(*) FROM buchungssaetze").fetchone() == (1,)
        _version_einfuegen(v)
        with pytest.raises(sqlite3.DatabaseError, match="unveränderbar"):
            v.execute("UPDATE einstellungen SET grund = 'x'")
        with pytest.raises(sqlite3.DatabaseError, match="unveränderbar"):
            v.execute("DELETE FROM einstellungen")
    ok(alembic(db, "upgrade", "head"))
    assert "No new upgrade operations detected" in ok(alembic(db, "check"))


def test_migration_uebernimmt_was_init_db_anlegte(tmp_path):
    from accounti.db import init_db, session_factory

    db = tmp_path / "alt.db"
    ok(alembic(db, "upgrade", VOR))
    engine, _ = session_factory(f"sqlite:///{db}")
    init_db(engine)  # Befehl des neuen Codes vor der Migration: Tabellen und Trigger
    engine.dispose()
    tabellen, trigger = _schema(db)
    assert tabellen >= NEU and trigger == TRIGGER
    ok(alembic(db, "upgrade", REV))
    assert _schema(db) == (tabellen, trigger)
    ok(alembic(db, "upgrade", "head"))
    assert "No new upgrade operations detected" in ok(alembic(db, "check"))


def test_downgrade_leer_und_wieder_hinauf(tmp_path):
    db = tmp_path / "alt.db"
    bestand(db)
    ok(alembic(db, "upgrade", REV))
    ok(alembic(db, "downgrade", VOR))
    tabellen, trigger = _schema(db)
    assert not tabellen & NEU and not trigger
    with sqlite3.connect(db) as v:  # der Bestand bleibt
        assert v.execute("SELECT count(*) FROM buchungssaetze").fetchone() == (1,)
    ok(alembic(db, "upgrade", "head"))
    assert "No new upgrade operations detected" in ok(alembic(db, "check"))


@pytest.mark.parametrize("tabelle", sorted(NEU))
def test_downgrade_mit_versionen_bricht_ab(tmp_path, tabelle):
    db = tmp_path / "alt.db"
    ok(alembic(db, "upgrade", REV))
    with sqlite3.connect(db) as v:
        if tabelle == "einstellungen":
            _version_einfuegen(v)
        elif tabelle == "einstellungsantraege":
            v.execute(
                "INSERT INTO einstellungsantraege (aenderungen, inhalt_hash, grund, "
                "antragsteller, erstellt_am, gueltig_bis, kontrolle, recht, felder, "
                "status) VALUES ('[]', 'h', 'g', 'jan', '2026-11-04 10:00:00', "
                "'2026-11-11 10:00:00', 'zahlung.vier_augen', 'zahlung_freigeben', "
                "'[]', 'offen')"
            )
        else:
            v.execute(
                "INSERT INTO geheimnisse (name, chiffrat, gesetzt_am, gesetzt_von) "
                "VALUES ('llm.api_key', 'c', '2026-11-04 10:00:00', 'jan')"
            )
    ergebnis = alembic(db, "downgrade", VOR)
    ausgabe = ergebnis.stdout + ergebnis.stderr
    assert ergebnis.returncode != 0
    assert "Downgrade abgebrochen" in ausgabe and tabelle in ausgabe, ausgabe
    assert "accounti sicherung erstellen" in ausgabe, ausgabe
    tabellen, trigger = _schema(db)
    assert tabellen >= NEU and trigger == TRIGGER  # nichts geändert
    with sqlite3.connect(db) as v:
        assert v.execute("SELECT version_num FROM alembic_version").fetchone() == (REV,)


def test_db_upgrade_leitet_stand_ab(tmp_path):
    """Paket A: Eine Datenbank ohne Vermerk auf dem Stand ``VOR`` — ``db upgrade``
    leitet ``VOR`` aus dem Schema ab (die neuen Tabellen fehlen) und holt ``REV`` nach;
    hat ``init_db`` sie schon angelegt, zählt der Schritt trotzdem als offen."""
    db = tmp_path / "alt.db"
    ok(alembic(db, "upgrade", VOR))
    with sqlite3.connect(db) as v:
        v.execute("DROP TABLE alembic_version")
    r = runner.invoke(
        app, ["db", "upgrade", "--db", f"sqlite:///{db}"], env={"COLUMNS": "250"}
    )
    assert r.exit_code == 0, r.output
    assert f"abgeleitet: {VOR}" in r.output
    tabellen, trigger = _schema(db)
    assert tabellen >= NEU and trigger == TRIGGER
    assert "No new upgrade operations detected" in ok(alembic(db, "check"))


@mit_postgresql
def test_postgresql_rundlauf(pg_datenbank):  # noqa: F811
    """PostgreSQL: hinauf mit Funktion und Triggern, zurück auf ``VOR`` (leer), wieder
    hinauf; mit einer Version bricht das Downgrade ab."""
    from sqlalchemy import create_engine, text

    url = pg_datenbank()
    ok(alembic(url, "upgrade", REV))
    ok(alembic(url, "upgrade", "head"))
    assert "No new upgrade operations detected" in ok(alembic(url, "check"))
    ok(alembic(url, "downgrade", VOR))
    engine = create_engine(url)
    try:
        with engine.connect() as v:
            funktion = v.execute(
                text(
                    "SELECT count(*) FROM pg_proc "
                    "WHERE proname = 'accounti_nur_anfuegen'"
                )
            ).scalar()
        assert funktion == 0
        ok(alembic(url, "upgrade", REV))
        with engine.begin() as v:
            v.execute(
                text(
                    "INSERT INTO einstellungen (abschnitt, version, daten, "
                    "schema_version, vollstaendig, fehlend, person, grund, quelle, "
                    "erstellt_am, hash, vorgaenger_hash) VALUES ('mandant', 1, '{}', "
                    "1, true, '[]', 'erika', 'Probe', 'cli', '2026-11-04 10:00:00', "
                    ":h, :v)"
                ),
                {"h": "a" * 64, "v": "0" * 64},
            )
        ergebnis = alembic(url, "downgrade", VOR)
        assert ergebnis.returncode != 0
        assert "accounti sicherung erstellen" in ergebnis.stdout + ergebnis.stderr
        with engine.connect() as v:
            assert v.execute(text("SELECT count(*) FROM einstellungen")).scalar() == 1
    finally:
        engine.dispose()
