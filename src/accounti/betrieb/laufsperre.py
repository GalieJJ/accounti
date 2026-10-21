"""Je Gesellschaft und Art höchstens ein Lauf — auch über Prozesse hinweg.

``bank lauf`` und ``aufgaben lauf`` starten aus dem Compose-Dienst ``lauf`` (eigener
Prozess), aus Cron und über ``POST /api/v1/laeufe/…`` in der App. Zwei gleichzeitige
Läufe kontierten denselben Umsatz doppelt (``transaktion_id`` ist nicht eindeutig).
Ein ``threading.Lock`` in der App sieht den anderen Prozess nicht; deshalb sperrt
die Datenbank selbst:

- PostgreSQL: ``pg_try_advisory_lock`` auf einer eigenen Verbindung (je Datenbank;
  stirbt der Prozess, endet die Verbindung und mit ihr die Sperre),
- SQLite: eine Dateisperre (``flock``) neben der Datenbankdatei,
- SQLite im Speicher (Tests): eine Sperre im Prozess.

Wer die Sperre nicht bekommt, wartet nicht: ``LaufLaeuftError`` (CLI: Exit 1,
REST: 409).
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.pool import NullPool


class LaufLaeuftError(RuntimeError):
    def __init__(self, art: str) -> None:
        self.art = art
        super().__init__(f"Der Lauf {art} läuft schon — später noch einmal starten")


_IM_PROZESS: dict[str, threading.Lock] = {}
_REGISTER = threading.Lock()


def _schluessel(art: str) -> int:
    """64-Bit-Schlüssel für ``pg_try_advisory_lock`` (gilt je Datenbank)."""
    roh = hashlib.sha256(f"accounti-lauf:{art}".encode()).digest()[:8]
    return int.from_bytes(roh, "big", signed=True)


@contextmanager
def _postgresql(db: str, art: str) -> Iterator[None]:
    engine = create_engine(db, poolclass=NullPool, hide_parameters=True)
    try:
        with engine.connect() as verbindung:
            verbindung = verbindung.execution_options(isolation_level="AUTOCOMMIT")
            schluessel = {"k": _schluessel(art)}
            frei = verbindung.execute(
                text("SELECT pg_try_advisory_lock(:k)"), schluessel
            ).scalar()
            if not frei:
                raise LaufLaeuftError(art)
            try:
                yield
            finally:
                verbindung.execute(text("SELECT pg_advisory_unlock(:k)"), schluessel)
    finally:
        engine.dispose()


@contextmanager
def _datei(datenbank: Path, art: str) -> Iterator[None]:
    import fcntl

    sperrdatei = datenbank.with_name(f"{datenbank.name}.lauf-{art}.sperre")
    sperrdatei.parent.mkdir(parents=True, exist_ok=True)
    with open(sperrdatei, "a+", encoding="utf-8") as datei:
        try:
            fcntl.flock(datei.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as fehler:
            raise LaufLaeuftError(art) from fehler
        try:
            yield
        finally:
            fcntl.flock(datei.fileno(), fcntl.LOCK_UN)


@contextmanager
def _im_prozess(schluessel: str, art: str) -> Iterator[None]:
    with _REGISTER:
        sperre = _IM_PROZESS.setdefault(schluessel, threading.Lock())
    if not sperre.acquire(blocking=False):
        raise LaufLaeuftError(art)
    try:
        yield
    finally:
        sperre.release()


@contextmanager
def laufsperre(db: str, art: str) -> Iterator[None]:
    """Hält die Sperre für den Lauf ``art`` in der Datenbank ``db``."""
    url = make_url(db)
    if url.get_backend_name() == "postgresql":
        with _postgresql(db, art):
            yield
        return
    pfad = url.database or ""
    if (
        url.get_backend_name() == "sqlite"
        and pfad not in ("", ":memory:")
        and not pfad.startswith("file:")
    ):
        with _datei(Path(pfad).expanduser().resolve(), art):
            yield
        return
    with _im_prozess(f"{url.render_as_string(hide_password=True)}|{art}", art):
        yield
