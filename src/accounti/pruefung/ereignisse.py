"""Journal-Ereignisse und die Sperre freigegebener Buchungen — zentral auf der Sitzung.

* ``before_flush`` liest den gespeicherten Stand jeder geänderten oder gelöschten
  Zeile der erfassten Tabellen aus der Datenbank. Für Buchungen prüft es dabei
  „Storno statt Änderung“: Eine freigegebene Buchung (``auto``, ``geprueft``,
  ``korrigiert``, ``exportiert``) ändert sich nur noch auf dem Statusweg
  ``auto → geprueft`` bzw. ``→ exportiert`` und durch den einmaligen Stornovermerk
  ``storniert_durch``; gelöscht wird sie nie (``BuchungFestgeschriebenError``).
* ``after_flush`` liest den neuen Stand und hängt je Vorgang einen Journaleintrag an
  — in derselben Transaktion.
* ``do_orm_execute`` lehnt Massen-``UPDATE``/``DELETE`` über das ORM auf Buchungen und
  Journal ab: Sie gingen an beidem vorbei.

Erfasst werden ``buchungssaetze``, ``belege``, ``beleg_eingaenge`` (verworfene
Dubletten), ``zahlungslaeufe`` (Anlage und Statuswechsel), ``abschluesse`` und
``periodenabschluesse``. Rohes SQL umgeht die Ereignisse — dafür gibt es die
Hash-Kette und den Bestandsabgleich in ``journal.pruefe_journal``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Connection, Table, event, inspect, select
from sqlalchemy.orm import ORMExecuteState, Session, UOWTransaction

from accounti.db.tabellen import (
    BelegEingangRow,
    BelegRow,
    BuchungssatzRow,
    UnveraenderbarError,
)
from accounti.db.tabellen_abschluss import ProtokollRow, jahr_gesperrt
from accounti.db.tabellen_pruefung import JournalRow
from accounti.db.tabellen_zahlung import LaufProtokollRow, ZahlungslaufRow
from accounti.pruefung.journal import (
    Vorgang,
    fuege_an,
    journal_vorhanden,
    schnappschuss,
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


def _beleg(v: Zeile | None, n: Zeile | None) -> list[Eintrag]:
    if v is None:
        return [Eintrag("beleg_importiert")]
    if n is None:
        return [Eintrag("beleg_geloescht")]
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

# Sperrprüfungen je Datum (Jahressperre aus Baustein 12, Monatssperre aus perioden)
SPERREN: list[Callable[[Connection, date], bool]] = [
    lambda verbindung, tag: jahr_gesperrt(verbindung, tag.year)
]


def gesperrt(verbindung: Connection, tag: date | None) -> bool:
    return tag is not None and any(pruefe(verbindung, tag) for pruefe in SPERREN)


def _tabelle(obj: object) -> Table | None:
    zustand: Any = inspect(obj, raiseerr=False)
    if zustand is None:  # pragma: no cover — kein ORM-Objekt
        return None
    tabelle = zustand.mapper.local_table
    if isinstance(tabelle, Table) and tabelle.name in ERFASST:
        return tabelle
    return None


def _schluessel(obj: object) -> str:
    zustand: Any = inspect(obj)
    (wert,) = zustand.mapper.primary_key_from_instance(obj)
    return str(wert)


def _lies(session: Session, tabelle: Table, schluessel: set[str]) -> dict[str, Zeile]:
    """Gespeicherte Zeilen, normiert, je Primärschlüssel."""
    if not schluessel:
        return {}
    (pk,) = tabelle.primary_key.columns
    werte: list[Any] = [int(s) if pk.type.python_type is int else s for s in schluessel]
    ohne = ERFASST[tabelle.name].ohne
    zeilen = session.connection().execute(select(tabelle).where(pk.in_(werte)))
    return {str(z[pk.name]): schnappschuss(tabelle, z, ohne) for z in zeilen.mappings()}


def _rohe_buchungen(session: Session, ids: set[str]) -> dict[str, Any]:
    if not ids:
        return {}
    t = BuchungssatzRow.__table__
    zeilen = session.connection().execute(select(t).where(t.c.id.in_(list(ids))))
    return {z["id"]: z for z in zeilen.mappings()}


def _pruefe_festschreibung(
    zeile: BuchungssatzRow, gespeichert: Any, geloescht: bool
) -> None:
    """Storno statt Änderung: was an einer freigegebenen Buchung noch geht."""
    status = gespeichert["status"]
    if status not in FREIGEGEBEN:
        return
    kurz = str(gespeichert["id"])[:8]
    hinweis = (
        f"Buchung {kurz} ist freigegeben ({status}) — Korrektur nur per Storno mit "
        f"Neubuchung: accounti korrigiere {kurz} --soll … --haben … "
        f"(oder accounti buchung storniere {kurz})"
    )
    if geloescht:
        raise BuchungFestgeschriebenError(hinweis)
    zustand = inspect(zeile)
    neu = {
        a.key: a.history.added[0]
        for a in zustand.attrs
        if a.history.has_changes() and a.history.added
    }
    geaendert = {k for k, w in neu.items() if w != gespeichert.get(k)}
    if not geaendert:
        return
    erlaubt = {"status", "geprueft_von", "storniert_durch"}
    if geaendert - erlaubt:
        felder = ", ".join(sorted(geaendert - erlaubt))
        raise BuchungFestgeschriebenError(f"{hinweis}; geändert: {felder}")
    if "status" in geaendert and (status, neu["status"]) not in STATUSWEGE:
        raise BuchungFestgeschriebenError(
            f"{hinweis}; Status {status} → {neu['status']} nicht erlaubt"
        )
    if "geprueft_von" in geaendert and not (
        status == "auto" and neu.get("status") == "geprueft"
    ):
        raise BuchungFestgeschriebenError(f"{hinweis}; Prüfvermerk festgeschrieben")
    if "storniert_durch" in geaendert and (
        gespeichert["storniert_durch"] is not None or not neu["storniert_durch"]
    ):
        raise BuchungFestgeschriebenError(f"Buchung {kurz} ist schon storniert")


# --- Ereignisse ---------------------------------------------------------------------


@event.listens_for(Session, "before_flush")
def _vor_dem_schreiben(session: Session, _: UOWTransaction, __: object) -> None:
    ziele: dict[str, set[str]] = defaultdict(set)
    tabellen: dict[str, Table] = {}
    buchungen: list[tuple[BuchungssatzRow, bool]] = []
    geloeschte = set(session.deleted)
    for obj in list(session.dirty) + list(geloeschte):
        tabelle = _tabelle(obj)
        if tabelle is None:
            continue
        geloescht = obj in geloeschte
        if not geloescht and not session.is_modified(obj):
            continue
        tabellen[tabelle.name] = tabelle
        ziele[tabelle.name].add(_schluessel(obj))
        if isinstance(obj, BuchungssatzRow):
            buchungen.append((obj, geloescht))
    if buchungen:
        roh = _rohe_buchungen(session, {_schluessel(b) for b, _ in buchungen})
        verbindung = session.connection()
        for b, geloescht in buchungen:
            gespeichert = roh.get(_schluessel(b))
            # Im gesperrten Zeitraum meldet die Sperre selbst (Jahres-/Monatssperre)
            if gespeichert is not None and not gesperrt(
                verbindung, gespeichert["datum"]
            ):
                _pruefe_festschreibung(b, gespeichert, geloescht)
    vorher: dict[tuple[str, str], Zeile] = session.info.setdefault(_INFO, {})
    for name, schluessel in ziele.items():
        for pk, zeile in _lies(session, tabellen[name], schluessel).items():
            vorher.setdefault((name, pk), zeile)


@event.listens_for(Session, "after_flush")
def _nach_dem_schreiben(session: Session, _: UOWTransaction) -> None:
    vorher: dict[tuple[str, str], Zeile] = session.info.pop(_INFO, {})
    verbindung = session.connection()
    if not journal_vorhanden(verbindung):
        return
    geloescht = set(session.deleted)
    reihe: list[tuple[Table, str, bool]] = []  # (Tabelle, Schlüssel, gelöscht)
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        tabelle = _tabelle(obj)
        if tabelle is None:
            continue
        pk = _schluessel(obj)
        if obj not in session.new and (tabelle.name, pk) not in vorher:
            continue  # nicht wirklich geändert
        reihe.append((tabelle, pk, obj in geloescht))
    if not reihe:
        return
    je_tabelle: dict[str, set[str]] = defaultdict(set)
    tabellen = {}
    for tabelle, pk, weg in reihe:
        tabellen[tabelle.name] = tabelle
        if not weg:
            je_tabelle[tabelle.name].add(pk)
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


_GESCHUETZT = frozenset({BuchungssatzRow.__tablename__, JournalRow.__tablename__})


@event.listens_for(Session, "do_orm_execute")
def _keine_massenaenderung(zustand: ORMExecuteState) -> None:
    if not (zustand.is_update or zustand.is_delete):
        return
    for mapper in zustand.all_mappers:
        if mapper.local_table.name in _GESCHUETZT:  # type: ignore[attr-defined]
            msg = (
                f"Massenänderung an {mapper.local_table.name} ist gesperrt — "  # type: ignore[attr-defined]
                "Buchungen einzeln über die Sitzung ändern (Journal, Storno-Regel)"
            )
            raise UnveraenderbarError(msg)
