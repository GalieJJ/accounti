"""Symbole der Oberfläche: ``statisch/symbole.svg`` (Lucide, Plan P1 L6).

Die Ids liest das Modul einmal aus dem Sprite. ``symbol_url`` baut den Verweis für
``<use href>`` mit Versionsanhang; ein unbekannter Name scheitert, statt in einen Pfad
zu gelangen. ``symbol_klasse`` bildet Größe und Strich auf Klassen ab — das Element
trägt weder ``width``/``height`` noch ``style`` (CSP).
"""

from __future__ import annotations

import re
from functools import cache
from importlib import resources

from accounti import __version__

GROESSEN = (14, 16, 18, 22, 28, 40)


@cache
def symbole() -> frozenset[str]:
    """Die Ids im Sprite."""
    text = (
        resources.files("accounti.api")
        .joinpath("statisch", "symbole.svg")
        .read_text(encoding="utf-8")
    )
    return frozenset(re.findall(r'<symbol id="([a-z0-9-]+)"', text))


def symbol_url(name: str) -> str:
    if name not in symbole():
        raise ValueError(f"Symbol {name!r} steht nicht im Sprite")
    return f"/statisch/symbole.svg?v={__version__}#{name}"


def symbol_klasse(groesse: int = 18, kraeftig: bool = False) -> str:
    if groesse not in GROESSEN:
        raise ValueError(f"Symbolgröße {groesse!r} gibt es nicht ({GROESSEN})")
    return f"symbol symbol-{groesse}" + (" symbol-kraeftig" if kraeftig else "")
