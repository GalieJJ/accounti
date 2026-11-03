"""Lesezugriff auf die Datenbanken der Gesellschaften für die Zähler der Oberfläche
(Navigation, ``/gesellschaft``, später die Übersicht) — Baustein 10c, Plan P1, B14.

Nie über ``Dienste._fabrik``: Dort entsteht die Engine samt ``init_db`` unter der
globalen Sperre, eine hängende Verbindung hielte jede Anfrage auf, und eine fehlende
SQLite-Datei entstünde still neu. Hier dagegen:

- eigene Engine je Datenbank **ohne** ``init_db``, angelegt außerhalb jeder globalen
  Sperre (Doppelprüfung beim Eintragen);
- SQLite nur, wenn die Datei existiert, als ``file:…?mode=ro`` mit 2 s Wartezeit;
- PostgreSQL mit ``connect_timeout`` 3 s, ``statement_timeout`` 2 s und
  ``default_transaction_read_only``;
- ein eigener Pool (acht Threads, Vorsilbe ``zaehler``) und eine Gesamtfrist je Aufruf
  (``asyncio.wait_for`` um ``run_in_executor``): Läuft die Frist ab, kehrt die Seite
  sofort zurück, der Thread läuft im Pool bis zum Zeitlimit seiner Verbindung zu Ende,
  und kein Platz im gemeinsamen Threadpool der Anfragen bleibt belegt.

Fehler und Zeitüberschreitungen lassen nur die Zahl weg; das Protokoll nennt nur die
Art (keine Adresse, keine Meldung der Datenbank).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from accounti.api.sicherheit import FEHLER
from accounti.db import AccountiSitzung, registriere_ereignisse

FRIST = 3.0  # Sekunden je Aufruf (Seite wartet höchstens so lange)
SQLITE_WARTEN = 2
PG_VERBINDEN = 3
PG_ANWEISUNG_MS = 2000
THREADS = 8

Zaehler = Callable[[Session], int]


class LeseError(RuntimeError):
    """Die Datenbank ist für den Lesezugriff nicht da (SQLite-Datei fehlt, im
    Speicher, unbekannte Art)."""


@dataclass(frozen=True)
class Verbindung:
    url: str
    optionen: dict[str, Any] = field(default_factory=dict)
    sqlite_datei: Path | None = None


def verbindung(url: str) -> Verbindung:
    """Adresse und Verbindungsoptionen für den reinen Lesezugriff."""
    adresse = make_url(url)
    if adresse.get_backend_name() == "sqlite":
        datei = adresse.database
        if not datei or datei == ":memory:" or datei.startswith("file:"):
            raise LeseError("SQLite ohne Datei lässt sich nicht nur lesend öffnen")
        return Verbindung(
            f"sqlite:///file:{quote(datei)}?mode=ro&uri=true",
            {"timeout": SQLITE_WARTEN},
            Path(datei),
        )
    if adresse.get_backend_name() == "postgresql":
        return Verbindung(
            url,
            {
                "connect_timeout": PG_VERBINDEN,
                "options": f"-c statement_timeout={PG_ANWEISUNG_MS} "
                "-c default_transaction_read_only=on",
            },
        )
    raise LeseError(f"Datenbankart {adresse.get_backend_name()} nicht vorgesehen")


class Lesezugriff:
    """``app.state.lesezugriff``; ``schliesse()`` in der Lebenszeit der App."""

    def __init__(self, threads: int = THREADS) -> None:
        self._sperre = threading.Lock()
        self._engines: dict[str, tuple[Engine, sessionmaker[Session]]] = {}
        self._pool = ThreadPoolExecutor(
            max_workers=threads, thread_name_prefix="zaehler"
        )

    def _fabrik(self, url: str, v: Verbindung) -> sessionmaker[Session]:
        with self._sperre:
            if url in self._engines:
                return self._engines[url][1]
        registriere_ereignisse()
        # außerhalb der Sperre (create_engine verbindet noch nicht); SQLite ohne Pool
        # — keine offenen Dateien zwischen zwei Seiten
        engine = create_engine(
            v.url,
            connect_args=v.optionen,
            hide_parameters=True,
            **({"poolclass": NullPool} if v.sqlite_datei else {}),
        )
        fabrik: sessionmaker[Session] = sessionmaker(
            bind=engine, class_=AccountiSitzung
        )
        with self._sperre:
            if url in self._engines:
                engine.dispose()
                return self._engines[url][1]
            self._engines[url] = (engine, fabrik)
            return fabrik

    @contextmanager
    def sitzung(self, url: str) -> Iterator[Session]:
        """Nur lesende Sitzung; ``LeseError``, wenn die SQLite-Datei fehlt."""
        v = verbindung(url)
        if v.sqlite_datei is not None and not v.sqlite_datei.is_file():
            raise LeseError("Datenbankdatei fehlt")
        with self._fabrik(url, v)() as s:
            try:
                yield s
            finally:
                s.rollback()

    def ausfuehren(self, funktion: Callable[[], Any]) -> asyncio.Future[Any]:
        """``funktion`` im eigenen Pool (nicht im Threadpool der Anfragen)."""
        return asyncio.get_running_loop().run_in_executor(self._pool, funktion)

    def schliesse(self) -> None:
        """Wartet nicht auf hängende Zähler; neue nimmt der Pool nicht mehr an."""
        self._pool.shutdown(wait=False, cancel_futures=True)
        with self._sperre:
            engines = [e for e, _ in self._engines.values()]
            self._engines.clear()
        for engine in engines:
            engine.dispose()


async def zaehle(
    lesezugriff: Lesezugriff,
    url: str,
    funktionen: Mapping[str, Zaehler],
    frist: float | None = None,
) -> dict[str, int] | None:
    """Alle ``funktionen`` mit **einer** Sitzung in **einem** Aufruf des Pools.
    ``None``: Datenbank nicht erreichbar oder Frist abgelaufen (Standard ``FRIST``);
    ein einzelner Zähler, der scheitert, fehlt nur im Ergebnis."""

    def lauf() -> dict[str, int]:
        ergebnis: dict[str, int] = {}
        with lesezugriff.sitzung(url) as s:
            for name, funktion in funktionen.items():
                try:
                    ergebnis[name] = int(funktion(s))
                except Exception as fehler:  # noqa: BLE001 - nur die Zahl fehlt
                    FEHLER.warning(
                        "Zähler %s nicht verfügbar (%s)", name, type(fehler).__name__
                    )
                    s.rollback()
        return ergebnis

    try:
        return await asyncio.wait_for(
            lesezugriff.ausfuehren(lauf), FRIST if frist is None else frist
        )
    except TimeoutError:
        FEHLER.warning("Zähler nicht verfügbar (Zeitüberschreitung)")
    except Exception as fehler:  # noqa: BLE001 - nur die Zahlen fehlen
        FEHLER.warning("Zähler nicht verfügbar (%s)", type(fehler).__name__)
    return None
