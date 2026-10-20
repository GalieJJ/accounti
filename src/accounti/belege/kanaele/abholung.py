"""Kanäle, die eine Gegenstelle abfragen (Postfach, Portal) — Basisklasse und Fehler."""

from __future__ import annotations

from accounti.belege.kanaele import BelegKanal


class KanalError(RuntimeError):
    """Abholen gescheitert — Verbindung, Anmeldung oder Antwort der Gegenstelle.

    Die Meldung enthält nie Passwörter oder Tokens.
    """


class AbholKanal(BelegKanal):
    """Kanal mit Gegenstelle (Postfach, Portal).

    Trägt eine Bezeichnung für die Ausgabe und sammelt Hinweise — übersprungene
    Dateien, Nachrichten ohne Beleg —, die der Mensch sehen soll, statt dass sie
    still verschwinden.
    """

    def __init__(self, bezeichnung: str) -> None:
        self.bezeichnung = bezeichnung
        self.hinweise: list[str] = []
