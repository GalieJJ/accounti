"""Lädt Kontierungsregeln aus der Regeldatei der Gesellschaft (``config/regeln.yaml``).

accounti schreibt die Datei nicht (mehr): gelernte Regeln liegen in der Datenbank
(``klassifikation.lernen``), die Datei pflegt der Betreiber. Optionales Feld
``richtung`` (``ausgabe``/``einnahme``) beschränkt eine Regel auf eine Zahlungsrichtung.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from accounti.klassifikation.engine import Regel


def lade_regeln(pfad: str | Path) -> list[Regel]:
    pfad = Path(pfad)
    if not pfad.exists():
        return []
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or []
    regeln: list[Regel] = []
    for eintrag in daten:
        regeln.append(
            Regel(
                name=eintrag["name"],
                muster=eintrag["muster"],
                soll_konto=str(eintrag["soll_konto"]),
                haben_konto=str(eintrag["haben_konto"]),
                steuer_schluessel=eintrag.get("steuer_schluessel"),
                buchungstext=eintrag.get("buchungstext"),
                feld=eintrag.get("feld", "verwendungszweck"),
                # optional: nur Ausgaben (negativ) bzw. Einnahmen (Baustein 10b)
                richtung=eintrag.get("richtung"),
            )
        )
    return regeln
