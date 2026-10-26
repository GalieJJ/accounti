"""Gruppe einer Belegbuchung je (Konto, Steuerschlüssel) — eine Regel für alle Wege.

Beleg → Buchung gibt es zweimal: als Rechnung auf ein Personenkonto
(``opos/verbuchung.py``) und als Bankumsatz mit Beleg (``buchung/mit_beleg.py``).
Beide fassen die Belegpositionen je Konto und Steuerschlüssel zusammen und behandeln
„kein Schlüssel“ gleich:

* Ohne Steuerschlüssel trägt eine Buchung keine Steuer. Nennt der Beleg trotzdem eine
  (Satz unbekannt, z. B. ZUGFeRD MINIMUM), gehört sie in den Betrag — brutto, zur
  Prüfung —, nie still verworfen: sonst stünde netto auf dem Personenkonto, der
  offene Posten aber brutto (GoBD: Hauptbuch = Nebenbuch).
* Bei § 13b UStG (94/91) und beim ig. Erwerb (19/18) steckt die Steuer nicht im
  Zahlbetrag: Der Leistungsempfänger schuldet sie (§ 13b Abs. 5, § 13a Abs. 1 Nr. 2
  UStG) und zieht sie als Vorsteuer ab (§ 15 Abs. 1 S. 1 Nr. 3, 4 UStG). Sie wird
  aus dem Netto berechnet.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from accounti.steuer.kennziffern import STEUERSCHLUESSEL

NULL = Decimal("0")
CENT = Decimal("0.01")

# § 13b und ig. Erwerb: Steuerschuld und Vorsteuer berechnet der Empfänger selbst
SELBST_BERECHNET = frozenset(
    s
    for s, r in STEUERSCHLUESSEL.items()
    if r.vorsteuer is not None and r.bmg is not None
)
# Steuerfall der Eingangsrechnung (UNTDID 5305) → vorgeschlagener Schlüssel (19 %)
SCHLUESSEL_FUER_STEUERFALL = {"AE": 94, "K": 19}


def selbst_berechnete_steuer(schluessel: int, netto: Decimal) -> Decimal:
    """Steuer zu § 13b bzw. ig. Erwerb aus dem Netto (Satz des Schlüssels)."""
    satz = STEUERSCHLUESSEL[schluessel].satz
    return (netto * satz / 100).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Gruppe:
    konto: str
    schluessel: int | None
    pruefen: bool
    netto: Decimal = NULL
    steuer: Decimal = NULL
    differenz: bool = False  # nur die Differenz gezahlt ≠ Beleg (eigene Zeile)

    def addiere(self, netto: Decimal, steuer: Decimal) -> None:
        """Ohne Schlüssel kommt die Steuer in den Betrag (brutto) und die Gruppe zur
        Prüfung; mit Schlüssel bleiben Netto und Steuer getrennt."""
        if self.schluessel is None:
            self.netto += netto + steuer
            if steuer:
                self.pruefen = True
        else:
            self.netto += netto
            self.steuer += steuer

    def berechne_selbst(self) -> None:
        """§ 13b bzw. ig. Erwerb: Steuer aus dem Netto der Gruppe."""
        if self.schluessel in SELBST_BERECHNET:
            self.steuer = selbst_berechnete_steuer(self.schluessel, self.netto)
