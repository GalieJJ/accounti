"""Gesetzliche Feiertage — bundeseinheitlich und je Land.

Für Fristen nach § 108 Abs. 3 AO zählt das Feiertagsrecht am Sitz der Behörde. Erfasst
sind Feiertage, die im ganzen Land gelten (Stand 2026); Feiertage einzelner Gemeinden
(Fronleichnam in Teilen von Sachsen und Thüringen, Mariä Himmelfahrt in Teilen Bayerns,
Augsburger Friedensfest) und einmalige Feiertage fehlen.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache

# Land → Feiertage, die dort zusätzlich gelten (Kennung aus _land_feiertage)
LAENDER: dict[str, tuple[str, ...]] = {
    "BW": ("drei_koenige", "fronleichnam", "allerheiligen"),
    "BY": ("drei_koenige", "fronleichnam", "allerheiligen"),
    "BE": ("frauentag",),
    "BB": ("reformationstag",),
    "HB": ("reformationstag",),
    "HH": ("reformationstag",),
    "HE": ("fronleichnam",),
    "MV": ("frauentag", "reformationstag"),
    "NI": ("reformationstag",),
    "NW": ("fronleichnam", "allerheiligen"),
    "RP": ("fronleichnam", "allerheiligen"),
    "SL": ("fronleichnam", "mariae_himmelfahrt", "allerheiligen"),
    "SN": ("reformationstag", "buss_und_bettag"),
    "ST": ("drei_koenige", "reformationstag"),
    "SH": ("reformationstag",),
    "TH": ("weltkindertag", "reformationstag"),
}


def ostersonntag(jahr: int) -> date:
    """Gregorianischer Ostersonntag (Algorithmus nach Meeus/Jones/Butcher)."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    monat, tag = divmod(h + ll - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def _bundeseinheitlich(jahr: int) -> dict[date, str]:
    ostern = ostersonntag(jahr)
    return {
        date(jahr, 1, 1): "Neujahr",
        ostern - timedelta(days=2): "Karfreitag",
        ostern + timedelta(days=1): "Ostermontag",
        date(jahr, 5, 1): "Tag der Arbeit",
        ostern + timedelta(days=39): "Christi Himmelfahrt",
        ostern + timedelta(days=50): "Pfingstmontag",
        date(jahr, 10, 3): "Tag der Deutschen Einheit",
        date(jahr, 12, 25): "1. Weihnachtstag",
        date(jahr, 12, 26): "2. Weihnachtstag",
    }


def _land_feiertage(jahr: int) -> dict[str, tuple[date, str]]:
    ostern = ostersonntag(jahr)
    # Buß- und Bettag: Mittwoch vor dem 23. November
    bettag = date(jahr, 11, 22)
    while bettag.weekday() != 2:
        bettag -= timedelta(days=1)
    return {
        "drei_koenige": (date(jahr, 1, 6), "Heilige Drei Könige"),
        "frauentag": (date(jahr, 3, 8), "Internationaler Frauentag"),
        "fronleichnam": (ostern + timedelta(days=60), "Fronleichnam"),
        "mariae_himmelfahrt": (date(jahr, 8, 15), "Mariä Himmelfahrt"),
        "weltkindertag": (date(jahr, 9, 20), "Weltkindertag"),
        "reformationstag": (date(jahr, 10, 31), "Reformationstag"),
        "allerheiligen": (date(jahr, 11, 1), "Allerheiligen"),
        "buss_und_bettag": (bettag, "Buß- und Bettag"),
    }


@cache
def _feiertage(jahr: int, bundesland: str | None) -> dict[date, str]:
    tage = _bundeseinheitlich(jahr)
    if bundesland is not None:
        land = _land_feiertage(jahr)
        for kennung in LAENDER[bundesland.upper()]:
            tag, name = land[kennung]
            tage[tag] = name
    return dict(sorted(tage.items()))


def feiertage(jahr: int, bundesland: str | None = None) -> dict[date, str]:
    """Gesetzliche Feiertage eines Jahres; ohne Land nur die bundeseinheitlichen."""
    return dict(_feiertage(jahr, bundesland.upper() if bundesland else None))


def feiertag(tag: date, bundesland: str | None = None) -> str | None:
    return _feiertage(tag.year, bundesland.upper() if bundesland else None).get(tag)


def kein_werktag(tag: date, bundesland: str | None = None) -> str | None:
    """Grund, warum an diesem Tag keine Frist endet — oder ``None``."""
    if tag.weekday() == 5:
        return "Samstag"
    if tag.weekday() == 6:
        return "Sonntag"
    return feiertag(tag, bundesland)


def naechster_werktag(tag: date, bundesland: str | None = None) -> date:
    """§ 108 Abs. 3 AO: Fristende an Sa, So oder Feiertag → nächster Werktag."""
    while kein_werktag(tag, bundesland):
        tag += timedelta(days=1)
    return tag
