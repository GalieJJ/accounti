"""Zustand der Web-Anwendung: Systemdatenbank, Gesellschaften, Datenbanken je
Gesellschaft, Einstellungen, Uhr und Tresor-Schlüssel.

Ohne Registry gibt es genau eine Gesellschaft ``standard`` mit Datenbank, Archiv und
Konfiguration aus den Optionen von ``accounti serve`` (bzw. ``ACCOUNTI_DB``,
``ACCOUNTI_ARCHIV``, ``ACCOUNTI_KONFIG``); die Systemdatenbank ist dann ihre
Datenbank.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from accounti.api.einstellungen import ServerEinstellungen, lade_server
from accounti.auth.einstellungen import AuthEinstellungen, lade_auth
from accounti.bank.tresor import lade_schluessel
from accounti.belege.pipeline import Erkenner
from accounti.betrieb.gesellschaften import Gesellschaft
from accounti.betrieb.kontext import Kontext
from accounti.db import init_db, session_factory
from accounti.konfiguration import lade_eigene_firma
from accounti.models.auth import STANDARD_GESELLSCHAFT


@dataclass
class Dienste:
    systemdatenbank: str
    gesellschaften: dict[str, Gesellschaft]
    auth: AuthEinstellungen = field(default_factory=AuthEinstellungen)
    server: ServerEinstellungen = field(default_factory=ServerEinstellungen)
    schluessel: Callable[[], str] = lade_schluessel
    uhr: Callable[[], datetime] = datetime.now
    # Belegerkennung (OCR) für Belege über die API; ohne: nur archivieren + erfassen
    erkenner: Callable[[Gesellschaft], Erkenner | None] = field(
        default=lambda _: None, repr=False
    )
    _engines: dict[str, tuple[Engine, sessionmaker[Session]]] = field(
        default_factory=dict, repr=False
    )
    _sperre: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _laeufe: dict[str, threading.Lock] = field(default_factory=dict, repr=False)

    def _fabrik(self, url: str) -> sessionmaker[Session]:
        with self._sperre:
            if url not in self._engines:
                engine, fabrik = session_factory(url)
                init_db(engine)
                self._engines[url] = (engine, fabrik)
            return self._engines[url][1]

    @contextmanager
    def system(self) -> Iterator[Session]:
        with self._fabrik(self.systemdatenbank)() as s:
            yield s

    @contextmanager
    def datenbank(self, kuerzel: str) -> Iterator[Session]:
        with self._fabrik(self.gesellschaften[kuerzel].datenbank)() as s:
            yield s

    def laufsperre(self, schluessel: str) -> threading.Lock:
        """Eine Sperre je Gesellschaft und Lauf — kein Lauf zweimal gleichzeitig."""
        with self._sperre:
            return self._laeufe.setdefault(schluessel, threading.Lock())

    def schliesse(self) -> None:
        with self._sperre:
            for engine, _ in self._engines.values():
                engine.dispose()
            self._engines.clear()


def ocr_erkenner(g: Gesellschaft) -> Erkenner | None:
    """Belegerkennung wie beim Webhook — eigene Firma aus der Konfiguration."""
    from accounti.belege.erkennung import BelegErkenner
    from accounti.belege.ocr.tesseract import TesseractEngine

    firma = lade_eigene_firma(g.konfiguration)
    return BelegErkenner(
        ocr=TesseractEngine(sprache="deu"),
        eigene_ust_ids={firma.ust_id} if firma and firma.ust_id else set(),
        eigene_firma=firma.name if firma else None,
    )


def einzelne_gesellschaft(db: str, archiv: str, config: str) -> Gesellschaft:
    firma = lade_eigene_firma(config)
    return Gesellschaft(
        kuerzel=STANDARD_GESELLSCHAFT,
        name=firma.name if firma else STANDARD_GESELLSCHAFT,
        datenbank=db,
        archiv=archiv,
        konfiguration=config,
        regeln=str(Path(config).parent / "regeln.yaml"),
    )


def dienste_aus_kontext(kontext: Kontext, db: str, archiv: str, config: str) -> Dienste:
    """Für ``accounti serve``: Registry, sonst die eine Gesellschaft der Optionen."""
    kontext.pruefe()
    if kontext.registry.eintraege:
        gesellschaften = {g.kuerzel: g for g in kontext.registry.alle()}
        pfad = kontext.globale_konfiguration
    else:
        gesellschaften = {
            STANDARD_GESELLSCHAFT: einzelne_gesellschaft(db, archiv, config)
        }
        pfad = config
    return Dienste(
        systemdatenbank=kontext.systemdatenbank(db),
        gesellschaften=gesellschaften,
        auth=lade_auth(pfad),
        server=lade_server(pfad),
        erkenner=ocr_erkenner,
    )
