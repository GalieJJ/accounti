"""Domänenmodelle der Steuermeldungen (Baustein 9): Freigabe und Protokoll."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Meldeart(str, enum.Enum):
    USTVA = "UStVA"  # Umsatzsteuer-Voranmeldung
    DAUERFRIST = "Dauerfrist"  # Dauerfristverlängerung / Sondervorauszahlung


class Modus(str, enum.Enum):
    PRUEFUNG = "pruefung"  # Testmodus: erzeugen und prüfen, nichts geht raus
    TESTFALL = "testfall"  # mit Testmerker gesendet, ELSTER löscht ihn sofort
    ECHT = "echt"  # abgegeben


class Freigabe(BaseModel):
    """Ein Mensch gibt genau diese Werte zur Abgabe frei."""

    id: UUID = Field(default_factory=uuid4)
    zeitpunkt: datetime = Field(default_factory=datetime.now)
    art: Meldeart
    zeitraum: str
    inhalt_hash: str = Field(description="SHA-256 über Art, Zeitraum und Werte")
    werte: str = Field(description="freigegebene Formularwerte (JSON)")
    freigegeben_von: str
    hinweise: str = Field(default="[]", description="gesehene Warnungen (JSON)")


class Uebermittlung(BaseModel):
    """Eintrag im Übermittlungsprotokoll — auch für Prüfläufe und Fehlschläge."""

    id: UUID = Field(default_factory=uuid4)
    nr: int = Field(default=0, description="laufende Nummer, vergibt das Protokoll")
    zeitpunkt: datetime = Field(default_factory=datetime.now)
    art: Meldeart
    zeitraum: str
    modus: Modus
    weg: str = Field(description="eric, attrappe oder intern")
    berichtigt: bool = False
    freigabe_id: UUID | None = None
    freigegeben_von: str | None = None
    datensatz: str = Field(description="übermittelter bzw. geprüfter ELSTER-XML")
    datensatz_hash: str = Field(description="SHA-256, Datei im Belegarchiv")
    ticket: str | None = Field(default=None, description="ELSTER-Transferticket")
    erfolgreich: bool
    ergebnis: str = Field(description="Kurzfassung für Menschen")
    pruefbericht: str = Field(description="interne Prüfung und ERiC-Rückgabe")
    server_antwort: str | None = None
    protokoll_pdf_hash: str | None = Field(default=None, description="ERiC-PDF")
    betrag: Decimal | None = Field(default=None, description="Kz 83 bzw. Kz 38")
    aufbewahren_bis: date
    vorgaenger_hash: str = ""
    hash: str = ""
