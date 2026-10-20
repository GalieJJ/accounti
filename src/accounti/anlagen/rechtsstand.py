"""Rechtsstand der Anlagenbuchhaltung — Grenzbeträge mit Gültigkeitszeitraum.

Die Werte stehen in ``rechtsstand.yaml`` (mit Quelle je Eintrag), nicht im Code: Sie
ändern sich mit der Gesetzgebung, und alte Jahre müssen mit den damals gültigen Werten
rechenbar bleiben. Maßgeblich ist der Tag der Anschaffung. Eine eigene Datei gleicher
Form ergänzt den mitgelieferten Stand; ihre Einträge gehen vor.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from accounti.models.anlagen import AfaArt


class RechtsstandError(ValueError):
    """Der Rechtsstand fehlt oder ist nicht lesbar."""


class _Zeitraum(BaseModel):
    von: date
    bis: date | None = None
    quelle: str = ""

    def gilt_am(self, tag: date) -> bool:
        return self.von <= tag and (self.bis is None or tag <= self.bis)


class Grenzen(_Zeitraum):
    """GWG-, Verzeichnis- und Sammelpostengrenzen (netto, in Euro)."""

    gwg: Decimal = Field(description="Sofortabzug bis einschließlich")
    verzeichnis_ab: Decimal | None = Field(
        default=None, description="Verzeichnis für GWG über diesem Betrag"
    )
    sammelposten_von: Decimal | None = Field(
        default=None, description="Sammelposten für mehr als diesen Betrag"
    )
    sammelposten_bis: Decimal | None = Field(
        default=None, description="… bis einschließlich diesen Betrag"
    )
    pflicht: bool = Field(
        default=False, description="Sofortabzug und Sammelposten zwingend (2008/2009)"
    )

    def im_sammelposten_bereich(self, kosten: Decimal) -> bool:
        return (
            self.sammelposten_von is not None
            and self.sammelposten_bis is not None
            and self.sammelposten_von < kosten <= self.sammelposten_bis
        )


class DegressivFenster(_Zeitraum):
    faktor: Decimal = Field(description="Vielfaches des linearen Satzes")
    hoechstsatz: Decimal = Field(description="in Prozent")

    def satz(self, nutzungsdauer: int) -> Decimal:
        """AfA-Satz als Anteil (0,30 = 30 %)."""
        return min(self.faktor / nutzungsdauer, self.hoechstsatz / 100)


class Staffel(_Zeitraum):
    saetze: list[Decimal] = Field(description="Prozent der AK je Jahr")


class AfaTabelleneintrag(BaseModel):
    bezeichnung: str
    nutzungsdauer: int = Field(ge=1)
    fundstelle: str
    konto: dict[str, str] = Field(
        default_factory=dict, description="Kontenrahmen → Anlagekonto"
    )
    afa_art: AfaArt | None = None
    immateriell: bool = False
    kfz: bool = False


class Rechtsstand(BaseModel):
    grenzen: list[Grenzen] = Field(default_factory=list)
    degressiv: list[DegressivFenster] = Field(default_factory=list)
    e_fahrzeug: list[Staffel] = Field(default_factory=list)
    digital: list[_Zeitraum] = Field(default_factory=list)
    rap_verzicht: list[_Zeitraum] = Field(default_factory=list)
    afa_tabelle: dict[str, AfaTabelleneintrag] = Field(default_factory=dict)

    def grenzen_am(self, tag: date) -> Grenzen:
        for g in self.grenzen:
            if g.gilt_am(tag):
                return g
        msg = f"Keine GWG-Grenzen für {tag:%d.%m.%Y} hinterlegt"
        raise RechtsstandError(msg)

    def degressiv_am(self, tag: date) -> DegressivFenster | None:
        return next((f for f in self.degressiv if f.gilt_am(tag)), None)

    def e_fahrzeug_am(self, tag: date) -> Staffel | None:
        return next((s for s in self.e_fahrzeug if s.gilt_am(tag)), None)

    def digital_am(self, tag: date) -> bool:
        return any(z.gilt_am(tag) for z in self.digital)

    def rap_verzicht_moeglich(self, stichtag: date) -> bool:
        """Wirtschaftsjahr endet nach dem Beginn des Wahlrechts (§ 5 Abs. 5 Satz 2)."""
        return any(stichtag > z.von for z in self.rap_verzicht)


def _lies(text: str, name: str) -> dict[str, Any]:
    try:
        daten: Any = yaml.safe_load(text) or {}
    except yaml.YAMLError as fehler:
        raise RechtsstandError(f"{name}: {fehler}") from fehler
    if not isinstance(daten, dict):
        raise RechtsstandError(f"{name}: erwartet wird eine Zuordnung")
    return daten


def _pruefe(daten: dict[str, Any], name: str) -> Rechtsstand:
    try:
        return Rechtsstand.model_validate(daten)
    except ValidationError as fehler:
        teile = [
            f"{'.'.join(str(x) for x in f['loc'])}: {f['msg']}" for f in fehler.errors()
        ]
        raise RechtsstandError(f"{name}: {'; '.join(teile)}") from fehler


def mitgelieferter_rechtsstand() -> Rechtsstand:
    text = (
        resources.files("accounti.anlagen")
        .joinpath("rechtsstand.yaml")
        .read_text(encoding="utf-8")
    )
    return _pruefe(_lies(text, "rechtsstand.yaml"), "rechtsstand.yaml")


def lade_rechtsstand(eigene: str | Path | None = None) -> Rechtsstand:
    """Mitgelieferter Stand, ergänzt um eine eigene Datei (deren Einträge vorgehen)."""
    stand = mitgelieferter_rechtsstand()
    if eigene is None:
        return stand
    pfad = Path(eigene)
    if not pfad.is_file():
        raise RechtsstandError(f"Rechtsstand {pfad} fehlt")
    zusatz = _pruefe(_lies(pfad.read_text(encoding="utf-8"), str(pfad)), str(pfad))
    return Rechtsstand(
        grenzen=[*zusatz.grenzen, *stand.grenzen],
        degressiv=[*zusatz.degressiv, *stand.degressiv],
        e_fahrzeug=[*zusatz.e_fahrzeug, *stand.e_fahrzeug],
        digital=[*zusatz.digital, *stand.digital],
        rap_verzicht=[*zusatz.rap_verzicht, *stand.rap_verzicht],
        afa_tabelle={**stand.afa_tabelle, **zusatz.afa_tabelle},
    )
