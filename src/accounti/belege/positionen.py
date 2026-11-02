"""Positionssplit — kontiert wird auf Positionen, nicht auf Belegen.

Das Regelwerk erzeugt eine Position je Steuersatz. Eine Kreditkartenabrechnung
wird in ihre Einzelumsätze zerlegt, die sich danach wie Transaktionen kontieren lassen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from accounti.belege.extraktion import STEUERKENNZEICHEN, Steuerzeile
from accounti.belege.zahlen import BETRAG, parse_betrag
from accounti.models import Belegposition

_KREDITKARTE = re.compile(
    r"kreditkarten(?:abrechnung|umsätze|umsaetze)|kartenabrechnung", re.IGNORECASE
)
_UMSATZZEILE = re.compile(
    r"^\s*(?P<beleg>\d{1,2}\.\d{1,2}\.(?:\d{2,4})?)\s+"
    r"(?:\d{1,2}\.\d{1,2}\.(?:\d{2,4})?\s+)?"
    rf"(?P<text>.+?)\s+(?P<betrag>{BETRAG})(?P<vz>\+)?\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class KartenUmsatz:
    datum: date
    beschreibung: str
    betrag: Decimal  # wie bei Transaktion: Belastung negativ, Gutschrift positiv


def positionen_aus_steuerzeilen(
    beleg_id: UUID, steuerzeilen: list[Steuerzeile], kennzeichen: str | None = None
) -> list[Belegposition]:
    """Eine Position je Steuersatz; eine 0-%-Position nennt den Steuerfall."""

    def bezeichnung(s: Steuerzeile) -> str:
        text = f"Netto {s.satz.normalize()} %"
        if s.satz == 0 and kennzeichen in STEUERKENNZEICHEN:
            text += f" — {STEUERKENNZEICHEN[kennzeichen]}"
        return text

    return [
        Belegposition(
            beleg_id=beleg_id,
            bezeichnung=bezeichnung(s),
            netto=s.netto,
            steuersatz=s.satz,
            steuer_betrag=s.steuer,
        )
        for s in steuerzeilen
    ]


def ist_kreditkartenabrechnung(text: str) -> bool:
    return bool(_KREDITKARTE.search(text))


def _datum(roh: str, abrechnungsdatum: date) -> date | None:
    tag, monat, jahr = (roh.split(".") + [""])[:3]
    try:
        if jahr:
            j = int(jahr)
            return date(j + 2000 if j < 100 else j, int(monat), int(tag))
        # Ohne Jahr: Umsätze nach dem Abrechnungsmonat gehören ins Vorjahr.
        j = abrechnungsdatum.year - (1 if int(monat) > abrechnungsdatum.month else 0)
        return date(j, int(monat), int(tag))
    except ValueError:
        return None


def zerlege_kreditkartenabrechnung(
    text: str, abrechnungsdatum: date
) -> list[KartenUmsatz]:
    umsaetze = []
    for m in _UMSATZZEILE.finditer(text):
        datum = _datum(m["beleg"], abrechnungsdatum)
        betrag = parse_betrag(m["betrag"])
        if datum is None or betrag is None:
            continue
        if not m["betrag"].endswith("-") and not m["vz"] and betrag > 0:
            betrag = -betrag  # ohne Vorzeichen ist ein Kartenumsatz eine Belastung
        umsaetze.append(KartenUmsatz(datum, m["text"].strip(), betrag))
    return umsaetze


def positionen_aus_umsaetzen(
    beleg_id: UUID, umsaetze: list[KartenUmsatz]
) -> list[Belegposition]:
    return [
        Belegposition(
            beleg_id=beleg_id,
            bezeichnung=f"{u.datum:%d.%m.%Y} {u.beschreibung}",
            netto=u.betrag,
        )
        for u in umsaetze
    ]
