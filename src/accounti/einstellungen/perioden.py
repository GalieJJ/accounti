"""Periodenwerte „ab Zeitraum → Wert“ (Baustein 10c P4, Spec E3, Plan D14).

Ein Feld, das vom Zeitraum abhängt (``inventar.PERIODENFELDER``), ist ein Einzelwert
(gilt immer) oder eine Zuordnung ab Zeitraum → Wert: ``{2026: monat, 2027: quartal}``
für Jahre und Wirtschaftsjahre (benannt nach dem Kalenderjahr ihres Endes, Paket F),
``{"2026-Q1": false, "2027-Q1": true}`` für Quartale (OSS). Es gilt der Eintrag mit dem
größten Schlüssel ≤ Zeitraum, der früheste auch für alle früheren Zeiträume.

Im Modell heißt das Rohfeld ``<name>_roh`` (Alias = Dateiname, ``populate_by_name``),
damit jeder alte Zugriff an mypy scheitert; gelesen wird nur über ``…_fuer(zeitraum)``
bzw. ``…_am(datum)`` (``tests/test_einstellungen_perioden.py``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import date
from typing import Annotated, Any, Literal, Self, TypeVar

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    TypeAdapter,
    ValidationError,
)

T = TypeVar("T")
Art = Literal["jahr", "quartal", "wirtschaftsjahr"]
Schluessel = int | str
_QUARTAL = re.compile(r"^(\d{4})-Q([1-4])$")
_JAHR = re.compile(r"^\d{4}$")
_JAHRE = range(1900, 3000)  # Jahre der Schlüssel — als Zahl, als Text und in JJJJ-Qn
_HINWEIS = {
    "jahr": "ein Jahr (z. B. 2027)",
    "wirtschaftsjahr": "ein Wirtschaftsjahr, benannt nach dem Jahr seines Endes "
    "(z. B. 2027)",
    "quartal": 'ein Quartal (z. B. "2027-Q1")',
}


def quartal_von(tag: date) -> str:
    """``"JJJJ-Qn"`` des Tages."""
    return f"{tag.year}-Q{(tag.month - 1) // 3 + 1}"


def schluessel_fuer(
    art: Art, zeitraum: date | int | str, *, beginn: date | None = None
) -> Schluessel:
    """Der Schlüssel, mit dem ein Verbraucher fragt: Jahr, ``"JJJJ-Qn"`` bzw. das
    Wirtschaftsjahr eines Tages (``beginn``: Beginn des WJ, nur Tag und Monat)."""
    if art == "quartal":
        if isinstance(zeitraum, date):
            return quartal_von(zeitraum)
        if isinstance(zeitraum, str) and _QUARTAL.match(zeitraum):
            return zeitraum
    elif isinstance(zeitraum, date):
        if art == "wirtschaftsjahr":
            from accounti.abschluss.konfiguration import wirtschaftsjahr_zum

            return wirtschaftsjahr_zum(zeitraum, beginn).jahr
        return zeitraum.year
    elif isinstance(zeitraum, int) and not isinstance(zeitraum, bool):
        return zeitraum
    msg = f"{zeitraum!r}: {_HINWEIS[art]}"
    raise ValueError(msg)


def _ordnung(schluessel: Schluessel) -> tuple[int, int]:
    if isinstance(schluessel, str):
        treffer = _QUARTAL.match(schluessel)
        if treffer is None:
            msg = f"{schluessel!r}: kein Quartal"
            raise ValueError(msg)
        return int(treffer[1]), int(treffer[2])
    return schluessel, 0


def _vorgaenger(schluessel: Schluessel) -> Schluessel:
    if isinstance(schluessel, str):
        jahr, quartal = _ordnung(schluessel)
        return f"{jahr - 1}-Q4" if quartal == 1 else f"{jahr}-Q{quartal - 1}"
    return schluessel - 1


def wert_fuer(feldwert: T | Mapping[Any, T], zeitraum: Schluessel) -> T:
    """Der Wert für ``zeitraum``: ein Einzelwert immer, sonst der Eintrag mit dem
    größten Schlüssel ≤ Zeitraum, vor dem frühesten der früheste."""
    if not isinstance(feldwert, Mapping):
        return feldwert
    eintraege: list[tuple[Any, T]] = sorted(
        feldwert.items(), key=lambda e: _ordnung(e[0])
    )
    ziel = _ordnung(zeitraum)
    passend = [w for k, w in eintraege if _ordnung(k) <= ziel]
    return passend[-1] if passend else eintraege[0][1]


def setze_ab(
    feldwert: T | Mapping[Any, T], ab: Schluessel, wert: T
) -> dict[Schluessel, T]:
    """„ab ``ab``: ``wert``“ — alle früheren Zeiträume behalten ihren Wert. Aus einem
    Einzelwert ``alt`` wird ``{ab−1: alt, ab: wert}``."""
    vorher = _vorgaenger(ab)
    if not isinstance(feldwert, Mapping):
        return {vorher: feldwert, ab: wert}
    neu: dict[Schluessel, T] = dict(feldwert)
    if not any(_ordnung(k) < _ordnung(ab) for k in neu):
        neu[vorher] = wert_fuer(feldwert, vorher)
    neu[ab] = wert
    return dict(sorted(neu.items(), key=lambda e: _ordnung(e[0])))


def _schluessel(art: Art, roh: object) -> Schluessel:
    """Ein Schlüssel aus Datei oder Datenbank (JSON: Text) in seiner Form — das Jahr
    1900–2999 auch als Text und in ``JJJJ-Qn`` (Prüfung steuer-4: „0207“ schaltete
    sonst still alle früheren Jahre um, „3027“ wirkte nie)."""
    if art == "quartal":
        treffer = _QUARTAL.match(roh.strip()) if isinstance(roh, str) else None
        if treffer is not None and int(treffer[1]) in _JAHRE:
            return treffer[0]
    elif isinstance(roh, int) and not isinstance(roh, bool):
        if roh in _JAHRE:
            return roh
    elif isinstance(roh, str) and _JAHR.match(roh.strip()) and int(roh) in _JAHRE:
        return int(roh)
    msg = f"Schlüssel {roh!r}: {_HINWEIS[art]}, Jahre 1900–2999"
    raise ValueError(msg)


def pruefe(art: Art, typ: Any) -> Callable[[Any], Any]:
    """Prüfung eines Periodenwerts (``BeforeValidator``): ein Wert vom Typ ``typ``
    oder eine nicht leere Zuordnung Schlüssel → Wert — mit einer Meldung, die
    Schlüssel und Grund nennt (statt der Meldungen jedes Zweigs der Union)."""
    adapter: TypeAdapter[Any] = TypeAdapter(typ)

    def einzeln(wert: Any, wo: str = "") -> Any:
        try:
            return adapter.validate_python(wert)
        except ValidationError as fehler:
            grund = "; ".join(str(f["msg"]) for f in fehler.errors())
            raise ValueError(f"{wo}{grund}") from fehler

    def pruefe_wert(wert: Any) -> Any:
        if not isinstance(wert, Mapping):
            return einzeln(wert)
        if not wert:
            msg = f"leere Zuordnung — {_HINWEIS[art]} → Wert, mindestens ein Eintrag"
            raise ValueError(msg)
        neu: dict[Schluessel, Any] = {}
        for roh, eintrag in wert.items():
            schluessel = _schluessel(art, roh)
            if schluessel in neu:  # 2026 und "2026": sonst gewönne still der letzte
                msg = f"Schlüssel {roh!r}: doppelt ({schluessel} steht schon da)"
                raise ValueError(msg)
            neu[schluessel] = einzeln(eintrag, f"{schluessel}: ")
        return dict(sorted(neu.items(), key=lambda e: _ordnung(e[0])))

    return pruefe_wert


class Periodenmodell(BaseModel):
    """Basis eines Modells mit Periodenwerten: Rohfelder auch über ihren Namen
    befüllbar (``populate_by_name``), und ``model_copy(update=…)`` nimmt auch den
    Dateinamen (Alias) — sonst landete ``update={"oss": True}`` still neben dem
    Rohfeld, und es bliebe beim alten Wert."""

    model_config = ConfigDict(populate_by_name=True)

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update:
            namen = {
                f.alias: name
                for name, f in type(self).model_fields.items()
                if f.alias is not None
            }
            update = {namen.get(k, k): v for k, v in update.items()}
        return super().model_copy(update=update, deep=deep)


# Typen der Rohfelder: Einzelwert oder Zuordnung ab Zeitraum → Wert
Voranmeldungszeitraum = Literal["monat", "quartal"]
Gewinnermittlung = Literal["euer", "bilanz"]
JahresVoranmeldung = Annotated[
    Voranmeldungszeitraum | dict[int, Voranmeldungszeitraum],
    BeforeValidator(pruefe("jahr", Voranmeldungszeitraum)),
]
JahresSchalter = Annotated[
    bool | dict[int, bool], BeforeValidator(pruefe("jahr", bool))
]
QuartalsSchalter = Annotated[
    bool | dict[str, bool], BeforeValidator(pruefe("quartal", bool))
]
WirtschaftsjahrGewinnermittlung = Annotated[
    Gewinnermittlung | dict[int, Gewinnermittlung],
    BeforeValidator(pruefe("wirtschaftsjahr", Gewinnermittlung)),
]
