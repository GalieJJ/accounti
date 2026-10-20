"""Repository für Aufgaben, Kommentare und Benachrichtigungen (Baustein 8)."""

from __future__ import annotations

import json
from collections.abc import Collection
from datetime import date
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounti.db import Base
from accounti.db.tabellen_aufgaben import AufgabeRow, BenachrichtigungRow, KommentarRow
from accounti.models.aufgaben import (
    Aufgabe,
    AufgabenStatus,
    Benachrichtigung,
    Kommentar,
    KommentarArt,
    Objekt,
    Prioritaet,
)

# ---------------------------------------------------------------------------
# Aufgaben
# ---------------------------------------------------------------------------

_FELDER = (
    "nr",
    "schluessel",
    "art",
    "titel",
    "beschreibung",
    "objekt_typ",
    "objekt_id",
    "zustaendig",
    "rolle",
    "faellig_am",
    "erzeugt_von",
    "erstellt_am",
    "aktualisiert_am",
    "quittiert_von",
    "erledigt_am",
    "abschluss_grund",
    "erinnerungsstufe",
    "gemeldet_am",
)


class AufgabeVeraltetError(ValueError):
    """Die Aufgabe wurde seit dem Lesen geändert (anderer Lauf, anderer Mensch)."""


def _werte(a: Aufgabe) -> dict[str, Any]:
    werte: dict[str, Any] = {f: getattr(a, f) for f in _FELDER}
    werte["status"] = a.status.value
    werte["prioritaet"] = a.prioritaet.value
    werte["merkmale"] = json.dumps(a.merkmale, ensure_ascii=False, sort_keys=True)
    werte["version"] = a.version
    return werte


def _row_zu_aufgabe(r: AufgabeRow) -> Aufgabe:
    return Aufgabe(
        id=UUID(r.id),
        **{f: getattr(r, f) for f in _FELDER},
        status=AufgabenStatus(r.status),
        prioritaet=Prioritaet(r.prioritaet),
        merkmale=json.loads(r.merkmale or "{}"),
        version=r.version or 0,
    )


def speichere_aufgabe(session: Session, a: Aufgabe) -> None:
    session.add(AufgabeRow(id=str(a.id), **_werte(a)))
    session.flush()


def lege_aufgabe_an(session: Session, a: Aufgabe) -> bool:
    """Legt an, wenn Nummer und Schlüssel frei sind; False, wenn einer belegt ist.

    Ohne Savepoint: Unter pysqlite eröffnet ``SAVEPOINT`` vor der ersten Änderung
    selbst die Transaktion, und ``RELEASE`` wirkt dann als ``COMMIT`` — die Aufgabe
    stünde fest in der Datenbank, obwohl der Aufrufer zurückrollt. ``INSERT … ON
    CONFLICT DO NOTHING`` bleibt in der Transaktion des Aufrufers und bricht sie
    auch unter Postgres bei einem Konflikt nicht ab.
    """
    werte = {"id": str(a.id), **_werte(a)}
    dialekt = session.get_bind().dialect.name
    if dialekt == "sqlite":
        anweisung: Any = sqlite.insert(AufgabeRow).values(**werte)
    elif dialekt == "postgresql":
        anweisung = postgresql.insert(AufgabeRow).values(**werte)
    else:  # andere Datenbanken: Savepoint (dort ohne die pysqlite-Eigenheit)
        try:
            with session.begin_nested():
                speichere_aufgabe(session, a)
        except IntegrityError:
            return False
        return True
    ergebnis = session.execute(anweisung.on_conflict_do_nothing())
    return cast("CursorResult[Any]", ergebnis).rowcount == 1


def aktualisiere_aufgabe(session: Session, a: Aufgabe) -> Aufgabe:
    """Schreibt die Aufgabe zurück — nur, wenn sie seit dem Lesen niemand geändert
    hat (``version``); sonst ``AufgabeVeraltetError``, die Sitzung bleibt nutzbar."""
    werte = _werte(a)
    werte["version"] = a.version + 1
    ergebnis = session.execute(
        update(AufgabeRow)
        .where(AufgabeRow.id == str(a.id), AufgabeRow.version == a.version)
        .values(**werte)
        .execution_options(synchronize_session=False)
    )
    row = session.get(AufgabeRow, str(a.id), populate_existing=True)
    if row is None:
        msg = f"Aufgabe {a.id} nicht gefunden."
        raise ValueError(msg)
    if cast("CursorResult[Any]", ergebnis).rowcount != 1:
        msg = (
            f"Aufgabe #{row.nr} wurde inzwischen geändert (Status {row.status}) — "
            "bitte neu laden und erneut versuchen."
        )
        raise AufgabeVeraltetError(msg)
    return _row_zu_aufgabe(row)


def naechste_aufgaben_nr(session: Session) -> int:
    hoechste = session.scalar(select(func.max(AufgabeRow.nr)))
    return (hoechste or 0) + 1


def lade_aufgabe_nach_schluessel(session: Session, schluessel: str) -> Aufgabe | None:
    row = session.scalars(
        select(AufgabeRow)
        .where(AufgabeRow.schluessel == schluessel)
        .execution_options(populate_existing=True)
    ).one_or_none()
    return _row_zu_aufgabe(row) if row is not None else None


def lade_aufgabe(session: Session, ref: str | int) -> Aufgabe:
    """Über die laufende Nummer (``42``) oder den Anfang der ID."""
    text = str(ref).strip().lstrip("#")
    abfrage = select(AufgabeRow).execution_options(populate_existing=True)
    if text.isdigit():
        abfrage = abfrage.where(AufgabeRow.nr == int(text))
    else:
        abfrage = abfrage.where(AufgabeRow.id.in_(_ids(session, text)))
    treffer = list(session.scalars(abfrage))
    if not treffer:
        msg = f"Keine Aufgabe '{ref}' gefunden."
        raise ValueError(msg)
    if len(treffer) > 1:
        msg = f"'{ref}' ist mehrdeutig ({len(treffer)} Treffer) — länger angeben."
        raise ValueError(msg)
    return _row_zu_aufgabe(treffer[0])


def _ids(session: Session, praefix: str) -> list[str]:
    return ids_mit_praefix(session, AufgabeRow, praefix)


def lade_aufgaben(
    session: Session,
    *,
    status: Collection[AufgabenStatus] | None = None,
    art: str | None = None,
    objekt: Objekt | None = None,
    erzeugt_von: str | None = None,
) -> list[Aufgabe]:
    abfrage = (
        select(AufgabeRow)
        .order_by(AufgabeRow.nr)
        .execution_options(populate_existing=True)  # frisch, nicht aus dem Cache
    )
    if status is not None:
        abfrage = abfrage.where(AufgabeRow.status.in_([s.value for s in status]))
    if art is not None:
        abfrage = abfrage.where(AufgabeRow.art == art)
    if objekt is not None:
        abfrage = abfrage.where(
            AufgabeRow.objekt_typ == objekt.typ, AufgabeRow.objekt_id == objekt.id
        )
    if erzeugt_von is not None:
        abfrage = abfrage.where(AufgabeRow.erzeugt_von == erzeugt_von)
    return [_row_zu_aufgabe(r) for r in session.scalars(abfrage)]


# ---------------------------------------------------------------------------
# Kommentare und Verlauf (nur anfügen)
# ---------------------------------------------------------------------------


def _row_zu_kommentar(r: KommentarRow) -> Kommentar:
    return Kommentar(
        id=UUID(r.id),
        aufgabe_id=UUID(r.aufgabe_id) if r.aufgabe_id else None,
        objekt_typ=r.objekt_typ,
        objekt_id=r.objekt_id,
        art=KommentarArt(r.art),
        autor=r.autor,
        text=r.text,
        erstellt_am=r.erstellt_am,
        anhang_beleg_id=UUID(r.anhang_beleg_id) if r.anhang_beleg_id else None,
    )


def speichere_kommentar(session: Session, k: Kommentar) -> None:
    session.add(
        KommentarRow(
            id=str(k.id),
            aufgabe_id=str(k.aufgabe_id) if k.aufgabe_id else None,
            objekt_typ=k.objekt_typ,
            objekt_id=k.objekt_id,
            art=k.art.value,
            autor=k.autor,
            text=k.text,
            erstellt_am=k.erstellt_am,
            anhang_beleg_id=str(k.anhang_beleg_id) if k.anhang_beleg_id else None,
        )
    )
    session.flush()


def lade_kommentare(
    session: Session,
    *,
    aufgabe_id: UUID | None = None,
    objekt: Objekt | None = None,
    arten: Collection[KommentarArt] | None = None,
) -> list[Kommentar]:
    """Kommentare einer Aufgabe und/oder an einem Objekt, älteste zuerst."""
    abfrage = select(KommentarRow).order_by(KommentarRow.erstellt_am)
    if aufgabe_id is not None:
        abfrage = abfrage.where(KommentarRow.aufgabe_id == str(aufgabe_id))
    if objekt is not None:
        abfrage = abfrage.where(
            KommentarRow.objekt_typ == objekt.typ, KommentarRow.objekt_id == objekt.id
        )
    if arten is not None:
        abfrage = abfrage.where(KommentarRow.art.in_([a.value for a in arten]))
    return [_row_zu_kommentar(r) for r in session.scalars(abfrage)]


# ---------------------------------------------------------------------------
# Benachrichtigungen
# ---------------------------------------------------------------------------


def speichere_benachrichtigung(session: Session, b: Benachrichtigung) -> None:
    session.add(
        BenachrichtigungRow(
            id=str(b.id),
            tag=b.tag,
            empfaenger=b.empfaenger,
            kanal=b.kanal,
            adresse=b.adresse,
            aufgaben=json.dumps(b.aufgaben),
            erfolgreich=b.erfolgreich,
            fehler=b.fehler,
            zeitpunkt=b.zeitpunkt,
        )
    )
    session.flush()


def lade_benachrichtigungen(
    session: Session, tag: date | None = None
) -> list[Benachrichtigung]:
    abfrage = select(BenachrichtigungRow).order_by(BenachrichtigungRow.zeitpunkt)
    if tag is not None:
        abfrage = abfrage.where(BenachrichtigungRow.tag == tag)
    return [
        Benachrichtigung(
            id=UUID(r.id),
            tag=r.tag,
            empfaenger=r.empfaenger,
            kanal=r.kanal,
            adresse=r.adresse,
            aufgaben=json.loads(r.aufgaben or "[]"),
            erfolgreich=r.erfolgreich,
            fehler=r.fehler,
            zeitpunkt=r.zeitpunkt,
        )
        for r in session.scalars(abfrage)
    ]


# ---------------------------------------------------------------------------
# Objekte anderer Bausteine über den Anfang ihrer ID finden
# ---------------------------------------------------------------------------


def ids_mit_praefix(
    session: Session, row_klasse: type[Base], praefix: str, grenze: int = 3
) -> list[str]:
    """IDs einer Tabelle, die mit ``praefix`` beginnen (höchstens ``grenze``)."""
    sauber = praefix.strip().lower()
    if not sauber or any(z in sauber for z in "%_\\"):
        return []
    spalte = row_klasse.id  # type: ignore[attr-defined]  # ORM-Spalte: autoflush
    abfrage = select(spalte).where(spalte.like(f"{sauber}%")).limit(grenze)
    return [str(i) for i in session.scalars(abfrage)]
