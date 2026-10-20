"""Aufgaben und Rückfragen (Baustein 8) — Domänenmodelle.

Eine Aufgabe hängt an einem beliebigen Objekt (Buchung, Beleg, Transaktion, offener
Posten, Kontakt, Bankkonto, später auch Fristen oder Zahlungsläufe). Art und
Objekttyp sind freie Bezeichner, damit andere Bausteine eigene mitbringen können,
ohne dieses Modul zu ändern. Der Idempotenzschlüssel aus Art und Objekt sorgt dafür,
dass ein wiederholter Prüflauf dieselbe Aufgabe aktualisiert, statt eine neue
anzulegen.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

BEZEICHNER = r"^[a-z][a-z0-9_]{0,39}$"
_BEZEICHNER = re.compile(BEZEICHNER)
MAX_OBJEKT_ID = 100


class AufgabenStatus(str, enum.Enum):
    OFFEN = "offen"
    IN_ARBEIT = "in_arbeit"
    WARTET = "wartet"  # z.B. auf Antwort des Lieferanten
    ERLEDIGT = "erledigt"  # von einem Menschen abgeschlossen
    HINFAELLIG = "hinfaellig"  # Anlass entfallen, vom System geschlossen


AKTIVE_STATUS = frozenset(
    {AufgabenStatus.OFFEN, AufgabenStatus.IN_ARBEIT, AufgabenStatus.WARTET}
)


class Prioritaet(str, enum.Enum):
    NIEDRIG = "niedrig"
    NORMAL = "normal"
    HOCH = "hoch"

    @property
    def rang(self) -> int:
        return {"niedrig": 0, "normal": 1, "hoch": 2}[self.value]


class KommentarArt(str, enum.Enum):
    KOMMENTAR = "kommentar"
    RUECKFRAGE = "rueckfrage"
    EREIGNIS = "ereignis"  # Verlauf: angelegt, zugewiesen, erledigt, hinfällig …


@dataclass(frozen=True, init=False)
class Objekt:
    """Bezug einer Aufgabe oder eines Kommentars, z.B. ``Objekt("beleg", beleg.id)``."""

    typ: str
    id: str

    def __init__(self, typ: str, id: str | UUID) -> None:
        text = str(id).strip()
        if not _BEZEICHNER.match(typ):
            msg = f"Objekttyp {typ!r} ungültig (klein, z.B. 'beleg' oder 'buchung')"
            raise ValueError(msg)
        if not text or len(text) > MAX_OBJEKT_ID:
            msg = f"ID des Objekts ungültig: {text!r}"
            raise ValueError(msg)
        object.__setattr__(self, "typ", typ)
        object.__setattr__(self, "id", text)

    def __str__(self) -> str:
        return f"{self.typ}:{self.id}"

    @classmethod
    def aus_text(cls, text: str) -> Objekt:
        """``"beleg:3fa2…"`` → ``Objekt("beleg", "3fa2…")``."""
        typ, trenner, ident = text.partition(":")
        if not trenner:
            msg = f"Objekt {text!r} bitte als typ:id angeben, z.B. beleg:3fa2"
            raise ValueError(msg)
        return cls(typ.strip(), ident)


def idempotenzschluessel(art: str, objekt: Objekt) -> str:
    """Eine Aufgabe je Art und Objekt — über alle Prüfläufe hinweg."""
    return f"{art}|{objekt.typ}|{objekt.id}"


class Aufgabe(BaseModel):
    """Etwas, das ein Mensch entscheiden muss — mit Bezug, Zuständigkeit und Frist."""

    id: UUID = Field(default_factory=uuid4)
    nr: int = Field(default=0, description="laufende Nummer, vergibt die Erzeugung")
    art: str = Field(pattern=BEZEICHNER, description="z.B. beleg_fehlt")
    titel: str = Field(min_length=1, max_length=200)
    beschreibung: str = ""
    objekt_typ: str = Field(pattern=BEZEICHNER)
    objekt_id: str = Field(min_length=1, max_length=MAX_OBJEKT_ID)
    schluessel: str = Field(default="", description="Idempotenzschlüssel")
    zustaendig: str | None = Field(default=None, description="Benutzer")
    rolle: str | None = Field(default=None, description="oder Rolle")
    faellig_am: date | None = None
    status: AufgabenStatus = AufgabenStatus.OFFEN
    prioritaet: Prioritaet = Prioritaet.NORMAL
    erzeugt_von: str = Field(default="system", description="Prüflauf, Baustein, Person")
    merkmale: dict[str, str] = Field(
        default_factory=dict, description="Kontext, auch für Zuständigkeitsregeln"
    )
    erstellt_am: datetime = Field(default_factory=datetime.now)
    aktualisiert_am: datetime = Field(default_factory=datetime.now)
    quittiert_von: str | None = Field(default=None, description="wer erledigt hat")
    erledigt_am: datetime | None = None
    abschluss_grund: str | None = Field(default=None, description="warum hinfällig")
    erinnerungsstufe: int = Field(default=0, ge=0, description="zuletzt gemeldet")
    gemeldet_am: date | None = Field(default=None, description="erste Tagesübersicht")

    @model_validator(mode="after")
    def _schluessel(self) -> Aufgabe:
        if not self.schluessel:
            self.schluessel = idempotenzschluessel(self.art, self.objekt)
        return self

    @property
    def objekt(self) -> Objekt:
        return Objekt(self.objekt_typ, self.objekt_id)

    @property
    def aktiv(self) -> bool:
        return self.status in AKTIVE_STATUS

    @property
    def unzugewiesen(self) -> bool:
        """Weder Benutzer noch Rolle — steht in der gemeinsamen Liste."""
        return self.zustaendig is None and self.rolle is None

    @property
    def zustaendigkeit(self) -> str:
        if self.zustaendig:
            return self.zustaendig
        return f"@{self.rolle}" if self.rolle else "gemeinsam"


class Kommentar(BaseModel):
    """Kommentar, Rückfrage oder Verlaufseintrag — an einer Aufgabe, einem Objekt
    oder beidem. Nur anfügen, nie ändern."""

    id: UUID = Field(default_factory=uuid4)
    aufgabe_id: UUID | None = None
    objekt_typ: str | None = Field(default=None, pattern=BEZEICHNER)
    objekt_id: str | None = Field(default=None, max_length=MAX_OBJEKT_ID)
    art: KommentarArt = KommentarArt.KOMMENTAR
    autor: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1)
    erstellt_am: datetime = Field(default_factory=datetime.now)
    anhang_beleg_id: UUID | None = Field(default=None, description="z.B. Antwortbeleg")

    @model_validator(mode="after")
    def _ziel(self) -> Kommentar:
        if self.aufgabe_id is None and self.objekt_typ is None:
            msg = "Ein Kommentar braucht eine Aufgabe oder ein Objekt"
            raise ValueError(msg)
        if (self.objekt_typ is None) != (self.objekt_id is None):
            msg = "Objekttyp und Objekt-ID nur zusammen"
            raise ValueError(msg)
        return self

    @property
    def objekt(self) -> Objekt | None:
        if self.objekt_typ is None or self.objekt_id is None:
            return None
        return Objekt(self.objekt_typ, self.objekt_id)


class Benachrichtigung(BaseModel):
    """Protokoll einer Tagesübersicht je Empfänger, Kanal und Tag (auch Fehlschläge)."""

    id: UUID = Field(default_factory=uuid4)
    tag: date
    empfaenger: str = Field(description="Benutzer, @rolle oder gemeinsam")
    kanal: str
    adresse: str | None = None
    aufgaben: list[int] = Field(default_factory=list, description="Nummern")
    erfolgreich: bool
    fehler: str | None = None
    zeitpunkt: datetime = Field(default_factory=datetime.now)
