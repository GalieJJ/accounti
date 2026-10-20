"""Dauerfristverlängerung und Sondervorauszahlung (§§ 46–48 UStDV).

Monatszahler mit Dauerfristverlängerung melden bis zum 10. Februar eine
Sondervorauszahlung an: ein Elftel der Vorauszahlungen des Vorjahres zuzüglich der im
Vorjahr abgezogenen Sondervorauszahlung (USt 5 E 2026). Abgezogen wird sie in der
letzten Voranmeldung des Jahres (Kz 39). Quartalszahler stellen den Antrag ohne
Sondervorauszahlung; er gilt fort.

Die Vorauszahlungen des Vorjahres kommen aus dem Übermittlungsprotokoll (je Monat die
zuletzt abgegebene Anmeldung); fehlt ein Monat, ist die Summe anzugeben.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv
from accounti.elster.datensatz import dauerfrist_xml
from accounti.elster.freigabe import (
    FreigabeError,
    inhalt,
    offene_freigabe,
    speichere,
)
from accounti.elster.konfiguration import ElsterEinstellungen
from accounti.elster.uebermittlung import Uebermittler, UebermittlungError
from accounti.elster.ustva import (
    Kontext,
    abgegeben,
    fuehre_aus,
    kopf_fuer,
    letzte_betraege,
)
from accounti.models.elster import Freigabe, Meldeart, Modus, Uebermittlung
from accounti.steuer.voranmeldung import sondervorauszahlung

NULL = Decimal("0.00")


class DauerfristError(ValueError):
    """Die Sondervorauszahlung lässt sich so nicht berechnen."""


@dataclass(frozen=True)
class Sondervorauszahlung:
    jahr: int
    summe_vorjahr: Decimal
    svz_vorjahr: Decimal
    betrag: Decimal | None  # None: Quartalszahler, Antrag ohne Sondervorauszahlung
    fehlende_monate: tuple[str, ...] = field(default=())

    @property
    def zeitraum(self) -> str:
        return str(self.jahr)


def berechne_svz(
    session: Session,
    jahr: int,
    einstellungen: ElsterEinstellungen,
    summe_vorjahr: Decimal | None = None,
    svz_vorjahr: Decimal | None = None,
) -> Sondervorauszahlung:
    if einstellungen.voranmeldungszeitraum == "quartal":
        return Sondervorauszahlung(jahr, NULL, NULL, None)
    vorjahr = letzte_betraege(session, Meldeart.USTVA)
    monate = [f"{jahr - 1}-{m:02d}" for m in range(1, 13)]
    fehlende = tuple(m for m in monate if m not in vorjahr)
    if summe_vorjahr is None:
        if fehlende:
            msg = (
                f"Im Protokoll fehlen Voranmeldungen {jahr - 1}: {', '.join(fehlende)} "
                "— Summe der Vorauszahlungen mit --summe-vorjahr angeben"
            )
            raise DauerfristError(msg)
        summe_vorjahr = sum((vorjahr[m] for m in monate), NULL)
    if svz_vorjahr is None:
        svz_vorjahr = letzte_betraege(session, Meldeart.DAUERFRIST).get(
            str(jahr - 1), NULL
        )
    betrag = sondervorauszahlung(summe_vorjahr, svz_vorjahr)
    return Sondervorauszahlung(jahr, summe_vorjahr, svz_vorjahr, betrag, fehlende)


def _inhalt(svz: Sondervorauszahlung) -> dict[str, Any]:
    werte: dict[int, Any] = {38: svz.betrag} if svz.betrag is not None else {}
    return inhalt(Meldeart.DAUERFRIST, svz.zeitraum, werte)


def gib_dauerfrist_frei(
    session: Session,
    svz: Sondervorauszahlung,
    von: str,
    jetzt: datetime | None = None,
) -> Freigabe:
    return speichere(session, Meldeart.DAUERFRIST, _inhalt(svz), von, (), jetzt)


def uebermittle_dauerfrist(
    session: Session,
    svz: Sondervorauszahlung,
    *,
    modus: Modus,
    kontext: Kontext,
    uebermittler: Uebermittler | None,
    archiv: BelegArchiv | None,
    jetzt: datetime | None = None,
) -> Uebermittlung:
    """Dauerfristverlängerung (mit Sondervorauszahlung) prüfen, testen oder abgeben."""
    if modus is not Modus.PRUEFUNG and uebermittler is None:
        raise UebermittlungError("Kein Übermittler: ERiC ist nicht eingerichtet")
    freigabe = None
    if modus is Modus.ECHT:
        try:
            freigabe = offene_freigabe(
                session, Meldeart.DAUERFRIST, svz.zeitraum, _inhalt(svz)
            )
        except FreigabeError as fehler:
            raise UebermittlungError(str(fehler)) from fehler
    berichtigt = abgegeben(session, Meldeart.DAUERFRIST, svz.zeitraum)
    xml = dauerfrist_xml(
        svz.jahr,
        kontext.steuernummer,
        kontext.absender,
        kopf_fuer(kontext, modus),
        svz.betrag,
        berichtigt,
        (jetzt or datetime.now()).date(),
    )
    return fuehre_aus(
        session,
        art=Meldeart.DAUERFRIST,
        zeitraum=svz.zeitraum,
        xml=xml,
        jahr=svz.jahr,
        modus=modus,
        uebermittler=uebermittler,
        archiv=archiv,
        plausi=[],
        betrag=svz.betrag,
        berichtigt=berichtigt,
        freigabe_id=freigabe.id if freigabe else None,
        freigegeben_von=freigabe.freigegeben_von if freigabe else None,
        jetzt=jetzt,
    )
