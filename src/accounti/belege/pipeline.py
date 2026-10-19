"""Beleg-Pipeline: Rohbeleg → Archiv → Erkennung → Dubletten → Beleg + Eingang."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePath

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv, aufbewahrungsende
from accounti.belege.dubletten import pruefe_dublette
from accounti.belege.kanaele import RohBeleg
from accounti.db.repository import (
    aktualisiere_beleg,
    lade_belege,
    speichere_beleg,
    speichere_eingang,
)
from accounti.models import Beleg, BelegEingang, BelegStatus, Eingangsergebnis

# Erkenner reichert einen Beleg aus der Rohdatei an (Belegart, Beträge, Positionen …).
Erkenner = Callable[[RohBeleg, Beleg], Beleg]


def _erkenne_sicher(
    erkenner: Erkenner, roh: RohBeleg, beleg: Beleg
) -> tuple[Beleg, bool]:
    """Ruft den Erkenner auf; ein Fehler schickt den Beleg in die Prüfung."""
    try:
        return erkenner(roh, beleg), True
    except Exception as fehler:  # jeder Fehler wird zur Prüfung, kein Abbruch
        return (
            beleg.model_copy(
                update={
                    "status": BelegStatus.ZUR_PRUEFUNG,
                    "pruef_grund": f"Erkennung fehlgeschlagen: {fehler}",
                }
            ),
            False,
        )


def nimm_auf(
    session: Session,
    archiv: BelegArchiv,
    roh: RohBeleg,
    erkenner: Erkenner | None = None,
) -> BelegEingang:
    """Nimmt einen Rohbeleg auf und protokolliert den Eingang.

    Die Originaldatei wird immer zuerst archiviert. Fehler im Erkenner brechen die
    Pipeline nicht ab: Der Beleg geht dann mit Begründung in die Prüfung.
    """
    datei_hash = archiv.ablegen(roh.inhalt, PurePath(roh.dateiname).suffix)
    beleg = Beleg(
        datei_hash=datei_hash,
        dateiname=roh.dateiname,
        kanal=roh.kanal,
        herkunft=roh.herkunft,
        eingegangen_am=roh.eingegangen_am,
        aufbewahren_bis=aufbewahrungsende(roh.eingegangen_am.date()),
    )
    bestand = lade_belege(session)

    # Stufe 1 vor der Erkennung: eine identische Datei muss niemand erneut lesen.
    befund = pruefe_dublette(beleg, bestand)
    if befund.ergebnis is Eingangsergebnis.NEU and erkenner is not None:
        beleg, gelesen = _erkenne_sicher(erkenner, roh, beleg)
        if gelesen:
            befund = pruefe_dublette(beleg, bestand)

    if befund.ergebnis is Eingangsergebnis.DUBLETTE:
        beleg_id = befund.beleg_id
    else:
        if befund.ergebnis is Eingangsergebnis.VERDACHT:
            beleg = beleg.model_copy(
                update={
                    "status": BelegStatus.ZUR_PRUEFUNG,
                    "pruef_grund": (
                        f"Dublettenverdacht zu Beleg {str(befund.beleg_id)[:8]}: "
                        f"{befund.grund}"
                    ),
                }
            )
        speichere_beleg(session, beleg)
        beleg_id = beleg.id

    eingang = BelegEingang(
        kanal=roh.kanal,
        dateiname=roh.dateiname,
        herkunft=roh.herkunft,
        datei_hash=datei_hash,
        eingegangen_am=roh.eingegangen_am,
        ergebnis=befund.ergebnis,
        beleg_id=beleg_id,
        hinweis=befund.grund or None,
    )
    speichere_eingang(session, eingang)
    return eingang


def erkenne_erneut(
    session: Session,
    archiv: BelegArchiv,
    beleg: Beleg,
    erkenner: Erkenner,
) -> Beleg:
    """Liest einen archivierten Beleg erneut — z.B. nachdem OCR installiert wurde."""
    roh = RohBeleg(
        dateiname=beleg.dateiname,
        inhalt=archiv.lese(beleg.datei_hash),
        kanal=beleg.kanal,
        herkunft=beleg.herkunft,
        eingegangen_am=beleg.eingegangen_am,
    )
    neu, gelesen = _erkenne_sicher(erkenner, roh, beleg)
    if gelesen:
        befund = pruefe_dublette(neu, lade_belege(session))
        if befund.ergebnis is not Eingangsergebnis.NEU:
            art = (
                "Dublette"
                if befund.ergebnis is Eingangsergebnis.DUBLETTE
                else "Dublettenverdacht"
            )
            neu = neu.model_copy(
                update={
                    "status": BelegStatus.ZUR_PRUEFUNG,
                    "pruef_grund": (
                        f"{art} zu Beleg {str(befund.beleg_id)[:8]}: {befund.grund}"
                    ),
                }
            )
    return aktualisiere_beleg(session, neu)
