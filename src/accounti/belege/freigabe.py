"""Belege freigeben — der Weg aus „zur Prüfung“ (und zum Berichtigen der Belegart).

Was die Erkennung nicht sicher lesen konnte, geht zur Prüfung. Der Mensch sieht das
Original an und gibt den Beleg frei — gegebenenfalls mit der richtigen Belegart und
dem Steuerfall einer Rechnung ohne Steuerausweis (§ 13b, ig. Lieferung, steuerfrei bzw.
Kleinunternehmer). Danach verbucht ``accounti opos verbuchen`` ihn wie jeden erfassten
Beleg. Die Änderung steht mit Person und Grund im Journal (``beleg_freigegeben``).

Verbuchte Belege ändert die Freigabe nicht mehr — dort gilt Storno statt Änderung.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.db.repository import (
    aktualisiere_beleg,
    lade_belege,
    verbuchte_beleg_ids,
)
from accounti.models import Beleg, Belegart, Belegrichtung, BelegStatus

# --steuer → Steuerkennzeichen (UNTDID 5305); „ohne“ hebt es auf
STEUERFAELLE: dict[str, str | None] = {
    "13b": "AE",
    "ig-erwerb": "K",
    "steuerfrei": "E",
    "ohne": None,
}
_RECHNUNGEN = frozenset({Belegart.EINGANGSRECHNUNG, Belegart.AUSGANGSRECHNUNG})


class FreigabeError(ValueError):
    """Der Beleg lässt sich so nicht freigeben."""


def finde_beleg(session: Session, praefix: str) -> Beleg:
    """Beleg über den Anfang seiner ID (wie ``belege liste`` sie zeigt)."""
    treffer = [b for b in lade_belege(session) if str(b.id).startswith(praefix)]
    if not praefix or not treffer:
        raise FreigabeError(f"Kein Beleg mit ID '{praefix}'")
    if len(treffer) > 1:
        raise FreigabeError(f"'{praefix}' ist mehrdeutig ({len(treffer)} Belege)")
    return treffer[0]


def gib_frei(
    session: Session,
    praefix: str,
    *,
    belegart: Belegart | None = None,
    steuer: str | None = None,
) -> Beleg:
    """Beleg → ``erfasst``; ``belegart``/``steuer`` (Schlüssel aus ``STEUERFAELLE``)
    berichtigen die Erkennung. Person und Grund kommen über den Journal-Kontext."""
    beleg = finde_beleg(session, praefix)
    kurz = str(beleg.id)[:8]
    if beleg.id in verbuchte_beleg_ids(session):
        raise FreigabeError(
            f"Beleg {kurz} ist schon verbucht — die Buchungen korrigieren oder "
            "stornieren (accounti korrigiere, accounti buchung storniere)"
        )
    if beleg.status is BelegStatus.EINGEGANGEN:
        raise FreigabeError(
            f"Beleg {kurz} ist noch nicht gelesen — erst accounti belege erkennen"
        )
    if steuer is not None and steuer not in STEUERFAELLE:
        erlaubt = ", ".join(STEUERFAELLE)
        raise FreigabeError(f"--steuer {steuer}: erlaubt sind {erlaubt}")
    art = belegart or beleg.belegart
    if art is Belegart.UNBEKANNT:
        raise FreigabeError(
            f"Beleg {kurz}: Belegart {art.value} — mit --belegart angeben, was er ist"
        )
    if art in _RECHNUNGEN:
        fehlt = [
            name
            for name, wert in (
                ("Lieferant", beleg.lieferant_name),
                ("Betrag", beleg.brutto if beleg.brutto is not None else beleg.netto),
            )
            if wert is None
        ]
        if fehlt:
            raise FreigabeError(
                f"Beleg {kurz}: {', '.join(fehlt)} fehlt — so lässt er sich nicht "
                "buchen; die Rechnung beim Aussteller berichtigen lassen bzw. erneut "
                "erfassen"
            )
    elif steuer is not None:
        raise FreigabeError("--steuer gilt nur für Rechnungen")
    update: dict[str, object] = {
        "belegart": art,
        "richtung": Belegrichtung.AUSGANG
        if art is Belegart.AUSGANGSRECHNUNG
        else Belegrichtung.EINGANG,
        "status": BelegStatus.ERFASST,
        "pruef_grund": None,
    }
    if steuer is not None:
        kennzeichen = STEUERFAELLE[steuer]
        update["steuerkennzeichen"] = kennzeichen
        if kennzeichen is not None and beleg.steuer is None:
            update["steuer"] = Decimal("0.00")  # Hinweis statt Steuerausweis
    return aktualisiere_beleg(session, beleg.model_copy(update=update))
