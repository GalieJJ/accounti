"""Lädt Kontierungsregeln aus config/regeln.yaml.

Felder je Regel: ``name``, ``muster``, ``soll_konto``, ``haben_konto``, optional
``steuer_schluessel``, ``buchungstext``, ``feld`` (verwendungszweck,
gegenkonto_name, beide), ``richtung`` (ausgabe, einnahme, beide), ``pruefen``
(Treffer immer zur Prüfung) und ``confidence`` (0–1, Standard 1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from accounti.klassifikation.engine import Regel
from accounti.konfiguration import KonfigurationError


def _regel(eintrag: Any, pfad: Path) -> Regel:
    if not isinstance(eintrag, dict):
        raise KonfigurationError(f"{pfad}: Regel {eintrag!r} ist keine Zuordnung")
    name = eintrag.get("name", "?")
    try:
        pruefen = eintrag.get("pruefen", False)
        if not isinstance(pruefen, bool):
            raise ValueError(f"Regel {name}: pruefen {pruefen!r} — true oder false")
        return Regel(
            name=eintrag["name"],
            muster=eintrag["muster"],
            soll_konto=str(eintrag["soll_konto"]),
            haben_konto=str(eintrag["haben_konto"]),
            steuer_schluessel=eintrag.get("steuer_schluessel"),
            buchungstext=eintrag.get("buchungstext"),
            feld=eintrag.get("feld", "verwendungszweck"),
            richtung=eintrag.get("richtung"),
            pruefen=pruefen,
            confidence=float(eintrag.get("confidence", 1.0)),
        )
    except KeyError as fehler:
        msg = f"{pfad}: Regel {name}: Feld {fehler.args[0]} fehlt"
        raise KonfigurationError(msg) from fehler
    except (TypeError, ValueError) as fehler:
        raise KonfigurationError(f"{pfad}: {fehler}") from fehler


def lade_regeln(pfad: str | Path) -> list[Regel]:
    pfad = Path(pfad)
    if not pfad.exists():
        return []
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or []
    return [_regel(eintrag, pfad) for eintrag in daten]
