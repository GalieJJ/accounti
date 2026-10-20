"""Auswertungen über offene Posten: Liste, Fälligkeitsstaffel, Summen je Kontakt."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from uuid import UUID

from accounti.models import OffenerPosten, PostenRichtung, PostenStatus

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
