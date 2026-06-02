"""Importer — wandeln Rohdaten einer Quelle in Transaktion-Objekte um."""

from __future__ import annotations

from pathlib import Path

from accounti.models import Transaktion


class BankImporter:
    """Basisklasse für Bank-Importer. Kennt nur das Format, keine Buchungslogik."""

    name: str = "base"

    def importiere(self, pfad: Path) -> list[Transaktion]:
        raise NotImplementedError


BANK_IMPORTERS: dict[str, type[BankImporter]] = {}

# Konkrete Importer importieren, damit sie sich in BANK_IMPORTERS registrieren.
from accounti.importers import sparkasse  # noqa: E402,F401
