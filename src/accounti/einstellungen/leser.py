"""Abschnittsleser der Einstellungen (Baustein 10c, Paket P4) — ohne Importe aus
Fachmodulen.

``normalform`` bringt Werte in JSON-Typen (D9): Datum als ISO-Text, ``Decimal`` als
Text, Schlüssel als Text, Tupel als Listen. In dieser Form werden Versionen
gespeichert, gehasht, verglichen und ins Journal geschrieben.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePath
from typing import Any


def normalform(wert: Any) -> Any:
    """``wert`` in JSON-Typen; ein Typ ohne Normalform ist ein ``TypeError``."""
    if isinstance(wert, enum.Enum):  # vor str: (str, Enum) als sein Wert
        return normalform(wert.value)
    if isinstance(wert, Mapping):
        return {str(k): normalform(v) for k, v in wert.items()}
    if isinstance(wert, list | tuple):
        return [normalform(v) for v in wert]
    if wert is None or isinstance(wert, bool | int | str):
        return wert
    if isinstance(wert, float):
        if not math.isfinite(wert):
            msg = f"Zahl {wert!r} hat keine Normalform"
            raise TypeError(msg)
        return wert
    if isinstance(wert, datetime | date):
        return wert.isoformat()
    if isinstance(wert, Decimal):
        return str(wert)
    if isinstance(wert, PurePath):
        return str(wert)
    if isinstance(wert, set | frozenset):
        return sorted(normalform(v) for v in wert)
    msg = f"{type(wert).__name__} hat keine Normalform"
    raise TypeError(msg)
