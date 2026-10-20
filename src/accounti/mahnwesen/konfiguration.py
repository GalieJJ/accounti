"""Abschnitt ``mahnwesen`` in ``config/accounti.yaml`` — Mahnstufen als Konfiguration.

Ohne den Abschnitt gelten die Stufen aus dem Beispiel der Spec. Mahngebühren sind
Konfiguration, keine Rechtsberatung.
"""

from __future__ import annotations

import string
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from accounti.konfiguration import STANDARD_PFAD, KonfigurationError
from accounti.mahnwesen.basiszins import Basiszins, halbjahresende, tabelle

PLATZHALTER = frozenset(
    {
        "kunde",
        "nummer",
        "datum",
        "faellig",
        "betrag",
        "summe",
        "frist",
        "firma",
        "stufe",
    }
)


class MahnStufe(BaseModel):
    name: str
    ab_tagen: int = Field(ge=0, description="Tage nach Fälligkeit")
    gebuehr: Decimal = Field(default=Decimal("0.00"), ge=0)
    verzugszinsen: bool = False
    text: str | None = Field(default=None, description="eigener Brieftext")

    @field_validator("text")
    @classmethod
    def _platzhalter(cls, wert: str | None) -> str | None:
        if wert is None:
            return None
        namen = {feld for _, feld, _, _ in string.Formatter().parse(wert) if feld}
        unbekannt = namen - PLATZHALTER
        if unbekannt:
            msg = (
                f"unbekannter Platzhalter {', '.join(sorted(unbekannt))} — erlaubt: "
                f"{', '.join(sorted(PLATZHALTER))}"
            )
            raise ValueError(msg)
        return wert


class BasiszinsEintrag(BaseModel):
    ab: date
    satz: Decimal
    bis: date | None = None

    @field_validator("ab")
    @classmethod
    def _halbjahr(cls, wert: date) -> date:
        if wert.day != 1 or wert.month not in (1, 7):
            msg = "Der Basiszinssatz ändert sich nur zum 1. Januar und 1. Juli"
            raise ValueError(msg)
        return wert


def _standard_stufen() -> list[MahnStufe]:
    return [
        MahnStufe(name="Zahlungserinnerung", ab_tagen=5, gebuehr=Decimal("0.00")),
        MahnStufe(
            name="1. Mahnung", ab_tagen=14, gebuehr=Decimal("5.00"), verzugszinsen=True
        ),
        MahnStufe(
            name="2. Mahnung", ab_tagen=28, gebuehr=Decimal("10.00"), verzugszinsen=True
        ),
    ]


class MahnEinstellungen(BaseModel):
    karenztage: int = Field(default=3, ge=0)
    mindestbetrag: Decimal = Field(default=Decimal("10.00"), ge=0)
    stufenabstand_tage: int = Field(default=7, ge=0)
    zahlungsfrist_tage: int = Field(default=10, ge=1)
    verzug_nach_tagen: int = Field(default=0, ge=0)
    unbekannt_als: Literal["verbraucher", "unternehmer"] = "verbraucher"
    pauschale_b2b: Decimal = Field(default=Decimal("40.00"), ge=0)
    pauschale_anrechnen: bool = True
    stufen: list[MahnStufe] = Field(default_factory=_standard_stufen)
    basiszinssaetze: list[BasiszinsEintrag] = Field(default_factory=list)

    @model_validator(mode="after")
    def _stufen(self) -> MahnEinstellungen:
        if not self.stufen:
            msg = "mindestens eine Stufe ist nötig"
            raise ValueError(msg)
        tage = [s.ab_tagen for s in self.stufen]
        if any(b <= a for a, b in zip(tage, tage[1:], strict=False)):
            msg = "ab_tagen muss von Stufe zu Stufe steigen"
            raise ValueError(msg)
        self.basiszinstabelle()  # Überschneidungen früh melden
        return self

    def basiszinstabelle(self) -> list[Basiszins]:
        return tabelle(
            Basiszins(e.ab, e.bis or halbjahresende(e.ab), e.satz)
            for e in self.basiszinssaetze
        )


def _fehlertext(fehler: ValidationError) -> str:
    return "; ".join(
        ".".join(str(x) for x in f["loc"])
        + (": " if f["loc"] else "")
        + str(f["msg"]).removeprefix("Value error, ")
        for f in fehler.errors()
    )


def lade_mahnwesen(pfad: str | Path = STANDARD_PFAD) -> MahnEinstellungen:
    pfad = Path(pfad)
    abschnitt: Any = None
    if pfad.is_file():
        daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
        abschnitt = daten.get("mahnwesen") if isinstance(daten, dict) else None
    try:
        return MahnEinstellungen.model_validate(abschnitt or {})
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'mahnwesen': {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler
