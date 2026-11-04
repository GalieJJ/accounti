"""Tabellen der Einstellungen (Baustein 10c, Paket P4, Schritt 1).

``einstellungen`` ist nur anfügbar — ORM-Sperre, ``db.GESCHUETZT`` gegen Massenwege und
Trigger unter SQLite und PostgreSQL (AK25) —, je Abschnitt fortlaufend nummeriert und
hash-verkettet (D9). ``einstellungsantraege`` ändert sich nur aus „offen“ heraus,
``geheimnisse`` trägt jeden Namen einmal.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from accounti.db import GESCHUETZT, init_db, session_factory
from accounti.db.repo_einstellungen import (
    fuege_version_an,
    lade_antraege,
    lade_chiffrate,
    lade_geheimnisse,
    lade_version,
    lade_versionen,
    neueste_versionen,
    pruefe_kette,
    versionshash,
    zeilenhash,
)
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_einstellungen import (
    EinstellungRow,
    EinstellungsantragRow,
    GeheimnisRow,
)
from accounti.pruefung.journal import GENESIS
from tests.pg_hilfe import mit_postgresql

WURZEL = Path(__file__).resolve().parents[1]
JETZT = datetime(2026, 11, 4, 9, 30, 15, 123456)


@pytest.fixture
def fabrik(tmp_path):
    engine, fabrik = session_factory(f"sqlite:///{tmp_path / 'e.db'}")
    init_db(engine)
    yield fabrik
    engine.dispose()


def _version(s, abschnitt="mandant", daten=None, **kw):
    werte = {
        "person": "erika",
        "grund": "Probe",
        "quelle": "cli",
        "jetzt": JETZT,
        **kw,
    }
    return fuege_version_an(s, abschnitt, daten or {"name": "A GmbH"}, **werte)


def _antrag(**kw):
    werte = {
        "aenderungen": '[{"abschnitt":"zahlung","basis":1,"daten":{}}]',
        "inhalt_hash": "a" * 64,
        "grund": "Urlaub",
        "antragsteller": "jan",
        "erstellt_am": JETZT,
        "gueltig_bis": JETZT + timedelta(days=7),
        "kontrolle": "zahlung.vier_augen",
        "recht": "zahlung_freigeben",
        "felder": '["zahlung.vier_augen"]',
        "status": "offen",
        **kw,
    }
    return EinstellungsantragRow(**werte)


def test_version_nur_anfuegen_orm(fabrik):
    with fabrik() as s:
        _version(s)
        s.commit()
    with fabrik() as s:
        zeile = s.scalars(select(EinstellungRow)).one()
        zeile.grund = "anders"
        with pytest.raises(UnveraenderbarError, match="unveränderbar"):
            s.flush()
        s.rollback()
        zeile = s.scalars(select(EinstellungRow)).one()
        s.delete(zeile)
        with pytest.raises(UnveraenderbarError, match="unveränderbar"):
            s.flush()
        s.rollback()
    with fabrik() as s:
        assert s.scalars(select(EinstellungRow.grund)).all() == ["Probe"]


def test_version_nur_anfuegen_rohes_sql_sqlite(fabrik, tmp_path):
    with fabrik() as s:
        _version(s)
        s.commit()
    with sqlite3.connect(tmp_path / "e.db") as v:
        with pytest.raises(sqlite3.DatabaseError, match="unveränderbar"):
            v.execute("UPDATE einstellungen SET grund = 'x'")
        with pytest.raises(sqlite3.DatabaseError, match="unveränderbar"):
            v.execute("DELETE FROM einstellungen")
        assert v.execute("SELECT count(*) FROM einstellungen").fetchone() == (1,)


def test_massenaenderung_gesperrt(fabrik):
    assert {"einstellungen", "einstellungsantraege"} <= GESCHUETZT
    with fabrik() as s:
        _version(s)
        s.commit()
    with fabrik() as s:
        for anweisung in (
            update(EinstellungRow).values(grund="x"),
            delete(EinstellungRow),
            insert(EinstellungRow).values(abschnitt="x", version=1),
            update(EinstellungsantragRow).values(status="bestaetigt"),
        ):
            with pytest.raises(UnveraenderbarError, match="Massenänderung"):
                s.execute(anweisung)
        zeile = s.scalars(select(EinstellungRow)).one()
        with pytest.raises(UnveraenderbarError, match="Massenänderung"):
            s.bulk_update_mappings(EinstellungRow, [{"id": zeile.id, "grund": "x"}])
        with pytest.raises(UnveraenderbarError, match="Massenänderung"):
            s.bulk_save_objects([EinstellungRow(abschnitt="y", version=1)])
        with pytest.raises(UnveraenderbarError, match="Massenänderung"):
            s.bulk_insert_mappings(EinstellungRow, [{"abschnitt": "y", "version": 1}])


def test_versionen_je_abschnitt_fortlaufend(fabrik):
    with fabrik() as s:
        assert neueste_versionen(s) == {}
        a1 = _version(s, "mandant")
        a2 = _version(s, "mandant", {"name": "B GmbH"})
        b1 = _version(s, "buchhaltung", {"kontenrahmen": "SKR04"})
        s.commit()
    assert (a1.version, a2.version, b1.version) == (1, 2, 1)
    with fabrik() as s:
        assert neueste_versionen(s) == {"mandant": 2, "buchhaltung": 1}
        v = lade_version(s, "mandant", 2)
        assert v is not None and v.daten == {"name": "B GmbH"}
        assert lade_version(s, "mandant", 3) is None
        assert [(x.abschnitt, x.version) for x in lade_versionen(s)] == [
            ("buchhaltung", 1),
            ("mandant", 1),
            ("mandant", 2),
        ]
        assert [x.version for x in lade_versionen(s, "mandant")] == [1, 2]


def test_lade_versionen_bis_zum_stichtag(fabrik):
    with fabrik() as s:
        _version(s, jetzt=JETZT)
        _version(s, daten={"name": "B"}, jetzt=JETZT + timedelta(days=1))
        s.commit()
    with fabrik() as s:
        assert [v.version for v in lade_versionen(s, bis=JETZT)] == [1]


def test_doppelte_version_scheitert(fabrik):
    with fabrik() as s:
        v = _version(s)
        s.commit()
    with fabrik() as s:
        doppelt = {
            **{
                k: getattr(s.get(EinstellungRow, v.id), k) for k in ("daten", "fehlend")
            },
            "abschnitt": "mandant",
            "version": 1,
            "schema_version": 1,
            "vollstaendig": True,
            "person": "x",
            "grund": "x",
            "quelle": "cli",
            "erstellt_am": JETZT,
            "hash": "f" * 64,
            "vorgaenger_hash": GENESIS,
        }
        s.add(EinstellungRow(**doppelt))
        with pytest.raises(IntegrityError):
            s.flush()


def test_hash_kette_je_abschnitt(fabrik):
    with fabrik() as s:
        m1 = _version(s, "mandant")
        b1 = _version(s, "buchhaltung", {"kontenrahmen": "SKR04"})
        m2 = _version(s, "mandant", {"name": "B"}, antrag_id=7, datei_hash="d" * 64)
        s.commit()
    assert m1.vorgaenger_hash == GENESIS and b1.vorgaenger_hash == GENESIS
    assert m2.vorgaenger_hash == m1.hash
    assert len({m1.hash, b1.hash, m2.hash}) == 3
    with fabrik() as s:
        for zeile in s.scalars(select(EinstellungRow)):
            assert zeilenhash(zeile) == zeile.hash
        assert pruefe_kette(s) == []
        # eine an accounti vorbei angefügte Version mit falschem Vorgänger
        s.connection().execute(
            insert(EinstellungRow.__table__).values(
                abschnitt="mandant",
                version=3,
                daten="{}",
                schema_version=1,
                vollstaendig=True,
                fehlend="[]",
                person="mallory",
                grund="x",
                quelle="cli",
                erstellt_am=JETZT,
                hash="e" * 64,
                vorgaenger_hash=GENESIS,
            )
        )
        befunde = pruefe_kette(s)
    assert len(befunde) == 1 and "mandant v3" in befunde[0]


def test_hash_ohne_id():
    zeile = {
        "abschnitt": "mandant",
        "version": 1,
        "daten": "{}",
        "schema_version": 1,
        "vollstaendig": True,
        "fehlend": "[]",
        "person": "x",
        "grund": "y",
        "quelle": "cli",
        "antrag_id": None,
        "datei_hash": None,
        "erstellt_am": JETZT,
        "vorgaenger_hash": GENESIS,
    }
    assert versionshash({**zeile, "id": 1}) == versionshash({**zeile, "id": 99})
    assert versionshash({**zeile, "hash": "x"}) == versionshash(zeile)
    assert versionshash({**zeile, "grund": "z"}) != versionshash(zeile)


def test_daten_in_normalform(fabrik):
    """Datum, Decimal und Zahlenschlüssel werden zu Text (D9) — Hash und Vergleich
    sehen so unter jeder Datenbank dasselbe."""
    with fabrik() as s:
        v = _version(
            s,
            "elster",
            {"sondervorauszahlung": {2026: Decimal("4000.00")}, "ab": date(2026, 7, 1)},
            fehlend=["mandant.ust_id oder mandant.steuernummer"],
            vollstaendig=False,
        )
        s.commit()
    with fabrik() as s:
        zeile = s.get(EinstellungRow, v.id)
        assert zeile is not None
        assert (
            zeile.daten
            == '{"ab":"2026-07-01","sondervorauszahlung":{"2026":"4000.00"}}'
        )
        geladen = lade_version(s, "elster", 1)
    assert geladen is not None and geladen.fehlend == [
        "mandant.ust_id oder mandant.steuernummer"
    ]
    assert geladen.vollstaendig is False


def _zeile_in(fabrik) -> str:  # noqa: ANN001
    with fabrik() as s:
        v = _version(
            s,
            "elster",
            {"svz": {2026: Decimal("4000.10")}, "ab": date(2026, 7, 1), "x": 1.5},
            jetzt=JETZT,
        )
        s.commit()
    with fabrik() as s:
        zeile = s.get(EinstellungRow, v.id)
        assert zeile is not None and zeilenhash(zeile) == zeile.hash
        return zeile.hash


@mit_postgresql
def test_hash_gleich_unter_sqlite_und_postgresql(fabrik, pg_datenbank):
    engine, pg = session_factory(pg_datenbank())
    init_db(engine)
    try:
        assert _zeile_in(fabrik) == _zeile_in(pg)
    finally:
        engine.dispose()


def test_antrag_status_nur_aus_offen(fabrik):
    with fabrik() as s:
        s.add(_antrag())
        s.commit()
    with fabrik() as s:
        a = s.scalars(select(EinstellungsantragRow)).one()
        a.grund = "anders"
        with pytest.raises(UnveraenderbarError, match="Antrag"):
            s.flush()
        s.rollback()
        a = s.scalars(select(EinstellungsantragRow)).one()
        a.status = "unbekannt"
        with pytest.raises(UnveraenderbarError, match="Antrag"):
            s.flush()
        s.rollback()
        a = s.scalars(select(EinstellungsantragRow)).one()
        a.status = "bestaetigt"
        a.entschieden_von = "erika"
        a.entschieden_am = JETZT
        a.versionen = '{"zahlung":2}'
        s.commit()
    with fabrik() as s:
        a = s.scalars(select(EinstellungsantragRow)).one()
        a.status = "abgelehnt"
        with pytest.raises(UnveraenderbarError, match="nicht mehr offen"):
            s.flush()
        s.rollback()
        (antrag,) = lade_antraege(s)
    assert antrag.status == "bestaetigt" and antrag.entschieden_von == "erika"
    assert antrag.aenderungen == [{"abschnitt": "zahlung", "basis": 1, "daten": {}}]
    assert antrag.felder == ["zahlung.vier_augen"]
    assert antrag.versionen == {"zahlung": 2}


def test_antrag_nicht_loeschbar(fabrik):
    with fabrik() as s:
        s.add(_antrag())
        s.commit()
    with fabrik() as s:
        s.delete(s.scalars(select(EinstellungsantragRow)).one())
        with pytest.raises(UnveraenderbarError, match="Antrag"):
            s.flush()


def test_geheimnis_name_eindeutig(fabrik):
    with fabrik() as s:
        for chiffrat in ("c1", "c2"):
            s.add(
                GeheimnisRow(
                    name="versand.smtp.passwort",
                    chiffrat=chiffrat,
                    gesetzt_am=JETZT,
                    gesetzt_von="erika",
                )
            )
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()
        s.add(
            GeheimnisRow(
                name="llm.api_key", chiffrat="c3", gesetzt_am=JETZT, gesetzt_von="jan"
            )
        )
        s.commit()
    with fabrik() as s:
        (info,) = lade_geheimnisse(s)
        assert info.name == "llm.api_key" and info.gesetzt_von == "jan"
        assert not hasattr(info, "chiffrat")
        assert lade_chiffrate(s) == {"llm.api_key": "c3"}


# --- PostgreSQL: Trigger (AK25) -----------------------------------------------------


def _alembic(url: str, *args: str) -> None:
    umgebung = {**os.environ, "ACCOUNTI_DB": url, "PYTHONPATH": str(WURZEL / "src")}
    e = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(WURZEL / "alembic.ini"), *args],
        cwd=WURZEL,
        env=umgebung,
        capture_output=True,
        text=True,
        check=False,
    )
    assert e.returncode == 0, e.stdout + e.stderr


def _pruefe_trigger_pg(url: str) -> None:
    engine, fabrik = session_factory(url)
    try:
        with fabrik() as s:
            _version(s)  # INSERT geht
            s.commit()
        for sql in (
            "UPDATE einstellungen SET grund = 'x'",
            "DELETE FROM einstellungen",
            "TRUNCATE einstellungen",
        ):
            with (
                pytest.raises(DBAPIError, match="ist unveränderbar"),
                engine.begin() as v,
            ):
                v.execute(text(sql))
        with engine.connect() as v:
            assert v.execute(text("SELECT count(*) FROM einstellungen")).scalar() == 1
    finally:
        engine.dispose()


@mit_postgresql
def test_trigger_postgresql(pg_datenbank):
    """Weg über die Migration (``alembic upgrade head``)."""
    url = pg_datenbank()
    _alembic(url, "upgrade", "head")
    _pruefe_trigger_pg(url)


@mit_postgresql
def test_trigger_nach_init_db_postgresql(pg_datenbank):
    """Weg über ``init_db`` (``create_all`` → ``after_create``)."""
    url = pg_datenbank()
    engine, _ = session_factory(url)
    init_db(engine)
    engine.dispose()
    _pruefe_trigger_pg(url)
