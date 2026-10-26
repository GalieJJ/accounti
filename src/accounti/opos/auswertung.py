"""Auswertungen über offene Posten: Liste, Fälligkeitsstaffel, Summen je Kontakt.

Die Liste zum Stichtag ist eine Stichtagsliste (Nachweis der Forderungen und
Verbindlichkeiten im Abschluss): Sie zeigt die Posten, die bis dahin gebucht waren, mit
ihrem Rest zum Ende des Stichtags — Zahlungen und Verrechnungen danach kommen wieder
dazu. So stimmt sie mit der Saldenliste zum selben Tag überein.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repo_opos import lade_verrechnungen
from accounti.db.repository import (
    lade_buchungen,
    lade_posten,
    lade_transaktionen,
    lade_zuordnungen,
)
from accounti.models import OffenerPosten, PostenRichtung, PostenStatus, ZuordnungStatus

NULL = Decimal("0.00")
STAFFELN = ("nicht fällig", "1–30 Tage", "31–60 Tage", "61–90 Tage", "über 90 Tage")


def ueberfaellig_tage(posten: OffenerPosten, stichtag: date) -> int:
    """Tage seit Fälligkeit; 0 oder negativ heißt: noch nicht überfällig."""
    return (stichtag - posten.faellig_am).days


def staffel_von(posten: OffenerPosten, stichtag: date) -> str:
    tage = ueberfaellig_tage(posten, stichtag)
    if tage <= 0:
        return STAFFELN[0]
    if tage <= 30:
        return STAFFELN[1]
    if tage <= 60:
        return STAFFELN[2]
    if tage <= 90:
        return STAFFELN[3]
    return STAFFELN[4]


def offene_posten(
    posten: Iterable[OffenerPosten],
    faellig_bis: date | None = None,
    richtung: PostenRichtung | None = None,
) -> list[OffenerPosten]:
    """Nicht ausgeglichene Posten, optional nur bis zu einem Fälligkeitsdatum."""
    return [
        p
        for p in posten
        if p.status is not PostenStatus.AUSGEGLICHEN
        and (faellig_bis is None or p.faellig_am <= faellig_bis)
        and (richtung is None or p.richtung is richtung)
    ]


def stand_zum(
    posten: Iterable[OffenerPosten],
    stichtag: date,
    bewegungen: Mapping[UUID, list[tuple[date, Decimal]]],
    gebucht_ab: Mapping[UUID, date] | None = None,
) -> list[OffenerPosten]:
    """Posten mit ihrem Rest zum Ende des Stichtags (ohne die ausgeglichenen).

    ``bewegungen``: je Posten (Tag, Minderung des Rests) — Zahlungen samt Skonto,
    Verrechnungen. Was nach dem Stichtag geschah, kommt zum heutigen Rest wieder
    dazu. Ein Posten zählt ab seiner frühesten Buchung (``gebucht_ab``, z.B. eine
    Ausgangsrechnung zum Leistungsdatum), sonst ab dem Belegdatum.
    """
    ergebnis = []
    for p in posten:
        ab = min(p.belegdatum, (gebucht_ab or {}).get(p.beleg_id, p.belegdatum))
        if ab > stichtag:
            continue
        spaeter = sum(
            (b for tag, b in bewegungen.get(p.id, []) if tag > stichtag), NULL
        )
        rest = p.restbetrag + spaeter
        if rest == 0:
            continue
        status = PostenStatus.OFFEN if rest == p.betrag else PostenStatus.TEILBEZAHLT
        ergebnis.append(p.model_copy(update={"restbetrag": rest, "status": status}))
    return ergebnis


def lade_stand_zum(session: Session, stichtag: date) -> list[OffenerPosten]:
    """``stand_zum`` aus der Datenbank: Zahlungen (gebuchte Zuordnungen),
    Verrechnungen und die Belegbuchungen der Posten."""
    tage = {t.id: t.datum for t in lade_transaktionen(session)}
    bewegungen: dict[UUID, list[tuple[date, Decimal]]] = defaultdict(list)
    for z in lade_zuordnungen(session, status={ZuordnungStatus.GEBUCHT}):
        if z.transaktion_id in tage:
            bewegungen[z.posten_id].append(
                (tage[z.transaktion_id], z.betrag + z.skonto)
            )
    for v in lade_verrechnungen(session):
        bewegungen[v.posten_id].append((v.datum, v.betrag))
        bewegungen[v.gegen_posten_id].append((v.datum, -v.betrag))
    gebucht_ab: dict[UUID, date] = {}
    for b in lade_buchungen(session):
        if b.beleg_id is not None and b.transaktion_id is None:
            gebucht_ab[b.beleg_id] = min(b.datum, gebucht_ab.get(b.beleg_id, b.datum))
    return stand_zum(lade_posten(session), stichtag, bewegungen, gebucht_ab)


def faelligkeitsstaffel(
    posten: Iterable[OffenerPosten], stichtag: date
) -> dict[str, Decimal]:
    """Summe der Restbeträge je Altersklasse — alle Klassen, auch leere."""
    staffel = dict.fromkeys(STAFFELN, NULL)
    for p in offene_posten(posten):
        staffel[staffel_von(p, stichtag)] += p.restbetrag
    return staffel


def summen_je_kontakt(posten: Iterable[OffenerPosten]) -> dict[UUID, Decimal]:
    summen: dict[UUID, Decimal] = defaultdict(lambda: NULL)
    for p in offene_posten(posten):
        summen[p.kontakt_id] += p.restbetrag
    return dict(summen)
