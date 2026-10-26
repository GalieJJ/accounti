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
    loesche_merker,
    merker_mit_praefix,
    rollen_von,
    setze_merker_einmal,
)
from accounti.konfiguration import KonfigurationError
from accounti.models.auth import RECHT_TEXT, Benutzer, Recht, Rolle, rechte_der_rollen

UMGEBUNG_BENUTZER = "ACCOUNTI_BENUTZER"
UMGEBUNG_EINMALCODE = "ACCOUNTI_EINMALCODE"
MERKER_SYSTEM = "systemkennung"
MERKER_BINDUNG = "benutzerverwaltung"
# "verwaltet:<Kürzel>": die Gesellschaft hatte einen aktiven Verwalter mit zweitem
# Faktor — ihre Einrichtungsphase öffnet sich nie wieder (Befund Betrieb B8)
MERKER_VERWALTET = "verwaltet:"

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
    aufheben. Die Sperrwerte kommen nie aus der Datei: „strenger“ hieße hier eine
    Waffe (``fehlversuche_obergrenze: 1`` sperrte jeden mit einem falschen Code) —
    in der CLI gelten immer die Standardwerte. Im Browser gilt die Datei, mit der
    ``accounti serve`` startete.
    """
    s = AuthEinstellungen()
    return e.model_copy(
        update={
            "einmalcode_bestaetigung": True,
            "sperre_nach_fehlversuchen": s.sperre_nach_fehlversuchen,
            "sperre_minuten": s.sperre_minuten,
            "fehlversuche_obergrenze": s.fehlversuche_obergrenze,
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


def binde_neu(db: str, kuerzel: str) -> None:
    """Nach dem bewussten Übernehmen einer fremden Sicherung (``sicherung
    wiederherstellen --fremde-gesellschaft``): der mitgebrachte Merker der Herkunft
    fällt weg; gibt es Benutzer, gehört die Datenbank danach zu dieser
    Systemdatenbank und Gesellschaft. Nur in eine leere Umgebung möglich — also eine
    Handlung des Betreibers, kein Umweg um eine bestehende Bindung."""
    kontext = aktueller_kontext().pruefe()
    system_url = kontext.systemdatenbank(db)
    with _sitzung(db) as g:
        loesche_merker(g, MERKER_BINDUNG)
        g.commit()
    with systemsitzung(db) as s:
        if anzahl_benutzer(s) > 0:
            _binde(db, system_url, s, kuerzel)


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


def _pruefe_zustaendig(
    s: Session, handelnder: str, ziel: str, einrichtung: str | None = None
) -> None:
    """Wer einen Benutzer verwaltet, ist Verwalter in **jeder** Gesellschaft, in
    der dieser Rollen hat — sonst übernähme ein Verwalter von b das Konto eines
    Freigebers von a (Passwort und zweiter Faktor gelten global). Wer die
    Gesellschaft ``einrichtung`` einrichtet, gilt dort als ihr Verwalter — aber nur
    für Benutzer, die dort keine andere Rolle als ``verwalter`` haben (Nachprüfung
    N2): Die Einrichtung bestimmt den ersten Verwalter; Passwort, Codes und Rollen
    eines Freigebers von b gäben dem Verwalter von a dessen Konto."""
    z = lade_benutzer(s, ziel)
    h = lade_benutzer(s, handelnder)
    if z is None or h is None:
        return
    zuordnungen = rollen_von(s, z.id)
    noetig = {r.gesellschaft for r in zuordnungen}
    darf = {r.gesellschaft for r in rollen_von(s, h.id) if r.rolle is Rolle.VERWALTER}
    if einrichtung is not None:
        andere = sorted(
            r.rolle.value
            for r in zuordnungen
            if r.gesellschaft == einrichtung and r.rolle is not Rolle.VERWALTER
        )
        if andere:
            _verweigert(s, "recht_verweigert", h.name, Recht.VERWALTEN, einrichtung)
            msg = (
                f"{ziel} hat in {einrichtung} schon die Rolle {', '.join(andere)} — "
                f"die Einrichtung von {einrichtung} bestimmt nur den ersten Verwalter "
                "(neuer Benutzer oder einer, der dort nur Verwalter ist); "
                f"{ziel} verwaltet danach der Verwalter von {einrichtung}"
            )
            raise RechteError(msg)
        darf.add(einrichtung)
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


def verwalter_mit_faktor(s: Session, gesellschaft: str | None = None) -> list[Benutzer]:
    """Aktive Verwalter mit zweitem Faktor (in der Gesellschaft bzw. irgendwo).
    Nach Fehlversuchen gesperrte zählen mit (``aktiv`` bleibt) — eine Flut aus dem
    Netz öffnet keine Einrichtungsphase."""
    return [
        b
        for b in benutzer_mit_rolle(s, Rolle.VERWALTER, gesellschaft)
        if b.aktiv and b.totp_aktiv
    ]


def _merke_verwaltete(s: Session) -> set[str]:
    """Merker ``verwaltet:<K>`` für jede Gesellschaft mit einem aktiven Verwalter mit
    zweitem Faktor setzen; gibt alle so gemerkten Gesellschaften zurück."""
    jetzt = datetime.now()
    neu = False
    for b in verwalter_mit_faktor(s):
        for z in rollen_von(s, b.id):
            schluessel = MERKER_VERWALTET + z.gesellschaft
            if z.rolle is Rolle.VERWALTER and lade_merker(s, schluessel) is None:
                setze_merker_einmal(s, schluessel, b.name, jetzt)
                neu = True
    if neu:
        s.commit()
    return {
        m.removeprefix(MERKER_VERWALTET)
        for m in merker_mit_praefix(s, MERKER_VERWALTET)
    }


def pruefe_verwaltung(
    db: str,
    config: str,
    selbst: str | None = None,
    frage: Frage = frage_einmalcode,
    ziel: str | None = None,
) -> str:
    """Wer Benutzer und Token verwalten will — gibt den Handelnden zurück.

    Einrichtungsphase der Installation: Solange kein aktiver Verwalter einen zweiten
    Faktor hat **und** keine Gesellschaft je einen hatte (Merker ``verwaltet:``), ist
    alles erlaubt (sonst sperrte man sich beim Einrichten aus). Danach braucht es
    einen Verwalter der Gesellschaft mit Einmalcode — oder, bei ``selbst``, den
    Benutzer selbst mit seinem eingerichteten zweiten Faktor. Den ersten zweiten
    Faktor eines Benutzers richtet ein Verwalter ein: Sonst könnte jeder mit Zugang
    zur Server-Shell unter fremdem Namen einen Faktor anlegen. Geht es um einen
    Benutzer (``ziel``), muss der Verwalter das in jeder Gesellschaft sein, in der
    dieser Rollen hat.

    Einrichtungsphase einer Gesellschaft (Befund Betrieb B7): Hatte die gewählte
    Gesellschaft noch nie einen aktiven Verwalter mit zweitem Faktor (zweite oder
    später ergänzte Gesellschaft), genügt ein Verwalter irgendeiner Gesellschaft mit
    Einmalcode — Ereignis ``einrichtung_gesellschaft`` im Protokoll. Den letzten
    Verwalter sperren oder entrechten lehnt ``pruefe_nicht_letzter_verwalter`` ab;
    der Merker hält die Phase auch dann geschlossen, wenn er an accounti vorbei
    wegfällt (Befund B8, fail-closed).
    """
    person = aktueller_benutzername()
    kontext = aktueller_kontext().pruefe()
    gesellschaft = kontext.gesellschaft.kuerzel if kontext.gesellschaft else None
    if gesellschaft is None and not kontext.registry.eintraege:
        gesellschaft = kontext.kuerzel
    with systemsitzung(db) as s:
        verwaltet = _merke_verwaltete(s)
        if not verwaltet and not verwalter_mit_faktor(s):
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
        einrichtung = (
            gesellschaft
            if gesellschaft is not None
            and gesellschaft not in verwaltet
            and not verwalter_mit_faktor(s, gesellschaft)
            else None
        )
        pruefe_recht_in(
            s,
            e,
            Recht.VERWALTEN,
            person,
            None if einrichtung else gesellschaft,
            frage,
        )
        if einrichtung is not None:
            ereignis(
                s,
                "einrichtung_gesellschaft",
                datetime.now(),
                person,
                gesellschaft=einrichtung,
                hinweis="noch kein Verwalter mit zweitem Faktor — eingerichtet "
                "durch den Verwalter einer anderen Gesellschaft",
            )
            s.commit()
        if ziel is not None and ziel != person:
            _pruefe_zustaendig(s, person, ziel, einrichtung)
        return person


def pruefe_nicht_letzter_verwalter(
    s: Session, b: Benutzer, gesellschaft: str | None = None
) -> None:
    """``RechteError``, wenn ``b`` in der Gesellschaft (ohne Angabe: in einer seiner
    Verwalter-Gesellschaften) der letzte aktive Verwalter mit zweitem Faktor ist.

    Für ``benutzer sperren`` und ``rolle verwalter --entfernen``: Sonst stünde die
    Gesellschaft ohne Verwalter da — früher öffnete das die Einrichtungsphase für
    jeden an der Shell (Befund Betrieb B8), heute bliebe nur die Datenbank."""
    if not (b.aktiv and b.totp_aktiv):
        return  # zählt ohnehin nicht als Verwalter
    eigene = {z.gesellschaft for z in rollen_von(s, b.id) if z.rolle is Rolle.VERWALTER}
    orte = sorted(eigene if gesellschaft is None else eigene & {gesellschaft})
    for k in orte:
        if not [v for v in verwalter_mit_faktor(s, k) if v.id != b.id]:
            msg = (
                f"{b.name} ist der letzte aktive Verwalter mit zweitem Faktor in {k} "
                f"— erst einen weiteren einrichten (accounti -g {k} benutzer rolle "
                "NAME --rolle verwalter, dann benutzer 2fa NAME); nichts geändert"
            )
            raise RechteError(msg)


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
