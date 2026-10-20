"""PIN des ELSTER-Zertifikats — verschlüsselt in einer Datei außerhalb der Datenbank.

Verschlüsselt wird mit dem Tresor der Bankzugänge (AES-GCM, Schlüssel aus
``ACCOUNTI_SCHLUESSEL``). Das Chiffrat ist an den Zweck „elster-pin“ gebunden und lässt
sich nicht als Bankzugang unterschieben. Die Datei ist nur für den Eigentümer lesbar.
"""

from __future__ import annotations

import os
from pathlib import Path

from accounti.bank.tresor import entschluessele, verschluessele

BEZUG = "elster-pin"


class PinError(RuntimeError):
    """PIN fehlt oder ist leer."""


def speichere_pin(datei: str | Path, pin: str, schluessel: str) -> None:
    if not pin:
        raise PinError("Leere PIN wird nicht gespeichert")
    datei = Path(datei)
    datei.parent.mkdir(parents=True, exist_ok=True)
    chiffrat = verschluessele({"pin": pin}, schluessel, BEZUG)
    tmp = datei.with_name(f".{datei.name}.tmp")
    tmp.unlink(missing_ok=True)
    deskriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(deskriptor, "w", encoding="utf-8") as ausgabe:
        ausgabe.write(chiffrat)
    tmp.replace(datei)


def lade_pin(datei: str | Path, schluessel: str) -> str:
    datei = Path(datei)
    if not datei.is_file():
        msg = f"PIN-Datei {datei} fehlt — mit 'accounti elster pin' anlegen"
        raise PinError(msg)
    return entschluessele(datei.read_text(encoding="utf-8").strip(), schluessel, BEZUG)[
        "pin"
    ]
