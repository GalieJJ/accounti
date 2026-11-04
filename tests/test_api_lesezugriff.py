"""Lesezugriff für die Zähler der Navigation (Spec 10c A5; Plan P1, Schritt 6, B14):
ohne ``init_db``, nur lesend, kurze Fristen, eigener Pool — eine fehlende oder hängende
Datenbank hält weder die Seite noch andere Gesellschaften auf und entsteht nicht neu."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from accounti.api.lesezugriff import LeseError, Lesezugriff, verbindung, zaehle
from accounti.db import init_db, session_factory
from tests.pg_hilfe import mit_postgresql, pg_datenbank  # noqa: F401


def _url(pfad: Path) -> str:
    return f"sqlite:///{pfad.as_posix()}"


@pytest.fixture
def db(tmp_path) -> str:
    url = _url(tmp_path / "a.db")
    engine, _ = session_factory(url)
    init_db(engine)
    engine.dispose()
    return url


@pytest.fixture
def lz():
    zugriff = Lesezugriff()
    yield zugriff
    zugriff.schliesse()


def _tabellen(pfad: Path) -> list[str]:
    with sqlite3.connect(pfad) as v:
        return [r[0] for r in v.execute("SELECT name FROM sqlite_master")]


def test_sqlite_nur_lesend(lz, db):
    with lz.sitzung(db) as s:
        assert s.execute(text("SELECT count(*) FROM buchungssaetze")).scalar() == 0
        with pytest.raises(OperationalError, match="readonly"):
            s.execute(text("CREATE TABLE neu (x INTEGER)"))


def test_fehlende_sqlite_datei_wird_nicht_angelegt(lz, tmp_path):
    pfad = tmp_path / "fehlt.db"
    with pytest.raises(LeseError), lz.sitzung(_url(pfad)):
        pass
    assert asyncio.run(zaehle(lz, _url(pfad), {"x": lambda s: 1})) is None
    assert not pfad.exists()


def test_legt_keine_tabelle_an(lz, tmp_path):
    pfad = tmp_path / "leer.db"
    with sqlite3.connect(pfad) as v:
        v.execute("CREATE TABLE fremd (x INTEGER)")
    ergebnis = asyncio.run(
        zaehle(
            lz, _url(pfad), {"fremd": lambda s: s.execute(text("SELECT 7")).scalar()}
        )
    )
    assert ergebnis == {"fremd": 7}
    assert _tabellen(pfad) == ["fremd"]


def test_zaehler_fehler_laesst_die_anderen_stehen(lz, db, caplog):
    def kaputt(s):  # noqa: ANN001, ANN202
        raise RuntimeError("geheim-4711")

    ergebnis = asyncio.run(
        zaehle(
            lz,
            db,
            {"kaputt": kaputt, "gut": lambda s: s.execute(text("SELECT 3")).scalar()},
        )
    )
    assert ergebnis == {"gut": 3}
    assert "RuntimeError" in caplog.text and "geheim-4711" not in caplog.text


def test_frist_bei_haengender_verbindung(lz, tmp_path, db):
    andere = _url(tmp_path / "b.db")
    engine, _ = session_factory(andere)
    init_db(engine)
    engine.dispose()
    frei = threading.Event()
    threads: list[str] = []

    def haengt(s):  # noqa: ANN001, ANN202
        threads.append(threading.current_thread().name)
        frei.wait(10)
        return 1

    async def beide() -> tuple[object, object, float, float]:
        beginn = time.monotonic()
        haengend = asyncio.create_task(zaehle(lz, db, {"x": haengt}, frist=0.5))
        await asyncio.sleep(0.05)
        zweite = await zaehle(lz, andere, {"y": lambda s: 2}, frist=0.5)
        mitte = time.monotonic() - beginn
        return await haengend, zweite, mitte, time.monotonic() - beginn

    try:
        erste, zweite, mitte, dauer = asyncio.run(beide())
    finally:
        frei.set()
    assert erste is None and zweite == {"y": 2}
    assert mitte < 0.5 and dauer < 1.5
    assert threads and threads[0].startswith("zaehler")


def test_schliessen_wartet_nicht_auf_haengende_zaehler(db):
    zugriff = Lesezugriff()
    frei = threading.Event()

    async def starten() -> None:
        aufgabe = asyncio.create_task(
            zaehle(zugriff, db, {"x": lambda s: frei.wait(10)})
        )
        await asyncio.sleep(0.1)
        beginn = time.monotonic()
        zugriff.schliesse()
        assert time.monotonic() - beginn < 0.5
        aufgabe.cancel()

    try:
        asyncio.run(starten())
    finally:
        frei.set()
    assert asyncio.run(zaehle(zugriff, db, {"x": lambda s: 1})) is None


def test_verbindung_mit_fristen():
    sqlite = verbindung("sqlite:////daten/a.db")
    assert sqlite.url.startswith("sqlite:///file:") and "mode=ro" in sqlite.url
    assert sqlite.optionen == {"timeout": 2}
    pg = verbindung("postgresql+psycopg://u:p@h/db")
    assert pg.optionen["connect_timeout"] == 3
    assert "statement_timeout=2000" in pg.optionen["options"]
    assert "default_transaction_read_only=on" in pg.optionen["options"]
    with pytest.raises(LeseError):
        verbindung("sqlite://")


@mit_postgresql
def test_postgresql_mit_zeitlimits(lz, pg_datenbank):  # noqa: F811
    url = pg_datenbank()
    engine, _ = session_factory(url)
    init_db(engine)
    engine.dispose()
    with lz.sitzung(url) as s:
        assert s.execute(text("SHOW statement_timeout")).scalar() == "2s"
        with pytest.raises(OperationalError):
            s.execute(text("SELECT pg_sleep(3)"))
    with lz.sitzung(url) as s, pytest.raises(Exception, match="read-only"):
        s.execute(text("CREATE TABLE neu (x INTEGER)"))
