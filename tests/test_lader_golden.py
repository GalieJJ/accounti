"""Golden-Test der Lader (Plan 10c P4, D20): Die Lader liefern nach dem Umbau auf den
Abschnittsleser dieselben Modelle wie vor Baustein 10c.

Die Golden-Daten stammen aus dem Code vor P4 (``tests/werkzeuge/golden_lader.py``).
Der Test „leer“ bleibt danach Wächter über alle Standards (D6): Ändert sich ein
Standard, steht das im CHANGELOG unter „Geändert“ mit altem und neuem Wert.

Erlaubte Unterschiede (``ERLAUBT``):
- neue Felder mit ihrem Standard (``NEUE_FELDER``: je Lader Punktpfad → Standard),
- ``wirtschaftsjahr_beginn`` nur nach Monat und Tag (Schritt 5 liest „MM-TT“),
- umbenannte Rohfelder (D14) über ihren Alias — ``serialisiere`` schreibt
  ``by_alias=True``, der Dateiname bleibt also der Schlüssel,
- eine Fehlermeldung darf ergänzt werden (gleiche Klasse, alter Text enthalten).
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from accounti.konfiguration import KonfigurationError
from tests.werkzeuge.golden_lader import (
    GOLDEN_LADER,
    KONFIGURATIONEN,
    feste_umgebung,
    golden_datei,
    lauf,
    roh,
    serialisiere,
)

# Punktpfade je Lader, die nach 10c neu sind, mit ihrem Standard
NEUE_FELDER: dict[str, dict[str, Any]] = {}
ERLAUBT = {
    "neue_felder": NEUE_FELDER,
    "nur_monat_und_tag": ("wirtschaftsjahr_beginn",),
}
_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _golden(konfig: str) -> dict[str, Any]:
    daten: dict[str, Any] = json.loads(golden_datei(konfig).read_text(encoding="utf-8"))
    return daten


def _monat_tag(wert: Any) -> Any:
    if isinstance(wert, str) and _DATUM.match(wert):
        return wert[5:]
    return wert


def unterschiede(lader: str, alt: Any, neu: Any, pfad: str = "") -> list[str]:
    """Abweichungen von ``neu`` gegenüber ``alt`` nach ``ERLAUBT``."""
    letzter = pfad.rsplit(".", 1)[-1]
    if letzter in ERLAUBT["nur_monat_und_tag"] or (
        not pfad and lader == "lade_wirtschaftsjahr_beginn"
    ):
        alt, neu = _monat_tag(alt), _monat_tag(neu)
    if isinstance(alt, dict) and isinstance(neu, dict):
        if set(alt) == {"fehler", "text"} and set(neu) == {"fehler", "text"}:
            if alt["fehler"] == neu["fehler"] and str(alt["text"]) in str(neu["text"]):
                return []
            return [f"{pfad or '(Ergebnis)'}: {alt!r} → {neu!r}"]
        funde: list[str] = []
        for schluessel in alt:
            unter = f"{pfad}.{schluessel}" if pfad else schluessel
            if schluessel not in neu:
                funde.append(f"{unter}: fehlt")
                continue
            funde += unterschiede(lader, alt[schluessel], neu[schluessel], unter)
        for schluessel in sorted(set(neu) - set(alt)):
            unter = f"{pfad}.{schluessel}" if pfad else schluessel
            neue = NEUE_FELDER.get(lader, {})
            if unter not in neue:
                funde.append(f"{unter}: neues Feld ohne Eintrag in NEUE_FELDER")
            elif neu[schluessel] != neue[unter]:
                funde.append(
                    f"{unter}: neu {neu[schluessel]!r}, Standard {neue[unter]!r}"
                )
        return funde
    if alt != neu:
        return [f"{pfad or '(Ergebnis)'}: {alt!r} → {neu!r}"]
    return []


FAELLE = [(k, lader) for k in KONFIGURATIONEN for lader in sorted(GOLDEN_LADER)]


@pytest.mark.parametrize(
    ("konfig", "lader"), FAELLE, ids=[f"{k}-{x}" for k, x in FAELLE]
)
def test_lader_wie_vor_10c(konfig, lader):
    golden = _golden(konfig)
    assert lader in golden, f"{lader} fehlt in {golden_datei(konfig).name}"
    with feste_umgebung():
        neu = lauf(lader, KONFIGURATIONEN[konfig])
    assert unterschiede(lader, golden[lader], neu) == []


def test_golden_daten_ohne_fremde_lader():
    """Jeder Eintrag der Golden-Daten gehört zu einem Lader aus ``GOLDEN_LADER`` — ein
    entfernter Lader fällt auf, statt still nicht mehr geprüft zu werden."""
    for konfig in KONFIGURATIONEN:
        assert set(_golden(konfig)) == set(GOLDEN_LADER), konfig


def test_serialisierer_kennt_jeden_rueckgabetyp():
    """Jedes Ergebnis jedes Laders auf jeder Konfiguration lässt sich serialisieren
    (Modelle, bool, dict, ``Partnerdaten``, Datum, Fehler) — ein unbekannter Typ ist
    ein Fehler, kein stilles ``str()``."""
    typen: set[str] = set()
    with feste_umgebung():
        for pfad in KONFIGURATIONEN.values():
            for lader in GOLDEN_LADER:
                ergebnis = roh(lader, pfad)
                serialisiere(ergebnis)  # wirft bei einem unbekannten Typ
                typen.add(type(ergebnis).__name__)
    assert {"bool", "dict", "Partnerdaten", "date", "KonfigurationError"} <= typen

    class Modell(BaseModel):
        wann: date
        betrag: Decimal

    assert serialisiere(Modell(wann=date(2026, 7, 1), betrag=Decimal("1.50"))) == {
        "wann": "2026-07-01",
        "betrag": "1.50",
    }
    assert serialisiere(KonfigurationError("x: kaputt")) == {
        "fehler": "KonfigurationError",
        "text": "x: kaputt",
    }
    assert serialisiere((1, {2})) == [1, [2]]
    with pytest.raises(TypeError, match="kein Golden-Wert"):
        serialisiere(object())


def test_vergleich_erlaubt_nur_die_genannten_unterschiede():
    assert unterschiede("x", {"a": 1}, {"a": 1, "b": 2}) == [
        "b: neues Feld ohne Eintrag in NEUE_FELDER"
    ]
    assert unterschiede("x", {"a": 1}, {"a": 2}) == ["a: 1 → 2"]
    assert unterschiede("x", {"a": 1}, {}) == ["a: fehlt"]
    alt = {"wirtschaftsjahr_beginn": "2025-07-01"}
    assert unterschiede("x", alt, {"wirtschaftsjahr_beginn": "2000-07-01"}) == []
    assert unterschiede("lade_wirtschaftsjahr_beginn", "2025-07-01", "2000-07-01") == []
    assert unterschiede("x", "2025-07-01", "2000-07-01") != []
    fehler = {"fehler": "KonfigurationError", "text": "<pfad>: mandant fehlt"}
    ergaenzt = {**fehler, "text": "<pfad>: mandant fehlt (Einstellungen › Firma)"}
    assert unterschiede("x", fehler, ergaenzt) == []
    assert unterschiede("x", fehler, {**fehler, "fehler": "ValueError"}) != []


def test_golden_daten_ohne_pfade():
    """Die Golden-Daten hängen nicht am Ort des Repos."""
    wurzel = str(Path(__file__).resolve().parents[1])
    for konfig in KONFIGURATIONEN:
        assert wurzel not in golden_datei(konfig).read_text(encoding="utf-8"), konfig
