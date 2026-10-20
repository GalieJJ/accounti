"""Abgabefristen der Umsatzsteuer-Meldungen.

- Voranmeldung: 10. Tag nach Ablauf des Voranmeldungszeitraums (§ 18 Abs. 1 UStG), mit
  Dauerfristverlängerung einen Monat später (§ 46 UStDV).
- Sondervorauszahlung (Monatszahler mit Dauerfristverlängerung): bis 10. Februar
  (§ 48 Abs. 2 UStDV, USt 5 E 2026).
- Zusammenfassende Meldung: 25. Tag nach Ablauf des Meldezeitraums (§ 18a Abs. 1 UStG),
  Feiertage am Sitz des BZSt (Bonn, Nordrhein-Westfalen).
- OSS: letzter Tag des Folgemonats nach Quartalsende (``steuer/oss.py``), ohne
  Verschiebung — die Frist folgt dem Unionsrecht.

Fällt ein Fristende auf Samstag, Sonntag oder Feiertag, endet die Frist am nächsten
Werktag (§ 108 Abs. 3 AO); maßgeblich ist das Land des Finanzamts.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from accounti.steuer.feiertage import kein_werktag, naechster_werktag
from accounti.steuer.oss import OSSEngine
from accounti.steuer.zeitraum import Zeitraum

BZST_LAND = "NW"  # Bundeszentralamt für Steuern, Bonn


@dataclass(frozen=True)
class Frist:
    art: str  # UStVA, Sondervorauszahlung, ZM, OSS
    zeitraum: str
    gesetzlich: date  # Fristende laut Gesetz
    faellig_am: date  # nach § 108 Abs. 3 AO
    grund: str | None = None  # warum verschoben

    @property
    def verschoben(self) -> bool:
        return self.faellig_am != self.gesetzlich

    @property
    def bezeichnung(self) -> str:
        return {
            "UStVA": "Umsatzsteuer-Voranmeldung",
            "Sondervorauszahlung": "Dauerfristverlängerung/Sondervorauszahlung",
            "ZM": "Zusammenfassende Meldung",
            "OSS": "OSS-Steuererklärung",
        }.get(self.art, self.art)


def _frist(art: str, zeitraum: str, ende: date, bundesland: str | None) -> Frist:
    grund = kein_werktag(ende, bundesland)
    return Frist(art, zeitraum, ende, naechster_werktag(ende, bundesland), grund)


def ustva_frist(
    zeitraum: Zeitraum, dauerfrist: bool = False, bundesland: str | None = None
) -> Frist:
    ende = zeitraum.bis + timedelta(days=10)
    if dauerfrist:  # ein Monat später, immer der 10.
        ende = date(ende.year + ende.month // 12, ende.month % 12 + 1, ende.day)
    return _frist("UStVA", str(zeitraum), ende, bundesland)


def sondervorauszahlung_frist(jahr: int, bundesland: str | None = None) -> Frist:
    return _frist("Sondervorauszahlung", str(jahr), date(jahr, 2, 10), bundesland)


def zm_frist(zeitraum: Zeitraum) -> Frist:
    return _frist("ZM", str(zeitraum), zeitraum.bis + timedelta(days=25), BZST_LAND)


def oss_frist(zeitraum: Zeitraum) -> Frist:
    if zeitraum.quartal is None:
        raise ValueError(f"OSS-Meldezeitraum ist das Quartal, nicht {zeitraum}")
    ende = OSSEngine()._abgabefrist(zeitraum.jahr, zeitraum.quartal)
    return Frist("OSS", str(zeitraum), ende, ende)


def _perioden(jahr: int, art: Literal["monat", "quartal"]) -> list[Zeitraum]:
    if art == "monat":
        return [Zeitraum(jahr, monat=m) for m in range(1, 13)]
    return [Zeitraum(jahr, quartal=q) for q in range(1, 5)]


def fristenkalender(
    jahr: int,
    *,
    voranmeldungszeitraum: Literal["monat", "quartal"] = "monat",
    dauerfrist: bool = False,
    zm: Literal["monat", "quartal"] | None = None,
    oss: bool = False,
    bundesland: str | None = None,
) -> list[Frist]:
    """Alle Fristen für die Meldezeiträume eines Jahres, nach Fälligkeit sortiert."""
    fristen = [
        ustva_frist(z, dauerfrist, bundesland)
        for z in _perioden(jahr, voranmeldungszeitraum)
    ]
    if dauerfrist and voranmeldungszeitraum == "monat":
        fristen.append(sondervorauszahlung_frist(jahr, bundesland))
    if zm is not None:
        fristen += [zm_frist(z) for z in _perioden(jahr, zm)]
    if oss:
        fristen += [oss_frist(z) for z in _perioden(jahr, "quartal")]
    return sorted(fristen, key=lambda f: (f.faellig_am, f.art))


def faellige_fristen(
    fristen: Iterable[Frist], stichtag: date, vorlauf_tage: int = 14
) -> list[Frist]:
    """Fristen, die ab dem Stichtag im Vorlauf enden — Stoff für Aufgaben."""
    bis = stichtag + timedelta(days=vorlauf_tage)
    return [f for f in fristen if stichtag <= f.faellig_am <= bis]
