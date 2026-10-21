"""Gemeinsame Hilfen für die Tests von Anmeldung, Rollen und API (Baustein 10)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from accounti.auth import passwort
from accounti.auth.dienst import bestaetige_2fa, lege_benutzer_an
from accounti.auth.einstellungen import AuthEinstellungen
from accounti.auth.totp import code, neues_geheimnis
from accounti.bank.tresor import neuer_schluessel
from accounti.db import init_db, session_factory
from accounti.models.auth import Benutzer, Rolle

JETZT = datetime(2026, 10, 20, 9, 0, 0)
PASSWORT = "ein sehr geheimer Satz"
SCHLUESSEL = neuer_schluessel()
BILLIG = passwort.Kosten(log_n=10, r=8, p=1)


def billige_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    """scrypt mit N = 2^17 braucht 128 MiB und eine halbe Sekunde je Hash —
    in Tests reicht N = 2^10 (``autouse``-Fixture im Testmodul)."""
    monkeypatch.setattr(passwort, "KOSTEN", BILLIG)


def setze_schluessel(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", SCHLUESSEL)
    return SCHLUESSEL


@contextmanager
def systemdatenbank(tmp_path: Path) -> Iterator[Session]:
    engine, fabrik = session_factory(f"sqlite:///{tmp_path / 'system.db'}")
    init_db(engine)
    with fabrik() as s:
        yield s
    engine.dispose()


def einstellungen(**werte: object) -> AuthEinstellungen:
    return AuthEinstellungen.model_validate(werte)


class Person:
    """Ein Benutzer mit Passwort, TOTP-Geheimnis und Wiederherstellungscodes."""

    def __init__(self, benutzer: Benutzer, geheimnis: bytes, codes: list[str]) -> None:
        self.benutzer = benutzer
        self.geheimnis = geheimnis
        self.codes = codes
        self.name = benutzer.name

    def code(self, zeit: datetime) -> str:
        return code(self.geheimnis, zeit.timestamp())


def lege_person_an(
    s: Session,
    name: str,
    *rollen: Rolle,
    gesellschaft: str = "standard",
    mit_2fa: bool = True,
    jetzt: datetime = JETZT,
    schluessel: str = SCHLUESSEL,
) -> Person:
    b = lege_benutzer_an(
        s,
        name,
        PASSWORT,
        [(gesellschaft, r) for r in rollen],
        einstellungen(),
        jetzt=jetzt,
    )
    geheimnis = neues_geheimnis()
    codes: list[str] = []
    if mit_2fa:
        # ein Schritt vor jetzt, damit der Code „jetzt“ in Tests noch frei ist
        frueher = datetime.fromtimestamp(jetzt.timestamp() - 30)
        codes = bestaetige_2fa(
            s,
            b,
            geheimnis,
            code(geheimnis, frueher.timestamp()),
            schluessel,
            einstellungen(),
            jetzt=frueher,
        )
    s.commit()
    from accounti.db.repo_auth import lade_benutzer

    gespeichert = lade_benutzer(s, name)
    assert gespeichert is not None
    return Person(gespeichert, geheimnis, codes)
