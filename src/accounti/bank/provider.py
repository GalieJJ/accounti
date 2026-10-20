"""Bank-Provider — eine Schnittstelle für alle Wege, Kontoumsätze zu holen.

Wie bei den Importern aus Baustein 1: Basisklasse plus Registry. Ein Provider kennt
seine Einstellungen (``felder``, nicht geheim) und seine Zugangsdaten
(``geheime_felder``, landen verschlüsselt im Tresor) und liefert Umsätze ab einem
Stand. Verlangt die Bank eine Freigabe (starke Kundenauthentifizierung), meldet er
das als ``FreigabeNoetigError`` — ein Zustand, kein Absturz. Wer interaktiv
abruft, gibt dem Provider eine Rückfrage (``freigabe``) mit; dann fragt er nach der
TAN bzw. wartet auf die Bestätigung in der App, statt aufzugeben.

Lehnt die Bank die Anmeldung ab, meldet der Provider ``ZugangAbgelehntError``;
ein automatischer Lauf versucht es dann nicht wieder, bis der Zugang erneuert ist.

Ändern sich Zugangsdaten beim Abruf (Sitzung der Bank, Tokens), gibt der Provider
sie in ``Abruf.zugang`` bzw. ``FreigabeNoetigError.zugang`` zurück; der Abruf
verschlüsselt sie neu.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
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


class ZugangAbgelehntError(ProviderError):
    """Die Bank lehnt die Anmeldung ab (PIN falsch, Zugang gesperrt).

    Ein unbeaufsichtigter Abruf versucht es nicht erneut — jeder weitere Versuch
    mit denselben Zugangsdaten kann den Zugang bei der Bank sperren.
    """


@dataclass
class Abruf:
    transaktionen: list[Transaktion] = field(default_factory=list)
    saldo: Decimal | None = None
    saldo_datum: date | None = None
    zugang: dict[str, str] | None = None  # geändert → wird neu verschlüsselt
    # wo in ``transaktionen`` ein Auszug bzw. eine Datei beginnt: gleiche Umsätze
    # ohne Bankreferenz zählt der Dublettenschutz je Abschnitt (leer: ein Abschnitt)
    abschnitte: list[int] = field(default_factory=list)

    def fuege_hinzu(
        self, umsaetze: Iterable[Transaktion], fortsetzung: bool = False
    ) -> None:
        """Umsätze eines Auszugs bzw. einer Datei als eigenen Abschnitt anhängen —
        die Folgeseite eines Auszugs (``fortsetzung``) gehört zum vorigen."""
        if not fortsetzung:
            self.abschnitte.append(len(self.transaktionen))
        self.transaktionen.extend(umsaetze)


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
