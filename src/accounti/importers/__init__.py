"""Importer — wandeln Rohdaten einer Quelle in Transaktion-Objekte um."""

from __future__ import annotations

from pathlib import Path

from accounti.models import Transaktion


class BankImporter:
    """Basisklasse für Bank-Importer. Kennt nur das Format, keine Buchungslogik."""

    name: str = "base"

    def importiere(self, pfad: str | Path) -> list[Transaktion]:
        raise NotImplementedError


# Registry: Bankname -> einsatzbereiter Importer.
BANK_IMPORTERS: dict[str, BankImporter] = {}

# Profile registrieren (füllt BANK_IMPORTERS mit den eingebauten Banken);
# sparkasse-Modul für den Rückwärtskompatibilitäts-Import bereitstellen.
from accounti.importers import profil, sparkasse  # noqa: E402, F401
