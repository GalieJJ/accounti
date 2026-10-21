"""Herkunft einer Buchung und gelernte Kontierungsregeln (Baustein 10b).

* ``Kontierungsgrund`` — woher ein Buchungsvorschlag kommt und welche Begründung
  Regelwerk, LLM, Beleg, Kontakt, Kreditkarten-, Anlagen- oder Marktplatzabgleich
  mitgeliefert haben (Architekturprinzip 2). Nur anfügen; je Buchung gilt der neueste.
* ``Kontierungsregel`` — eine aus einer Korrektur (oder per ``accounti lerne``)
  gelernte Regel in der Datenbank der Gesellschaft. Sie greift vor der Regeldatei und
  nur in der Zahlungsrichtung ihres Quellumsatzes; geändert wird sie nie, nur
  deaktiviert (und neu gelernt).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

QUELLEN = (
    "regelwerk",
    "llm",
    "beleg",
    "kontakt",
    "standard",
    "opos",
    "kreditkarte",
    "anlagen",
    "marktplatz",
)
Quelle = Literal[
    "regelwerk",
    "llm",
    "beleg",
    "kontakt",
    "standard",
    "opos",
    "kreditkarte",
    "anlagen",
    "marktplatz",
]
BEGRUENDUNG_LAENGE = 500


class Kontierungsgrund(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    buchung_id: UUID
    quelle: Quelle
    regel: str | None = Field(default=None, max_length=100)
    modell: str | None = Field(default=None, max_length=100)
    begruendung: str = ""
    erstellt_am: datetime = Field(default_factory=datetime.now)

    @field_validator("begruendung")
    @classmethod
    def _kuerzen(cls, wert: str) -> str:
        return " ".join(wert.split())[:BEGRUENDUNG_LAENGE]


class Richtung(str, enum.Enum):
    """Zahlungsrichtung des Quellumsatzes (Vorzeichen des Betrags)."""

    AUSGABE = "ausgabe"
    EINNAHME = "einnahme"


class RegelHerkunft(str, enum.Enum):
    KORREKTUR = "korrektur"  # Haken „Regel daraus machen“ / korrigiere --lernen
    LERNE = "lerne"  # accounti lerne (Regex vom Betreiber)
    UEBERNAHME = "uebernahme"  # accounti regeln uebernehmen (alte gelernt_*-Einträge)


Feld = Literal["verwendungszweck", "gegenkonto_name", "beide"]


class Kontierungsregel(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=100)
    muster: str = Field(min_length=1, max_length=200)
    ist_text: bool = True  # Text (wörtlich, ganze Wörter) statt regulärem Ausdruck
    feld: Feld = "beide"
    richtung: Richtung | None = None
    soll_konto: str = Field(min_length=1, max_length=10)
    haben_konto: str = Field(min_length=1, max_length=10)
    steuer_schluessel: int | None = None
    buchungstext: str | None = Field(default=None, max_length=60)
    quelle_buchung_id: UUID | None = None
    herkunft: RegelHerkunft = RegelHerkunft.KORREKTUR
    angelegt_von: str = Field(min_length=1, max_length=100)
    angelegt_am: datetime = Field(default_factory=datetime.now)
    aktiv: bool = True
    deaktiviert_von: str | None = None
    deaktiviert_am: datetime | None = None
    deaktiviert_grund: str | None = Field(default=None, max_length=500)
