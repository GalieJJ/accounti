"""Deutsche Beträge und Datumsangaben aus Belegtexten lesen."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

# Betrag mit zwei Nachkommastellen, wie er auf Belegen steht: 1.234,56 · 23,99- · -5,00
BETRAG = r"[-+]?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}-?"

_MONATE = {
    "januar": 1,
    "jänner": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}

DATUM = (
    r"\d{1,2}\.\s?\d{1,2}\.\s?(?:\d{4}|\d{2})(?!\d)"
    r"|\d{1,2}\.\s*(?:" + "|".join(_MONATE) + r")\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
)

_ZAHL = re.compile(r"^([-+]?)([\d.,]+?)(-?)$")


def parse_betrag(text: str) -> Decimal | None:
    """``1.234,56 €`` → ``Decimal('1234.56')``; Minus vorne oder hinten."""
    roh = re.sub(r"(?i)\s|€|eur", "", text)
    treffer = _ZAHL.match(roh)
    if not treffer:
        return None
    vorzeichen, zahl, minus_hinten = treffer.groups()
    if "," in zahl:
        ganz, _, nachkomma = zahl.rpartition(",")
        if not re.fullmatch(r"\d{1,3}(\.\d{3})*|\d+", ganz) or "." in nachkomma:
            return None
        zahl = ganz.replace(".", "") + "." + nachkomma
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", zahl):
        zahl = zahl.replace(".", "")
    elif zahl.count(".") > 1:
        return None
    try:
        wert = Decimal(zahl).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return -wert if "-" in (vorzeichen, minus_hinten) else wert


def parse_datum(text: str) -> date | None:
    """``05.03.2026`` · ``5.3.26`` · ``5. März 2026`` · ``2026-03-05`` → ``date``."""
    text = text.strip().lower()
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.fullmatch(r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})", text):
            jahr = int(m[3])
            return date(jahr + 2000 if jahr < 100 else jahr, int(m[2]), int(m[1]))
        if m := re.fullmatch(r"(\d{1,2})\.\s*([a-zä]+)\s+(\d{4})", text):
            monat = _MONATE.get(m[2])
            return date(int(m[3]), monat, int(m[1])) if monat else None
    except ValueError:
        return None
    return None
