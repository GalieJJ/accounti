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
from accounti.einstellungen.leser import (
    DatenbankQuelle,
    EinstellungenNichtLesbar,
    mit_quelle,
)
from accounti.i18n import Text
from accounti.konfiguration import lade_eigene_firma
from accounti.models.auth import STANDARD_GESELLSCHAFT


class SchemaError(RuntimeError):
    """Die Datenbank ist nicht auf dem Stand dieser Version (Migration fehlt)."""


# Einstellungen je Anfrage: so lange wartet der Schnappschuss höchstens auf eine
# gesperrte SQLite-Datei bzw. den Verbindungsaufbau zu PostgreSQL (Sekunden; wie die
# Frist des Lesezugriffs, P1)
QUELLE_WARTEN = 3

# Spalten, die ``init_db`` (create_all) in einer bestehenden Tabelle nicht anlegt —
# ohne sie scheitert jede Anmeldung mit einem SQL-Fehler
PFLICHTSPALTEN = {
    "auth_benutzer": (
        "sprache",  # Baustein 10b
        "darstellung",  # Baustein 10c P1: Anzeige-Vorlieben
        "fachansicht",
        "betraege_verbergen",
        "tastenkuerzel",
    )
}


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
    _anmeldeplaetze: threading.BoundedSemaphore | None = field(default=None, repr=False)
    _einlieferung: dict[str, threading.Lock] = field(default_factory=dict, repr=False)
    _quellen: dict[str, DatenbankQuelle] = field(default_factory=dict, repr=False)

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

    def quelle(self, kuerzel: str) -> DatenbankQuelle:
        """Einstellungen der Gesellschaft (Baustein 10c P4, D4) — eine eigene Engine je
        Datenbank, nie über ``_fabrik``: Die Bindung jeder angemeldeten Anfrage legt so
        keine Datenbank an (``init_db``) und verbindet nie unter der globalen Sperre;
        der Schnappschuss beim ersten Lesen eines Datenbank-Abschnitts wartet höchstens
        ``QUELLE_WARTEN`` Sekunden. Ist die Datenbank nicht lesbar, steht das im
        Schnappschuss; nur dieses Lesen scheitert, ``/gesellschaft``, Wechsel und
        Abmelden gehen weiter (Prüfung sicher-3)."""
        url = self.gesellschaften[kuerzel].datenbank
        with self._sperre:  # DatenbankQuelle(…) verbindet noch nicht
            if url not in self._quellen:
                self._quellen[url] = DatenbankQuelle(
                    url, wartezeit=QUELLE_WARTEN, behalten=True
                )
            return self._quellen[url]

    def pruefe_schema(self) -> None:
        """Systemdatenbank auf dem Stand dieser Version? Sonst ``SchemaError`` mit
        Hinweis (ohne URL). Neue Tabellen legt ``init_db`` selbst an, neue Spalten
        nur die Migration."""
        from sqlalchemy import inspect

        with self.system() as s:
            pruefer = inspect(s.connection())
            fehlt = [
                f"{tabelle}.{spalte}"
                for tabelle, spalten in PFLICHTSPALTEN.items()
                for vorhanden in [{c["name"] for c in pruefer.get_columns(tabelle)}]
                for spalte in spalten
                if spalte not in vorhanden
            ]
        if fehlt:
            raise SchemaError(
                str(
                    Text(
                        "Die Systemdatenbank ist nicht auf dem Stand dieser Version "
                        "(es fehlen: %(spalten)s) — vorher accounti db upgrade für die "
                        "Systemdatenbank und jede Gesellschaftsdatenbank ausführen; "
                        "bei Datenbanken mit Versionsvermerk geht gleichwertig alembic "
                        "upgrade head (siehe docs/betrieb.md, Upgrades)",
                        spalten=", ".join(fehlt),
                    )
                )
            )

    def einlieferung(self, kuerzel: str) -> threading.Lock:
        """Belege einer Gesellschaft nacheinander aufnehmen (Dublettenprüfung) —
        im App-Prozess; Läufe sperren prozessübergreifend (``betrieb.laufsperre``)."""
        with self._sperre:
            return self._einlieferung.setdefault(kuerzel, threading.Lock())

    def anmeldeplatz(self) -> bool:
        """Platz für eine Passwort-Prüfung (scrypt, 128 MiB) — höchstens
        ``server.anmeldungen_gleichzeitig`` zugleich. Wartet nicht (``False``: alle
        belegt); das Warten übernimmt die Seite ohne Arbeitsthread. Freigeben mit
        ``anmeldeplatz_frei``."""
        with self._sperre:
            if self._anmeldeplaetze is None:
                self._anmeldeplaetze = threading.BoundedSemaphore(
                    self.server.anmeldungen_gleichzeitig
                )
            plaetze = self._anmeldeplaetze
        return plaetze.acquire(blocking=False)

    def anmeldeplatz_frei(self) -> None:
        assert self._anmeldeplaetze is not None
        self._anmeldeplaetze.release()

    def schliesse(self) -> None:
        with self._sperre:
            for engine, _ in self._engines.values():
                engine.dispose()
            self._engines.clear()
            quellen = list(self._quellen.values())
            self._quellen.clear()
        for quelle in quellen:
            quelle.schliesse()


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
    """Die eine Gesellschaft ohne Registry — ihr Name aus ``mandant.name``, wie er in
    ihrer Datenbank gilt (D21: ein im Browser geänderter Name folgt nach dem Neustart);
    ohne Datei und Version bzw. mit unlesbarer Datenbank bleibt es beim Kürzel."""
    try:
        with mit_quelle(DatenbankQuelle(db), config):
            firma = lade_eigene_firma(config)
    except EinstellungenNichtLesbar:
        firma = None
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
