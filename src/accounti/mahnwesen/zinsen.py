"""Verzugszinsen nach § 288 BGB.

Satz: Basiszinssatz plus 5 Prozentpunkte (Abs. 1), bei Entgeltforderungen ohne
Verbraucherbeteiligung plus 9 Prozentpunkte (Abs. 2). Gerechnet wird taggenau mit 365
Zinstagen im Jahr, in Abschnitten gleichen Kapitals und gleichen Satzes: Ein neuer
Abschnitt beginnt an jedem Wechsel des Basiszinssatzes und an jedem Zahltag.

Das Kapital eines Tages ist der heutige Rest plus alle Zahlungen, die erst danach
eingingen — Teilzahlungen während des Verzugs werden so zeitanteilig berücksichtigt.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from accounti.mahnwesen.basiszins import Basiszins, basiszins_am
from accounti.models.mahnwesen import Zinsabschnitt

AUFSCHLAG_UNTERNEHMER = Decimal("9")  # § 288 Abs. 2 BGB
AUFSCHLAG_VERBRAUCHER = Decimal("5")  # § 288 Abs. 1 BGB
ZINSTAGE_JAHR = Decimal("365")
CENT = Decimal("0.01")
NULL = Decimal("0.00")


def zinssatz(basiszins: Decimal, unternehmer: bool) -> Decimal:
    return basiszins + (AUFSCHLAG_UNTERNEHMER if unternehmer else AUFSCHLAG_VERBRAUCHER)


def _zinsen(kapital: Decimal, satz: Decimal, tage: int) -> Decimal:
    roh = kapital * satz / Decimal(100) * Decimal(tage) / ZINSTAGE_JAHR
    return roh.quantize(CENT, rounding=ROUND_HALF_UP)


def verzugszinsen(
    rest_heute: Decimal,
    zahlungen: Iterable[tuple[date, Decimal]],
    von: date,
    bis: date,
    unternehmer: bool,
    saetze: Sequence[Basiszins] | None = None,
) -> list[Zinsabschnitt]:
    """Zinsabschnitte vom ersten Zinstag ``von`` bis einschließlich ``bis``.

    ``zahlungen``: (Tag, Betrag inkl. Skonto) aller Zahlungen auf den Posten. Vom
    Zahltag an zählt nur noch der verringerte Betrag.
    """
    eingaenge = sorted(zahlungen)
    abschnitte: list[Zinsabschnitt] = []
    tag = von
    while tag <= bis:
        bz = basiszins_am(tag, saetze)
        naechste_zahlung = next((d for d, _ in eingaenge if d > tag), None)
        ende = min(bis, bz.bis)
        if naechste_zahlung is not None and naechste_zahlung <= ende:
            ende = naechste_zahlung - timedelta(days=1)
        kapital = rest_heute + sum((b for d, b in eingaenge if d > tag), NULL)
        satz = zinssatz(bz.satz, unternehmer)
        letzter = abschnitte[-1] if abschnitte else None
        if (
            letzter is not None
            and letzter.kapital == kapital
            and letzter.satz == satz
            and letzter.bis + timedelta(days=1) == tag
        ):
            tage = letzter.tage + (ende - tag).days + 1
            abschnitte[-1] = letzter.model_copy(
                update={
                    "bis": ende,
                    "tage": tage,
                    "zinsen": _zinsen(kapital, satz, tage),
                }
            )
        elif kapital > 0:
            tage = (ende - tag).days + 1
            abschnitte.append(
                Zinsabschnitt(
                    von=tag,
                    bis=ende,
                    tage=tage,
                    kapital=kapital,
                    basiszins=bz.satz,
                    satz=satz,
                    zinsen=_zinsen(kapital, satz, tage),
                )
            )
        tag = ende + timedelta(days=1)
    return abschnitte


def summe(abschnitte: Iterable[Zinsabschnitt]) -> Decimal:
    return sum((a.zinsen for a in abschnitte), NULL)
