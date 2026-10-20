"""Bank-Provider — eine Schnittstelle für alle Wege, Kontoumsätze zu holen.

Wie bei den Importern aus Baustein 1: Basisklasse plus Registry. Ein Provider kennt
seine Einstellungen (``felder``, nicht geheim) und seine Zugangsdaten
(``geheime_felder``, landen verschlüsselt im Tresor) und liefert Umsätze ab einem
Stand. Verlangt die Bank eine Freigabe (starke Kundenauthentifizierung), meldet er
das als ``FreigabeNoetigError`` — ein Zustand, kein Absturz. Wer interaktiv
abruft, gibt dem Provider eine Rückfrage (``freigabe``) mit; dann fragt er nach der
TAN bzw. wartet auf die Bestätigung in der App, statt aufzugeben.

Ändern sich Zugangsdaten beim Abruf (Sitzung der Bank, Tokens), gibt der Provider
sie in ``Abruf.zugang`` bzw. ``FreigabeNoetigError.zugang`` zurück; der Abruf
verschlüsselt sie neu.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import ClassVar

from accounti.models import Bankkonto, Transaktion


class FreigabeNoetigError(RuntimeError):
    """Die Bank verlangt eine Freigabe (TAN, App) — später erneut abrufen."""

    def __init__(self, meldung: str, zugang: dict[str, str] | None = None) -> None:
        super().__init__(meldung)
        self.zugang = zugang


class ProviderError(RuntimeError):
    """Der Abruf ist gescheitert (Verbindung, Format, Einstellungen)."""


@dataclass
class Abruf:
    transaktionen: list[Transaktion] = field(default_factory=list)
    saldo: Decimal | None = None
    saldo_datum: date | None = None
    zugang: dict[str, str] | None = None  # geändert → wird neu verschlüsselt


@dataclass(frozen=True)
class Freigabeanfrage:
    """Was die Bank zur Freigabe sagt — für die Rückfrage an den Menschen."""

    konto: Bankkonto
    text: str
    app: bool  # Freigabe in der App (decoupled): keine TAN eintippen
    hinweis: str | None = None  # z.B. Grafik/Flickercode, den die Konsole nicht zeigt


# Rückfrage: liefert die TAN ("" bei Freigabe in der App) oder None (abbrechen)
Freigabe = Callable[[Freigabeanfrage], "str | None"]


class BankProvider:
    name: ClassVar[str] = "basis"
    felder: ClassVar[tuple[str, ...]] = ()
    geheime_felder: ClassVar[tuple[str, ...]] = ()

    def __init__(self, freigabe: Freigabe | None = None) -> None:
        self.freigabe = freigabe

    def abrufen(
        self, konto: Bankkonto, zugang: dict[str, str], ab: date | None
    ) -> Abruf:
        raise NotImplementedError


BANK_PROVIDER: dict[str, type[BankProvider]] = {}


def registriere(klasse: type[BankProvider]) -> type[BankProvider]:
    BANK_PROVIDER[klasse.name] = klasse
    return klasse


# eingebaute Provider registrieren
from accounti.bank import abrechnung, datei, fints  # noqa: E402, F401
