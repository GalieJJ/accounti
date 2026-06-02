"""LLM-Klassifikationsstufe über LiteLLM (Claude default / Ollama)."""

from __future__ import annotations

import json
import re

from litellm import completion

from accounti.models import Klassifikationsergebnis, Transaktion

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_ZAHLENFOLGE = re.compile(r"\b\d{6,}\b")


def maskiere_pii(text: str) -> str:
    """Entfernt IBANs und lange Zahlenfolgen, bevor Text an ein LLM geht."""
    text = _IBAN.sub("[IBAN]", text)
    text = _ZAHLENFOLGE.sub("[NR]", text)
    return text


_PROMPT = """Du bist Buchhaltungs-Assistent für SKR03 (Deutschland).
Kontiere diese Bankbuchung. Antworte NUR mit JSON:
{{"soll_konto","haben_konto","steuer_schluessel","buchungstext","confidence","begruendung"}}
Betrag: {betrag} EUR
Verwendungszweck: {zweck}
Empfänger: {empfaenger}"""


class LLMEngine:
    """Stufe 2 — LLM-basierte Kontierung für unbekannte Transaktionen."""

    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4-20250514",
        confidence_schwelle: float = 0.85,
    ) -> None:
        self.model = model
        self.confidence_schwelle = confidence_schwelle

    def klassifiziere(self, transaktion: Transaktion) -> Klassifikationsergebnis | None:
        prompt = _PROMPT.format(
            betrag=transaktion.betrag,
            zweck=maskiere_pii(transaktion.verwendungszweck),
            empfaenger=maskiere_pii(transaktion.gegenkonto_name or ""),
        )
        try:
            antwort = completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            inhalt = antwort["choices"][0]["message"]["content"]
            daten = json.loads(inhalt)
        except Exception:
            return None

        return Klassifikationsergebnis(
            transaktion_id=transaktion.id,
            soll_konto=str(daten["soll_konto"]),
            haben_konto=str(daten["haben_konto"]),
            steuer_schluessel=daten.get("steuer_schluessel"),
            buchungstext=daten.get("buchungstext", transaktion.verwendungszweck[:60]),
            confidence=float(daten.get("confidence", 0.0)),
            begruendung=daten.get("begruendung", ""),
            quelle="llm",
        )
