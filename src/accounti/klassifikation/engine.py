"""Klassifikations-Engine — dreistufiger Ansatz zur automatischen Kontierung.

Stufe 1: Regelwerk (deterministisch)
Stufe 2: LLM-Klassifikation (probabilistisch)
Stufe 3: Supervisor-Feedback (menschliche Korrektur → neue Regel)
"""

from __future__ import annotations

import re
from decimal import Decimal

from accounti.models import (
    Klassifikationsergebnis,
    Transaktion,
)


# ---------------------------------------------------------------------------
# Stufe 1: Regelwerk
# ---------------------------------------------------------------------------


class Regel:
    """Eine deterministische Kontierungsregel."""

    def __init__(
        self,
        name: str,
        muster: str,  # Regex auf verwendungszweck oder gegenkonto_name
        soll_konto: str,
        haben_konto: str,
        steuer_schluessel: int | None = None,
        buchungstext: str | None = None,
        feld: str = "verwendungszweck",  # oder "gegenkonto_name"
    ) -> None:
        self.name = name
        self.muster = re.compile(muster, re.IGNORECASE)
        self.soll_konto = soll_konto
        self.haben_konto = haben_konto
        self.steuer_schluessel = steuer_schluessel
        self.buchungstext = buchungstext
        self.feld = feld

    def passt(self, transaktion: Transaktion) -> bool:
        """Prüft ob die Regel auf die Transaktion zutrifft."""
        text = getattr(transaktion, self.feld, "") or ""
        return bool(self.muster.search(text))


# Standard-Regelwerk für häufige Geschäftsvorfälle (SKR03)
STANDARD_REGELN: list[Regel] = [
    # --- Erlöse ---
    Regel(
        name="amazon_erloes",
        muster=r"amazon\s*(payments|marketplace|eu)",
        soll_konto="1200",  # Bank
        haben_konto="8400",  # Erlöse 19%
        steuer_schluessel=3,
        buchungstext="Amazon Marketplace Erlöse",
        feld="gegenkonto_name",
    ),
    Regel(
        name="paypal_erloes",
        muster=r"paypal.*gutschrift",
        soll_konto="1200",
        haben_konto="8400",
        steuer_schluessel=3,
        buchungstext="PayPal Erlöse",
    ),
    # --- Betriebsausgaben ---
    Regel(
        name="aws_hosting",
        muster=r"(amazon web services|aws)",
        soll_konto="4970",  # Nebenkosten Geldverkehr / oder 6815 EDV
        haben_konto="1200",
        steuer_schluessel=9,
        buchungstext="AWS Cloud-Hosting",
    ),
    Regel(
        name="miete",
        muster=r"(miete|mietvertrag|grundst.ck)",
        soll_konto="4210",  # Miete
        haben_konto="1200",
        steuer_schluessel=9,
        buchungstext="Miete Geschäftsräume",
    ),
    Regel(
        name="versicherung",
        muster=r"(versicherung|haftpflicht|berufsgenossenschaft)",
        soll_konto="4360",  # Versicherungen
        haben_konto="1200",
        steuer_schluessel=None,
        buchungstext="Versicherung",
    ),
    # TODO: Weitere Regeln aus YAML laden (config/regeln.yaml)
]


class RegelwerkEngine:
    """Stufe 1 — deterministische Kontierung über Muster-Matching."""

    def __init__(self, regeln: list[Regel] | None = None) -> None:
        self.regeln = regeln or STANDARD_REGELN

    def klassifiziere(self, transaktion: Transaktion) -> Klassifikationsergebnis | None:
        """Versucht die Transaktion regelbasiert zu kontieren.

        Returns None wenn keine Regel greift.
        """
        for regel in self.regeln:
            if regel.passt(transaktion):
                return Klassifikationsergebnis(
                    transaktion_id=transaktion.id,
                    soll_konto=regel.soll_konto,
                    haben_konto=regel.haben_konto,
                    steuer_schluessel=regel.steuer_schluessel,
                    buchungstext=regel.buchungstext or transaktion.verwendungszweck[:60],
                    confidence=1.0,  # Regelwerk = volle Confidence
                    begruendung=f"Regel '{regel.name}' greift auf Feld '{regel.feld}'",
                    quelle="regelwerk",
                )
        return None

    def regel_hinzufuegen(self, regel: Regel) -> None:
        """Neue Regel hinzufügen (z.B. aus Supervisor-Feedback)."""
        self.regeln.insert(0, regel)  # Neue Regeln haben Vorrang


# ---------------------------------------------------------------------------
# Stufe 2: LLM-Klassifikation (Stub)
# ---------------------------------------------------------------------------


class LLMEngine:
    """Stufe 2 — LLM-basierte Kontierung für unbekannte Transaktionen.

    Nutzt LiteLLM um verschiedene Modelle anzusprechen
    (Anthropic Claude, OpenAI, Ollama).
    """

    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4-20250514",
        confidence_schwelle: float = 0.85,
    ) -> None:
        self.model = model
        self.confidence_schwelle = confidence_schwelle

    async def klassifiziere(
        self,
        transaktion: Transaktion,
        kontenrahmen: str = "SKR03",
    ) -> Klassifikationsergebnis:
        """Transaktion per LLM kontieren.

        TODO: Implementation mit LiteLLM
        - Kontenrahmen als Kontext
        - Structured Output für Konto + Steuerschlüssel
        - Confidence aus Log-Probabilities oder Self-Assessment
        """
        raise NotImplementedError(
            "LLM-Engine ist noch nicht implementiert. "
            "Siehe Roadmap Phase 2 und docs/llm-integration.md"
        )


# ---------------------------------------------------------------------------
# Orchestrator — kombiniert alle Stufen
# ---------------------------------------------------------------------------


class KlassifikationsEngine:
    """Orchestriert die dreistufige Klassifikation."""

    def __init__(
        self,
        regelwerk: RegelwerkEngine | None = None,
        llm: LLMEngine | None = None,
        auto_buchen_schwelle: float = 0.95,
    ) -> None:
        self.regelwerk = regelwerk or RegelwerkEngine()
        self.llm = llm
        self.auto_buchen_schwelle = auto_buchen_schwelle

    def klassifiziere(self, transaktion: Transaktion) -> Klassifikationsergebnis | None:
        """Transaktion klassifizieren — erst Regelwerk, dann LLM.

        Returns None wenn weder Regel noch LLM eine Klassifikation liefern.
        """
        # Stufe 1: Regelwerk
        ergebnis = self.regelwerk.klassifiziere(transaktion)
        if ergebnis is not None:
            return ergebnis

        # Stufe 2: LLM (TODO)
        # if self.llm is not None:
        #     ergebnis = await self.llm.klassifiziere(transaktion)
        #     return ergebnis

        return None
