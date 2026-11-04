"""Datenbank-Abschnitt ``einrichtung`` (Baustein 10c P4, für den Assistenten in P7).

Nur in der Datenbank (``inventar.ABSCHNITTE``: ``nur_db``) — die Datei wird für ihn
nie gelesen. ``ausgeblendet``: Punkte der Einrichtung, die die Gesellschaft nicht
braucht.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from accounti.einstellungen.leser import KonfigurationError, lies_abschnitt

STANDARD_PFAD = Path("config/accounti.yaml")


class EinrichtungEinstellungen(BaseModel):
    ausgeblendet: list[str] = Field(default_factory=list)


def lade_einrichtung(pfad: str | Path = STANDARD_PFAD) -> EinrichtungEinstellungen:
    """``pfad`` nur für die Bindung (fremde Konfiguration im Web, D5)."""
    pfad = Path(pfad)
    try:
        return EinrichtungEinstellungen.model_validate(
            lies_abschnitt(pfad, "einrichtung")
        )
    except ValidationError as fehler:
        teile = "; ".join(
            ".".join(str(x) for x in f["loc"]) + ": " + str(f["msg"])
            for f in fehler.errors()
        )
        raise KonfigurationError(f"Abschnitt 'einrichtung': {teile}") from fehler
