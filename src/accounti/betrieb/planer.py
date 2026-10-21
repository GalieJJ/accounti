"""Geplanter Lauf ohne Cron: ``bank lauf`` und ``aufgaben lauf`` je Gesellschaft.

Jeder Schritt läuft als eigener Prozess (``python -m accounti.cli …``) — ein Fehler
in einer Gesellschaft hält die anderen nicht auf, und jeder Lauf beginnt mit frischem
Zustand. Ins Protokoll kommen Schritt, Rückgabewert und Dauer; die Ausgabe der
Befehle nur geschwärzt und auf Stufe DEBUG (sie kann Namen enthalten). SIGTERM
beendet die Schleife nach dem laufenden Schritt.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import FrameType

from accounti.betrieb.kontext import Kontext
from accounti.betrieb.protokoll import schwaerze

LOG = logging.getLogger("accounti.lauf")
BEFEHLE: list[list[str]] = [["bank", "lauf"], ["aufgaben", "lauf"]]
ZEITLIMIT_SEKUNDEN = 3600


@dataclass(frozen=True)
class Ergebnis:
    argumente: tuple[str, ...]
    code: int
    sekunden: float


Ausfuehren = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def schritte(kontext: Kontext) -> list[list[str]]:
    if kontext.registry.eintraege:
        return [
            ["--gesellschaft", kuerzel, *befehl]
            for kuerzel in sorted(kontext.registry.eintraege)
            for befehl in BEFEHLE
        ]
    return [list(b) for b in BEFEHLE]


def _starte(argumente: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - feste Argumente, kein Shell
        [sys.executable, "-m", "accounti.cli", *argumente],
        capture_output=True,
        text=True,
        timeout=ZEITLIMIT_SEKUNDEN,
        check=False,
    )


def einmal(kontext: Kontext, ausfuehren: Ausfuehren = _starte) -> list[Ergebnis]:
    ergebnisse = []
    for argumente in schritte(kontext):
        beginn = time.monotonic()
        try:
            fertig = ausfuehren(argumente)
            code = fertig.returncode
            for zeile in (fertig.stdout or "").splitlines() + (
                fertig.stderr or ""
            ).splitlines():
                LOG.debug("%s", schwaerze(zeile))
        except subprocess.TimeoutExpired:
            code = -1
        dauer = time.monotonic() - beginn
        ergebnis = Ergebnis(tuple(argumente), code, dauer)
        stufe = logging.INFO if code == 0 else logging.WARNING
        LOG.log(stufe, "%s → %s (%.0f s)", " ".join(argumente), code, dauer)
        ergebnisse.append(ergebnis)
    return ergebnisse


def schleife(
    kontext: Kontext,
    intervall_minuten: float,
    ausfuehren: Ausfuehren = _starte,
    halt: threading.Event | None = None,
) -> int:
    """Läuft, bis ``halt`` gesetzt ist (SIGTERM/SIGINT); gibt die Runden zurück."""
    halt = halt or threading.Event()

    def beenden(_nr: int, _rahmen: FrameType | None) -> None:
        LOG.info("Lauf wird beendet")
        halt.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, beenden)
        signal.signal(signal.SIGINT, beenden)
    runden = 0
    while not halt.is_set():
        einmal(kontext, ausfuehren)
        runden += 1
        halt.wait(intervall_minuten * 60)
    return runden
