"""Abschnitt ``pruefung`` in ``config/accounti.yaml`` — optional, mit Standardwerten.

Schwellen gehören in die Konfiguration, nicht in den Code (Spec 4.1)::

    pruefung:
      abgeschaltet: [op_alter]            # Regeln, die nicht laufen
      schwere: {dublette: fehler}         # Schweregrad je Regel überschreiben
      regeln:                             # Schwellen je Regel (nur Abweichungen)
        umsatz_ohne_beleg: {ab_betrag: 5.00, nach_tagen: 3}
        beleg_unbearbeitet: {frist_tage: 10}
      belegfrei:                          # Umsätze ohne Beleg — begründet
        - {name: kontofuehrung, muster: "kontoführung|kontoentgelt",
           feld: verwendungszweck, begruendung: "Bankentgelt — der Auszug ist Beleg"}
      kleinbetrag_grenze: 250.00          # § 33 UStDV
      eigene_namen: ["Galerie Muster"]    # weitere Namen der Gesellschaft (Adressat)

Ob die Regeln unter ``regeln``, ``schwere`` und ``abgeschaltet`` existieren und ihre
Schwellen passen, prüft der Lauf gegen die Registry (eigene Regeln kommen dazu).
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from accounti.konfiguration import STANDARD_PFAD, KonfigurationError
from accounti.models.pruefung import Schwere

# § 33 UStDV: Kleinbetragsrechnung bis 250 Euro (seit 01.01.2017)
KLEINBETRAG = Decimal("250.00")

STANDARD_BETREFF = "Beleg zu unserer Zahlung vom {datum} über {betrag} €"
STANDARD_TEXT = """Sehr geehrte Damen und Herren,

zu folgender Zahlung fehlt uns die Rechnung bzw. der Beleg:

  Datum:            {datum}
  Betrag:           {betrag} €
  Verwendungszweck: {verwendungszweck}

Bitte senden Sie uns den Beleg als E-Rechnung oder PDF an {antwort}.

Vielen Dank und freundliche Grüße
{firma}
"""


class BelegfreiRegel(BaseModel):
    """Umsätze, die keinen eigenen Beleg brauchen — mit Begründung (GoBD Rz. 61 ff.)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    muster: str = Field(description="regulärer Ausdruck, Groß/klein egal")
    feld: Literal["verwendungszweck", "gegenpartei", "beide"] = "beide"
    begruendung: str = Field(min_length=3)

    @field_validator("muster")
    @classmethod
    def _muster(cls, wert: str) -> str:
        try:
            re.compile(wert)
        except re.error as fehler:
            msg = f"Muster {wert!r} ist kein gültiger regulärer Ausdruck: {fehler}"
            raise ValueError(msg) from fehler
        return wert

    def passt(self, verwendungszweck: str, gegenpartei: str | None) -> bool:
        felder = {
            "verwendungszweck": [verwendungszweck],
            "gegenpartei": [gegenpartei or ""],
            "beide": [verwendungszweck, gegenpartei or ""],
        }[self.feld]
        return any(re.search(self.muster, f, re.IGNORECASE) for f in felder)


class NachforderungEinstellungen(BaseModel):
    """Vorlage für die Anfrage beim Lieferanten — verschickt wird nur auf Befehl."""

    model_config = ConfigDict(extra="forbid")

    betreff: str = STANDARD_BETREFF
    text: str = STANDARD_TEXT
    antwort_an: str | None = Field(
        default=None, description="Adresse für den Beleg (sonst versand.absender)"
    )


class PruefEinstellungen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    abgeschaltet: list[str] = Field(default_factory=list)
    schwere: dict[str, Schwere] = Field(default_factory=dict)
    regeln: dict[str, dict[str, Any]] = Field(default_factory=dict)
    belegfrei: list[BelegfreiRegel] = Field(default_factory=list)
    kleinbetrag_grenze: Decimal = Field(default=KLEINBETRAG, ge=0)
    eigene_namen: list[str] = Field(default_factory=list)
    kontenrahmen_datei: str | None = Field(
        default=None,
        description="Steuerautomatik der Konten (SKR03: mitgelieferte skr03.yaml)",
    )
    archiv: str = Field(default="archiv/belege", description="Belegarchiv")
    nachforderung: NachforderungEinstellungen = Field(
        default_factory=NachforderungEinstellungen
    )

    def belegfrei_nach_regel(
        self, verwendungszweck: str, gegenpartei: str | None
    ) -> BelegfreiRegel | None:
        return next(
            (r for r in self.belegfrei if r.passt(verwendungszweck, gegenpartei)), None
        )


def _fehlertext(fehler: ValidationError) -> str:
    teile = []
    for f in fehler.errors():
        pfad = ".".join(str(x) for x in f["loc"])
        grund = str(f["msg"]).removeprefix("Value error, ")
        teile.append(f"{pfad}: {grund}" if pfad else grund)
    return "; ".join(teile)


def lade_pruefung(pfad: str | Path = STANDARD_PFAD) -> PruefEinstellungen:
    """Abschnitt ``pruefung``; ohne Datei oder Abschnitt gelten die Standards."""
    pfad = Path(pfad)
    abschnitt: Any = None
    if pfad.is_file():
        daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
        abschnitt = daten.get("pruefung") if isinstance(daten, dict) else None
    if abschnitt is not None and not isinstance(abschnitt, dict):
        raise KonfigurationError(f"{pfad}: Abschnitt 'pruefung' ist keine Zuordnung")
    try:
        return PruefEinstellungen.model_validate(abschnitt or {})
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'pruefung': {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler
