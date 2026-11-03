"""Zweisprachigkeit der Oberfläche (Deutsch, Englisch) — ohne Babel, ohne Build-Schritt.

Deutsch ist die Quellsprache: Der deutsche Text ist der Schlüssel (``msgid``), der
Katalog ``en.yaml`` ordnet ihm den englischen zu (Mehrzahl als ``{one, other}``).
Fehlt ein Eintrag, bleibt der Text deutsch. Fachbegriffe ohne tragfähige
Entsprechung (Steuerschlüssel, BWA, GoBD, USt-VA, DATEV, ELSTER …) bleiben auch im
Englischen deutsch — ein Test hält das fest.

* ``aktive_sprache`` — Sprache der laufenden Anfrage (``seite()`` setzt sie beim
  Rendern und setzt sie im ``finally`` zurück).
* ``gettext``/``_``, ``ngettext``, ``N_`` (nur Markierung), ``Text`` (Meldung mit
  Platzhaltern: ``str()`` deutsch, übersetzt in der Oberfläche).
* ``waehle_sprache`` — Benutzer → ``Accept-Language`` → Standard der Konfiguration.
* Formate: ``betrag``, ``datum``, ``prozent``, ``monat`` je Sprache.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

SPRACHEN = ("de", "en")
STANDARD = "de"
NAMEN = {"de": "Deutsch", "en": "English"}

aktive_sprache: ContextVar[str] = ContextVar("accounti_sprache", default=STANDARD)


@lru_cache(maxsize=4)
def katalog(sprache: str) -> dict[str, Any]:
    """Übersetzungen der Sprache (Deutsch: leer — die Schlüssel sind deutsch)."""
    if sprache == STANDARD or sprache not in SPRACHEN:
        return {}
    text = (
        resources.files("accounti.i18n")
        .joinpath(f"{sprache}.yaml")
        .read_text(encoding="utf-8")
    )
    daten = yaml.safe_load(text) or {}
    if not isinstance(daten, dict):  # pragma: no cover — Paketfehler
        raise ValueError(f"Katalog {sprache}.yaml ist keine Zuordnung")
    return daten


def _sprache(sprache: str | None) -> str:
    return sprache if sprache in SPRACHEN else aktive_sprache.get()


def gettext(msgid: str, sprache: str | None = None) -> str:
    eintrag = katalog(_sprache(sprache)).get(msgid)
    if isinstance(eintrag, str) and eintrag:
        return eintrag
    if isinstance(eintrag, dict) and eintrag.get("one"):
        return str(eintrag["one"])
    return msgid


_ = gettext


def ngettext(
    singular: str, plural: str, anzahl: int, sprache: str | None = None
) -> str:
    eintrag = katalog(_sprache(sprache)).get(singular)
    if isinstance(eintrag, dict):
        wahl = eintrag.get("one" if anzahl == 1 else "other")
        if wahl:
            return str(wahl)
    return singular if anzahl == 1 else plural


def N_(text: str) -> str:  # noqa: N802 — gettext-Konvention
    """Nur Markierung für die Katalogprüfung — übersetzt wird beim Anzeigen."""
    return text


class Text:
    """Meldung mit Platzhaltern (``%(name)s``): ``str()`` liefert Deutsch (Protokoll,
    CLI, API), ``uebersetzt()`` die Sprache der Oberfläche."""

    __slots__ = ("msgid", "werte")

    def __init__(self, msgid: str, **werte: Any) -> None:
        self.msgid = msgid
        self.werte = werte

    def uebersetzt(self, sprache: str | None = None) -> str:
        vorlage = gettext(self.msgid, sprache)
        return vorlage % self.werte if self.werte else vorlage

    def __str__(self) -> str:
        return self.msgid % self.werte if self.werte else self.msgid

    def __repr__(self) -> str:
        return f"Text({self.msgid!r})"

    def __eq__(self, anderes: object) -> bool:
        return str(self) == str(anderes)

    def __hash__(self) -> int:
        return hash(str(self))


def uebersetze(wert: object, sprache: str | None = None) -> str:
    """``Text`` übersetzen; andere Werte unverändert als Text (Fachmeldungen bleiben
    deutsch)."""
    if isinstance(wert, Text):
        return wert.uebersetzt(sprache)
    return "" if wert is None else str(wert)


@contextmanager
def sprache_aktiv(sprache: str) -> Iterator[str]:
    token = aktive_sprache.set(sprache if sprache in SPRACHEN else STANDARD)
    try:
        yield aktive_sprache.get()
    finally:
        aktive_sprache.reset(token)


# --- Sprachwahl -------------------------------------------------------------------

_ACCEPT = re.compile(
    r"^\s*([A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*|\*)\s*(?:;\s*q\s*=\s*([0-9.]+))?\s*$"
)


def aus_accept_language(kopf: str | None) -> str | None:
    """Beste unterstützte Sprache aus ``Accept-Language`` (q-Werte), sonst ``None``."""
    kandidaten: list[tuple[float, int, str]] = []
    for nr, teil in enumerate((kopf or "").split(",")[:20]):
        treffer = _ACCEPT.match(teil)
        if treffer is None:
            continue
        try:
            q = float(treffer.group(2)) if treffer.group(2) else 1.0
        except ValueError:
            continue
        sprache = treffer.group(1).split("-")[0].lower()
        if q > 0 and sprache in SPRACHEN:
            kandidaten.append((-q, nr, sprache))
    return min(kandidaten)[2] if kandidaten else None


def waehle_sprache(
    benutzer: str | None, accept_language: str | None, standard: str = STANDARD
) -> str:
    """Benutzerwahl (``auth_benutzer.sprache``) → Browser → Konfiguration."""
    if benutzer in SPRACHEN:
        return benutzer
    return aus_accept_language(accept_language) or (
        standard if standard in SPRACHEN else STANDARD
    )


# --- Formate ------------------------------------------------------------------------

LEER = "—"


def betrag(wert: Decimal | float | int | None, sprache: str | None = None) -> str:
    """DE ``1.234,50``, EN ``1,234.50`` (ohne Währungszeichen; ``None`` → ``—``)."""
    if wert is None:
        return LEER
    text = f"{Decimal(str(wert)).quantize(Decimal('0.01')):,.2f}"
    if _sprache(sprache) == "en":
        return text
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def euro(wert: Decimal | float | int | None, sprache: str | None = None) -> str:
    """Im Fließtext: DE ``1.234,50 €``, EN ``€1,234.50``."""
    if wert is None:
        return LEER
    zahl = betrag(wert, sprache)
    if _sprache(sprache) == "en":
        return f"-€{zahl[1:]}" if zahl.startswith("-") else f"€{zahl}"
    return f"{zahl} €"


def datum(wert: date | None, sprache: str | None = None) -> str:
    """DE ``21.10.2026``, EN ``2026-10-21``."""
    if wert is None:
        return LEER
    return wert.isoformat()[:10] if _sprache(sprache) == "en" else f"{wert:%d.%m.%Y}"


def prozent(
    wert: Decimal | float | None, sprache: str | None = None, stellen: int = 1
) -> str:
    """DE ``12,5 %``, EN ``12.5%`` (``wert`` in Prozent)."""
    if wert is None:
        return LEER
    text = f"{float(wert):.{stellen}f}"
    if _sprache(sprache) == "en":
        return f"{text}%"
    return f"{text.replace('.', ',')} %"


MONATE = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


def monat(nummer: int, sprache: str | None = None) -> str:
    if not 1 <= nummer <= 12:
        return str(nummer)
    return gettext(MONATE[nummer - 1], sprache)


def platzhalter(text: str) -> set[str]:
    """``%(name)s``-Platzhalter eines Textes (für die Katalogprüfung)."""
    return set(re.findall(r"%\((\w+)\)[sd]", text))


def katalogtexte(eintrag: object) -> Mapping[str, str]:
    """Übersetzungen eines Katalogeintrags je Form (``einzig``, ``one``, ``other``)."""
    if isinstance(eintrag, dict):
        return {str(k): str(v) for k, v in eintrag.items()}
    return {"einzig": str(eintrag)}
