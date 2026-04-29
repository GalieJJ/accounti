"""BWA — Betriebswirtschaftliche Auswertung nach DATEV-Schema (Form 01).

Berechnet die BWA aus Buchungssätzen, gruppiert nach BWA-Zeilen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from accounti.models import BWA, BWAZeile, Buchungssatz, Kontenrahmen


# ---------------------------------------------------------------------------
# BWA-Schema (Form 01) — Zuordnung Konten → BWA-Zeilen für SKR03
# ---------------------------------------------------------------------------

BWA_SCHEMA_SKR03: dict[int, dict] = {
    1: {
        "bezeichnung": "Umsatzerlöse",
        "konten_von": ["8000", "8100", "8200", "8300", "8400"],
        "konten_bereiche": [("8000", "8099"), ("8100", "8199"), ("8300", "8499")],
    },
    2: {
        "bezeichnung": "Bestandsveränderungen und aktivierte Eigenleistungen",
        "konten_bereiche": [("8900", "8999")],
    },
    3: {
        "bezeichnung": "Sonstige betriebliche Erlöse",
        "konten_bereiche": [("8500", "8899")],
    },
    4: {
        "bezeichnung": "Materialaufwand / Wareneinsatz",
        "konten_bereiche": [("3000", "3999")],
    },
    5: {
        "bezeichnung": "Rohertrag",
        "berechnung": "1+2+3-4",  # Summenzeile
    },
    6: {
        "bezeichnung": "Sonstige betriebliche Erlöse (Gesamtleistung)",
        "berechnung": "1+2+3",
    },
    7: {
        "bezeichnung": "Gesamtleistung",
        "berechnung": "6",
    },
    8: {
        "bezeichnung": "Personalkosten",
        "konten_bereiche": [("4100", "4199")],
    },
    9: {
        "bezeichnung": "Raumkosten",
        "konten_bereiche": [("4200", "4299")],
    },
    10: {
        "bezeichnung": "Betriebliche Steuern",
        "konten_bereiche": [("4300", "4399")],
    },
    11: {
        "bezeichnung": "Versicherungen / Beiträge",
        "konten_bereiche": [("4360", "4399")],
    },
    12: {
        "bezeichnung": "Besondere Aufwendungen (Kfz, Reise, Bewirtung)",
        "konten_bereiche": [("4500", "4699")],
    },
    13: {
        "bezeichnung": "Abschreibungen",
        "konten_bereiche": [("4800", "4899")],
    },
    14: {
        "bezeichnung": "Sonstige betriebliche Aufwendungen",
        "konten_bereiche": [("4900", "4999")],
    },
    15: {
        "bezeichnung": "Gesamtkosten",
        "berechnung": "4+8+9+10+11+12+13+14",
    },
    16: {
        "bezeichnung": "Betriebsergebnis",
        "berechnung": "7-15",
    },
    17: {
        "bezeichnung": "Zinsaufwand",
        "konten_bereiche": [("7300", "7399")],
    },
    18: {
        "bezeichnung": "Sonstige neutrale Aufwendungen",
        "konten_bereiche": [("7000", "7299")],
    },
    19: {
        "bezeichnung": "Zinserträge",
        "konten_bereiche": [("7100", "7199")],
    },
    20: {
        "bezeichnung": "Sonstige neutrale Erträge",
        "konten_bereiche": [("7400", "7499")],
    },
    21: {
        "bezeichnung": "Ergebnis vor Steuern",
        "berechnung": "16-17-18+19+20",
    },
    22: {
        "bezeichnung": "Steuern vom Einkommen und Ertrag",
        "konten_bereiche": [("7600", "7699")],
    },
    23: {
        "bezeichnung": "Vorläufiges Ergebnis",
        "berechnung": "21-22",
    },
}


def _konto_in_bereich(konto: str, von: str, bis: str) -> bool:
    """Prüft ob ein Konto in einem Nummernbereich liegt."""
    try:
        return int(von) <= int(konto) <= int(bis)
    except ValueError:
        return False


class BWABerechner:
    """Berechnet eine BWA aus Buchungssätzen."""

    def __init__(self, kontenrahmen: Kontenrahmen = Kontenrahmen.SKR03) -> None:
        self.kontenrahmen = kontenrahmen
        if kontenrahmen == Kontenrahmen.SKR03:
            self.schema = BWA_SCHEMA_SKR03
        else:
            raise NotImplementedError(
                f"BWA-Schema für {kontenrahmen} noch nicht implementiert"
            )

    def _summe_fuer_zeile(
        self,
        zeilen_def: dict,
        konten_summen: dict[str, Decimal],
    ) -> Decimal:
        """Berechnet die Summe für eine BWA-Zeile aus den Kontensalden."""
        summe = Decimal("0.00")
        for von, bis in zeilen_def.get("konten_bereiche", []):
            for konto, betrag in konten_summen.items():
                if _konto_in_bereich(konto, von, bis):
                    summe += betrag
        return summe

    def berechne(
        self,
        buchungen: list[Buchungssatz],
        zeitraum: str,
        mandant: str = "",
    ) -> BWA:
        """BWA aus Buchungssätzen berechnen.

        Args:
            buchungen: Alle Buchungssätze des Zeitraums
            zeitraum: z.B. "2026-04"
            mandant: Mandantenbezeichnung

        Returns:
            Vollständige BWA mit allen Zeilen
        """
        # Schritt 1: Kontensalden aufbauen
        konten_summen: dict[str, Decimal] = {}
        for b in buchungen:
            # Haben-Buchungen (Erlöse) positiv, Soll-Buchungen (Aufwand) positiv
            konten_summen.setdefault(b.haben_konto, Decimal("0.00"))
            konten_summen[b.haben_konto] += b.betrag_netto
            konten_summen.setdefault(b.soll_konto, Decimal("0.00"))
            konten_summen[b.soll_konto] += b.betrag_netto

        # Schritt 2: BWA-Zeilen berechnen
        zeilen_ergebnisse: dict[int, Decimal] = {}
        bwa_zeilen: list[BWAZeile] = []

        for nr, definition in sorted(self.schema.items()):
            if "berechnung" in definition:
                # Summenzeile — wird später berechnet
                continue
            betrag = self._summe_fuer_zeile(definition, konten_summen)
            zeilen_ergebnisse[nr] = betrag

        # Summenzeilen berechnen (vereinfacht)
        # TODO: Formelparser für "1+2+3-4" etc.
        for nr, definition in sorted(self.schema.items()):
            betrag = zeilen_ergebnisse.get(nr, Decimal("0.00"))
            bwa_zeilen.append(
                BWAZeile(
                    nummer=nr,
                    bezeichnung=definition["bezeichnung"],
                    betrag_aktuell=betrag,
                    betrag_kumuliert=betrag,  # TODO: kumuliert über Monate
                )
            )

        return BWA(
            mandant=mandant,
            zeitraum=zeitraum,
            kontenrahmen=self.kontenrahmen,
            zeilen=bwa_zeilen,
        )
