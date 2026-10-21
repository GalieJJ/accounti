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

Die Trennung prüft die Registry nach dem Ersetzen und auf normalisierten Werten
(``archiv/a`` = ``./archiv/a``, ``postgresql+psycopg://x@DB/acc`` =
``postgresql://y@db:5432/acc``): keine zwei Gesellschaften teilen Datenbank, Archiv,
Konfiguration oder Regeldatei. Ohne ``konfiguration`` gilt die globale Datei — das
darf höchstens eine Gesellschaft.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import make_url
from sqlalchemy.exc import ArgumentError

from accounti.erechnung.versand import _ersetze_variablen
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError
from accounti.models.auth import pruefe_gesellschaft

_STANDARD_PORTS = {"postgresql": 5432, "mysql": 3306, "mariadb": 3306}


def datenbank_schluessel(url: str) -> str:
    """Vergleichswert einer Datenbank-URL: ohne Treiber, Benutzer und Passwort;
    SQLite mit aufgelöstem Pfad, sonst Rechner (klein) und Port."""
    try:
        u = make_url(url.strip())
    except ArgumentError:
        return url.strip()
    art = u.get_backend_name()
    if art == "sqlite":
        pfad = u.database or ""
        if pfad and pfad != ":memory:" and not pfad.startswith("file:"):
            pfad = str(Path(pfad).expanduser().resolve())
        return f"sqlite:///{pfad}"
    rechner = (u.host or "").lower()
    port = u.port or _STANDARD_PORTS.get(art)
    return f"{art}://{rechner}:{port}/{u.database or ''}"


def pfad_schluessel(pfad: str | Path) -> str:
    return str(Path(pfad).expanduser().resolve())


def gleiche_datenbank(a: str, b: str) -> bool:
    return datenbank_schluessel(a) == datenbank_schluessel(b)


def gleicher_pfad(a: str | Path, b: str | Path) -> bool:
    return pfad_schluessel(a) == pfad_schluessel(b)


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
        self._pruefe_trennung()
        return self

    def _vergleichswerte(self) -> dict[str, dict[str, str]]:
        """Je Gesellschaft die normalisierten Werte nach dem Ersetzen — eine
        Gesellschaft mit fehlender Variable bleibt außen vor (sie scheitert erst,
        wenn sie gebraucht wird)."""
        werte: dict[str, dict[str, str]] = {}
        for kuerzel, e in self.eintraege.items():
            try:
                roh: dict[str, Any] = _ersetze_variablen(e.model_dump())
            except KonfigurationError:
                continue
            konfiguration = roh["konfiguration"] or self.quelle
            regeln = roh["regeln"] or str(Path(konfiguration).parent / "regeln.yaml")
            werte[kuerzel] = {
                "datenbank": datenbank_schluessel(roh["datenbank"]),
                "archiv": pfad_schluessel(roh["archiv"]),
                "konfiguration": pfad_schluessel(konfiguration),
                "regeln": pfad_schluessel(regeln),
            }
        return werte

    def _pruefe_trennung(self) -> None:
        werte = self._vergleichswerte()
        for feld, wort, hinweis in (
            ("datenbank", "dieselbe Datenbank", ""),
            ("archiv", "dasselbe Archiv", ""),
            (
                "konfiguration",
                "dieselbe Konfiguration",
                " — je Gesellschaft eine eigene Datei unter konfiguration: "
                "(höchstens eine darf die globale nutzen)",
            ),
            (
                "regeln",
                "dieselbe Regeldatei",
                " — regeln: je Gesellschaft angeben (sonst regeln.yaml neben der "
                "Konfiguration)",
            ),
        ):
            gesehen: dict[str, str] = {}
            for kuerzel in self.eintraege:
                if kuerzel not in werte:
                    continue
                wert = werte[kuerzel][feld]
                if wert in gesehen:
                    msg = f"{gesehen[wert]} und {kuerzel} nutzen {wort}{hinweis}"
                    raise ValueError(msg)
                gesehen[wert] = kuerzel

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


def lies_yaml(pfad: Path) -> Any:
    """YAML-Datei lesen — ein Syntaxfehler wird zum ``KonfigurationError``."""
    try:
        return yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as fehler:
        stelle = getattr(fehler, "problem_mark", None)
        wo = f", Zeile {stelle.line + 1}" if stelle is not None else ""
        msg = f"{pfad}: kein gültiges YAML{wo}"
        raise KonfigurationError(msg) from fehler


def lade_gesellschaften(pfad: str | Path = STANDARD_PFAD) -> Gesellschaften:
    """Abschnitt ``gesellschaften``; ohne ihn gibt es keine Einträge."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return Gesellschaften(quelle=str(pfad))
    daten: Any = lies_yaml(pfad)
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
