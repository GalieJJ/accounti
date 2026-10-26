"""Belege freigeben — der Weg aus „zur Prüfung“ (und zum Berichtigen der Belegart).

Was die Erkennung nicht sicher lesen konnte, geht zur Prüfung. Der Mensch sieht das
Original an und gibt den Beleg frei — gegebenenfalls mit der richtigen Belegart, dem
Steuerfall einer Rechnung ohne Steuerausweis (§ 13b, ig. Lieferung, steuerfrei bzw.
Kleinunternehmer), der fehlenden Belegnummer oder umgekehrtem Vorzeichen (eine
Rechnung, die die Erkennung als Korrekturbeleg negiert hat, oder umgekehrt). Danach
verbucht ``accounti opos verbuchen`` ihn wie jeden erfassten Beleg. Die Änderung steht
mit Person, Grund und Vorher/Nachher im Journal (``beleg_freigegeben``). Lag der Beleg
wegen Dublettenverdacht, Rechenprobe oder gedrehtem Vorzeichen in der Prüfung, oder
ändert die Freigabe Vorzeichen bzw. eine gelesene Belegnummer, braucht sie einen Grund
(GoBD Rz. 58: Änderungen nachvollziehbar).

Verbuchte Belege ändert die Freigabe nicht mehr — dort gilt Storno statt Änderung.
Andere Beträge als das Vorzeichen berichtigt sie nicht (Grenze, siehe Plan).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.belege.dubletten import gleiche_belegnummer
from accounti.belege.extraktion import TOLERANZ
from accounti.db.repository import (
    aktualisiere_beleg,
    lade_belege,
    verbuchte_beleg_ids,
)
from accounti.models import Beleg, Belegart, Belegrichtung, BelegStatus
from accounti.pruefung.ereignisse import belegfreigabe
from accounti.pruefung.person import journal_kontext, kontext

# --steuer → Steuerkennzeichen (UNTDID 5305); „ohne“ hebt es auf
STEUERFAELLE: dict[str, str | None] = {
    "13b": "AE",
    "ig-erwerb": "K",
    "steuerfrei": "E",
    "ohne": None,
}
_RECHNUNGEN = frozenset({Belegart.EINGANGSRECHNUNG, Belegart.AUSGANGSRECHNUNG})
VORZEICHEN = ("umkehren",)
# Prüfgründe, die eine Entscheidung verlangen — nicht nur ein fehlendes Feld
_ERNSTE_GRUENDE = ("Dublette", "Rechenprobe", "Vorzeichen gedreht")


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
    vorzeichen: str | None = None,
    belegnummer: str | None = None,
    grund: str | None = None,
) -> Beleg:
    """Beleg → ``erfasst``; ``belegart``/``steuer`` (Schlüssel aus ``STEUERFAELLE``),
    ``vorzeichen`` (``umkehren``) und ``belegnummer`` berichtigen die Erkennung. Die
    Person kommt über den Journal-Kontext, ``grund`` steht im Journal."""
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
    if vorzeichen is not None and vorzeichen not in VORZEICHEN:
        raise FreigabeError(f"--vorzeichen {vorzeichen}: erlaubt ist umkehren")
    belegnummer = belegnummer.strip() if belegnummer is not None else None
    grund = grund or kontext().grund  # auch über den Journal-Kontext (Web, API)
    if not grund:
        _pruefe_grund(beleg, kurz, vorzeichen, belegnummer)
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
                "buchen; die Rechnung beim Aussteller berichtigen lassen"
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
        if kennzeichen is not None and _steuer_in_der_summe(beleg):
            raise FreigabeError(
                f"Beleg {kurz}: Netto {beleg.netto} ≠ Brutto {beleg.brutto} — die "
                f"Rechnung weist Steuer aus, --steuer {steuer} (ohne Steuerausweis) "
                "passt nicht; ohne --steuer freigeben (Position brutto, zur Prüfung)"
            )
        update["steuerkennzeichen"] = kennzeichen
        if kennzeichen is not None and beleg.steuer is None:
            update["steuer"] = Decimal("0.00")  # Hinweis statt Steuerausweis
    if belegnummer:
        neu = beleg.model_copy(update={"belegnummer": belegnummer})
        if (andere := gleiche_belegnummer(neu, lade_belege(session))) is not None:
            raise FreigabeError(
                f"Beleg {kurz}: Belegnummer {belegnummer} hat schon Beleg "
                f"{str(andere.id)[:8]} desselben Lieferanten"
            )
        update["belegnummer"] = belegnummer
    if vorzeichen == "umkehren":
        update.update(_umgekehrt(beleg))
    with belegfreigabe(), journal_kontext(grund=grund):
        frei = aktualisiere_beleg(session, beleg.model_copy(update=update))
        session.flush()  # das Journal entsteht hier, im Block der Freigabe
    return frei


def _pruefe_grund(
    beleg: Beleg, kurz: str, vorzeichen: str | None, belegnummer: str | None
) -> None:
    """Ohne --grund: nur, wenn keine Entscheidung im Journal fehlen würde."""
    anlass = None
    if vorzeichen is not None:
        anlass = "das Vorzeichen umgekehrt wird"
    elif belegnummer and beleg.belegnummer and belegnummer != beleg.belegnummer:
        anlass = f"die gelesene Belegnummer {beleg.belegnummer} ersetzt wird"
    elif beleg.pruef_grund and any(g in beleg.pruef_grund for g in _ERNSTE_GRUENDE):
        anlass = f"der Beleg so in der Prüfung lag: {beleg.pruef_grund}"
    if anlass is not None:
        raise FreigabeError(
            f"Beleg {kurz}: Freigabe nur mit --grund, weil {anlass} (steht im Journal)"
        )


def _steuer_in_der_summe(beleg: Beleg) -> bool:
    return (
        beleg.netto is not None
        and beleg.brutto is not None
        and abs(beleg.netto - beleg.brutto) > TOLERANZ
    )


def _minus(wert: Decimal | None) -> Decimal | None:
    return -wert if wert else wert  # keine „-0.00“


def _umgekehrt(beleg: Beleg) -> dict[str, object]:
    """Beträge und Positionen mit umgekehrtem Vorzeichen (Rechnung ↔ Korrektur)."""
    return {
        "netto": _minus(beleg.netto),
        "steuer": _minus(beleg.steuer),
        "brutto": _minus(beleg.brutto),
        "positionen": [
            p.model_copy(
                update={
                    "netto": _minus(p.netto),
                    "steuer_betrag": _minus(p.steuer_betrag),
                }
            )
            for p in beleg.positionen
        ],
    }
