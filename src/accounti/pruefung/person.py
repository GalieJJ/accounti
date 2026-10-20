"""Wer handelt — und mit welchem Grund? Kontext für das Journal.

Benutzerkonten bringt Baustein 10; bis dahin ist die Person eine Zeichenkette:
``--von`` des Befehls, sonst ``ACCOUNTI_BENUTZER``, sonst der Anmeldename (wie im
Zahlungsverkehr). Ein Befehl setzt Person und Grund mit ``journal_kontext``; die
Journal-Ereignisse lesen sie von dort.
"""

from __future__ import annotations

import getpass
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace


def aktuelle_person(von: str | None = None) -> str:
    """``von``, sonst ``ACCOUNTI_BENUTZER``, sonst der Anmeldename."""
    if von and von.strip():
        return von.strip()
    try:
        login = getpass.getuser()
    except (KeyError, OSError):  # pragma: no cover — ohne Benutzerdatenbank
        login = "unbekannt"
    return os.environ.get("ACCOUNTI_BENUTZER") or login


@dataclass(frozen=True)
class JournalKontext:
    person: str | None = None
    grund: str | None = None
    bezug: str | None = None


_KONTEXT: ContextVar[JournalKontext | None] = ContextVar(
    "accounti_journal_kontext", default=None
)


def kontext() -> JournalKontext:
    return _KONTEXT.get() or JournalKontext()


@contextmanager
def journal_kontext(
    person: str | None = None, grund: str | None = None, bezug: str | None = None
) -> Iterator[JournalKontext]:
    """Person, Grund und Bezug für alle Journaleinträge im Block (innen gewinnt)."""
    alt = kontext()
    neu = replace(
        alt,
        person=person if person is not None else alt.person,
        grund=grund if grund is not None else alt.grund,
        bezug=bezug if bezug is not None else alt.bezug,
    )
    token = _KONTEXT.set(neu)
    try:
        yield neu
    finally:
        _KONTEXT.reset(token)
