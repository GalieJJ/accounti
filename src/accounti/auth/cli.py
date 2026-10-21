"""Rechteprüfung in der CLI.

Ohne eingerichtete Benutzer prüft accounti nichts — alles läuft wie bisher. Sobald
es Benutzer gibt, muss die handelnde Person ein aktiver Benutzer mit dem nötigen
Recht in der aktiven Gesellschaft sein. Mit ``auth.einmalcode_bestaetigung``
(Standard) gibt sie dazu ihren Einmalcode ein (TOTP oder Wiederherstellungscode;
für Skripte aus ``ACCOUNTI_EINMALCODE``): Ein Name in ``ACCOUNTI_BENUTZER`` oder
``--von`` beweist nichts, der zweite Faktor schon.

Die CLI läuft auf dem Server; wer sie aufrufen kann, kann meist auch die Datenbank
lesen. Die Prüfung hier bindet Freigaben an eine Person und verhindert Versehen —
eine Zugriffskontrolle gegen Betreiber ist sie nicht.
"""

from __future__ import annotations

import getpass
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime

import typer
from rich.console import Console
from rich.markup import escape
from sqlalchemy.orm import Session

from accounti.auth.dienst import ereignis, pruefe_zweiten_faktor, rollen_in
from accounti.auth.einstellungen import AuthEinstellungen, lade_auth
from accounti.auth.fehler import AnmeldungError, AuthError, RechteError
from accounti.bank.tresor import TresorError, lade_schluessel
from accounti.betrieb.kontext import aktueller_kontext
from accounti.db import init_db, session_factory
from accounti.db.repo_auth import (
    anzahl_benutzer,
    benutzer_mit_rolle,
    lade_benutzer,
    rollen_von,
)
from accounti.konfiguration import KonfigurationError
from accounti.models.auth import RECHT_TEXT, Benutzer, Recht, Rolle, rechte_der_rollen

UMGEBUNG_BENUTZER = "ACCOUNTI_BENUTZER"
UMGEBUNG_EINMALCODE = "ACCOUNTI_EINMALCODE"

Frage = Callable[[str], str]
console = Console(stderr=True)


def aktueller_benutzername() -> str:
    """``ACCOUNTI_BENUTZER``, sonst der Anmeldename — wie in ``accounti.aufgaben``."""
    return os.environ.get(UMGEBUNG_BENUTZER) or getpass.getuser()


@contextmanager
def systemsitzung(db: str) -> Iterator[Session]:
    """Sitzung der Systemdatenbank — ohne Registry ist das ``db``."""
    engine, fabrik = session_factory(aktueller_kontext().systemdatenbank(db))
    init_db(engine)
    try:
        with fabrik() as s:
            yield s
    finally:
        engine.dispose()


def auth_einstellungen(config: str) -> AuthEinstellungen:
    """Abschnitt ``auth``: bei mehreren Gesellschaften aus der globalen Datei."""
    kontext = aktueller_kontext()
    return lade_auth(
        kontext.globale_konfiguration if kontext.registry.eintraege else config
    )


def gesellschaft_fuer_rechte() -> str:
    """Kürzel der aktiven Gesellschaft — bei mehreren ohne Wahl ein Fehler."""
    kontext = aktueller_kontext()
    if kontext.gesellschaft is None and kontext.registry.mehrere:
        msg = "Mehrere Gesellschaften eingerichtet — --gesellschaft angeben"
        raise AuthError(msg)
    return kontext.kuerzel


def frage_einmalcode(person: str) -> str:
    wert = os.environ.get(UMGEBUNG_EINMALCODE)
    if wert:
        return wert
    antwort: str = typer.prompt(
        f"Einmalcode für {person} (App oder Wiederherstellungscode)",
        hide_input=True,
        err=True,
    )
    return antwort


def benutzer_eingerichtet(db: str) -> bool:
    with systemsitzung(db) as s:
        return anzahl_benutzer(s) > 0


def _verweigert(
    s: Session, art: str, person: str | None, recht: Recht, gesellschaft: str | None
) -> None:
    ereignis(
        s,
        art,
        datetime.now(),
        person,
        ok=False,
        gesellschaft=gesellschaft,
        hinweis=recht.value,
    )
    s.commit()


def pruefe_recht_in(
    s: Session,
    einstellungen: AuthEinstellungen,
    recht: Recht,
    person: str,
    gesellschaft: str | None,
    frage: Frage = frage_einmalcode,
    jetzt: datetime | None = None,
) -> Benutzer:
    """Person hat das Recht (in der Gesellschaft; ``None`` = in irgendeiner) und
    bestätigt es mit dem Einmalcode — sonst ``RechteError``/``AnmeldungError``."""
    b = lade_benutzer(s, person)
    if b is None or not b.aktiv:
        _verweigert(s, "recht_verweigert", None, recht, gesellschaft)
        msg = (
            f"{person} ist kein aktiver Benutzer von accounti (accounti benutzer liste)"
        )
        raise RechteError(msg)
    if gesellschaft is None:
        rollen = [z.rolle for z in rollen_von(s, b.id)]
    else:
        rollen = rollen_in(s, b.id, gesellschaft)
    if recht not in rechte_der_rollen(rollen):
        _verweigert(s, "recht_verweigert", b.name, recht, gesellschaft)
        wo = f" in der Gesellschaft {gesellschaft}" if gesellschaft else ""
        liste = ", ".join(sorted({r.value for r in rollen})) or "keine"
        msg = f"{person} darf{wo} nicht: {RECHT_TEXT[recht]} (Rollen: {liste})"
        raise RechteError(msg)
    if einstellungen.einmalcode_bestaetigung:
        pruefe_zweiten_faktor(
            s, b, frage(person), lade_schluessel(), einstellungen, jetzt, quelle="cli"
        )
    ereignis(
        s,
        "recht_genutzt",
        jetzt or datetime.now(),
        b.name,
        gesellschaft=gesellschaft,
        hinweis=recht.value,
    )
    s.commit()
    return b


def pruefe_befehlsrecht(
    db: str,
    config: str,
    recht: Recht,
    person: str,
    frage: Frage = frage_einmalcode,
) -> Benutzer | None:
    """Für Befehle mit einem Recht. ``None``: keine Benutzer eingerichtet."""
    with systemsitzung(db) as s:
        if anzahl_benutzer(s) == 0:
            return None
        return pruefe_recht_in(
            s,
            auth_einstellungen(config),
            recht,
            person,
            gesellschaft_fuer_rechte(),
            frage,
        )


def pruefe_verwaltung(
    db: str,
    config: str,
    selbst: str | None = None,
    frage: Frage = frage_einmalcode,
) -> str:
    """Wer Benutzer und Token verwalten will — gibt den Handelnden zurück.

    Einrichtungsphase: Solange kein aktiver Verwalter einen zweiten Faktor hat, ist
    alles erlaubt (sonst sperrte man sich beim Einrichten aus). Danach braucht es
    einen Verwalter mit Einmalcode — oder, bei ``selbst``, den Benutzer selbst mit
    seinem eingerichteten zweiten Faktor. Den ersten zweiten Faktor eines Benutzers
    richtet ein Verwalter ein: Sonst könnte jeder mit Zugang zur Server-Shell unter
    fremdem Namen einen Faktor anlegen.
    """
    person = aktueller_benutzername()
    with systemsitzung(db) as s:
        verwalter = [
            b
            for b in benutzer_mit_rolle(s, Rolle.VERWALTER)
            if b.aktiv and b.totp_aktiv
        ]
        if not verwalter:
            return person
        e = auth_einstellungen(config)
        if selbst is not None and person == selbst:
            b = lade_benutzer(s, person)
            if b is not None and b.aktiv and b.totp_aktiv:
                if e.einmalcode_bestaetigung:
                    pruefe_zweiten_faktor(
                        s, b, frage(person), lade_schluessel(), e, quelle="cli"
                    )
                    s.commit()
                return person
        kontext = aktueller_kontext()
        gesellschaft = kontext.gesellschaft.kuerzel if kontext.gesellschaft else None
        if gesellschaft is None and not kontext.registry.eintraege:
            gesellschaft = kontext.kuerzel
        pruefe_recht_in(s, e, Recht.VERWALTEN, person, gesellschaft, frage)
        return person


def _meldung(fehler: Exception) -> str:
    if isinstance(fehler, AnmeldungError):
        return "Einmalcode falsch, schon benutzt oder Benutzer gesperrt"
    return str(fehler)


def befehlsrecht_oder_ende(db: str, config: str, recht: Recht, person: str) -> None:
    """Wie ``pruefe_befehlsrecht`` — Fehler werden zur Meldung mit Exit-Code 1."""
    try:
        pruefe_befehlsrecht(db, config, recht, person)
    except (AuthError, TresorError, KonfigurationError) as fehler:
        console.print(f"[red]{escape(_meldung(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(1) from fehler


def verwaltung_oder_ende(db: str, config: str, selbst: str | None = None) -> str:
    try:
        return pruefe_verwaltung(db, config, selbst)
    except (AuthError, TresorError, KonfigurationError) as fehler:
        console.print(f"[red]{escape(_meldung(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(1) from fehler
