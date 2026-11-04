"""Einstellungen in der Datenbank (Baustein 10c, Paket P4) — Domänenmodelle.

* **Einstellungsversion** — eine Version eines Abschnitts (nur anfügen, Hash-Kette je
  Abschnitt). ``daten`` steht in Normalform (``einstellungen.normalform``).
* **Antrag** — eine Änderung, die eine zweite Person bestätigt (K3).
* **GeheimnisInfo** — Name und Herkunft eines Geheimnisses, nie das Chiffrat.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Quelle = Literal["browser", "cli", "assistent", "datei_uebernahme", "antrag"]
Antragsstatus = Literal["offen", "bestaetigt", "abgelehnt", "abgelaufen", "veraltet"]


class Einstellungsversion(BaseModel):
    """Eine Version eines Abschnitts."""

    id: int | None = None
    abschnitt: str
    version: int = Field(ge=1)
    daten: dict[str, Any]
    schema_version: int = 1
    vollstaendig: bool = True
    fehlend: list[str] = Field(default_factory=list)
    person: str
    grund: str
    quelle: Quelle
    antrag_id: int | None = None
    datei_hash: str | None = Field(
        default=None, description="Hash des normalisierten Datei-Abschnitts (D9)"
    )
    erstellt_am: datetime
    hash: str = ""
    vorgaenger_hash: str = ""


class Antrag(BaseModel):
    """Antrag auf eine Änderung, die eine Kontrolle lockert."""

    id: int
    aenderungen: list[dict[str, Any]]
    inhalt_hash: str
    grund: str
    antragsteller: str
    erstellt_am: datetime
    gueltig_bis: datetime
    kontrolle: str
    recht: str
    felder: list[str]
    status: Antragsstatus
    entschieden_von: str | None = None
    entschieden_am: datetime | None = None
    entscheidungsgrund: str | None = None
    versionen: dict[str, int] | None = None


class GeheimnisInfo(BaseModel):
    """Ein gespeichertes Geheimnis — ohne Wert und ohne Chiffrat."""

    name: str
    gesetzt_am: datetime
    gesetzt_von: str
