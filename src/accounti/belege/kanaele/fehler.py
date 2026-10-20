"""Fehler der Kanäle."""

from __future__ import annotations


class KanalError(RuntimeError):
    """Abholen gescheitert — Verbindung, Anmeldung oder Antwort der Gegenstelle.

    Die Meldung enthält nie Passwörter oder Tokens.
    """
