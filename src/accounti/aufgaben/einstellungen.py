"""Abschnitt ``aufgaben`` in ``config/accounti.yaml`` — optional, mit Standardwerten.

Ohne Datei und ohne Abschnitt läuft alles: Aufgaben bleiben unzugewiesen (gemeinsame
Liste), Fristen und Erinnerungsstufen haben Standardwerte, die Tagesübersicht geht
per E-Mail an die Adressen unter ``benachrichtigung.empfaenger``. ``${VARIABLE}``
wird wie im Abschnitt ``versand`` aus der Umgebung ersetzt.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from accounti.aufgaben.zustaendigkeit import Zustaendigkeitsregel
from accounti.erechnung.versand import _ersetze_variablen
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError

# Tage bis zur Fälligkeit, wenn der Erzeuger keine nennt. Zehn Tage für Vorgänge,
# die die laufende Erfassung betreffen: GoBD Rz. 47 hält die Erfassung unbarer
# Geschäftsvorfälle innerhalb von zehn Tagen für unbedenklich.
STANDARD_FRISTEN: dict[str, int] = {
    "standard": 7,
    "beleg_fehlt": 10,
    "kontierung_pruefen": 10,
    "beleg_pruefen": 10,
    "kontakt_pruefen": 7,
    "bank_freigabe": 0,
    "rueckfrage": 7,
}


def _pruefe_stufen(stufen: list[int]) -> list[int]:
    if not stufen:
        msg = "stufen: mindestens eine Stufe (Tage nach Fälligkeit)"
        raise ValueError(msg)
    if any(s < 0 for s in stufen):
        msg = "stufen: Tage nach Fälligkeit, nicht negativ"
        raise ValueError(msg)
    if stufen != sorted(set(stufen)):
        msg = "stufen müssen aufsteigend und verschieden sein"
        raise ValueError(msg)
    return stufen


class Erinnerungsplan(BaseModel):
    """Stufen in Tagen nach Fälligkeit; die letzte eskaliert, wenn ein Ziel da ist."""

    stufen: list[int] = Field(default_factory=lambda: [0, 3, 7])
    eskalation_an: str | None = Field(
        default=None, description='Benutzer oder "@rolle"'
    )

    @field_validator("stufen")
    @classmethod
    def _stufen(cls, wert: list[int]) -> list[int]:
        return _pruefe_stufen(wert)


class Artplan(BaseModel):
    stufen: list[int] | None = None
    eskalation_an: str | None = None

    @field_validator("stufen")
    @classmethod
    def _stufen(cls, wert: list[int] | None) -> list[int] | None:
        return _pruefe_stufen(wert) if wert is not None else None


class ErinnerungsEinstellungen(Erinnerungsplan):
    arten: dict[str, Artplan] = Field(default_factory=dict)

    def plan(self, art: str) -> Erinnerungsplan:
        eigen = self.arten.get(art, Artplan())
        return Erinnerungsplan(
            stufen=eigen.stufen if eigen.stufen is not None else self.stufen,
            eskalation_an=eigen.eskalation_an or self.eskalation_an,
        )


class PruefEinstellungen(BaseModel):
    kontierung_schwelle: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="darunter wird eine Kontierung zur Aufgabe (wie auto_schwelle)",
    )
    beleg_fehlt_ab_betrag: Decimal = Field(default=Decimal("0"), ge=0)
    beleg_fehlt_nach_tagen: int = Field(default=0, ge=0)
    abgeschaltet: list[str] = Field(default_factory=list)


class WebhookEinstellungen(BaseModel):
    url: str
    timeout_sekunden: float = Field(default=10, gt=0)

    @field_validator("url")
    @classmethod
    def _url(cls, wert: str) -> str:
        # die Meldung nennt die URL nicht: Pfad und Abfrage tragen oft ein Geheimnis
        teile = urlsplit(wert.strip())
        if teile.scheme not in ("http", "https"):
            msg = "Adresse mit http:// oder https:// angeben"
            raise ValueError(msg)
        if not teile.hostname:
            msg = "Host fehlt in der Adresse"
            raise ValueError(msg)
        return wert.strip()


class BenachrichtigungsEinstellungen(BaseModel):
    kanaele: list[str] = Field(default_factory=lambda: ["email"])
    neue_melden: bool = Field(default=True, description="neue Aufgaben aufnehmen")
    absender: str | None = Field(default=None, description="sonst versand.absender")
    empfaenger: dict[str, str] = Field(
        default_factory=dict,
        description='Adresse je Benutzer, "@rolle" oder "gemeinsam"',
    )
    webhook: WebhookEinstellungen | None = None

    @field_validator("kanaele")
    @classmethod
    def _kanaele(cls, wert: list[str]) -> list[str]:
        # Ob es einen Kanal gibt, weiß erst die Registry KANAELE (andere Bausteine
        # tragen eigene ein) — das prüft baue_kanaele und meldet es je Kanal.
        if not wert:
            # ohne Kanal gälte jede Aufgabe als gemeldet, ohne dass jemand sie sah
            msg = "mindestens ein Kanal (z.B. email oder webhook)"
            raise ValueError(msg)
        return wert

    @model_validator(mode="after")
    def _webhook(self) -> BenachrichtigungsEinstellungen:
        if "webhook" in self.kanaele and self.webhook is None:
            msg = "Kanal webhook braucht webhook.url"
            raise ValueError(msg)
        return self


class AufgabenEinstellungen(BaseModel):
    ich: str | None = Field(default=None, description="Standard für --zustaendig ich")
    rollen: dict[str, list[str]] = Field(default_factory=dict)
    zustaendigkeit: list[Zustaendigkeitsregel] = Field(default_factory=list)
    fristen: dict[str, int] = Field(default_factory=dict)
    erinnerung: ErinnerungsEinstellungen = Field(
        default_factory=ErinnerungsEinstellungen
    )
    pruefung: PruefEinstellungen = Field(default_factory=PruefEinstellungen)
    benachrichtigung: BenachrichtigungsEinstellungen = Field(
        default_factory=BenachrichtigungsEinstellungen
    )

    @field_validator("fristen")
    @classmethod
    def _fristen(cls, wert: dict[str, int]) -> dict[str, int]:
        if any(tage < 0 for tage in wert.values()):
            msg = "Tage bis zur Fälligkeit dürfen nicht negativ sein"
            raise ValueError(msg)
        return wert

    def frist_tage(self, art: str) -> int:
        """Tage von der Anlage bis zur Fälligkeit für eine Aufgabenart."""
        fristen = {**STANDARD_FRISTEN, **self.fristen}
        return fristen.get(art, fristen["standard"])


def _fehlertext(fehler: ValidationError) -> str:
    teile = []
    for f in fehler.errors():
        pfad = ".".join(str(x) for x in f["loc"])
        grund = str(f["msg"]).removeprefix("Value error, ")
        teile.append(f"{pfad}: {grund}" if pfad else grund)
    return "; ".join(teile)


def lade_aufgaben_einstellungen(
    pfad: str | Path = STANDARD_PFAD,
) -> AufgabenEinstellungen:
    """Abschnitt ``aufgaben``; fehlt Datei oder Abschnitt, gelten die Standardwerte."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return AufgabenEinstellungen()
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    abschnitt = daten.get("aufgaben") if isinstance(daten, dict) else None
    if abschnitt is None:
        return AufgabenEinstellungen()
    if not isinstance(abschnitt, dict):
        msg = f"{pfad}: Abschnitt 'aufgaben' muss eine Zuordnung sein"
        raise KonfigurationError(msg)
    try:
        return AufgabenEinstellungen.model_validate(_ersetze_variablen(abschnitt))
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'aufgaben': {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler
