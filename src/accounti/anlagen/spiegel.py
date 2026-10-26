"""Anlagenspiegel — Entwicklung je Anlagekonto (Sammelposten je Jahrgang).

Gerechnet wird aus dem AfA-Plan, also die Sollrechnung. Ob die AfA auch gebucht ist und
die Anlagekonten zum Spiegel passen, prüft ``accounti abschluss pruefen``. GWG und
Sammelposten bleiben bis zum tatsächlichen Abgang mit Restbuchwert 0 stehen.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from accounti.anlagen.afa import AfaPlan, plane, plane_sammelposten
from accounti.anlagen.rechtsstand import Rechtsstand
from accounti.anzeige import betrag_de
from accounti.models.anlagen import AfaArt, Anlagegut

NULL = Decimal("0")


@dataclass
class SpiegelZeile:
    gruppe: str
    bezeichnung: str
    ak_beginn: Decimal = NULL
    zugang: Decimal = NULL
    abgang: Decimal = NULL
    afa_beginn: Decimal = NULL
    afa_jahr: Decimal = NULL
    afa_abgang: Decimal = NULL

    @property
    def ak_ende(self) -> Decimal:
        return self.ak_beginn + self.zugang - self.abgang

    @property
    def afa_ende(self) -> Decimal:
        return self.afa_beginn + self.afa_jahr - self.afa_abgang

    @property
    def rbw_beginn(self) -> Decimal:
        return self.ak_beginn - self.afa_beginn

    @property
    def rbw_ende(self) -> Decimal:
        return self.ak_ende - self.afa_ende

    def addiere(self, andere: SpiegelZeile) -> None:
        for name in _BETRAEGE:
            setattr(self, name, getattr(self, name) + getattr(andere, name))


_BETRAEGE = ("ak_beginn", "zugang", "abgang", "afa_beginn", "afa_jahr", "afa_abgang")


@dataclass
class Anlagenspiegel:
    jahr: int
    gruppen: list[SpiegelZeile]
    einzeln: list[SpiegelZeile]
    summe: SpiegelZeile


def _zeile(
    gruppe: str,
    bezeichnung: str,
    ak: Decimal,
    plan: AfaPlan,
    anschaffung: date,
    abgang: date | None,
    jahr: int,
) -> SpiegelZeile | None:
    beginn, ende = date(jahr, 1, 1), date(jahr, 12, 31)
    if anschaffung > ende or (abgang is not None and abgang < beginn):
        return None
    z = SpiegelZeile(gruppe, bezeichnung)
    if anschaffung < beginn:
        z.ak_beginn = ak
        z.afa_beginn = plan.kumuliert_bis(jahr - 1, 12)
    else:
        z.zugang = ak
    z.afa_jahr = plan.afa_im_jahr(jahr)
    if abgang is not None and abgang <= ende:
        z.abgang = ak
        z.afa_abgang = plan.kumuliert_bis(jahr, abgang.month)
    return z


def anlagenspiegel(
    anlagen: Iterable[Anlagegut], jahr: int, rechtsstand: Rechtsstand
) -> Anlagenspiegel:
    alle = list(anlagen)
    einzeln: list[SpiegelZeile] = []
    gruppen: dict[str, SpiegelZeile] = {}
    sammelposten: set[tuple[str, int]] = set()
    for a in sorted(alle, key=lambda a: a.nr):
        plan = plane(a, rechtsstand)
        z = _zeile(
            str(a.nr),
            a.bezeichnung,
            a.anschaffungskosten,
            plan,
            a.anschaffungsdatum,
            a.abgang_datum,
            jahr,
        )
        im_posten = a.afa_art is AfaArt.SAMMELPOSTEN and plan.jahre
        if im_posten:
            sammelposten.add((a.konto, a.anschaffungsdatum.year))
            if z is not None:  # Gut sichtbar, Abgang mindert den Posten nicht
                z.abgang = z.afa_abgang = NULL
        if z is None:
            continue
        einzeln.append(z)
        if not im_posten:
            gruppen.setdefault(a.konto, SpiegelZeile(a.konto, a.konto)).addiere(z)
    for konto, anschaffungsjahr in sammelposten:
        plan = plane_sammelposten(konto, anschaffungsjahr, alle, rechtsstand)
        name = f"{konto}/{anschaffungsjahr}"
        z = _zeile(
            name,
            f"Sammelposten {name}",
            plan.anschaffungskosten,
            plan,
            date(anschaffungsjahr, 1, 1),
            None,
            jahr,
        )
        if z is not None:
            gruppen[name] = z
    reihe = [gruppen[k] for k in sorted(gruppen)]
    summe = SpiegelZeile("Summe", "Summe")
    for z in reihe:
        summe.addiere(z)
    return Anlagenspiegel(jahr, reihe, einzeln, summe)


def restbuchwerte(
    anlagen: Iterable[Anlagegut], stichtag: date, rechtsstand: Rechtsstand
) -> dict[str, Decimal]:
    """Restbuchwert je Anlagekonto zum Stichtag (Ende seines Monats) — für die
    Abstimmung mit dem Saldo des Anlagekontos, auch zum Ende eines abweichenden
    Wirtschaftsjahres. Ein Sammelposten zählt als Ganzes (ein Abgang mindert ihn
    nicht), ein abgegangenes Gut nicht mehr."""
    alle = list(anlagen)
    rbw: dict[str, Decimal] = {}
    sammelposten: set[tuple[str, int]] = set()
    for a in alle:
        if a.anschaffungsdatum > stichtag:
            continue
        plan = plane(a, rechtsstand)
        if a.afa_art is AfaArt.SAMMELPOSTEN and plan.jahre:
            sammelposten.add((a.konto, a.anschaffungsdatum.year))
            continue
        if a.abgang_datum is not None and a.abgang_datum <= stichtag:
            continue
        wert = plan.restbuchwert(stichtag.year, stichtag.month)
        rbw[a.konto] = rbw.get(a.konto, NULL) + wert
    # nur Güter bis zum Stichtag — beim abweichenden WJ liegt er mitten im Jahrgang
    bis_stichtag = [a for a in alle if a.anschaffungsdatum <= stichtag]
    for konto, jahr in sorted(sammelposten):
        plan = plane_sammelposten(konto, jahr, bis_stichtag, rechtsstand)
        wert = plan.restbuchwert(stichtag.year, stichtag.month)
        rbw[konto] = rbw.get(konto, NULL) + wert
    return rbw


SPALTEN = (
    "AK 01.01.",
    "Zugang",
    "Abgang",
    "AK 31.12.",
    "AfA kum. 01.01.",
    "AfA Jahr",
    "AfA auf Abgänge",
    "AfA kum. 31.12.",
    "RBW 01.01.",
    "RBW 31.12.",
)


def werte(z: SpiegelZeile) -> list[Decimal]:
    return [
        z.ak_beginn,
        z.zugang,
        z.abgang,
        z.ak_ende,
        z.afa_beginn,
        z.afa_jahr,
        z.afa_abgang,
        z.afa_ende,
        z.rbw_beginn,
        z.rbw_ende,
    ]


def als_csv(spiegel: Anlagenspiegel) -> str:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\n")
    schreiber.writerow(["Gruppe", "Bezeichnung", *SPALTEN])
    for z in [*spiegel.gruppen, spiegel.summe]:
        schreiber.writerow(
            [
                z.gruppe,
                z.bezeichnung,
                *(betrag_de(w).replace(".", "") for w in werte(z)),
            ]
        )
    return puffer.getvalue()
