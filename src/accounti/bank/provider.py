"""Bank-Provider — eine Schnittstelle für alle Wege, Kontoumsätze zu holen.

Wie bei den Importern aus Baustein 1: Basisklasse plus Registry. Ein Provider kennt
seine Einstellungen (``felder``, nicht geheim) und seine Zugangsdaten
(``geheime_felder``, landen verschlüsselt im Tresor) und liefert Umsätze ab einem
Stand. Verlangt die Bank eine Freigabe (starke Kundenauthentifizierung), meldet er
das als ``FreigabeNoetigError`` — ein Zustand, kein Absturz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import ClassVar

from accounti.models import Bankkonto, Transaktion


class FreigabeNoetigError(RuntimeError):
    """Die Bank verlangt eine Freigabe (TAN, App) — später erneut abrufen."""


class ProviderError(RuntimeError):
    """Der Abruf ist gescheitert (Verbindung, Format, Einstellungen)."""


@dataclass
class Abruf:
    transaktionen: list[Transaktion] = field(default_factory=list)
    saldo: Decimal | None = None
    saldo_datum: date | None = None


class BankProvider:
    name: ClassVar[str] = "basis"
    felder: ClassVar[tuple[str, ...]] = ()
    geheime_felder: ClassVar[tuple[str, ...]] = ()

    def abrufen(
        self, konto: Bankkonto, zugang: dict[str, str], ab: date | None
    ) -> Abruf:
        raise NotImplementedError


BANK_PROVIDER: dict[str, type[BankProvider]] = {}


def registriere(klasse: type[BankProvider]) -> type[BankProvider]:
    BANK_PROVIDER[klasse.name] = klasse
    return klasse


# eingebaute Provider registrieren
from accounti.bank import datei  # noqa: E402, F401
