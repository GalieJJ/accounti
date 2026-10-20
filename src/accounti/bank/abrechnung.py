"""Provider ``abrechnung`` — für Konten, deren Umsätze aus Abrechnungen kommen.

Typisch eine Kreditkarte mit PDF-Abrechnung: Die Umsätze entstehen über
``accounti kreditkarte uebernehmen`` aus dem erfassten Beleg (Positionssplit aus
Baustein 2), nicht über einen Abruf. Der Provider meldet deshalb nichts Neues —
``bank abrufen`` läuft für solche Konten ohne Fehler durch.
"""

from __future__ import annotations

from datetime import date

from accounti.bank.provider import Abruf, BankProvider, registriere
from accounti.models import Bankkonto


@registriere
class AbrechnungsProvider(BankProvider):
    name = "abrechnung"

    def abrufen(
        self, konto: Bankkonto, zugang: dict[str, str], ab: date | None
    ) -> Abruf:
        return Abruf()
