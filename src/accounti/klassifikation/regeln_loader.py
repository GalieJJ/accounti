"""Lädt Kontierungsregeln aus der Regeldatei der Gesellschaft (``config/regeln.yaml``).

accounti schreibt die Datei nicht (mehr): gelernte Regeln liegen in der Datenbank
(``klassifikation.lernen``) und haben Vorrang, die Datei pflegt der Betreiber.

Felder je Regel: ``name``, ``muster``, ``soll_konto``, ``haben_konto``, optional
``steuer_schluessel``, ``buchungstext``, ``feld`` (verwendungszweck,
gegenkonto_name, beide), ``richtung`` (ausgabe, einnahme, beide), ``pruefen``
(Treffer immer zur Prüfung) und ``confidence`` (0–1, Standard 1).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from accounti.klassifikation.engine import Regel
from accounti.konfiguration import KonfigurationError

FELDER = ("verwendungszweck", "gegenkonto_name", "beide")


def _regel(eintrag: Any, pfad: Path) -> Regel:
    if not isinstance(eintrag, dict):
        raise KonfigurationError(f"{pfad}: Regel {eintrag!r} ist keine Zuordnung")
    name = eintrag.get("name", "?")
    try:
        pruefen = eintrag.get("pruefen", False)
        if not isinstance(pruefen, bool):
            raise ValueError(f"Regel {name}: pruefen {pruefen!r} — true oder false")
        feld = eintrag.get("feld", "verwendungszweck")
        if feld not in FELDER:
            raise ValueError(f"Regel {name}: feld {feld!r} — {', '.join(FELDER)}")
        return Regel(
            name=eintrag["name"],
            muster=eintrag["muster"],
            soll_konto=str(eintrag["soll_konto"]),
            haben_konto=str(eintrag["haben_konto"]),
            steuer_schluessel=eintrag.get("steuer_schluessel"),
            buchungstext=eintrag.get("buchungstext"),
            feld=feld,
            richtung=eintrag.get("richtung"),
            pruefen=pruefen,
            confidence=float(eintrag.get("confidence", 1.0)),
        )
    except KeyError as fehler:
        msg = f"{pfad}: Regel {name}: Feld {fehler.args[0]} fehlt"
        raise KonfigurationError(msg) from fehler
    except re.error as fehler:
        msg = (
            f"{pfad}: Regel {name}: Muster ist kein gültiger regulärer Ausdruck: "
            f"{fehler}"
        )
        raise KonfigurationError(msg) from fehler
    except (TypeError, ValueError) as fehler:
        raise KonfigurationError(f"{pfad}: {fehler}") from fehler


def lade_regeln(pfad: str | Path) -> list[Regel]:
    """Regeln der Datei (keine Datei: keine Regeln). Eine fehlerhafte Datei — kein
    YAML, keine Liste, ein Muster, das kein regulärer Ausdruck ist, ein unbekanntes
    ``feld`` — meldet ``KonfigurationError`` mit Datei und Regelname: CLI und
    Oberfläche zeigen dann eine Meldung statt eines Tracebacks bzw. 500
    (Gesamttest 10b-1 nach dem Merge, gw-regeln N-2)."""
    pfad = Path(pfad)
    if not pfad.exists():
        return []
    try:
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or []
    except yaml.YAMLError as fehler:
        raise KonfigurationError(f"{pfad}: kein gültiges YAML — {fehler}") from fehler
    if not isinstance(daten, list):
        msg = f"{pfad}: keine Liste von Regeln (- name: …, muster: …)"
        raise KonfigurationError(msg)
    return [_regel(eintrag, pfad) for eintrag in daten]
