"""Abschlussprotokoll — nur anfügen, jeder Eintrag per Hash an den Vorgänger gekettet.

Die Kette wird bei jeder Abschlussprüfung nachgerechnet (Prüfung ``protokoll``): Eine
Änderung am Datenbestand an accounti vorbei (rohes SQL, unter Postgres ohne Trigger)
fällt so auf.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from accounti.db.repo_abschluss import lade_protokoll, speichere_protokolleintrag
from accounti.models.abschluss import Protokolleintrag

# Spaltenlängen der Tabelle ``abschlussprotokoll`` — gekürzt wird vor dem Hash
VON_LAENGE = 50
GRUND_LAENGE = 500


def hash_von(daten: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(daten, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def protokolliere(
    session: Session,
    jahr: int,
    aktion: str,
    von: str,
    grund: str | None = None,
    details: dict[str, object] | None = None,
) -> Protokolleintrag:
    bisher = lade_protokoll(session)
    e = Protokolleintrag(
        nr=(bisher[-1].nr if bisher else 0) + 1,
        jahr=jahr,
        aktion=aktion,
        von=von[:VON_LAENGE],
        grund=grund[:GRUND_LAENGE] if grund is not None else None,
        details=json.dumps(
            details or {}, sort_keys=True, ensure_ascii=False, default=str
        ),
        vorgaenger_hash=bisher[-1].hash if bisher else "",
    )
    e = e.model_copy(update={"hash": hash_von(e.model_dump(exclude={"hash"}))})
    speichere_protokolleintrag(session, e)
    return e


def pruefe_protokoll(session: Session) -> list[str]:
    """Lücken, geänderte oder umsortierte Einträge im Abschlussprotokoll."""
    fehler = []
    vorgaenger = ""
    for erwartet, e in enumerate(lade_protokoll(session), start=1):
        if e.nr != erwartet:
            fehler.append(f"Eintrag {erwartet} fehlt (gefunden: {e.nr})")
        if e.vorgaenger_hash != vorgaenger:
            fehler.append(f"Eintrag {e.nr}: Verkettung unterbrochen")
        if hash_von(e.model_dump(exclude={"hash"})) != e.hash:
            fehler.append(f"Eintrag {e.nr} wurde verändert")
        vorgaenger = e.hash
    return fehler
