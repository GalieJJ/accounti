"""Abschnitt ``llm`` in ``config/accounti.yaml`` — wirkt seit Baustein 10c (P4, D18).

``auto_buchen_schwelle``: ab dieser Confidence bucht ein Vorschlag automatisch (bisher
fest 0,95, ``buchung.mapper.AUTO_SCHWELLE`` ist der Standard), über die
``KlassifikationsEngine`` an ``zu_buchungssatz`` und an das Sachkonto einer
Belegbuchung (``kontiere_beleg``), dazu an ``opos verbuchen`` — eine Schwelle für
jeden Weg, auf dem eine Regel kontiert. ``provider`` und
``model`` bestimmen die LLM-Stufe (``LLMEngine(model="<provider>/<model>")``).
``api_key``: ``${VAR}`` wird nur hier und nachsichtig eingesetzt — fehlt die Variable,
bleibt der Schlüssel leer, und litellm liest ihn wie bisher selbst aus der Umgebung;
die Schwellen bleiben so auch ohne Schlüssel lesbar (``bank lauf --no-llm``,
``verfahrensdoku``). ``pruefung_schwelle`` ist geprüft, wirkt aber noch nicht.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator

from accounti.buchung.mapper import AUTO_SCHWELLE
from accounti.einstellungen.leser import lies_abschnitt
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError, _fehlertext

_VARIABLE = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


class LlmEinstellungen(BaseModel):
    provider: str = Field(default="anthropic", min_length=1)
    model: str = Field(default="claude-sonnet-4-20250514", min_length=1)
    api_key: str | None = None
    auto_buchen_schwelle: float = Field(default=AUTO_SCHWELLE, ge=0, le=1)
    pruefung_schwelle: float = Field(default=0.70, ge=0, le=1)

    @model_validator(mode="after")
    def _schwellen(self) -> LlmEinstellungen:
        if self.pruefung_schwelle > self.auto_buchen_schwelle:
            msg = (
                f"pruefung_schwelle {self.pruefung_schwelle} liegt über "
                f"auto_buchen_schwelle {self.auto_buchen_schwelle}"
            )
            raise ValueError(msg)
        return self

    @property
    def modell(self) -> str:
        """Modell für litellm: ``<provider>/<model>``."""
        return f"{self.provider}/{self.model}"


def _schluessel(wert: object) -> str | None:
    """``${VAR}`` aus der Umgebung — fehlt eine Variable: ``None`` (G-M5)."""
    if not isinstance(wert, str):
        return None if wert is None else str(wert)
    fehlt = False

    def ersetze(treffer: re.Match[str]) -> str:
        nonlocal fehlt
        if treffer[1] not in os.environ:
            fehlt = True
            return ""
        return os.environ[treffer[1]]

    text = _VARIABLE.sub(ersetze, wert)
    return None if fehlt or not text else text


def lade_llm(pfad: str | Path = STANDARD_PFAD) -> LlmEinstellungen:
    """Abschnitt ``llm``; ohne ihn die bisherigen Werte (0,95, Standardmodell)."""
    pfad = Path(pfad)
    werte = lies_abschnitt(pfad, "llm")
    if "api_key" in werte:
        werte["api_key"] = _schluessel(werte["api_key"])
    try:
        return LlmEinstellungen.model_validate(werte)
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'llm': {_fehlertext(fehler, 'llm')}"
        raise KonfigurationError(msg) from fehler
