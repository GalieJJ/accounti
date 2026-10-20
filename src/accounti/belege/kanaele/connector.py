"""Connector-Kanal — Belege aus Belegportalen und Rechnungssammeldiensten.

Wie bei den Bank-Providern: eine Basisklasse plus Registry (``BELEG_CONNECTOREN``,
Typ → Klasse). Ein Connector kennt nur die API seines Portals — er listet Dokumente
und lädt eines; Prüfung, Gedächtnis und Pipeline sind für alle gleich. Mitgeliefert
ist der generische Typ ``json`` (``json_http.py``), der typische REST-Portale allein
über die Konfiguration beschreibt.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, ValidationError

from accounti.belege.kanaele import RohBeleg, registriere
from accounti.belege.kanaele.abholung import AbholKanal, KanalError
from accounti.belege.kanaele.einstellungen import ConnectorEintrag
from accounti.belege.kanaele.gedaechtnis import Gedaechtnis
from accounti.belege.kanaele.pruefung import (
    STANDARD_MAX_BYTES,
    DateiAbgelehntError,
    Dateipruefung,
)
from accounti.konfiguration import KonfigurationError
from accounti.models.kanaele import AbgeholteNachricht

KANAL = "connector"


@dataclass(frozen=True)
class PortalDokument:
    """Ein Dokument, wie das Portal es auflistet."""

    id: str
    dateiname: str | None = None
    absender: str | None = None
    datum: str | None = None
    url: str | None = None


class BelegConnector:
    """Basisklasse — ein Connector-Typ mit eigenem Einstellungsmodell.

    ``geheimnis`` liefert den im Tresor gespeicherten Zugang (``accounti kanaele
    zugang connector NAME``) oder ``None``; er wird erst bei Bedarf abgefragt.
    """

    typ: ClassVar[str] = "basis"
    beschreibung: ClassVar[str] = ""
    Einstellungen: ClassVar[type[BaseModel]] = BaseModel

    def __init__(
        self,
        name: str,
        einstellungen: BaseModel,
        geheimnis: Callable[[], str | None],
        max_bytes: int = STANDARD_MAX_BYTES,
    ) -> None:
        self.name = name
        self.einstellungen = einstellungen
        self.geheimnis = geheimnis
        self.max_bytes = max_bytes
        self.hinweise: list[str] = []

    def dokumente(self) -> Iterator[PortalDokument]:
        """Alle Dokumente des Portals (Gemerktes filtert der Kanal)."""
        raise NotImplementedError

    def lade(self, dokument: PortalDokument) -> bytes:
        """Die Datei eines Dokuments; ``KanalError``, wenn das gerade nicht geht."""
        raise NotImplementedError


BELEG_CONNECTOREN: dict[str, type[BelegConnector]] = {}


def registriere_connector(klasse: type[BelegConnector]) -> type[BelegConnector]:
    BELEG_CONNECTOREN[klasse.typ] = klasse
    return klasse


def _fehlertext(fehler: ValidationError) -> str:
    teile = []
    for f in fehler.errors():
        pfad = ".".join(str(x) for x in f["loc"])
        grund = (
            "fehlt"
            if f["type"] == "missing"
            else "unbekanntes Feld"
            if f["type"] == "extra_forbidden"
            else str(f["msg"]).removeprefix("Value error, ")
        )
        teile.append(f"{pfad}: {grund}" if pfad else grund)
    return "; ".join(teile)


def baue_connector(
    eintrag: ConnectorEintrag,
    geheimnis: Callable[[], str | None],
    max_bytes: int = STANDARD_MAX_BYTES,
) -> BelegConnector:
    """Connector aus einem Konfigurationseintrag; prüft die Einstellungen des Typs."""
    klasse = BELEG_CONNECTOREN.get(eintrag.typ)
    if klasse is None:
        msg = (
            f"belegkanaele.connectoren[{eintrag.name}]: Connector-Typ "
            f"'{eintrag.typ}' gibt es nicht (vorhanden: "
            f"{', '.join(sorted(BELEG_CONNECTOREN))})"
        )
        raise KonfigurationError(msg)
    try:
        einstellungen = klasse.Einstellungen.model_validate(eintrag.einstellungen())
    except ValidationError as fehler:
        msg = f"belegkanaele.connectoren[{eintrag.name}]: {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from None
    return klasse(eintrag.name, einstellungen, geheimnis, max_bytes)


@registriere
class ConnectorKanal(AbholKanal):
    """Holt neue Dokumente eines konfigurierten Connectors."""

    name = KANAL
    beschreibung = (
        "Belegportale über deren API (Registry BELEG_CONNECTOREN, generisch: json)"
    )

    def __init__(
        self,
        connector: BelegConnector,
        gedaechtnis: Gedaechtnis,
        pruefung: Dateipruefung | None = None,
    ) -> None:
        super().__init__(f"Connector {connector.name} ({connector.typ})")
        self.connector = connector
        self.gedaechtnis = gedaechtnis
        self.pruefung = pruefung or Dateipruefung(max_bytes=connector.max_bytes)
        connector.max_bytes = self.pruefung.max_bytes
        self._bestaetigt: set[int] = set()

    def bestaetige(self, roh: RohBeleg) -> None:
        self._bestaetigt.add(id(roh))

    def _merke(
        self, dokument: PortalDokument, roh: RohBeleg | None, hinweis: str | None
    ) -> None:
        self.gedaechtnis.merke(
            AbgeholteNachricht(
                kanal=KANAL,
                quelle=self.connector.name,
                schluessel=dokument.id,
                absender=dokument.absender,
                betreff=dokument.dateiname,
                datei_hashes=[hashlib.sha256(roh.inhalt).hexdigest()] if roh else [],
                hinweis=hinweis,
            )
        )

    def abholen(self) -> Iterator[RohBeleg]:
        name = self.connector.name
        try:
            for dokument in self.connector.dokumente():
                if self.gedaechtnis.bekannt(KANAL, name, dokument.id):
                    continue
                try:
                    inhalt = self.connector.lade(dokument)
                    dateiname = self.pruefung.pruefe(
                        dokument.dateiname or f"{name}-{dokument.id}", inhalt
                    )
                except KanalError as fehler:
                    self.hinweise.append(
                        f"{name}: Dokument {dokument.id} nicht geladen ({fehler}) — "
                        "der nächste Lauf versucht es erneut"
                    )
                    continue
                except DateiAbgelehntError as fehler:
                    text = f"übersprungen: {fehler}"
                    self.hinweise.append(f"{name}: Dokument {dokument.id}: {text}")
                    self._merke(dokument, None, text)
                    continue
                herkunft = f"Connector {name}: Dokument {dokument.id}" + (
                    f" von {dokument.absender}" if dokument.absender else ""
                )
                roh = RohBeleg(
                    dateiname=dateiname,
                    inhalt=inhalt,
                    kanal=KANAL,
                    herkunft=herkunft[:500],
                )
                yield roh
                if id(roh) in self._bestaetigt:
                    self._merke(dokument, roh, None)
        finally:
            self.hinweise.extend(self.connector.hinweise)
            self.connector.hinweise.clear()


# eingebaute Connectoren registrieren
from accounti.belege.kanaele import json_http  # noqa: E402, F401
