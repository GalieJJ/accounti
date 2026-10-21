"""Klassifikations-Engine — dreistufiger Ansatz zur automatischen Kontierung.

Stufe 1: Regelwerk (deterministisch)
Stufe 2: LLM-Klassifikation (probabilistisch)
Stufe 3: Supervisor-Feedback (menschliche Korrektur → neue Regel)
"""

from __future__ import annotations

import re

from accounti.klassifikation.llm import LLMEngine
from accounti.models import (
    Klassifikationsergebnis,
    Transaktion,
)

# ---------------------------------------------------------------------------
# Stufe 1: Regelwerk
# ---------------------------------------------------------------------------


RICHTUNGEN = ("ausgabe", "einnahme")


def text_muster(text: str) -> str:
    """Regulärer Ausdruck für ein Text-Muster: wörtlich (``re.escape``), nur als ganzes
    Wort — „Müller“ trifft nicht „Müllerstraße“. Lookarounds statt ``\\b``: das
    Muster darf auch mit Satzzeichen beginnen oder enden."""
    return rf"(?<!\w){re.escape(text.strip())}(?!\w)"


class Regel:
    """Eine deterministische Kontierungsregel.

    ``richtung`` (``ausgabe``/``einnahme``) beschränkt sie auf das Vorzeichen des
    Betrags (Ausgabe: negativ); ohne Angabe gilt sie in beide Richtungen wie bisher.
    ``confidence`` unter der Schwelle von ``buchung.mapper`` legt einen Treffer nur zur
    Prüfung vor (gelernte Regeln mit ``buchhaltung.gelernte_regeln: pruefen``).
    """

    def __init__(
        self,
        name: str,
        muster: str,  # Regex auf verwendungszweck oder gegenkonto_name
        soll_konto: str,
        haben_konto: str,
        steuer_schluessel: int | None = None,
        buchungstext: str | None = None,
        feld: str = "verwendungszweck",  # oder "gegenkonto_name"
        richtung: str | None = None,
        confidence: float = 1.0,
        hinweis: str | None = None,
    ) -> None:
        if richtung is not None and richtung not in RICHTUNGEN:
            msg = f"Regel {name}: richtung muss ausgabe oder einnahme sein"
            raise ValueError(msg)
        self.name = name
        self.muster = re.compile(muster, re.IGNORECASE)
        self.soll_konto = soll_konto
        self.haben_konto = haben_konto
        self.steuer_schluessel = steuer_schluessel
        self.buchungstext = buchungstext
        self.feld = feld
        self.richtung = richtung
        self.confidence = confidence
        self.hinweis = hinweis

    @classmethod
    def aus_text(
        cls, name: str, text: str, soll_konto: str, haben_konto: str, **kw: object
    ) -> Regel:
        """Regel aus einem Text-Muster (kein regulärer Ausdruck, ganze Wörter)."""
        return cls(name, text_muster(text), soll_konto, haben_konto, **kw)  # type: ignore[arg-type]

    def passt_richtung(self, transaktion: Transaktion) -> bool:
        if self.richtung == "ausgabe":
            return transaktion.betrag < 0
        if self.richtung == "einnahme":
            return transaktion.betrag > 0
        return True

    def passt_muster(self, transaktion: Transaktion) -> bool:
        if self.feld == "beide":
            text = f"{transaktion.verwendungszweck} {transaktion.gegenkonto_name or ''}"
        else:
            text = getattr(transaktion, self.feld, "") or ""
        return bool(self.muster.search(text))

    def passt(self, transaktion: Transaktion) -> bool:
        """Prüft ob die Regel auf die Transaktion zutrifft (Muster und Richtung).

        feld="beide" durchsucht Verwendungszweck UND Gegenkonto-Name —
        nützlich, weil Banken den Händlernamen mal hier, mal dort führen.
        """
        return self.passt_richtung(transaktion) and self.passt_muster(transaktion)


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
                    buchungstext=regel.buchungstext
                    or transaktion.verwendungszweck[:60],
                    confidence=regel.confidence,  # Regelwerk: volle Confidence
                    begruendung=f"Regel '{regel.name}' greift auf Feld '{regel.feld}'"
                    + (f" ({regel.hinweis})" if regel.hinweis else ""),
                    quelle="regelwerk",
                    regel=regel.name,
                )
        return None

    def regel_hinzufuegen(self, regel: Regel) -> None:
        """Neue Regel hinzufügen (z.B. aus Supervisor-Feedback)."""
        self.regeln.insert(0, regel)  # Neue Regeln haben Vorrang


# ---------------------------------------------------------------------------
# Stufe 2: LLM-Klassifikation — siehe accounti.klassifikation.llm (LLMEngine)
# ---------------------------------------------------------------------------


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

        # Stufe 2: LLM (nur wenn konfiguriert)
        if self.llm is not None:
            return self.llm.klassifiziere(transaktion)

        return None
