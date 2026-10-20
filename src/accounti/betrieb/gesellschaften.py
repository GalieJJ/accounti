"""Registry der eigenen Gesellschaften — Abschnitt ``gesellschaften``.

Jede Gesellschaft hat ihre **eigene Datenbank, ihr eigenes Belegarchiv und ihre
eigene Konfiguration** (Kontenrahmen, Wirtschaftsjahr, Firmendaten …). Nummernkreise,
Bankkonten, Buchungen und Abschlüsse liegen in ihrer Datenbank und sind damit
getrennt, ohne dass eine Tabelle eine Spalte ``gesellschaft`` braucht. Benutzer,
Rollen, Sitzungen und API-Token liegen in der **Systemdatenbank**.

```yaml
gesellschaften:
  systemdatenbank: "${ACCOUNTI_SYSTEM_DB}"   # Pflicht ab zwei Gesellschaften
  standard: muster                            # ohne --gesellschaft
  eintraege:
    muster:
      name: Muster GmbH
      datenbank: "${ACCOUNTI_DB_MUSTER}"
      archiv: /daten/muster/belege
      konfiguration: /konfiguration/muster.yaml   # sonst diese Datei
      regeln: /konfiguration/muster-regeln.yaml   # sonst regeln.yaml daneben
```

``${VARIABLE}`` wird erst ersetzt, wenn eine Gesellschaft gebraucht wird — eine
fehlende Variable betrifft nur sie. Gemeint sind ausdrücklich **eigene**
Gesellschaften, kein Mandantenportal (Bauplan, Nicht-Ziele).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from accounti.erechnung.versand import _ersetze_variablen
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError
from accounti.models.auth import pruefe_gesellschaft


class Eintrag(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    datenbank: str = Field(min_length=1)
    archiv: str = Field(min_length=1)
    konfiguration: str | None = None
    regeln: str | None = None


@dataclass(frozen=True)
class Gesellschaft:
    """Eine Gesellschaft mit aufgelösten Pfaden und Adressen."""

    kuerzel: str
    name: str
    datenbank: str
    archiv: str
    konfiguration: str
    regeln: str


class Gesellschaften(BaseModel):
    systemdatenbank: str | None = None
    standard: str | None = None
    eintraege: dict[str, Eintrag] = Field(default_factory=dict)
    quelle: str = Field(default=str(STANDARD_PFAD), exclude=True)

    @field_validator("eintraege")
    @classmethod
    def _kuerzel(cls, wert: dict[str, Eintrag]) -> dict[str, Eintrag]:
        for kuerzel in wert:
            pruefe_gesellschaft(kuerzel)
        return wert

    @model_validator(mode="after")
    def _stimmig(self) -> Gesellschaften:
        if len(self.eintraege) == 1 and self.standard is None:
            self.standard = next(iter(self.eintraege))
        if self.standard is not None and self.standard not in self.eintraege:
            msg = f"standard {self.standard!r} steht nicht unter eintraege"
            raise ValueError(msg)
        if len(self.eintraege) > 1 and not self.systemdatenbank:
            msg = (
                "systemdatenbank fehlt — bei mehreren Gesellschaften liegen Benutzer "
                "und Token in einer eigenen Datenbank"
            )
            raise ValueError(msg)
        for feld, wort in (
            ("datenbank", "dieselbe Datenbank"),
            ("archiv", "dasselbe Archiv"),
        ):
            gesehen: dict[str, str] = {}
            for kuerzel, e in self.eintraege.items():
                wert = getattr(e, feld)
                if wert in gesehen:
                    msg = f"{gesehen[wert]} und {kuerzel} nutzen {wort}"
                    raise ValueError(msg)
                gesehen[wert] = kuerzel
        return self

    @property
    def mehrere(self) -> bool:
        return len(self.eintraege) > 1

    def finde(self, kuerzel: str) -> Gesellschaft:
        eintrag = self.eintraege.get(kuerzel)
        if eintrag is None:
            bekannt = ", ".join(sorted(self.eintraege)) or "keine"
            msg = f"Gesellschaft {kuerzel!r} gibt es nicht (eingetragen: {bekannt})"
            raise KonfigurationError(msg)
        try:
            werte: dict[str, Any] = _ersetze_variablen(eintrag.model_dump())
        except KonfigurationError as fehler:
            msg = f"Gesellschaft {kuerzel}: {fehler}"
            raise KonfigurationError(msg) from fehler
        konfiguration = werte["konfiguration"] or self.quelle
        regeln = werte["regeln"] or str(Path(konfiguration).parent / "regeln.yaml")
        return Gesellschaft(
            kuerzel=kuerzel,
            name=werte["name"],
            datenbank=werte["datenbank"],
            archiv=werte["archiv"],
            konfiguration=konfiguration,
            regeln=regeln,
        )

    def alle(self) -> list[Gesellschaft]:
        return [self.finde(k) for k in sorted(self.eintraege)]

    def system(self) -> str | None:
        """Adresse der Systemdatenbank (ohne Eintrag: die der einzigen Gesellschaft)."""
        if self.systemdatenbank:
            wert: str = _ersetze_variablen(self.systemdatenbank)
            return wert
        if self.standard is not None:
            return self.finde(self.standard).datenbank
        return None


def _fehlertext(fehler: ValidationError) -> str:
    teile = []
    for f in fehler.errors():
        pfad = ".".join(str(x) for x in f["loc"])
        grund = str(f["msg"]).removeprefix("Value error, ")
        teile.append(f"{pfad}: {grund}" if pfad else grund)
    return "; ".join(teile)


def lade_gesellschaften(pfad: str | Path = STANDARD_PFAD) -> Gesellschaften:
    """Abschnitt ``gesellschaften``; ohne ihn gibt es keine Einträge."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return Gesellschaften(quelle=str(pfad))
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    abschnitt = daten.get("gesellschaften") if isinstance(daten, dict) else None
    if abschnitt is None:
        return Gesellschaften(quelle=str(pfad))
    if not isinstance(abschnitt, dict):
        msg = f"{pfad}: Abschnitt 'gesellschaften' muss eine Zuordnung sein"
        raise KonfigurationError(msg)
    try:
        return Gesellschaften.model_validate({**abschnitt, "quelle": str(pfad)})
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'gesellschaften': {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler
