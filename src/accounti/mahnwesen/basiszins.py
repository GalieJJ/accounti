"""Basiszinssatz nach § 247 BGB — jeder Satz mit Gültigkeitszeitraum.

Der Basiszinssatz ändert sich zum 1. Januar und 1. Juli; die Deutsche Bundesbank gibt
ihn im Bundesanzeiger bekannt. Die Tabelle unten ist die der Bundesbank
(https://www.bundesbank.de/de/bundesbank/basiszinssatz-nach---247-bgb-607820),
abgerufen am 20.10.2026; ihr letzter Zeitraum endet am 31.12.2026, weil der Satz ab
01.01.2027 noch nicht bekannt ist. Neue Sätze kommen über die Konfiguration
(``mahnwesen.basiszinssaetze``) dazu — für Tage ohne bekannten Satz wird nicht still
mit dem alten weitergerechnet, sondern abgebrochen.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

QUELLE = "https://www.bundesbank.de/de/bundesbank/basiszinssatz-nach---247-bgb-607820"
STAND = date(2026, 10, 20)


class BasiszinsUnbekanntError(LookupError):
    """Für einen Tag ist kein Basiszinssatz hinterlegt."""


@dataclass(frozen=True, order=True)
class Basiszins:
    ab: date
    bis: date
    satz: Decimal  # Prozent


def halbjahresende(ab: date) -> date:
    return date(ab.year, 6, 30) if ab.month <= 6 else date(ab.year, 12, 31)


# Gültig ab → Satz in Prozent (Deutsche Bundesbank, Stand 20.10.2026)
_BUNDESBANK: tuple[tuple[date, str], ...] = (
    (date(2002, 7, 1), "2.47"),
    (date(2003, 1, 1), "1.97"),
    (date(2003, 7, 1), "1.22"),
    (date(2004, 1, 1), "1.14"),
    (date(2004, 7, 1), "1.13"),
    (date(2005, 1, 1), "1.21"),
    (date(2005, 7, 1), "1.17"),
    (date(2006, 1, 1), "1.37"),
    (date(2006, 7, 1), "1.95"),
    (date(2007, 1, 1), "2.70"),
    (date(2007, 7, 1), "3.19"),
    (date(2008, 1, 1), "3.32"),
    (date(2008, 7, 1), "3.19"),
    (date(2009, 1, 1), "1.62"),
    (date(2009, 7, 1), "0.12"),
    (date(2010, 1, 1), "0.12"),
    (date(2010, 7, 1), "0.12"),
    (date(2011, 1, 1), "0.12"),
    (date(2011, 7, 1), "0.37"),
    (date(2012, 1, 1), "0.12"),
    (date(2012, 7, 1), "0.12"),
    (date(2013, 1, 1), "-0.13"),
    (date(2013, 7, 1), "-0.38"),
    (date(2014, 1, 1), "-0.63"),
    (date(2014, 7, 1), "-0.73"),
    (date(2015, 1, 1), "-0.83"),
    (date(2015, 7, 1), "-0.83"),
    (date(2016, 1, 1), "-0.83"),
    (date(2016, 7, 1), "-0.88"),
    (date(2017, 1, 1), "-0.88"),
    (date(2017, 7, 1), "-0.88"),
    (date(2018, 1, 1), "-0.88"),
    (date(2018, 7, 1), "-0.88"),
    (date(2019, 1, 1), "-0.88"),
    (date(2019, 7, 1), "-0.88"),
    (date(2020, 1, 1), "-0.88"),
    (date(2020, 7, 1), "-0.88"),
    (date(2021, 1, 1), "-0.88"),
    (date(2021, 7, 1), "-0.88"),
    (date(2022, 1, 1), "-0.88"),
    (date(2022, 7, 1), "-0.88"),
    (date(2023, 1, 1), "1.62"),
    (date(2023, 7, 1), "3.12"),
    (date(2024, 1, 1), "3.62"),
    (date(2024, 7, 1), "3.37"),
    (date(2025, 1, 1), "2.27"),
    (date(2025, 7, 1), "1.27"),
    (date(2026, 1, 1), "1.27"),
    (date(2026, 7, 1), "1.52"),
)

BASISZINSSAETZE: tuple[Basiszins, ...] = tuple(
    Basiszins(ab, halbjahresende(ab), Decimal(satz)) for ab, satz in _BUNDESBANK
)


def tabelle(zusaetze: Iterable[Basiszins] = ()) -> list[Basiszins]:
    """Eingebaute Sätze plus Ergänzungen; eine Ergänzung mit gleichem Beginn ersetzt.

    Überschneiden sich Zeiträume, ist die Tabelle unbrauchbar → ``ValueError``.
    """
    nach_beginn = {s.ab: s for s in BASISZINSSAETZE}
    for s in zusaetze:
        nach_beginn[s.ab] = s
    saetze = sorted(nach_beginn.values())
    for vorher, nachher in zip(saetze, saetze[1:], strict=False):
        if vorher.bis >= nachher.ab:
            msg = (
                f"Basiszinssätze überschneiden sich: {vorher.ab:%d.%m.%Y}–"
                f"{vorher.bis:%d.%m.%Y} und ab {nachher.ab:%d.%m.%Y}"
            )
            raise ValueError(msg)
    return saetze


def basiszins_am(tag: date, saetze: Sequence[Basiszins] | None = None) -> Basiszins:
    for s in BASISZINSSAETZE if saetze is None else saetze:
        if s.ab <= tag <= s.bis:
            return s
    msg = (
        f"Kein Basiszinssatz für den {tag:%d.%m.%Y} hinterlegt — nach der "
        "Bekanntgabe der Bundesbank in mahnwesen.basiszinssaetze eintragen "
        f"(ab, satz); Quelle: {QUELLE}"
    )
    raise BasiszinsUnbekanntError(msg)
