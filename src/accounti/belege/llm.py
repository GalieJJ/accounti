"""LLM-Stufe für Belege — liest, was das Regelwerk offen lässt.

Der Belegtext geht nur maskiert hinaus: IBAN, USt-IdNr., E-Mail, Telefon, Lieferant,
Belegnummer und lange Ziffernfolgen werden ersetzt. Beträge, Daten und Steuersätze
bleiben lesbar — genau die braucht das Modell.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from litellm import completion

from accounti.belege.extraktion import Extrakt
from accounti.belege.zahlen import parse_datum
from accounti.models import Belegart

MAX_ZEICHEN = 6000

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
_UST_ID = re.compile(r"\b[A-Z]{2} ?\d{3} ?\d{3} ?\d{3,5}\b")
# nur am Wortanfang: sonst setzte das Muster an jedem Zeichen eines langen Wortes neu
# an (quadratisch, Nachprüfung C, Runde 4, Mittel 2) — die Treffer sind dieselben
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TELEFON = re.compile(r"(?:\+\d{2}[ /-]?|\b0)\d{2,5}[ /-]?\d{3,}(?:[ -]\d+)*")
_ZAHLENFOLGE = re.compile(r"\b\d{6,}\b")


def maskiere_beleg(text: str, extrakt: Extrakt) -> str:
    text = _IBAN.sub("[IBAN]", text)
    for ust_id in extrakt.ust_ids:
        text = text.replace(ust_id, "[UST-ID]")
    text = _UST_ID.sub("[UST-ID]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = _TELEFON.sub("[TEL]", text)
    if extrakt.lieferant_name:
        text = text.replace(extrakt.lieferant_name, "[LIEFERANT]")
    if extrakt.belegnummer:
        text = text.replace(extrakt.belegnummer, "[BELEGNR]")
    return _ZAHLENFOLGE.sub("[NR]", text)


_PROMPT = """Du bist Buchhaltungs-Assistent in Deutschland. Lies den Beleg.
Personenbezogene Angaben sind durch [PLATZHALTER] ersetzt. Antworte NUR mit JSON:
{{"belegart":
   "eingangsrechnung|ausgangsrechnung|quittung|kontoauszug|vertrag|sonstiges",
 "belegdatum": "JJJJ-MM-TT", "leistungsdatum": "JJJJ-MM-TT",
 "netto": "0.00", "steuer": "0.00", "brutto": "0.00",
 "positionen": [
   {{"bezeichnung": "...", "menge": 1, "netto": "0.00", "steuersatz": 19}}],
 "confidence": 0.0, "begruendung": "..."}}
Unbekannte Werte: null. Keine Werte erfinden.

Beleg:
{text}"""


@dataclass(frozen=True)
class LLMPosition:
    bezeichnung: str
    netto: Decimal
    menge: Decimal = Decimal("1")
    steuersatz: Decimal | None = None


@dataclass
class LLMBefund:
    belegart: Belegart | None = None
    belegdatum: date | None = None
    leistungsdatum: date | None = None
    netto: Decimal | None = None
    steuer: Decimal | None = None
    brutto: Decimal | None = None
    positionen: list[LLMPosition] = field(default_factory=list)
    confidence: float = 0.0
    begruendung: str = ""


def _dezimal(wert: Any) -> Decimal | None:
    if wert is None or isinstance(wert, bool):
        return None
    try:
        return Decimal(str(wert).replace(",", "."))
    except InvalidOperation:
        return None


def _datum(wert: Any) -> date | None:
    return parse_datum(wert) if isinstance(wert, str) else None


def _belegart(wert: Any) -> Belegart | None:
    try:
        art = Belegart(wert)
    except ValueError:
        return None
    return None if art is Belegart.UNBEKANNT else art


def _positionen(roh: Any) -> list[LLMPosition]:
    positionen = []
    for p in roh if isinstance(roh, list) else []:
        if not isinstance(p, dict):
            continue
        netto = _dezimal(p.get("netto"))
        if netto is None or not p.get("bezeichnung"):
            continue
        positionen.append(
            LLMPosition(
                bezeichnung=str(p["bezeichnung"])[:500],
                netto=netto.quantize(Decimal("0.01")),
                menge=_dezimal(p.get("menge")) or Decimal("1"),
                steuersatz=_dezimal(p.get("steuersatz")),
            )
        )
    return positionen


def _json(inhalt: str) -> dict[str, Any]:
    inhalt = re.sub(r"^```(?:json)?\s*|\s*```$", "", inhalt.strip())
    daten = json.loads(inhalt)
    if not isinstance(daten, dict):
        msg = "Antwort ist kein JSON-Objekt"
        raise ValueError(msg)
    return daten


class LLMBelegEngine:
    """Zweite Stufe der Belegerkennung, nur auf ausdrücklichen Wunsch aktiv."""

    def __init__(self, model: str = "anthropic/claude-sonnet-4-20250514") -> None:
        self.model = model

    def lies(self, text: str, extrakt: Extrakt) -> LLMBefund | None:
        prompt = _PROMPT.format(text=maskiere_beleg(text, extrakt)[:MAX_ZEICHEN])
        try:
            antwort = completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            daten = _json(antwort["choices"][0]["message"]["content"])
        except Exception:
            return None

        def betrag(schluessel: str) -> Decimal | None:
            wert = _dezimal(daten.get(schluessel))
            return wert.quantize(Decimal("0.01")) if wert is not None else None

        try:
            confidence = min(max(float(daten.get("confidence", 0.0)), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.0
        return LLMBefund(
            belegart=_belegart(daten.get("belegart")),
            belegdatum=_datum(daten.get("belegdatum")),
            leistungsdatum=_datum(daten.get("leistungsdatum")),
            netto=betrag("netto"),
            steuer=betrag("steuer"),
            brutto=betrag("brutto"),
            positionen=_positionen(daten.get("positionen")),
            confidence=confidence,
            begruendung=str(daten.get("begruendung", ""))[:500],
        )
