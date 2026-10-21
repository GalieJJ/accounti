"""Wer handelt — und mit welchem Grund? Kontext für das Journal.

Ohne eingerichtete Benutzer ist die Person eine Zeichenkette: ``--von`` des Befehls,
sonst ``ACCOUNTI_BENUTZER``, sonst der Anmeldename (wie im Zahlungsverkehr). Ein
Befehl setzt Person und Grund mit ``journal_kontext``; die Journal-Ereignisse lesen
sie von dort. Hat die Rechteprüfung (Baustein 10a: Rolle und Einmalcode) oder ein
API-Token die Person bestätigt, steht ``geprueft``; sonst kennzeichnet das Journal
die Person als „(ungeprüft)“, sobald Benutzer eingerichtet sind.
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
    geprueft: bool = False  # Person durch Rechteprüfung bzw. API-Token bestätigt


_KONTEXT: ContextVar[JournalKontext | None] = ContextVar(
    "accounti_journal_kontext", default=None
)


def kontext() -> JournalKontext:
    return _KONTEXT.get() or JournalKontext()


@contextmanager
def geprueft_als(name: str | None) -> Iterator[None]:
    """Journal-Kontext einer Person, die die Rechteprüfung bestätigt hat (Rolle und
    Einmalcode bzw. Anmeldung im Browser). ``None`` (keine Benutzer): nichts ändern."""
    if name is None:
        yield
        return
    with journal_kontext(person=name, geprueft=True):
        yield


@contextmanager
def journal_kontext(
    person: str | None = None,
    grund: str | None = None,
    bezug: str | None = None,
    *,
    geprueft: bool | None = None,
) -> Iterator[JournalKontext]:
    """Person, Grund und Bezug für alle Journaleinträge im Block (innen gewinnt).

    Eine neue Person ohne ``geprueft=True`` gilt als ungeprüft — auch innerhalb eines
    geprüften Blocks."""
    alt = kontext()
    if geprueft is None:
        geprueft = alt.geprueft if person is None or person == alt.person else False
    neu = replace(
        alt,
        person=person if person is not None else alt.person,
        grund=grund if grund is not None else alt.grund,
        bezug=bezug if bezug is not None else alt.bezug,
        geprueft=geprueft,
    )
    token = _KONTEXT.set(neu)
    try:
        yield neu
    finally:
        _KONTEXT.reset(token)
