"""Repository für Aufgaben, Kommentare und Benachrichtigungen (Baustein 8)."""

from __future__ import annotations

import json
from collections.abc import Collection
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
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


def _werte(a: Aufgabe) -> dict[str, Any]:
    werte: dict[str, Any] = {f: getattr(a, f) for f in _FELDER}
    werte["status"] = a.status.value
    werte["prioritaet"] = a.prioritaet.value
    werte["merkmale"] = json.dumps(a.merkmale, ensure_ascii=False, sort_keys=True)
    return werte


def _row_zu_aufgabe(r: AufgabeRow) -> Aufgabe:
    return Aufgabe(
        id=UUID(r.id),
        **{f: getattr(r, f) for f in _FELDER},
        status=AufgabenStatus(r.status),
        prioritaet=Prioritaet(r.prioritaet),
        merkmale=json.loads(r.merkmale or "{}"),
    )


def speichere_aufgabe(session: Session, a: Aufgabe) -> None:
    session.add(AufgabeRow(id=str(a.id), **_werte(a)))
    session.flush()


def aktualisiere_aufgabe(session: Session, a: Aufgabe) -> Aufgabe:
    row = session.get(AufgabeRow, str(a.id))
    if row is None:
        msg = f"Aufgabe {a.id} nicht gefunden."
        raise ValueError(msg)
    for feld, wert in _werte(a).items():
        setattr(row, feld, wert)
    session.flush()
    return _row_zu_aufgabe(row)


def naechste_aufgaben_nr(session: Session) -> int:
    hoechste = session.scalar(select(func.max(AufgabeRow.nr)))
    return (hoechste or 0) + 1


def lade_aufgabe_nach_schluessel(session: Session, schluessel: str) -> Aufgabe | None:
    row = session.scalars(
        select(AufgabeRow).where(AufgabeRow.schluessel == schluessel)
    ).one_or_none()
    return _row_zu_aufgabe(row) if row is not None else None


def lade_aufgabe(session: Session, ref: str | int) -> Aufgabe:
    """Über die laufende Nummer (``42``) oder den Anfang der ID."""
    text = str(ref).strip().lstrip("#")
    if text.isdigit():
        rows = session.scalars(select(AufgabeRow).where(AufgabeRow.nr == int(text)))
        treffer = list(rows)
    else:
        treffer = list(
            session.scalars(
                select(AufgabeRow).where(AufgabeRow.id.in_(_ids(session, text)))
            )
        )
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
    abfrage = select(AufgabeRow).order_by(AufgabeRow.nr)
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
