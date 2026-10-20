"""Freigabe durch einen Menschen — nie automatisch.

Eine Steuererklärung wird abgegeben, nicht ausgelöst. Die Freigabe hält fest, wer welche
Werte wann freigegeben hat, und hängt am Hash genau dieser Werte: Ändert sich danach
eine Buchung im Zeitraum, passt sie nicht mehr. Eine Freigabe trägt genau eine
erfolgreiche Abgabe; Fehler in der Plausibilisierung sperren sie.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from accounti.db.repo_elster import (
    lade_freigaben,
    lade_uebermittlungen,
    speichere_freigabe,
)
from accounti.models.elster import Freigabe, Meldeart, Modus
from accounti.steuer.plausibilitaet import Schweregrad

if TYPE_CHECKING:
    from accounti.elster.ustva import Vorbereitung


class FreigabeError(RuntimeError):
    """Die Freigabe ist so nicht möglich."""


def inhalt(art: Meldeart, zeitraum: str, werte: dict[int, Any]) -> dict[str, Any]:
    return {
        "art": art.value,
        "zeitraum": zeitraum,
        "werte": {str(kz): str(w) for kz, w in sorted(werte.items())},
    }


def inhalt_hash(daten: dict[str, Any]) -> str:
    roh = json.dumps(daten, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(roh.encode()).hexdigest()


def ustva_inhalt(v: Vorbereitung) -> dict[str, Any]:
    return inhalt(Meldeart.USTVA, str(v.zeitraum), v.voranmeldung.formularwerte())


def gib_frei(
    session: Session,
    v: Vorbereitung,
    von: str,
    jetzt: datetime | None = None,
    art: Meldeart = Meldeart.USTVA,
    daten: dict[str, Any] | None = None,
) -> Freigabe:
    """Speichert die Freigabe; Fehler-Befunde sperren sie."""
    if not von.strip():
        raise FreigabeError("Wer gibt frei? Name angeben (--von)")
    if v.gesperrt:
        gruende = "; ".join(b.text for b in v.fehler)
        raise FreigabeError(f"Freigabe gesperrt: {gruende}")
    daten = daten if daten is not None else ustva_inhalt(v)
    gesehen = [
        f"{b.schweregrad.value}: {b.text}"
        for b in v.befunde
        if b.schweregrad is not Schweregrad.FEHLER
    ]
    freigabe = Freigabe(
        zeitpunkt=jetzt or datetime.now(),
        art=art,
        zeitraum=daten["zeitraum"],
        inhalt_hash=inhalt_hash(daten),
        werte=json.dumps(daten["werte"], ensure_ascii=False),
        freigegeben_von=von.strip(),
        hinweise=json.dumps(gesehen, ensure_ascii=False),
    )
    speichere_freigabe(session, freigabe)
    return freigabe


def offene_freigabe(
    session: Session, art: Meldeart, zeitraum: str, daten: dict[str, Any]
) -> Freigabe:
    """Unverbrauchte Freigabe genau dieser Werte — sonst ein klarer Fehler."""
    alle = lade_freigaben(session, art, zeitraum)
    verbraucht = {
        u.freigabe_id
        for u in lade_uebermittlungen(session, art, zeitraum, Modus.ECHT)
        if u.erfolgreich
    }
    soll = inhalt_hash(daten)
    for f in reversed(alle):
        if f.inhalt_hash == soll and f.id not in verbraucht:
            return f
    if any(f.id not in verbraucht for f in alle):
        msg = (
            f"Die Werte für {zeitraum} haben sich seit der Freigabe geändert — "
            "erneut prüfen und freigeben"
        )
    else:
        msg = f"{art.value} {zeitraum} ist nicht freigegeben (accounti ustva freigeben)"
    raise FreigabeError(msg)
