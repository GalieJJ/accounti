"""Steuernummer im 13-stelligen ELSTER-Format (Bundesschema zur Übermittlung).

Aufbau: Bundesfinanzamtsnummer (4 Stellen) + ``0`` + Bezirk, Unterscheidungsnummer und
Prüfziffer (8 Stellen). Die Finanzamtsnummer beginnt mit dem Länderpräfix; im
Landesformat steht nur ihr Rest (z. B. Bayern ``181/815/08155`` → ``9181 0 81508155``).
Quelle: Wikipedia „Steuernummer“, Tabelle der Länderschemata.
"""

from __future__ import annotations

import re

# Länderpräfix der Bundesfinanzamtsnummer
PRAEFIX = {
    "BW": "28",
    "BY": "9",
    "BE": "11",
    "BB": "3",
    "HB": "24",
    "HH": "22",
    "HE": "26",
    "MV": "4",
    "NI": "23",
    "NW": "5",
    "RP": "27",
    "SL": "10",
    "SN": "3",
    "ST": "3",
    "SH": "21",
    "TH": "4",
}


class SteuernummerError(ValueError):
    """Die Steuernummer lässt sich nicht ins ELSTER-Format bringen."""


def elster_steuernummer(nummer: str, bundesland: str | None = None) -> str:
    """Landesformat (``181/815/08155``), 12- oder 13-stellig → 13-stellig."""
    if re.search(r"[^\d\s/.\-]", nummer):
        raise SteuernummerError(f"Steuernummer {nummer!r}: nur Ziffern und Trenner")
    ziffern = re.sub(r"\D", "", nummer)
    land = bundesland.upper() if bundesland else None
    if land is not None and land not in PRAEFIX:
        raise SteuernummerError(f"Bundesland {bundesland!r} unbekannt")

    if len(ziffern) == 13:
        ergebnis = ziffern
    elif len(ziffern) == 12:
        ergebnis = ziffern[:4] + "0" + ziffern[4:]
    elif len(ziffern) in (10, 11):
        if land is None:
            msg = (
                f"Steuernummer {nummer} steht im Landesformat — dafür braucht es das "
                "Bundesland (elster.bundesland) oder die 13-stellige ELSTER-Nummer"
            )
            raise SteuernummerError(msg)
        praefix = PRAEFIX[land]
        kopf = ziffern[:-8]
        ergebnis = praefix + kopf[-(4 - len(praefix)) :] + "0" + ziffern[-8:]
    else:
        msg = f"Steuernummer {nummer}: {len(ziffern)} Stellen — erwartet 10 bis 13"
        raise SteuernummerError(msg)

    if ergebnis[4] != "0":
        raise SteuernummerError(f"{ergebnis}: fünfte Stelle muss 0 sein")
    if land is not None and not ergebnis.startswith(PRAEFIX[land]):
        msg = f"Steuernummer {ergebnis} passt nicht zum Bundesland {land}"
        raise SteuernummerError(msg)
    return ergebnis


def finanzamtsnummer(elster: str) -> str:
    """Bundesfinanzamtsnummer — Empfänger im NutzdatenHeader."""
    return elster[:4]
