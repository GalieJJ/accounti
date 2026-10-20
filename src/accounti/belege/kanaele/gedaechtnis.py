"""Gedächtnis der Kanäle — welche Nachricht schon verarbeitet ist.

Ein Kanal merkt sich eine Nachricht erst, wenn alle ihre Dateien aufgenommen sind.
Geschrieben wird in einer eigenen Transaktion: Das Gedächtnis hängt nicht davon ab,
wann der Aufrufer seine Sitzung festschreibt.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from accounti.db.repo_kanaele import (
    merke_nachricht,
    nachricht_bekannt,
    nachricht_zu_datei,
)
from accounti.models import Beleg
from accounti.models.kanaele import AbgeholteNachricht


class Gedaechtnis(Protocol):
    def bekannt(
        self,
        kanal: str,
        quelle: str,
        schluessel: str,
        message_id: str | None = None,
    ) -> bool: ...

    def merke(self, nachricht: AbgeholteNachricht) -> None: ...


class DbGedaechtnis:
    """Gedächtnis in der Datenbank (Tabelle ``kanal_nachrichten``)."""

    def __init__(self, make_session: sessionmaker[Session]) -> None:
        self.make_session = make_session

    def bekannt(
        self,
        kanal: str,
        quelle: str,
        schluessel: str,
        message_id: str | None = None,
    ) -> bool:
        with self.make_session() as s:
            return nachricht_bekannt(s, kanal, quelle, schluessel, message_id)

    def merke(self, nachricht: AbgeholteNachricht) -> None:
        with self.make_session() as s:
            if nachricht_bekannt(
                s, nachricht.kanal, nachricht.quelle, nachricht.schluessel
            ):
                return
            try:
                merke_nachricht(s, nachricht)
                s.commit()
            except IntegrityError:  # gleichzeitig schon gemerkt
                s.rollback()


def absender_zu_beleg(session: Session, beleg: Beleg) -> AbgeholteNachricht | None:
    """Die Nachricht, mit der die Datei des Belegs kam — Absender als Hinweis."""
    return nachricht_zu_datei(session, beleg.datei_hash)
