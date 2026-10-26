"""Migration von Baustein 7 — der dokumentierte Upgrade-Weg.

Alembic läuft wie im Container als eigener Prozess (``ACCOUNTI_DB``) gegen eine
Wegwerf-Datenbank: erst der Stand vor Baustein 7 mit Bestand, dann die Migration,
dann ``accounti journal uebernehmen`` — danach ist ``journal pruefen`` in Ordnung.
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

WURZEL = Path(__file__).resolve().parents[1]
VOR = "a684d10751de"  # Baustein 10a, der Stand vor Baustein 7
ORIGINAL = "00000000-0000-0000-0000-000000000001"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)


def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess[str]:
    umgebung = {
        **os.environ,
        "ACCOUNTI_DB": f"sqlite:///{db}",
        "PYTHONPATH": str(WURZEL / "src"),
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(WURZEL / "alembic.ini"), *args],
        cwd=db.parent,
        env=umgebung,
        capture_output=True,
        text=True,
        check=False,
    )


def _ok(ergebnis: subprocess.CompletedProcess[str]) -> str:
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    return ergebnis.stdout + ergebnis.stderr


def _alter_stand(db: Path) -> None:
    """Datenbank auf dem Stand vor Baustein 7, mit einer freigegebenen Buchung und
    einem abgeschlossenen Jahr — geschrieben, wie es der alte Code getan hätte."""
    _ok(_alembic(db, "upgrade", VOR))
    with sqlite3.connect(db) as v:
        v.execute(
            "INSERT INTO buchungssaetze (id, transaktion_id, beleg_id, datum, "
            "soll_konto, haben_konto, betrag_netto, steuer_schluessel, steuer_betrag, "
            "buchungstext, beleg_nummer, status, confidence, geprueft_von, "
            "beleg_position_id) VALUES (?, NULL, NULL, '2025-06-01', '4930', '1200', "
            "100.00, 9, 19.00, 'Bürobedarf', 'RE-1', 'geprueft', 1.0, 'chef', NULL)",
            (ORIGINAL,),
        )
        v.execute(
            "INSERT INTO abschluesse VALUES "
            "(2024, 1, 'euer', 0, '2025-03-01 10:00:00.000000', 'chef')"
        )


def _schema(db: Path) -> tuple[set[str], set[str], dict[str, bool], set[str]]:
    with sqlite3.connect(db) as v:
        tabellen = {
            n for (n,) in v.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        trigger = {
            n
            for (n,) in v.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        indizes = {
            name: bool(eindeutig)
            for _, name, eindeutig, *_ in v.execute(
                "PRAGMA index_list('buchungssaetze')"
            )
        }
        spalten = {z[1] for z in v.execute("PRAGMA table_info('buchungssaetze')")}
    return tabellen, trigger, indizes, spalten


NEU = {"journal", "buchungskorrekturen", "periodenabschluesse"}
TRIGGER = {
    "journal_kein_update",
    "journal_kein_delete",
    "buchungskorrekturen_kein_update",
    "buchungskorrekturen_kein_delete",
}


def _journal(db: Path, *befehl: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, ["journal", *befehl, "--db", f"sqlite:///{db}"])


def test_upgrade_auf_bestand_dann_journal_uebernehmen(tmp_path):
    db = tmp_path / "alt.db"
    _alter_stand(db)
    _ok(_alembic(db, "upgrade", "head"))
    tabellen, trigger, indizes, spalten = _schema(db)
    assert tabellen >= NEU and trigger >= TRIGGER
    assert {"storniert_durch", "storno_von"} <= spalten
    assert indizes["ix_buchungssaetze_storniert_durch"] is True
    assert indizes["ix_buchungssaetze_storno_von"] is True
    assert "No new upgrade operations detected" in _ok(_alembic(db, "check"))
    assert _ok(_alembic(db, "heads")).count("(head)") == 1

    # der dokumentierte Weg: vor der Übernahme Befunde, danach in Ordnung
    r = _journal(db, "pruefen")
    assert r.exit_code == 1 and "ohne_eintrag" in r.output
    r = _journal(db, "uebernehmen", "--von", "chef")
    assert r.exit_code == 0, r.output
    assert "2 Objekte" in r.output  # die Buchung und das abgeschlossene Jahr
    r = _journal(db, "pruefen")
    assert r.exit_code == 0, r.output

    # Trigger und Unique-Indizes wirken auch auf rohes SQL
    with sqlite3.connect(db) as v:
        with pytest.raises(sqlite3.DatabaseError, match="unveränderbar"):
            v.execute("UPDATE journal SET person = 'x'")
        v.execute("UPDATE buchungssaetze SET storniert_durch = 's1'")
        with pytest.raises(sqlite3.IntegrityError):
            v.execute(
                "INSERT INTO buchungssaetze (id, datum, soll_konto, haben_konto, "
                "betrag_netto, buchungstext, status, confidence, storniert_durch) "
                "VALUES ('x', '2025-06-02', '1', '2', 1, 't', 'geprueft', 1, 's1')"
            )
        v.rollback()


def test_downgrade_und_wieder_hinauf(tmp_path):
    db = tmp_path / "alt.db"
    _alter_stand(db)
    _ok(_alembic(db, "upgrade", "head"))
    _ok(_alembic(db, "downgrade", "-1"))
    tabellen, trigger, indizes, spalten = _schema(db)
    assert not tabellen & NEU and not trigger & TRIGGER
    assert not {"storniert_durch", "storno_von"} & spalten
    assert not {i for i in indizes if "storn" in i}
    with sqlite3.connect(db) as v:  # der Bestand bleibt
        assert v.execute("SELECT count(*) FROM buchungssaetze").fetchone() == (1,)
    _ok(_alembic(db, "upgrade", "head"))
    assert "No new upgrade operations detected" in _ok(_alembic(db, "check"))


def test_migration_uebernimmt_was_init_db_schon_anlegte(tmp_path):
    """Ein Befehl des neuen Codes vor der Migration (``init_db``) legt die neuen
    Tabellen samt Triggern schon an — die Migration bricht daran nicht ab."""
    from accounti.db import init_db, session_factory

    db = tmp_path / "alt.db"
    _alter_stand(db)
    engine, _ = session_factory(f"sqlite:///{db}")
    init_db(engine)
    engine.dispose()
    assert _schema(db)[0] >= NEU
    _ok(_alembic(db, "upgrade", "head"))
    assert "No new upgrade operations detected" in _ok(_alembic(db, "check"))
    r = _journal(db, "uebernehmen")
    assert r.exit_code == 0, r.output
    assert _journal(db, "pruefen").exit_code == 0


def test_sicherung_vor_der_migration_mit_neuem_code(tmp_path):
    """Upgrade-Reihenfolge aus docs/betrieb.md: neues Abbild bauen, sichern, migrieren.
    Die Sicherung liest die alte Datenbank (ohne die neuen Spalten); zurückgespielt
    in eine neue Umgebung lässt sie sich migrieren und übernehmen."""
    import secrets

    from accounti.betrieb.sicherung import erstelle, stelle_wieder_her

    db = tmp_path / "alt.db"
    _alter_stand(db)
    schluessel = secrets.token_bytes(32)
    ziel = tmp_path / "vorher.accounti"
    e = erstelle(f"sqlite:///{db}", None, ziel, schluessel)
    assert e.tabellen["buchungssaetze"] == 1
    neu = tmp_path / "neu" / "x.db"
    neu.parent.mkdir()
    stelle_wieder_her(ziel, f"sqlite:///{neu}", None, schluessel)
    # das Ziel legt init_db nach dem neuen Code an und vermerkt dessen Stand — nicht
    # die ältere Revision aus der Sicherung (Befund Betrieb B2)
    from accounti.db import SCHEMA_STAND

    with sqlite3.connect(neu) as v:
        assert v.execute("SELECT version_num FROM alembic_version").fetchall() == [
            (SCHEMA_STAND,)
        ]
    _ok(_alembic(neu, "upgrade", "head"))
    assert "No new upgrade operations detected" in _ok(_alembic(neu, "check"))
    assert _journal(neu, "uebernehmen").exit_code == 0
    r = _journal(neu, "pruefen")
    assert r.exit_code == 0, r.output
