"""Übermittler — die schmale Schicht zwischen accounti und ELSTER.

Ein Übermittler kann einen Datensatz **prüfen** (ohne Versand) und **senden**. Zwei
gibt es:

- ``EricUebermittler`` (``elster/eric.py``): die ERiC-Bibliothek der Steuerverwaltung
  über ctypes. Aktiv nur, wenn Bibliothek, Zertifikat und PIN-Datei konfiguriert sind
  und der Schlüssel für die PIN in der Umgebung steht.
- ``AttrappenUebermittler``: für Tests und Probeläufe; gibt nie etwas ab. Nur auf
  ausdrücklichen Wunsch (``elster.uebermittler: attrappe``), im Protokoll als Weg
  „attrappe“ erkennbar.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from accounti.bank.tresor import UMGEBUNG, TresorError
from accounti.elster.konfiguration import ElsterEinstellungen
from accounti.elster.pin import PinError, lade_pin


@dataclass(frozen=True)
class Ergebnis:
    erfolgreich: bool
    ticket: str | None = None  # ELSTER-Transferticket
    pruefbericht: str = ""  # Rückgabe von ERiC (Fehler, Hinweise)
    server_antwort: str | None = None  # Antwort des Annahmeservers
    pdf: bytes | None = None  # Übertragungsprotokoll als PDF
    fehler: str | None = None
    hinweise: tuple[str, ...] = ()


class Uebermittler(Protocol):
    @property
    def weg(self) -> str: ...

    def pruefe(self, xml: str, datenart_version: str) -> Ergebnis: ...

    def sende(self, xml: str, datenart_version: str) -> Ergebnis: ...


class UebermittlungError(RuntimeError):
    """Die Übermittlung ist so nicht zulässig oder nicht möglich."""


class AttrappenUebermittler:
    """Nimmt alles an und gibt nichts ab — für Tests und Probeläufe."""

    weg = "attrappe"

    def __init__(self, fehler: str | None = None, hinweise: tuple[str, ...] = ()):
        self.fehler = fehler
        self.hinweise = hinweise
        self.geprueft: list[str] = []
        self.gesendet: list[str] = []

    def pruefe(self, xml: str, datenart_version: str) -> Ergebnis:
        self.geprueft.append(xml)
        return Ergebnis(
            self.fehler is None,
            pruefbericht="<EricBearbeiteVorgang/>",
            fehler=self.fehler,
            hinweise=self.hinweise,
        )

    def sende(self, xml: str, datenart_version: str) -> Ergebnis:
        self.gesendet.append(xml)
        if self.fehler is not None:
            return Ergebnis(False, fehler=self.fehler)
        ticket = f"attrappe-{len(self.gesendet):04d}"
        antwort = (
            "<Elster><TransferHeader><TransferTicket>"
            f"{ticket}</TransferTicket><RC><Rueckgabe><Code>0</Code>"
            "<Text>Attrappe — nichts wurde abgegeben</Text></Rueckgabe></RC>"
            "</TransferHeader></Elster>"
        )
        return Ergebnis(
            True,
            ticket=ticket,
            pruefbericht="<EricBearbeiteVorgang/>",
            server_antwort=antwort,
            pdf=b"%PDF-1.4\n% Attrappe\n",
            hinweise=self.hinweise,
        )


def waehle_uebermittler(
    einstellungen: ElsterEinstellungen, umgebung: Mapping[str, str] | None = None
) -> tuple[Uebermittler | None, str]:
    """(Übermittler oder ``None``, Begründung für Menschen)."""
    from accounti.elster.eric import EricUebermittler

    if einstellungen.uebermittler == "attrappe":
        grund = "Attrappe (elster.uebermittler) — nichts wird abgegeben"
        return AttrappenUebermittler(), grund
    eric = einstellungen.eric
    for feld in ("bibliothek", "zertifikat", "pin_datei"):
        if not getattr(eric, feld):
            return None, f"ERiC nicht eingerichtet: elster.eric.{feld} fehlt"
    assert eric.bibliothek and eric.zertifikat and eric.pin_datei
    for name, pfad in (
        ("Bibliothek", eric.bibliothek),
        ("Zertifikat", eric.zertifikat),
    ):
        if not Path(pfad).is_file():
            return None, f"ERiC: {name} {pfad} nicht gefunden"
    umgebung = os.environ if umgebung is None else umgebung
    schluessel = umgebung.get(UMGEBUNG)
    if not schluessel:
        return None, f"ERiC: {UMGEBUNG} fehlt — ohne ihn bleibt die PIN verschlossen"
    try:
        pin = lade_pin(eric.pin_datei, schluessel)
    except (PinError, TresorError) as fehler:
        return None, f"ERiC: PIN nicht verfügbar — {fehler}"
    uebermittler = EricUebermittler(
        bibliothek=eric.bibliothek,
        zertifikat=eric.zertifikat,
        pin=pin,
        plugins=eric.plugins,
        log=eric.log,
        druck_version=eric.druck_parameter_version,
        crypto_version=eric.verschluesselungs_parameter_version,
    )
    return uebermittler, f"ERiC ({eric.bibliothek})"
