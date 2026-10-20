"""Fehler von Anmeldung und Rechteprüfung."""

from __future__ import annotations


class AuthError(RuntimeError):
    """Anmeldung, zweiter Faktor oder Verwaltung ist so nicht möglich."""


class AnmeldungError(AuthError):
    """Anmeldung abgelehnt. Die Meldung sagt bewusst nicht, was falsch war; der
    Grund steht nur im Ereignisprotokoll."""

    def __init__(self, grund: str) -> None:
        self.grund = grund
        super().__init__("Anmeldung fehlgeschlagen")


class RechteError(AuthError):
    """Die Rolle erlaubt diese Aktion nicht."""
