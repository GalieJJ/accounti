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

# Zahlungsrichtung einer Regel: Ausgabe (Betrag < 0, Bank im Haben) oder Einnahme
# (Betrag > 0, Bank im Soll). Ohne Richtung („beide“) prüft der Mapper die Bankseite
# gegen das Vorzeichen (``buchung.mapper.zu_buchungssatz``).
RICHTUNGEN = ("ausgabe", "einnahme")


class Regel:
    """Eine deterministische Kontierungsregel.

    ``richtung`` (``ausgabe``/``einnahme``): Die Regel gilt nur für Umsätze dieser
    Richtung. Eine Erstattung auf eine Ausgaberegel ist keine zweite Ausgabe, sondern
    mindert sie samt Vorsteuer (§ 17 Abs. 1 Satz 2 UStG) — sie bekommt die Regel nur
    als Gegenbuchung zur Prüfung (``RegelwerkEngine.gegenrichtung``).
    ``pruefen``: Treffer immer zur Prüfung, z.B. Miete (steuerfrei nach § 4 Nr. 12
    UStG, Vorsteuer nur bei Option nach § 9 UStG) oder § 13b-Leistungen.
    ``confidence``: Sicherheit eines Treffers (Standard 1.0 = automatisch buchen).
    """

    def __init__(
        self,
        name: str,
        muster: str,  # Regex auf verwendungszweck oder gegenkonto_name
        soll_konto: str,
        haben_konto: str,
        steuer_schluessel: int | None = None,
        buchungstext: str | None = None,
        feld: str = "verwendungszweck",  # oder "gegenkonto_name", "beide"
        richtung: str | None = None,
        pruefen: bool = False,
        confidence: float = 1.0,
    ) -> None:
        if richtung == "beide":
            richtung = None
        if richtung is not None and richtung not in RICHTUNGEN:
            msg = f"Regel {name}: richtung {richtung!r} — ausgabe, einnahme oder beide"
            raise ValueError(msg)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Regel {name}: confidence {confidence} — 0 bis 1")
        self.name = name
        self.muster = re.compile(muster, re.IGNORECASE)
        self.soll_konto = soll_konto
        self.haben_konto = haben_konto
        self.steuer_schluessel = steuer_schluessel
        self.buchungstext = buchungstext
        self.feld = feld
        self.richtung = richtung
        self.pruefen = pruefen
        self.confidence = confidence

    def passt(self, transaktion: Transaktion) -> bool:
        """Prüft ob die Regel auf die Transaktion zutrifft (Text, ohne Richtung).

        feld="beide" durchsucht Verwendungszweck UND Gegenkonto-Name —
        nützlich, weil Banken den Händlernamen mal hier, mal dort führen.
        """
        if self.feld == "beide":
            text = f"{transaktion.verwendungszweck} {transaktion.gegenkonto_name or ''}"
        else:
            text = getattr(transaktion, self.feld, "") or ""
        return bool(self.muster.search(text))

    def passt_richtung(self, transaktion: Transaktion) -> bool:
        """Vorzeichen des Umsatzes passt zur Richtung der Regel (ohne Richtung: ja)."""
        if self.richtung is None or not transaktion.betrag:
            return True
        return (transaktion.betrag < 0) == (self.richtung == "ausgabe")

    def ergebnis(
        self, transaktion: Transaktion, gegenrichtung: bool = False
    ) -> Klassifikationsergebnis:
        soll, haben = self.soll_konto, self.haben_konto
        begruendung = f"Regel '{self.name}' greift auf Feld '{self.feld}'"
        confidence = self.confidence
        if gegenrichtung:
            soll, haben = haben, soll
            erwartet = "Ausgaben" if self.richtung == "ausgabe" else "Einnahmen"
            ist = "Einnahme" if transaktion.betrag > 0 else "Ausgabe"
            begruendung += (
                f" — sie gilt für {erwartet}, der Umsatz ist eine {ist}: "
                "Gegenbuchung (Erstattung, Gutschrift, Rückzahlung?) zur Prüfung"
            )
            confidence = min(confidence, 0.5)
        return Klassifikationsergebnis(
            transaktion_id=transaktion.id,
            soll_konto=soll,
            haben_konto=haben,
            steuer_schluessel=self.steuer_schluessel,
            buchungstext=self.buchungstext or transaktion.verwendungszweck[:60],
            confidence=confidence,
            begruendung=begruendung,
            quelle="regelwerk",
            pruefen=self.pruefen or gegenrichtung,
        )


# Konten der Standardregeln je Kontenrahmen (DATEV SKR03 bzw. SKR04)
_STANDARDKONTEN: dict[str, dict[str, str]] = {
    "SKR03": {
        "bank": "1200",
        "geldtransit": "1360",
        "sonstige": "4900",  # Sonstige betriebliche Aufwendungen
        "miete": "4210",  # Miete (unbewegliche Wirtschaftsgüter)
        "versicherung": "4360",
    },
    "SKR04": {
        "bank": "1800",
        "geldtransit": "1460",
        "sonstige": "6300",
        "miete": "6310",
        "versicherung": "6400",
    },
}


def standard_regeln(
    kontenrahmen: str = "SKR03", bank_konto: str | None = None
) -> list[Regel]:
    """Eingebautes Regelwerk für häufige Vorfälle, in den Konten des Kontenrahmens.

    ``bank_konto``: Bankkonto der Buchhaltung (sonst das übliche des Kontenrahmens).
    Für einen anderen Kontenrahmen gibt es keine Standardregeln — lieber offen als
    auf Konten eines fremden Kontenrahmens gebucht. Bewusst konservativ: Miete und
    AWS ohne Steuerschlüssel und zur Prüfung, Marktplatz-Auszahlungen als
    Geldtransit (der Erlös steht in der Abrechnung, ``accounti marktplatz import``).
    """
    k = _STANDARDKONTEN.get(kontenrahmen.upper())
    if k is None:
        return []
    bank = bank_konto or k["bank"]
    return [
        # --- Auszahlungen von Marktplätzen/Zahlungsdiensten: Geldbewegung, kein
        # Entgelt (§ 10 Abs. 1 UStG) — die Erlöse bucht die Abrechnung
        Regel(
            name="amazon_auszahlung",
            muster=r"amazon\s*(payments|marketplace|eu)",
            soll_konto=bank,
            haben_konto=k["geldtransit"],
            buchungstext="Amazon-Auszahlung (Geldtransit)",
            feld="gegenkonto_name",
            richtung="einnahme",
            pruefen=True,
        ),
        Regel(
            name="paypal_auszahlung",
            muster=r"paypal.*gutschrift",
            soll_konto=bank,
            haben_konto=k["geldtransit"],
            buchungstext="PayPal-Auszahlung (Geldtransit)",
            richtung="einnahme",
            pruefen=True,
        ),
        # --- Betriebsausgaben ---
        # AWS EMEA SARL (LU): sonstige Leistung eines EU-Unternehmers, § 13b Abs. 1
        # UStG — keine Vorsteuer „aus Rechnung“, Schlüssel bestimmt der Mensch
        Regel(
            name="aws_hosting",
            muster=r"(amazon web services|\baws\b)",
            soll_konto=k["sonstige"],
            haben_konto=bank,
            buchungstext="AWS Cloud-Hosting (§ 13b prüfen)",
            richtung="ausgabe",
            pruefen=True,
        ),
        # Miete: steuerfrei (§ 4 Nr. 12 UStG), Vorsteuer nur bei Option (§ 9 UStG)
        # und Rechnung bzw. Mietvertrag mit Steuerausweis (§ 15 Abs. 1 Nr. 1 UStG)
        Regel(
            name="miete",
            muster=r"(miete|mietvertrag|grundst.ck)",
            soll_konto=k["miete"],
            haben_konto=bank,
            buchungstext="Miete Geschäftsräume",
            richtung="ausgabe",
            pruefen=True,
        ),
        Regel(
            name="versicherung",
            muster=r"(versicherung|haftpflicht|berufsgenossenschaft)",
            soll_konto=k["versicherung"],
            haben_konto=bank,
            buchungstext="Versicherung",
            richtung="ausgabe",
        ),
    ]


# Standard-Regelwerk im SKR03 (für den Kontenrahmen der Buchhaltung:
# ``standard_regeln(buchhaltung.kontenrahmen, buchhaltung.bank_konto)``)
STANDARD_REGELN: list[Regel] = standard_regeln("SKR03")


class RegelwerkEngine:
    """Stufe 1 — deterministische Kontierung über Muster-Matching."""

    def __init__(self, regeln: list[Regel] | None = None) -> None:
        # eine leere Liste bleibt leer (kein Kontenrahmen ohne Standardregeln)
        self.regeln = regeln if regeln is not None else standard_regeln()

    def klassifiziere(self, transaktion: Transaktion) -> Klassifikationsergebnis | None:
        """Die erste Regel, deren Muster und Richtung passen.

        Returns None wenn keine Regel greift.
        """
        for regel in self.regeln:
            if regel.passt(transaktion) and regel.passt_richtung(transaktion):
                return regel.ergebnis(transaktion)
        return None

    def gegenrichtung(self, transaktion: Transaktion) -> Klassifikationsergebnis | None:
        """Die erste Regel, deren Muster passt, aber nicht die Richtung — als
        Gegenbuchung (Soll und Haben getauscht), immer zur Prüfung."""
        for regel in self.regeln:
            if regel.passt(transaktion) and not regel.passt_richtung(transaktion):
                return regel.ergebnis(transaktion, gegenrichtung=True)
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
        """Transaktion klassifizieren — erst Regelwerk, dann LLM, zuletzt eine Regel
        der Gegenrichtung als Gegenbuchung zur Prüfung (Erstattung auf eine
        Ausgaberegel).

        Returns None wenn weder Regel noch LLM eine Klassifikation liefern.
        """
        # Stufe 1: Regelwerk
        ergebnis = self.regelwerk.klassifiziere(transaktion)
        if ergebnis is not None:
            return ergebnis

        # Stufe 2: LLM (nur wenn konfiguriert)
        if self.llm is not None:
            ergebnis = self.llm.klassifiziere(transaktion)
            if ergebnis is not None:
                return ergebnis

        return self.regelwerk.gegenrichtung(transaktion)
