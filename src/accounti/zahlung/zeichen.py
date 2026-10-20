"""Zeichensatz für SEPA-Nachrichten nach Anlage 3 des DFÜ-Abkommens (Kap. 2).

UTF-8 ohne BOM, Latin Character Set; Banken müssen zusätzlich Umlaute, ß, ``&``,
``*``, ``$`` und ``%`` annehmen. Referenzen (MsgId, PmtInfId, EndToEndId) sind auf den
Latin-Satz beschränkt und dürfen nicht mit ``/`` beginnen oder enden und kein ``//``
enthalten.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal

from accounti.anzeige import betrag_de, datum_de

LATIN = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'/?:().,+- "
DK_ZUSATZ = "ÄÖÜäöüß&*$%"
_TEXT_ZEICHEN = frozenset(LATIN + DK_ZUSATZ)
_REFERENZ_ZEICHEN = frozenset(LATIN)
# Buchstaben, die NFKD nicht in Grundbuchstabe + Akzent zerlegt
_ERSATZ = {
    "Ł": "L",
    "ł": "l",
    "Ø": "O",
    "ø": "o",
    "Đ": "D",
    "đ": "d",
    "Æ": "AE",
    "æ": "ae",
    "Œ": "OE",
    "œ": "oe",
    "ı": "i",
    "Þ": "Th",
    "þ": "th",
}


def _ohne_akzent(zeichen: str) -> str:
    if zeichen in _ERSATZ:
        return _ERSATZ[zeichen]
    zerlegt = unicodedata.normalize("NFKD", zeichen)
    return "".join(z for z in zerlegt if not unicodedata.combining(z))


def sepa_text(text: str | None, laenge: int = 140) -> str:
    """Freitext (Namen, Verwendungszweck) im DK-Zeichensatz, gekürzt auf ``laenge``.

    Umlaute und ß bleiben, andere Buchstaben verlieren ihren Akzent (é → e), alles
    Übrige wird zum Leerzeichen; Leerraum wird zusammengefasst.
    """
    teile = []
    for zeichen in text or "":
        if zeichen in _TEXT_ZEICHEN:
            teile.append(zeichen)
            continue
        ersatz = _ohne_akzent(zeichen)
        teile.append(ersatz if ersatz and set(ersatz) <= _TEXT_ZEICHEN else " ")
    sauber = re.sub(r"\s+", " ", "".join(teile)).strip()
    return sauber[:laenge].rstrip()


def referenz(text: str | None, laenge: int = 35) -> str:
    """Kennung (MsgId, EndToEndId …): nur Latin, ohne ``/`` am Rand und ohne ``//``."""
    zeichen = "".join(
        z
        for z in "".join(_ohne_akzent(z) for z in text or "")
        if z in _REFERENZ_ZEICHEN
    )
    zeichen = re.sub(r"/{2,}", "/", re.sub(r"\s+", " ", zeichen))
    return zeichen.strip(" /")[:laenge].strip(" /")


def verwendungszweck(
    belegnummer: str | None, belegdatum: date | None, skonto: Decimal
) -> str:
    """``<Rechnungsnummer> vom <Datum>[, abzgl. <x> EUR Skonto]`` — höchstens 140."""
    text = belegnummer or "Rechnung"
    if belegdatum is not None:
        text += f" vom {datum_de(belegdatum)}"
    if skonto > 0:
        text += f", abzgl. {betrag_de(skonto)} EUR Skonto"
    return sepa_text(text, 140)
