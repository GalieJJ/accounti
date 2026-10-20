"""Anbindungen anderer Bausteine finden — ohne dass dieses Paket sie kennt.

Ein Baustein, der eigene Prüfläufe, Objekttypen oder Benachrichtigungskanäle
mitbringt, trägt sie in einem Modul ``accounti.<baustein>.aufgaben_anbindung`` ein
(``registriere_prueflauf``, ``registriere_objekttyp``, ``KANAELE[...]``). Die
Funktionen, die diese Registries lesen (``fuehre_prueflaeufe_aus``, ``beschreibe``,
``loese_auf``, ``baue_kanaele``), laden vorher alle solchen Module — wie die
Befehlsgruppen in ``befehle/`` und die Tabellen in ``db/tabellen_*``. Sonst liefe
ein Prüflauf nur, wenn zufällig jemand sein Modul importiert hat.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

ANBINDUNG = "aufgaben_anbindung"

# Pakete, deren Unterpakete durchsucht werden (Tests ergänzen ein eigenes)
PAKETE: list[str] = ["accounti"]

_gefunden: dict[str, list[str]] = {}


def _durchsuche(paket: str) -> list[str]:
    pfade = [str(p) for p in importlib.import_module(paket).__path__]
    module = []
    for info in sorted(pkgutil.iter_modules(pfade), key=lambda i: i.name):
        if not info.ispkg:
            continue
        unterpfade = [
            str(Path(p) / info.name) for p in pfade if (Path(p) / info.name).is_dir()
        ]
        if any(m.name == ANBINDUNG for m in pkgutil.iter_modules(unterpfade)):
            module.append(f"{paket}.{info.name}.{ANBINDUNG}")
    return module


def lade_anbindungen() -> list[str]:
    """Importiert alle ``<paket>.<baustein>.aufgaben_anbindung`` (je Paket einmal)
    und gibt ihre Namen zurück. Ein fehlerhaftes Modul bricht laut ab."""
    geladen = []
    for paket in PAKETE:
        if paket not in _gefunden:
            module = _durchsuche(paket)
            for name in module:
                importlib.import_module(name)
            _gefunden[paket] = module
        geladen.extend(_gefunden[paket])
    return geladen


def vergiss() -> None:
    """Für Tests: beim nächsten Aufruf wieder suchen."""
    _gefunden.clear()
