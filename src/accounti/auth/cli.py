"""Rechteprüfung in der CLI.

Ohne eingerichtete Benutzer prüft accounti nichts — alles läuft wie bisher. Sobald
es Benutzer gibt, muss die handelnde Person ein aktiver Benutzer mit dem nötigen
Recht in der aktiven Gesellschaft sein. Mit ``auth.einmalcode_bestaetigung``
(Standard) gibt sie dazu ihren Einmalcode ein (TOTP oder Wiederherstellungscode;
für Skripte aus ``ACCOUNTI_EINMALCODE``): Ein Name in ``ACCOUNTI_BENUTZER`` oder
``--von`` beweist nichts, der zweite Faktor schon.

Die Prüfung gilt für die Datenbank, die der Befehl **tatsächlich** benutzt:

- Mit Registry müssen ``--db`` und ``--config`` die der gewählten Gesellschaft sein —
  eine abweichende Datenbank wird abgewiesen (sonst prüfte man Rechte in b und gäbe
  in a frei).
- Jede Gesellschafts-Datenbank trägt einen Merker (``auth_merker``), zu welcher
  Systemdatenbank und Gesellschaft sie gehört. Zeigt ``ACCOUNTI_SYSTEM_DB`` oder eine
  andere Registry auf eine leere oder fremde Systemdatenbank, bricht der Befehl ab
  (fail-closed) — statt „keine Benutzer, keine Prüfung“.
- ``auth``-Werte aus einer frei wählbaren Datei (``--config``, ``ACCOUNTI_KONFIG``)
  können die Prüfung nur verschärfen: in der CLI gilt immer der Einmalcode, die
  Sperre höchstens so mild wie der Standard (``streng``).

Die CLI läuft auf dem Server; wer sie aufrufen kann, kann meist auch die Datenbank
lesen. Die Prüfung hier bindet Freigaben an eine Person und verhindert Versehen —
eine Zugriffskontrolle gegen Betreiber ist sie nicht.
"""

from __future__ import annotations

import getpass
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import typer
from rich.console import Console
from rich.markup import escape
from sqlalchemy.orm import Session

from accounti.auth.dienst import ereignis, pruefe_zweiten_faktor, rollen_in
from accounti.auth.einstellungen import AuthEinstellungen, lade_auth
from accounti.auth.fehler import AnmeldungError, AuthError, RechteError
from accounti.bank.tresor import TresorError, lade_schluessel
from accounti.betrieb.gesellschaften import gleiche_datenbank, gleicher_pfad
from accounti.betrieb.kontext import Kontext, aktueller_kontext
from accounti.db import init_db, session_factory
from accounti.db.repo_auth import (
    anzahl_benutzer,
    benutzer_mit_rolle,
    lade_benutzer,
    lade_merker,
    rollen_von,
    setze_merker_einmal,
)
from accounti.konfiguration import KonfigurationError
from accounti.models.auth import RECHT_TEXT, Benutzer, Recht, Rolle, rechte_der_rollen

UMGEBUNG_BENUTZER = "ACCOUNTI_BENUTZER"
UMGEBUNG_EINMALCODE = "ACCOUNTI_EINMALCODE"
MERKER_SYSTEM = "systemkennung"
MERKER_BINDUNG = "benutzerverwaltung"

Frage = Callable[[str], str]
console = Console(stderr=True)


def aktueller_benutzername() -> str:
    """``ACCOUNTI_BENUTZER``, sonst der Anmeldename — wie in ``accounti.aufgaben``."""
    return os.environ.get(UMGEBUNG_BENUTZER) or getpass.getuser()


@contextmanager
def _sitzung(url: str) -> Iterator[Session]:
    engine, fabrik = session_factory(url)
    init_db(engine)
    try:
        with fabrik() as s:
            yield s
    finally:
        engine.dispose()


@contextmanager
def systemsitzung(db: str) -> Iterator[Session]:
    """Sitzung der Systemdatenbank — ohne Registry ist das ``db``."""
    with _sitzung(aktueller_kontext().pruefe().systemdatenbank(db)) as s:
        yield s


def streng(e: AuthEinstellungen) -> AuthEinstellungen:
    """Für die CLI: Die Datei kann die Prüfung verschärfen, nicht abschwächen.

    ``--config`` und ``ACCOUNTI_KONFIG`` wählt, wer den Befehl aufruft — ein
    ``einmalcode_bestaetigung: false`` darin darf die Bindung an die Person nicht
    aufheben. Im Browser gilt die Datei, mit der ``accounti serve`` startete.
    """
    s = AuthEinstellungen()
    return e.model_copy(
        update={
            "einmalcode_bestaetigung": True,
            "sperre_nach_fehlversuchen": min(
                e.sperre_nach_fehlversuchen, s.sperre_nach_fehlversuchen
            ),
            "sperre_minuten": max(e.sperre_minuten, s.sperre_minuten),
            "fehlversuche_obergrenze": min(
                e.fehlversuche_obergrenze, s.fehlversuche_obergrenze
            ),
            "totp_toleranz_schritte": min(
                e.totp_toleranz_schritte, s.totp_toleranz_schritte
            ),
            "passwort_mindestlaenge": max(
                e.passwort_mindestlaenge, s.passwort_mindestlaenge
            ),
        }
    )


def auth_einstellungen(config: str) -> AuthEinstellungen:
    """Abschnitt ``auth`` für die CLI (bei mehreren Gesellschaften aus der globalen
    Datei) — nur in der strengeren Richtung (``streng``)."""
    kontext = aktueller_kontext()
    return streng(
        lade_auth(
            kontext.globale_konfiguration if kontext.registry.eintraege else config
        )
    )


# ---------------------------------------------------------------------------
# Bindung der Gesellschafts-Datenbank an ihre Benutzerverwaltung (fail-closed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bindung:
    system: str
    gesellschaft: str


def systemkennung(s: Session, erzeugen: bool = False) -> str | None:
    """Zufällige Kennung der Systemdatenbank (entsteht beim ersten Bedarf)."""
    wert = lade_merker(s, MERKER_SYSTEM)
    if wert is None and erzeugen:
        wert = setze_merker_einmal(s, MERKER_SYSTEM, uuid4().hex, datetime.now())
        s.commit()
    return wert


def _lies_bindung(s: Session) -> Bindung | None:
    roh = lade_merker(s, MERKER_BINDUNG)
    if roh is None:
        return None
    try:
        daten = json.loads(roh)
        return Bindung(str(daten["system"]), str(daten["gesellschaft"]))
    except (ValueError, KeyError, TypeError) as fehler:
        msg = "Der Merker auth_merker.benutzerverwaltung ist unlesbar"
        raise RechteError(msg) from fehler


def pruefe_bindung(
    db: str, system_url: str, s: Session, kuerzel: str
) -> Bindung | None:
    """Gehört ``db`` zu dieser Systemdatenbank und Gesellschaft? Sonst
    ``RechteError``. ``None``: noch nicht gebunden (und keine eigenen Benutzer)."""
    eigene = 0
    if gleiche_datenbank(db, system_url):
        bindung = _lies_bindung(s)
    else:
        with _sitzung(db) as g:
            bindung = _lies_bindung(g)
            eigene = anzahl_benutzer(g)
    if bindung is not None:
        if anzahl_benutzer(s) == 0 or systemkennung(s) != bindung.system:
            msg = (
                "Die Datenbank gehört zur Benutzerverwaltung einer anderen "
                "Systemdatenbank (die benutzte ist leer oder fremd) — "
                "ACCOUNTI_SYSTEM_DB bzw. gesellschaften.systemdatenbank prüfen"
            )
            raise RechteError(msg)
        if bindung.gesellschaft != kuerzel:
            msg = (
                f"Die Datenbank gehört zur Gesellschaft {bindung.gesellschaft}, nicht "
                f"{kuerzel} — accounti -g {bindung.gesellschaft} …"
            )
            raise RechteError(msg)
        return bindung
    if eigene:
        msg = (
            "Die Datenbank hat eigene Benutzer, geprüft würde aber gegen eine andere "
            "Systemdatenbank — ACCOUNTI_SYSTEM_DB bzw. gesellschaften.systemdatenbank "
            "prüfen"
        )
        raise RechteError(msg)
    return None


def _binde(db: str, system_url: str, s: Session, kuerzel: str) -> None:
    """Merker setzen — nur, wenn es noch keinen gibt; ein fremder bleibt (Fehler)."""
    if pruefe_bindung(db, system_url, s, kuerzel) is not None:
        return
    kennung = systemkennung(s, erzeugen=True)
    wert = json.dumps({"system": kennung, "gesellschaft": kuerzel}, sort_keys=True)
    if gleiche_datenbank(db, system_url):
        setze_merker_einmal(s, MERKER_BINDUNG, wert, datetime.now())
        s.commit()
    else:
        with _sitzung(db) as g:
            setze_merker_einmal(g, MERKER_BINDUNG, wert, datetime.now())
            g.commit()
    pruefe_bindung(db, system_url, s, kuerzel)  # gleichzeitig gesetzt: Gewinner prüfen


def _bindungsziele(kontext: Kontext, db: str, alle: bool) -> list[tuple[str, str]]:
    """(Kürzel, Datenbank) — mit Registry deren Datenbanken, sonst ``db``."""
    if not kontext.registry.eintraege:
        return [(kontext.kuerzel, db)]
    if not alle:
        g = kontext.gesellschaft
        return [(g.kuerzel, g.datenbank)] if g is not None else []
    ziele = []
    for kuerzel in sorted(kontext.registry.eintraege):
        try:
            ziele.append((kuerzel, kontext.registry.finde(kuerzel).datenbank))
        except KonfigurationError:
            continue  # fehlende Variable — die Gesellschaft bindet ihre erste Prüfung
    return ziele


def pruefe_bindungen(db: str, *, alle: bool = False) -> None:
    """Vor dem Anlegen oder Ändern von Benutzern: keine fremde Bindung (Fehler)."""
    kontext = aktueller_kontext().pruefe()
    system_url = kontext.systemdatenbank(db)
    with systemsitzung(db) as s:
        for kuerzel, url in _bindungsziele(kontext, db, alle):
            pruefe_bindung(url, system_url, s, kuerzel)


def binde_gesellschaften(db: str, *, alle: bool = False) -> None:
    """Nach dem Anlegen bzw. einer Rollenvergabe: Gesellschaften binden."""
    kontext = aktueller_kontext().pruefe()
    system_url = kontext.systemdatenbank(db)
    with systemsitzung(db) as s:
        for kuerzel, url in _bindungsziele(kontext, db, alle):
            _binde(url, system_url, s, kuerzel)


def _pruefe_registry(kontext: Kontext, db: str, config: str) -> None:
    """Mit Registry: ``--db``/``--config`` sind die der gewählten Gesellschaft."""
    g = kontext.gesellschaft
    if not kontext.registry.eintraege or g is None:
        return
    for option, passt in (
        ("--db", gleiche_datenbank(db, g.datenbank)),
        ("--config", gleicher_pfad(config, g.konfiguration)),
    ):
        if not passt:
            msg = (
                f"Mit eingerichteten Benutzern gelten Datenbank und Konfiguration der "
                f"Gesellschaft {g.kuerzel} — {option} weicht ab (ohne {option} oder "
                "mit passendem --gesellschaft aufrufen)"
            )
            raise RechteError(msg)


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
    """Für Befehle mit einem Recht. ``None``: keine Benutzer eingerichtet.

    Geprüft wird in der Gesellschaft, zu der ``db`` gehört (Registry und Merker);
    eine leere oder fremde Systemdatenbank führt zum Abbruch, nicht zu „frei“.
    """
    kontext = aktueller_kontext().pruefe()
    kuerzel = gesellschaft_fuer_rechte()
    system_url = kontext.systemdatenbank(db)
    with systemsitzung(db) as s:
        bindung = pruefe_bindung(db, system_url, s, kuerzel)
        if bindung is None and anzahl_benutzer(s) == 0:
            return None
        _pruefe_registry(kontext, db, config)
        if bindung is None:
            _binde(db, system_url, s, kuerzel)
        return pruefe_recht_in(
            s, auth_einstellungen(config), recht, person, kuerzel, frage
        )


def _pruefe_zustaendig(s: Session, handelnder: str, ziel: str) -> None:
    """Wer einen Benutzer verwaltet, ist Verwalter in **jeder** Gesellschaft, in
    der dieser Rollen hat — sonst übernähme ein Verwalter von b das Konto eines
    Freigebers von a (Passwort und zweiter Faktor gelten global)."""
    z = lade_benutzer(s, ziel)
    h = lade_benutzer(s, handelnder)
    if z is None or h is None:
        return
    noetig = {r.gesellschaft for r in rollen_von(s, z.id)}
    darf = {r.gesellschaft for r in rollen_von(s, h.id) if r.rolle is Rolle.VERWALTER}
    fehlend = sorted(noetig - darf)
    if fehlend:
        _verweigert(
            s, "recht_verweigert", h.name, Recht.VERWALTEN, ",".join(fehlend)[:30]
        )
        msg = (
            f"{ziel} hat Rollen in {', '.join(sorted(noetig))} — verwalten darf das "
            f"Konto nur, wer überall dort Verwalter ist ({handelnder} ist nicht "
            f"Verwalter in {', '.join(fehlend)})"
        )
        raise RechteError(msg)


def pruefe_verwaltung(
    db: str,
    config: str,
    selbst: str | None = None,
    frage: Frage = frage_einmalcode,
    ziel: str | None = None,
) -> str:
    """Wer Benutzer und Token verwalten will — gibt den Handelnden zurück.

    Einrichtungsphase: Solange kein aktiver Verwalter einen zweiten Faktor hat, ist
    alles erlaubt (sonst sperrte man sich beim Einrichten aus). Danach braucht es
    einen Verwalter mit Einmalcode — oder, bei ``selbst``, den Benutzer selbst mit
    seinem eingerichteten zweiten Faktor. Den ersten zweiten Faktor eines Benutzers
    richtet ein Verwalter ein: Sonst könnte jeder mit Zugang zur Server-Shell unter
    fremdem Namen einen Faktor anlegen. Geht es um einen Benutzer (``ziel``), muss
    der Verwalter das in jeder Gesellschaft sein, in der dieser Rollen hat.
    """
    person = aktueller_benutzername()
    aktueller_kontext().pruefe()
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
        if ziel is not None and ziel != person:
            _pruefe_zustaendig(s, person, ziel)
        return person


def _meldung(fehler: Exception) -> str:
    if isinstance(fehler, AnmeldungError):
        return "Einmalcode falsch, schon benutzt oder Benutzer gesperrt"
    return str(fehler)


def befehlsrecht_oder_ende(
    db: str, config: str, recht: Recht, person: str
) -> Benutzer | None:
    """Wie ``pruefe_befehlsrecht`` — Fehler werden zur Meldung mit Exit-Code 1."""
    try:
        return pruefe_befehlsrecht(db, config, recht, person)
    except (AuthError, TresorError, KonfigurationError) as fehler:
        console.print(f"[red]{escape(_meldung(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(1) from fehler


def verwaltung_oder_ende(
    db: str, config: str, selbst: str | None = None, ziel: str | None = None
) -> str:
    try:
        return pruefe_verwaltung(db, config, selbst, ziel=ziel)
    except (AuthError, TresorError, KonfigurationError) as fehler:
        console.print(f"[red]{escape(_meldung(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(1) from fehler


def bindung_oder_ende(db: str, *, alle: bool = False, binden: bool = False) -> None:
    """``pruefe_bindungen``/``binde_gesellschaften`` mit Meldung und Exit-Code 1."""
    try:
        if binden:
            binde_gesellschaften(db, alle=alle)
        else:
            pruefe_bindungen(db, alle=alle)
    except (AuthError, KonfigurationError) as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(1) from fehler
