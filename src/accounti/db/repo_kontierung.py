"""Repository für Kontierungsgründe und gelernte Regeln (Baustein 10b).

Alles in der Sitzung des Aufrufers — ohne ``commit``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounti.db.tabellen_kontierung import KontierungsgrundRow, KontierungsregelRow
from accounti.models.kontierung import (
    Kontierungsgrund,
    Kontierungsregel,
    Quelle,
    RegelHerkunft,
    Richtung,
)

_JE_ABFRAGE = 500


def speichere_kontierungsgrund(
    session: Session,
    buchung_id: UUID,
    *,
    quelle: Quelle,
    begruendung: str,
    regel: str | None = None,
    modell: str | None = None,
    jetzt: datetime | None = None,
) -> Kontierungsgrund:
    """Herkunft einer Buchung anhängen — in derselben Transaktion wie die Buchung."""
    g = Kontierungsgrund(
        buchung_id=buchung_id,
        quelle=quelle,
        regel=(regel or None) and regel[:100],
        modell=(modell or None) and modell[:100],
        begruendung=begruendung,
        erstellt_am=jetzt or datetime.now(),
    )
    session.add(
        KontierungsgrundRow(
            id=str(g.id),
            buchung_id=str(g.buchung_id),
            quelle=g.quelle,
            regel=g.regel,
            modell=g.modell,
            begruendung=g.begruendung,
            erstellt_am=g.erstellt_am,
        )
    )
    return g


def _zu_grund(r: KontierungsgrundRow) -> Kontierungsgrund:
    return Kontierungsgrund.model_validate(
        {
            "id": UUID(r.id),
            "buchung_id": UUID(r.buchung_id),
            "quelle": r.quelle,
            "regel": r.regel,
            "modell": r.modell,
            "begruendung": r.begruendung,
            "erstellt_am": r.erstellt_am,
        }
    )


def lade_kontierungsgrund(
    session: Session, buchung_id: UUID | str
) -> Kontierungsgrund | None:
    """Der neueste Grund zur Buchung (oder ``None``)."""
    zeile = session.scalars(
        select(KontierungsgrundRow)
        .where(KontierungsgrundRow.buchung_id == str(buchung_id))
        .order_by(KontierungsgrundRow.erstellt_am.desc(), KontierungsgrundRow.id)
        .limit(1)
    ).first()
    return _zu_grund(zeile) if zeile is not None else None


def lade_kontierungsgruende(
    session: Session, buchung_ids: Iterable[UUID | str]
) -> dict[UUID, Kontierungsgrund]:
    """Je Buchung der neueste Grund — für Listen in einer Abfrage je 500 IDs."""
    ids = sorted({str(i) for i in buchung_ids})
    ergebnis: dict[UUID, Kontierungsgrund] = {}
    for start in range(0, len(ids), _JE_ABFRAGE):
        teil = ids[start : start + _JE_ABFRAGE]
        zeilen = session.scalars(
            select(KontierungsgrundRow)
            .where(KontierungsgrundRow.buchung_id.in_(teil))
            .order_by(KontierungsgrundRow.erstellt_am, KontierungsgrundRow.id.desc())
        )
        for z in zeilen:  # aufsteigend: der neueste überschreibt
            g = _zu_grund(z)
            ergebnis[g.buchung_id] = g
    return ergebnis


def zaehle_regeltreffer(session: Session, namen: Iterable[str]) -> dict[str, int]:
    """Wie oft eine Regel seither kontiert hat (laut ``kontierungsgruende.regel``)."""
    liste = sorted(set(namen))
    if not liste:
        return {}
    zeilen = session.execute(
        select(KontierungsgrundRow.regel, func.count())
        .where(KontierungsgrundRow.regel.in_(liste))
        .group_by(KontierungsgrundRow.regel)
    )
    return {str(name): int(anzahl) for name, anzahl in zeilen}


# --- gelernte Regeln ----------------------------------------------------------------


def speichere_regel(session: Session, r: Kontierungsregel) -> None:
    session.add(
        KontierungsregelRow(
            id=str(r.id),
            name=r.name,
            muster=r.muster,
            ist_text=r.ist_text,
            feld=r.feld,
            richtung=r.richtung.value if r.richtung else None,
            soll_konto=r.soll_konto,
            haben_konto=r.haben_konto,
            steuer_schluessel=r.steuer_schluessel,
            buchungstext=r.buchungstext,
            quelle_buchung_id=str(r.quelle_buchung_id) if r.quelle_buchung_id else None,
            herkunft=r.herkunft.value,
            rang=r.rang,
            angelegt_von=r.angelegt_von[:100],
            angelegt_am=r.angelegt_am,
            aktiv=r.aktiv,
            deaktiviert_von=r.deaktiviert_von,
            deaktiviert_am=r.deaktiviert_am,
            deaktiviert_grund=r.deaktiviert_grund,
        )
    )
    session.flush()


def _zu_regel(z: KontierungsregelRow) -> Kontierungsregel:
    return Kontierungsregel.model_validate(
        {
            "id": UUID(z.id),
            "name": z.name,
            "muster": z.muster,
            "ist_text": z.ist_text,
            "feld": z.feld,
            "richtung": Richtung(z.richtung) if z.richtung else None,
            "soll_konto": z.soll_konto,
            "haben_konto": z.haben_konto,
            "steuer_schluessel": z.steuer_schluessel,
            "buchungstext": z.buchungstext,
            "quelle_buchung_id": UUID(z.quelle_buchung_id)
            if z.quelle_buchung_id
            else None,
            "herkunft": RegelHerkunft(z.herkunft),
            "rang": z.rang,
            "angelegt_von": z.angelegt_von,
            "angelegt_am": z.angelegt_am,
            "aktiv": z.aktiv,
            "deaktiviert_von": z.deaktiviert_von,
            "deaktiviert_am": z.deaktiviert_am,
            "deaktiviert_grund": z.deaktiviert_grund,
        }
    )


def lade_kontierungsregeln(
    session: Session, *, nur_aktive: bool = False
) -> list[Kontierungsregel]:
    """Gelernte Regeln in ihrem Vorrang: die neueste zuerst — die aus der
    Regeldatei übernommenen (``accounti regeln uebernehmen``) hinter allen anderen,
    wie vorher die Datei hinter den Korrekturen in der Datenbank (Gesamttest 10b-1
    M-1: sonst gewann ein alter Eintrag gegen eine neuere Korrektur).

    Übernommene untereinander nach ihrer Stelle in der Regeldatei (``rang``), bei
    gleicher Stelle der früher übernommene zuerst — unabhängig davon, in wie vielen
    Läufen übernommen wurde (Runde 3, gegen:regeln:1: ein zweiter Lauf mit ``--name``
    stellte seinen Eintrag sonst vor die früher übernommenen). Ohne ``rang`` (vor
    Runde 3 übernommen) wie bisher nach Zeitpunkt, vor denen mit ``rang``."""
    abfrage = select(KontierungsregelRow).order_by(
        KontierungsregelRow.angelegt_am.desc(), KontierungsregelRow.name
    )
    if nur_aktive:
        abfrage = abfrage.where(KontierungsregelRow.aktiv.is_(True))
    zeilen = list(session.scalars(abfrage))
    uebernahme = RegelHerkunft.UEBERNAHME.value
    gelernt = [z for z in zeilen if z.herkunft != uebernahme]
    alt = [z for z in zeilen if z.herkunft == uebernahme and z.rang is None]
    neu = sorted(
        (z for z in zeilen if z.herkunft == uebernahme and z.rang is not None),
        key=lambda z: (z.rang or 0, z.angelegt_am, z.name),
    )
    return [_zu_regel(z) for z in (*gelernt, *alt, *neu)]


def lade_kontierungsregel(session: Session, regel_id: UUID | str) -> Kontierungsregel:
    """Regel per voller ID — sonst ``ValueError``."""
    zeile = session.get(KontierungsregelRow, str(regel_id))
    if zeile is None:
        raise ValueError(f"Gelernte Regel {str(regel_id)[:8]} nicht gefunden")
    return _zu_regel(zeile)


def finde_kontierungsregel(session: Session, schluessel: str) -> Kontierungsregel:
    """Regel per Name oder ID-Anfang (CLI) — eindeutig, sonst ``ValueError``."""
    zeile = session.scalars(
        select(KontierungsregelRow).where(KontierungsregelRow.name == schluessel)
    ).first()
    if zeile is not None:
        return _zu_regel(zeile)
    roh = schluessel.strip().lower()
    if len(roh) < 4 or not all(c in "0123456789abcdef-" for c in roh):
        raise ValueError(f"Gelernte Regel {schluessel!r} nicht gefunden")
    treffer = list(
        session.scalars(
            select(KontierungsregelRow).where(KontierungsregelRow.id.startswith(roh))
        )
    )
    if len(treffer) != 1:
        art = "mehrdeutig" if treffer else "nicht gefunden"
        raise ValueError(f"Gelernte Regel {schluessel!r} {art}")
    return _zu_regel(treffer[0])


def regelnamen(session: Session) -> set[str]:
    return set(session.scalars(select(KontierungsregelRow.name)))


def deaktiviere_regel(
    session: Session,
    regel_id: UUID | str,
    von: str,
    grund: str,
    jetzt: datetime | None = None,
) -> Kontierungsregel:
    """aktiv → aus (der einzige erlaubte Weg); schon aus → ``ValueError``."""
    zeile = session.get(KontierungsregelRow, str(regel_id))
    if zeile is None:
        raise ValueError(f"Gelernte Regel {str(regel_id)[:8]} nicht gefunden")
    if not zeile.aktiv:
        raise ValueError(f"Regel {zeile.name} ist schon deaktiviert")
    zeile.aktiv = False
    zeile.deaktiviert_von = von[:100]
    zeile.deaktiviert_am = jetzt or datetime.now()
    zeile.deaktiviert_grund = grund.strip()[:500]
    session.flush()
    return _zu_regel(zeile)
