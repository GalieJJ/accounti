"""Geplanter Lauf ohne Cron: ``bank lauf`` und ``aufgaben lauf`` je Gesellschaft.

Jeder Schritt läuft als eigener Prozess (``python -m accounti.cli …``) — ein Fehler
in einer Gesellschaft hält die anderen nicht auf, und jeder Lauf beginnt mit frischem
Zustand. Ins Protokoll kommen Schritt, Rückgabewert und Dauer; die Ausgabe der
Befehle nur geschwärzt und auf Stufe DEBUG (sie kann Namen enthalten). Schlägt ein
Schritt fehl, steht sein Grund — die letzten Zeilen der Ausgabe, geschwärzt und
gekürzt — mit in der Warnung (sonst stand dort nur „bank lauf → 1“; Runde 5, g4w N6).
Rahmenzeichen (Rich) kommen nicht ins Protokoll, jede Zeile ist begrenzt (Runde 7,
g6w B-1). SIGTERM beendet die Schleife nach dem laufenden Schritt.
"""

from __future__ import annotations

import logging
import os
import re
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
GRUND_ZEILEN = 5  # die Meldung am Ende der Ausgabe
AUSGABE_BREITE = "10000"  # COLUMNS der Schritte: Rich bricht so nicht um
GRUND_ZEICHEN = 600
ZEILE_ZEICHEN = 1000  # höchstens so lang steht eine Zeile der Ausgabe auf DEBUG
# Rahmen von Rich (Box Drawing, U+2500–U+257F) — sonst stand ein Traceback in
# Terminalbreite im Protokoll (mit COLUMNS=10000: 10 000 Zeichen je Zeile)
_RAHMEN = re.compile(r"[\u2500-\u257f]+")


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
        # ohne Terminal bricht Rich nach 80 Zeichen hart um — ein zerschnittenes
        # Geheimnis (Token in einer Webhook-Adresse) erkennt kein Muster ganz
        # (Runde 6, g5w-konten N1). Ein Traceback kommt von Python, nicht als
        # Rich-Panel in Terminalbreite (Typer ab 0.12: TYPER_STANDARD_TRACEBACK,
        # davor _TYPER_STANDARD_TRACEBACK; Runde 7, g6w B-1)
        env={
            **os.environ,
            "COLUMNS": AUSGABE_BREITE,
            "TYPER_STANDARD_TRACEBACK": "1",
            "_TYPER_STANDARD_TRACEBACK": "1",
        },
    )


def _ohne_rahmen(zeile: str) -> str:
    """Ohne Rahmenzeichen und Füllraum — der Einzug bleibt (Traceback lesbar)."""
    zeile = _RAHMEN.sub(" ", zeile).rstrip()
    rest = zeile.lstrip(" ")
    return zeile[: min(len(zeile) - len(rest), 8)] + " ".join(rest.split())


def _debug_zeile(zeile: str) -> str:
    # erst schwärzen, dann kürzen: ein angeschnittenes Geheimnis erkennt kein Muster
    text = schwaerze(_ohne_rahmen(zeile))
    return text if len(text) <= ZEILE_ZEICHEN else text[:ZEILE_ZEICHEN] + " …"


def _grund(zeilen: list[str]) -> str:
    """Die letzten Zeilen der Ausgabe eines fehlgeschlagenen Schritts, geschwärzt —
    jede Zeile für sich und verbunden (ein Muster über einen Umbruch hinweg); ohne
    Rahmenzeichen, die nur aus ihnen bestehenden Zeilen zählen nicht."""
    belegt = [
        schwaerze(text) for z in zeilen if (text := " ".join(_ohne_rahmen(z).split()))
    ]
    # erst schwärzen, dann kürzen: eine angeschnittene IBAN erkennt kein Muster
    text = schwaerze(" ".join(belegt[-GRUND_ZEILEN:]))
    return text if len(text) <= GRUND_ZEICHEN else "…" + text[-GRUND_ZEICHEN:]


def einmal(kontext: Kontext, ausfuehren: Ausfuehren = _starte) -> list[Ergebnis]:
    ergebnisse = []
    for argumente in schritte(kontext):
        beginn = time.monotonic()
        try:
            fertig = ausfuehren(argumente)
            code = fertig.returncode
            zeilen = (fertig.stdout or "").splitlines() + (
                fertig.stderr or ""
            ).splitlines()
            for zeile in zeilen:
                if zeile.strip() and not _RAHMEN.fullmatch(zeile.strip()):
                    LOG.debug("%s", _debug_zeile(zeile))
            grund = _grund(zeilen) if code != 0 else ""
        except subprocess.TimeoutExpired:
            code = -1
            grund = f"Zeitlimit von {ZEITLIMIT_SEKUNDEN} s überschritten"
        dauer = time.monotonic() - beginn
        ergebnis = Ergebnis(tuple(argumente), code, dauer)
        if code == 0:
            LOG.info("%s → %s (%.0f s)", " ".join(argumente), code, dauer)
        else:
            LOG.warning(
                "%s → %s (%.0f s)%s",
                " ".join(argumente),
                code,
                dauer,
                f": {grund}" if grund else "",
            )
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
