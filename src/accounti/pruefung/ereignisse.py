"""Journal-Ereignisse und die Sperre freigegebener Buchungen — zentral auf der Sitzung.

Eingehängt von ``accounti.db.session_factory`` bzw. ``init_db``
(``registriere_ereignisse``), nicht durch den Import eines Tabellenmoduls.

* ``before_flush`` liest den gespeicherten Stand jeder geänderten oder gelöschten
  Zeile der erfassten Tabellen aus der Datenbank — nie aus der Attribut-Historie, die
  nach einem ``commit`` leer ist. Für Buchungen prüft es damit Jahres- und
  Monatssperre (gespeichertes und neues Datum) und „Storno statt Änderung“: Eine
  freigegebene Buchung (``auto``, ``geprueft``, ``korrigiert``, ``exportiert``) ändert
  sich nur noch auf dem Statusweg ``auto → geprueft`` bzw. ``→ exportiert`` und durch
  den einmaligen Stornovermerk ``storniert_durch``, der auf eine Stornobuchung mit
  ``storno_von`` zeigen muss; gelöscht wird sie nie (``BuchungFestgeschriebenError``).
  Der Primärschlüssel einer erfassten Zeile ändert sich nie.
* ``after_flush`` liest den neuen Stand und hängt je Vorgang einen Journaleintrag an
  — in derselben Transaktion.
* ``do_orm_execute`` lehnt Massen-``INSERT``/``UPDATE``/``DELETE`` über das ORM auf
  Buchungen, Journal und Korrekturen ab: Sie gingen an beidem vorbei. Die alten
  ``bulk_*``-Wege sperrt die Sitzungsklasse aus ``session_factory``.

Erfasst werden ``buchungssaetze``, ``belege``, ``beleg_eingaenge`` (verworfene
Dubletten), ``zahlungslaeufe`` (Anlage), ``zahlungslauf_protokoll`` (Statuswechsel)
und ``abschlussprotokoll`` (Jahres- und Monatsabschlüsse, Öffnen). Die Sperrtabellen
``abschluesse`` und ``periodenabschluesse`` selbst nicht — ihren Stand gleicht
``journal.pruefe_journal`` mit dem Journal ab. Rohes SQL umgeht die Ereignisse —
dafür gibt es die Hash-Kette und den Bestandsabgleich in ``journal.pruefe_journal``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, Table, event, inspect, select
from sqlalchemy.orm import ORMExecuteState, Session, UOWTransaction

from accounti.db import GESCHUETZT
from accounti.db.tabellen import (
    BelegEingangRow,
    BelegRow,
    BuchungssatzRow,
    UnveraenderbarError,
)
from accounti.db.tabellen_abschluss import SPERRCACHE, VORAB_GEPRUEFT, ProtokollRow
from accounti.db.tabellen_pruefung import sperrfehler
from accounti.db.tabellen_zahlung import LaufProtokollRow, ZahlungslaufRow
from accounti.pruefung.journal import (
    Vorgang,
    fuege_an,
    journal_vorhanden,
    schnappschuss,
    schreibsperre,
)

FREIGEGEBEN = frozenset({"auto", "geprueft", "korrigiert", "exportiert"})
VORSCHLAG = frozenset({"entwurf", "pruefung"})
# erlaubte Statuswege einer freigegebenen Buchung
STATUSWEGE = frozenset(
    {
        ("auto", "geprueft"),
        ("auto", "exportiert"),
        ("geprueft", "exportiert"),
        ("korrigiert", "exportiert"),
    }
)
_INFO = "accounti_journal_vorher"
# Felder einer Buchung, die keinen Inhalt tragen (Status, Prüfvermerk)
_VERMERKE = frozenset({"status", "geprueft_von", "confidence", "storniert_durch"})


class BuchungFestgeschriebenError(UnveraenderbarError):
    """Eine freigegebene Buchung soll geändert oder gelöscht werden."""


Zeile = dict[str, Any]


@dataclass(frozen=True)
class Eintrag:
    """Was ein Vorgang ins Journal schreibt; leere Felder füllt die Erfassung."""

    vorgang: str
    bezug: str | None = None
    objekt_typ: str | None = None
    objekt_id: str | None = None
    person: str | None = None
    grund: str | None = None
    ohne_stand: bool = False  # Vorher/Nachher nicht mitschreiben


Einordnung = Callable[[Zeile | None, Zeile | None], list[Eintrag]]


@dataclass(frozen=True)
class Erfassung:
    objekt_typ: str
    einordnen: Einordnung
    ohne: frozenset[str] = frozenset()  # Spalten, die nicht ins Journal gehören


ERFASST: dict[str, Erfassung] = {}


def erfasse(tabelle: Table, erfassung: Erfassung) -> None:
    """Weitere Tabelle ins Journal aufnehmen."""
    ERFASST[tabelle.name] = erfassung


# --- Einordnung: welcher Vorgang ist das? ------------------------------------------


def _pruefvermerk(v: Zeile | None, n: Zeile) -> str | None:
    """Bei Freigabe und Korrektur zählt der neue Prüfvermerk der Buchung."""
    von = n.get("geprueft_von")
    if von and (v is None or v.get("geprueft_von") != von):
        return str(von)
    return None


def _buchung(v: Zeile | None, n: Zeile | None) -> list[Eintrag]:
    if v is None and n is not None:
        if n.get("storno_von"):
            return [Eintrag("storno_gebucht", n["storno_von"])]
        return [Eintrag("buchung_angelegt")]
    if n is None:
        return [Eintrag("buchung_verworfen")]
    assert v is not None
    geaendert = {k for k in set(v) | set(n) if v.get(k) != n.get(k)}
    person = _pruefvermerk(v, n)
    vorgaenge: list[Eintrag] = []
    if geaendert - _VERMERKE:
        vorgaenge.append(Eintrag("buchung_korrigiert", person=person))
    alt, neu = v.get("status"), n.get("status")
    if alt != neu:
        if neu == "exportiert":
            vorgaenge.append(Eintrag("buchung_exportiert"))
        elif neu in FREIGEGEBEN:
            vorgaenge.append(Eintrag("buchung_freigegeben", person=person))
    if "storniert_durch" in geaendert and n.get("storniert_durch"):
        vorgaenge.append(Eintrag("buchung_storniert", n["storniert_durch"]))
    return vorgaenge or [Eintrag("buchung_geaendert")]


_BELEGFREIGABE: ContextVar[bool] = ContextVar("accounti_belegfreigabe", default=False)


@contextmanager
def belegfreigabe() -> Iterator[None]:
    """Block, in dem ein Mensch Belege freigibt (``accounti belege freigeben``): nur
    dort steht ``beleg_freigegeben`` im Journal — nicht, wenn ``belege erkennen`` einen
    Beleg aus der Prüfung neu liest und er jetzt vollständig ist."""
    token = _BELEGFREIGABE.set(True)
    try:
        yield
    finally:
        _BELEGFREIGABE.reset(token)


def _beleg(v: Zeile | None, n: Zeile | None) -> list[Eintrag]:
    if v is None:
        return [Eintrag("beleg_importiert")]
    if n is None:
        return [Eintrag("beleg_geloescht")]
    if _BELEGFREIGABE.get():
        return [Eintrag("beleg_freigegeben")]  # accounti belege freigeben
    return [Eintrag("beleg_geaendert")]


def _eingang(v: Zeile | None, n: Zeile | None) -> list[Eintrag]:
    # nur die verworfene Dublette — ein neuer Beleg steht schon als beleg_importiert
    if v is None and n is not None and n.get("ergebnis") == "dublette":
        return [Eintrag("beleg_verworfen", n.get("beleg_id"))]
    return []


def _zahlungslauf(v: Zeile | None, n: Zeile | None) -> list[Eintrag]:
    # Statuswechsel stehen mit Person im Protokoll des Laufs (siehe _laufprotokoll)
    if v is None and n is not None:
        return [Eintrag("zahlungslauf_angelegt", person=n.get("erstellt_von"))]
    return []


def _laufprotokoll(v: Zeile | None, n: Zeile | None) -> list[Eintrag]:
    if v is not None or n is None or not n.get("nach_status"):
        return []
    # ohne Ausgangsstatus: die Anlage — sie steht schon als zahlungslauf_angelegt
    if not n.get("von_status") or n.get("nach_status") == n.get("von_status"):
        return []
    return [
        Eintrag(
            f"zahlungslauf_{n['nach_status']}",
            objekt_typ="zahlungslauf",
            objekt_id=str(n["lauf_id"]),
            person=n.get("person"),
            grund=n.get("text"),
        )
    ]


# Abschlussprotokoll (Baustein 12) → Journal: Jahres- und Monatsabschlüsse
_ABSCHLUSS = {
    "abgeschlossen": ("jahr_abgeschlossen", "geschaeftsjahr"),
    "geoeffnet": ("jahr_geoeffnet", "geschaeftsjahr"),
    "periode_geschlossen": ("periode_geschlossen", "periode"),
    "periode_geoeffnet": ("periode_geoeffnet", "periode"),
}


def _abschlussprotokoll(v: Zeile | None, n: Zeile | None) -> list[Eintrag]:
    if v is not None or n is None or n.get("aktion") not in _ABSCHLUSS:
        return []
    vorgang, typ = _ABSCHLUSS[n["aktion"]]
    ident = str(n["jahr"])
    if typ == "periode":
        with suppress(ValueError):
            ident = str(json.loads(n.get("details") or "{}").get("monat") or ident)
    return [
        Eintrag(
            vorgang,
            objekt_typ=typ,
            objekt_id=ident,
            person=n.get("von"),
            grund=n.get("grund"),
            bezug=f"abschlussprotokoll {n['nr']}",
        )
    ]


erfasse(BuchungssatzRow.__table__, Erfassung("buchung", _buchung))  # type: ignore[arg-type]
erfasse(BelegRow.__table__, Erfassung("beleg", _beleg))  # type: ignore[arg-type]
erfasse(
    BelegEingangRow.__table__,  # type: ignore[arg-type]
    Erfassung("beleg_eingang", _eingang),
)
erfasse(
    ZahlungslaufRow.__table__,  # type: ignore[arg-type]
    Erfassung("zahlungslauf", _zahlungslauf, ohne=frozenset({"datei", "version"})),
)
erfasse(
    LaufProtokollRow.__table__,  # type: ignore[arg-type]
    Erfassung("zahlungslauf_protokoll", _laufprotokoll),
)
erfasse(
    ProtokollRow.__table__,  # type: ignore[arg-type]
    Erfassung("abschlussprotokoll", _abschlussprotokoll),
)


# --- Hilfen --------------------------------------------------------------------------

# so viele Schlüssel je IN-Abfrage (SQLite kennt eine Obergrenze für Parameter)
_JE_ABFRAGE = 500


def gesperrt(
    verbindung: Connection, tag: date | None, cache: dict[str, Any] | None = None
) -> bool:
    """Liegt der Tag in einem abgeschlossenen Jahr oder festgeschriebenen Monat?"""
    return tag is not None and sperrfehler(verbindung, tag, cache) is not None


def _tabelle(obj: object) -> Table | None:
    zustand: Any = inspect(obj, raiseerr=False)
    if zustand is None:  # pragma: no cover — kein ORM-Objekt
        return None
    tabelle = zustand.mapper.local_table
    if isinstance(tabelle, Table) and tabelle.name in ERFASST:
        return tabelle
    return None


def _schluessel(obj: object) -> str:
    """Der gespeicherte Primärschlüssel (Identität), bei neuen Objekten der gesetzte."""
    zustand: Any = inspect(obj)
    if zustand.identity is not None:
        (wert,) = zustand.identity
    else:
        (wert,) = zustand.mapper.primary_key_from_instance(obj)
    return str(wert)


def _pruefe_schluessel(obj: object, tabelle: Table, gesetzt: dict[str, Any]) -> None:
    """Der Primärschlüssel einer erfassten Zeile ändert sich nie (Journal, Bestand)."""
    zustand: Any = inspect(obj)
    if zustand.identity is None:
        return
    (spalte,) = zustand.mapper.primary_key
    schluessel = zustand.mapper.get_property_by_column(spalte).key
    if schluessel in gesetzt and str(gesetzt[schluessel]) != str(zustand.identity[0]):
        raise UnveraenderbarError(
            f"Primärschlüssel von {tabelle.name} {str(zustand.identity[0])[:8]} "
            "darf sich nicht ändern — neu anlegen statt umschlüsseln"
        )


def _je_abfrage(werte: list[Any]) -> Iterator[list[Any]]:
    for start in range(0, len(werte), _JE_ABFRAGE):
        yield werte[start : start + _JE_ABFRAGE]


def _lies(session: Session, tabelle: Table, schluessel: set[str]) -> dict[str, Zeile]:
    """Gespeicherte Zeilen, normiert, je Primärschlüssel."""
    if not schluessel:
        return {}
    (pk,) = tabelle.primary_key.columns
    werte: list[Any] = [int(s) if pk.type.python_type is int else s for s in schluessel]
    ohne = ERFASST[tabelle.name].ohne
    ergebnis: dict[str, Zeile] = {}
    for teil in _je_abfrage(werte):
        zeilen = session.connection().execute(select(tabelle).where(pk.in_(teil)))
        for z in zeilen.mappings():
            ergebnis[str(z[pk.name])] = schnappschuss(tabelle, z, ohne)
    return ergebnis


def _rohe_buchungen(session: Session, ids: set[str]) -> dict[str, Any]:
    t = BuchungssatzRow.__table__
    ergebnis: dict[str, Any] = {}
    for teil in _je_abfrage(sorted(ids)):
        zeilen = session.connection().execute(select(t).where(t.c.id.in_(teil)))
        ergebnis |= {z["id"]: z for z in zeilen.mappings()}
    return ergebnis


def _gesetzt(obj: object) -> dict[str, Any]:
    """Die in dieser Sitzung gesetzten Attribute mit ihrem neuen Wert.

    ``committed_state`` führt genau die gesetzten Attribute (auch abgelaufene) — das
    ist billiger, als die Historie aller Spalten je Zeile abzufragen."""
    zustand: Any = inspect(obj)
    return {k: zustand.dict.get(k) for k in zustand.committed_state}


def _aenderungen(zeile: BuchungssatzRow, gespeichert: Any) -> dict[str, Any]:
    """Was sich gegenüber dem gespeicherten Stand ändert: Spalte → neuer Wert."""
    return {k: w for k, w in _gesetzt(zeile).items() if w != gespeichert.get(k)}


def _nur_stornovermerk(neu: dict[str, Any], gespeichert: Any) -> bool:
    return (
        set(neu) == {"storniert_durch"}
        and gespeichert["storniert_durch"] is None
        and bool(neu["storniert_durch"])
    )


def _hinweis(gespeichert: Any) -> str:
    kurz = str(gespeichert["id"])[:8]
    return (
        f"Buchung {kurz} ist freigegeben ({gespeichert['status']}) — Korrektur nur per "
        f"Storno mit Neubuchung: accounti korrigiere {kurz} --soll … --haben … "
        f"[--steuer … | --ohne-steuer] (oder accounti buchung storniere {kurz})"
    )


def _pruefe_sperre(
    verbindung: Connection,
    gespeichert: Any,
    neu: dict[str, Any],
    geloescht: bool,
    cache: dict[str, Any],
) -> None:
    """Jahres- und Monatssperre nach dem gespeicherten und dem neuen Datum.

    Der gespeicherte Stand kommt aus der Datenbank — ein abgelaufenes Attribut (nach
    ``commit``) verbirgt das alte Datum also nicht. Angenommen wird im gesperrten
    Zeitraum nur der einmalige Stornovermerk."""
    if not geloescht and (not neu or _nur_stornovermerk(neu, gespeichert)):
        return
    tage = {gespeichert["datum"], neu.get("datum")} - {None}
    for tag in sorted(tage):
        if (fehler := sperrfehler(verbindung, tag, cache)) is not None:
            raise fehler


def _pruefe_festschreibung(
    gespeichert: Any, neu: dict[str, Any], geloescht: bool
) -> None:
    """Storno statt Änderung: was an einer freigegebenen Buchung noch geht."""
    status = gespeichert["status"]
    if status not in FREIGEGEBEN:
        return
    hinweis = _hinweis(gespeichert)
    if geloescht:
        raise BuchungFestgeschriebenError(hinweis)
    if not neu:
        return
    erlaubt = {"status", "geprueft_von", "storniert_durch"}
    if set(neu) - erlaubt:
        felder = ", ".join(sorted(set(neu) - erlaubt))
        raise BuchungFestgeschriebenError(f"{hinweis}; geändert: {felder}")
    if "status" in neu and (status, neu["status"]) not in STATUSWEGE:
        raise BuchungFestgeschriebenError(
            f"{hinweis}; Status {status} → {neu['status']} nicht erlaubt"
        )
    if "geprueft_von" in neu and not (
        status == "auto" and neu.get("status") == "geprueft"
    ):
        raise BuchungFestgeschriebenError(f"{hinweis}; Prüfvermerk festgeschrieben")
    if "storniert_durch" in neu and (
        gespeichert["storniert_durch"] is not None or not neu["storniert_durch"]
    ):
        kurz = str(gespeichert["id"])[:8]
        raise BuchungFestgeschriebenError(f"Buchung {kurz} ist schon storniert")


_SPIEGEL = ("storno_von", "status", "soll_konto", "haben_konto", "betrag_netto")
_GLEICH = ("betrag_netto", "steuer_schluessel", "steuer_betrag")


def _spiegelt(storno: dict[str, Any], original: Any) -> bool:
    """Freigegebene Gegenbuchung: Seiten getauscht, Beträge und Schlüssel gleich."""
    return (
        str(storno["storno_von"]) == str(original["id"])
        and storno["status"] in FREIGEGEBEN
        and storno["soll_konto"] == original["haben_konto"]
        and storno["haben_konto"] == original["soll_konto"]
        and all(
            (storno[f] is None and original[f] is None)
            or (
                storno[f] is not None
                and original[f] is not None
                and Decimal(str(storno[f])) == Decimal(str(original[f]))
            )
            for f in _GLEICH
        )
    )


def _pruefe_stornovermerke(
    session: Session,
    vermerke: dict[str, tuple[str, Any]],
    neue: list[BuchungssatzRow],
) -> None:
    """Ein Stornovermerk zeigt auf eine freigegebene Stornobuchung, die ``storno_von``
    auf das Original setzt und es spiegelt — sonst fiele die Buchung ohne Gegenbuchung
    (oder mit einer beliebigen) aus allen Läufen."""
    if not vermerke:
        return
    ziele = {storno for storno, _ in vermerke.values()}
    felder = (*_SPIEGEL, "steuer_schluessel", "steuer_betrag")
    gefunden = {
        str(z.id): {f: getattr(z, f) for f in felder}
        for z in neue
        if str(z.id) in ziele
    }
    t = BuchungssatzRow.__table__
    for teil in _je_abfrage(sorted(ziele - set(gefunden))):
        zeilen = session.connection().execute(
            select(t.c.id, *(t.c[f] for f in felder)).where(t.c.id.in_(teil))
        )
        gefunden |= {str(z["id"]): dict(z) for z in zeilen.mappings()}
    for original, (storno, gespeichert) in vermerke.items():
        zeile = gefunden.get(storno)
        if zeile is None or not _spiegelt(zeile, gespeichert):
            raise BuchungFestgeschriebenError(
                f"Buchung {original[:8]}: Stornovermerk ohne Stornobuchung — "
                f"{storno[:8]} ist kein freigegebenes, spiegelbildliches Storno dieser "
                f"Buchung (accounti buchung storniere {original[:8]})"
            )


# --- Ereignisse ---------------------------------------------------------------------


# Tabellen, deren Änderung Prüfung oder Journal braucht: die erfassten (ERFASST),
# die geschützten und die Sperren selbst
_SPERRBEDARF = frozenset(
    {"journal", "buchungskorrekturen", "abschluesse", "periodenabschluesse"}
)


def _ohne_buchungsbezug(name: str) -> bool:
    """Anmeldedaten (Systemdatenbank) — nie in einer Transaktion mit Buchungen."""
    return name.startswith("auth_") or name == "api_tokens"


def _braucht_sperre(session: Session) -> bool:
    """Braucht dieser Flush die Schreibsperre?

    Ja, wenn er eine Tabelle mit Journal- oder Sperrbezug berührt. Unter PostgreSQL
    außerdem, wenn er bestehende Zeilen ändert oder löscht (außer Anmeldedaten):
    Die Advisory-Sperre ist dann die erste Sperre jeder Transaktion, die beides
    braucht — holte eine Transaktion erst Zeilensperren und danach die
    Advisory-Sperre, während eine andere es umgekehrt tut, entstünde ein Deadlock.
    Neue Zeilen sperren nichts, was andere sehen — außer bei eindeutigen Schlüsseln:
    Fügen zwei Transaktionen gleichzeitig denselben Wert ein, wartet die zweite auf
    die erste, und mit der Advisory-Sperre dazwischen bricht eine davon als Deadlock
    ab (Daten bleiben konsistent; siehe Plan, Grenzen). Anmeldungen warten nicht."""
    namen = _SPERRBEDARF | GESCHUETZT | ERFASST.keys()
    postgres = session.get_bind().dialect.name == "postgresql"
    for aendert, menge in (
        (False, session.new),
        (True, session.dirty),
        (True, session.deleted),
    ):
        for obj in menge:
            zustand: Any = inspect(obj, raiseerr=False)
            if zustand is None:  # pragma: no cover — kein ORM-Objekt
                continue
            name = zustand.mapper.local_table.name
            if name in namen or (
                postgres and aendert and not _ohne_buchungsbezug(name)
            ):
                return True
    return False


@event.listens_for(Session, "before_flush")
def _vor_dem_schreiben(session: Session, _: UOWTransaction, __: object) -> None:
    # erst die Schreibsperre, dann lesen und prüfen: kein zweiter Schreiber ändert
    # den geprüften Stand, bevor dieser Flush schreibt (auch nicht die Sperren). Ein
    # Flush ohne Journal- und Sperrbezug (Umsätze, Anmeldungen, Sitzungen) holt sie
    # nicht — unter PostgreSQL warteten sonst alle Schreiber auf jede Transaktion,
    # die irgendwann einmal flushte (z.B. während einer TAN-Abfrage)
    if not _braucht_sperre(session):
        return
    schreibsperre(session.connection())
    cache: dict[str, Any] = {}  # Sperren für diesen Flush (auch für die Mapper)
    session.info[SPERRCACHE] = cache
    # je Flush frisch: Reste eines gescheiterten Flushs gelten nicht mehr
    vorher: dict[tuple[str, str], Zeile] = {}
    session.info[_INFO] = vorher
    ziele: dict[str, set[str]] = defaultdict(set)
    tabellen: dict[str, Table] = {}
    buchungen: list[tuple[BuchungssatzRow, bool]] = []
    geloeschte = set(session.deleted)
    for obj in list(session.dirty) + list(geloeschte):
        tabelle = _tabelle(obj)
        if tabelle is None:
            continue
        geloescht = obj in geloeschte
        gesetzt = {} if geloescht else _gesetzt(obj)
        if not geloescht and not gesetzt:
            continue
        if not geloescht:
            _pruefe_schluessel(obj, tabelle, gesetzt)
        tabellen[tabelle.name] = tabelle
        ziele[tabelle.name].add(_schluessel(obj))
        if isinstance(obj, BuchungssatzRow):
            buchungen.append((obj, geloescht))
    if buchungen:
        t: Table = BuchungssatzRow.__table__  # type: ignore[assignment]
        roh = _rohe_buchungen(session, ziele.pop(t.name))
        ohne = ERFASST[t.name].ohne
        for pk, z in roh.items():  # derselbe gespeicherte Stand fürs Journal
            vorher[(t.name, str(pk))] = schnappschuss(t, z, ohne)
        verbindung = session.connection()
        vermerke: dict[str, tuple[str, Any]] = {}
        for b, geloescht in buchungen:
            gespeichert = roh.get(_schluessel(b))
            if gespeichert is None:
                continue
            neu = {} if geloescht else _aenderungen(b, gespeichert)
            _pruefe_sperre(verbindung, gespeichert, neu, geloescht, cache)
            _pruefe_festschreibung(gespeichert, neu, geloescht)
            if not geloescht:  # die Mapper-Sperre muss diese Zeile nicht noch einmal
                cache.setdefault(VORAB_GEPRUEFT, set()).add(id(b))
            if neu.get("storniert_durch"):
                vermerke[str(gespeichert["id"])] = (
                    str(neu["storniert_durch"]),
                    gespeichert,
                )
        neue = [o for o in session.new if isinstance(o, BuchungssatzRow)]
        _pruefe_stornovermerke(session, vermerke, neue)
    for name, schluessel in ziele.items():
        for pk, zeile in _lies(session, tabellen[name], schluessel).items():
            vorher[(name, pk)] = zeile


@event.listens_for(Session, "after_flush")
def _nach_dem_schreiben(session: Session, _: UOWTransaction) -> None:
    session.info.pop(SPERRCACHE, None)
    vorher: dict[tuple[str, str], Zeile] = session.info.pop(_INFO, {})
    verbindung = session.connection()
    if not journal_vorhanden(verbindung):
        return
    reihe: list[tuple[Table, str, bool]] = []  # (Tabelle, Schlüssel, gelöscht)
    neu_angelegt: set[tuple[str, str]] = set()
    for obj in session.new:  # einmal gebildet: ``session.new`` kostet je Zugriff O(n)
        if (tabelle := _tabelle(obj)) is not None:
            pk = _schluessel(obj)
            neu_angelegt.add((tabelle.name, pk))
            reihe.append((tabelle, pk, False))
    for weg, objekte in ((False, session.dirty), (True, session.deleted)):
        for obj in objekte:
            if (tabelle := _tabelle(obj)) is None:
                continue
            pk = _schluessel(obj)
            if (tabelle.name, pk) not in vorher:
                continue  # nicht wirklich geändert
            if weg and (tabelle.name, pk) in neu_angelegt:
                continue  # gelöscht und mit derselben ID neu angelegt: eine Änderung
            reihe.append((tabelle, pk, weg))
    if not reihe:
        return
    je_tabelle: dict[str, set[str]] = defaultdict(set)
    tabellen = {}
    for tabelle, pk, weg in reihe:
        tabellen[tabelle.name] = tabelle
        if not weg:
            je_tabelle[tabelle.name].add(pk)
    # der neue Stand immer aus der Datenbank (nicht aus dem Vorher-Stand abgeleitet)
    nachher = {
        (name, pk): zeile
        for name, schluessel in je_tabelle.items()
        for pk, zeile in _lies(session, tabellen[name], schluessel).items()
    }
    vorgaenge = []
    for tabelle, pk, weg in reihe:
        erfassung = ERFASST[tabelle.name]
        v = vorher.get((tabelle.name, pk))
        n = None if weg else nachher.get((tabelle.name, pk))
        if v is not None and n is not None and v == n:
            continue
        for e in erfassung.einordnen(v, n):
            vorgaenge.append(
                Vorgang(
                    e.vorgang,
                    e.objekt_typ or erfassung.objekt_typ,
                    e.objekt_id or pk,
                    vorher=None if e.ohne_stand else v,
                    nachher=None if e.ohne_stand else n,
                    bezug=e.bezug,
                    person=e.person,
                    grund=e.grund,
                )
            )
    fuege_an(verbindung, vorgaenge)


@event.listens_for(Session, "do_orm_execute")
def _keine_massenaenderung(zustand: ORMExecuteState) -> None:
    if not (zustand.is_insert or zustand.is_update or zustand.is_delete):
        return
    namen = {mapper.local_table.name for mapper in zustand.all_mappers}  # type: ignore[attr-defined]
    # auch Core-DML auf die Tabelle, wenn sie über die Sitzung läuft — durch Aliase
    # hindurch, der Name ohne Schema und Groß-/Kleinschreibung (SQLite unterscheidet
    # sie nicht)
    ziel = getattr(zustand.statement, "table", None)
    for _ in range(10):
        weiter = getattr(ziel, "element", None)
        if weiter is None or weiter is ziel:
            break
        ziel = weiter
    namen.add(getattr(ziel, "name", None))
    for name in sorted(
        str(n).split(".")[-1].strip('"`[] ').lower() for n in namen if n
    ):
        if name in GESCHUETZT:
            msg = (
                f"Massenänderung an {name} ist gesperrt — Buchungen einzeln über die "
                "Sitzung anlegen und ändern (Journal, Storno-Regel, Sperren)"
            )
            raise UnveraenderbarError(msg)
