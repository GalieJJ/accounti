"""Abschnitt ``import`` in ``config/accounti.yaml`` (Baustein 10c P4, A44).

Nur Modell und Lader: Die Erkennung des Formats ist automatisch, Dubletten prüft
accounti immer — beide Werte haben (noch) keine Wirkung.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ValidationError

from accounti.einstellungen.leser import lies_abschnitt
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError, _fehlertext


class ImportEinstellungen(BaseModel):
    standard_bank: str | None = None
    duplikat_check: bool = True


def lade_import(pfad: str | Path = STANDARD_PFAD) -> ImportEinstellungen:
    pfad = Path(pfad)
    try:
        return ImportEinstellungen.model_validate(lies_abschnitt(pfad, "import"))
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'import': {_fehlertext(fehler, 'import')}"
        raise KonfigurationError(msg) from fehler
