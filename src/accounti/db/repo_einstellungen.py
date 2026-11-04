"""Repository der Einstellungen (Baustein 10c, Paket P4).

Versionen werden nur angefügt: ``fuege_version_an`` holt unter ``journal.schreibsperre``
die letzte Version des Abschnitts, nummeriert fortlaufend und verkettet per Hash
(``versionshash``: sha256 über das kanonische JSON aller Spalten außer ``id`` und
``hash``; ``erstellt_am`` so, wie ``Einstellungsversion`` es serialisiert — dann
liefern SQLite und PostgreSQL denselben Text, D9). ``daten`` steht in Normalform
(``einstellungen.normalform``). ``pruefe_kette`` findet Lücken, falsche Vorgänger und
veränderte Zeilen.

Wie in jedem Repository: ``flush``, nie ``commit`` — der Aufrufer committet.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounti.db.tabellen_einstellungen import (
    EinstellungRow,
    EinstellungsantragRow,
    GeheimnisRow,
)
from accounti.einstellungen.leser import normalform
from accounti.models.einstellungen import Antrag, Einstellungsversion, GeheimnisInfo
from accounti.pruefung.journal import (
    GENESIS,
    GRUND_LAENGE,
    PERSON_LAENGE,
    schreibsperre,
)

_ZEIT: TypeAdapter[datetime] = TypeAdapter(datetime)


def _json(wert: Any) -> str:
    return json.dumps(wert, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def versionshash(werte: Mapping[str, Any]) -> str:
    """Hash einer Version aus ihren Spaltenwerten (``id`` und ``hash`` zählen nicht)."""
    zeile = {k: v for k, v in werte.items() if k not in ("id", "hash")}
    if isinstance(zeile.get("erstellt_am"), datetime):
        # wie Einstellungsversion.model_dump(mode="json")["erstellt_am"]
        zeile["erstellt_am"] = _ZEIT.dump_python(zeile["erstellt_am"], mode="json")
    return hashlib.sha256(_json(zeile).encode()).hexdigest()


def zeilenhash(zeile: EinstellungRow) -> str:
    """Der Hash, den die gespeicherte Zeile tragen muss."""
    spalten = EinstellungRow.__table__.columns
    return versionshash({s.name: getattr(zeile, s.name) for s in spalten})


def _version(zeile: EinstellungRow) -> Einstellungsversion:
    return Einstellungsversion(
        id=zeile.id,
        abschnitt=zeile.abschnitt,
        version=zeile.version,
        daten=json.loads(zeile.daten),
        schema_version=zeile.schema_version,
        vollstaendig=zeile.vollstaendig,
        fehlend=json.loads(zeile.fehlend),
        person=zeile.person,
        grund=zeile.grund,
        quelle=zeile.quelle,  # type: ignore[arg-type]
        antrag_id=zeile.antrag_id,
        datei_hash=zeile.datei_hash,
        erstellt_am=zeile.erstellt_am,
        hash=zeile.hash,
        vorgaenger_hash=zeile.vorgaenger_hash,
    )


def fuege_version_an(
    session: Session,
    abschnitt: str,
    daten: Mapping[str, Any],
    *,
    person: str,
    grund: str,
    quelle: str,
    schema_version: int = 1,
    vollstaendig: bool = True,
    fehlend: Iterable[str] = (),
    antrag_id: int | None = None,
    datei_hash: str | None = None,
    jetzt: datetime | None = None,
) -> Einstellungsversion:
    """Die nächste Version von ``abschnitt`` anfügen (Nummer, Vorgänger, Hash)."""
    schreibsperre(session.connection())  # erst sperren, dann die letzte Version lesen
    letzte = session.execute(
        select(EinstellungRow.version, EinstellungRow.hash)
        .where(EinstellungRow.abschnitt == abschnitt)
        .order_by(EinstellungRow.version.desc())
        .limit(1)
    ).first()
    nummer, vorgaenger = (letzte[0], letzte[1]) if letzte else (0, GENESIS)
    zeile = EinstellungRow(
        abschnitt=abschnitt,
        version=nummer + 1,
        daten=_json(normalform(dict(daten))),
        schema_version=schema_version,
        vollstaendig=vollstaendig,
        fehlend=_json(list(fehlend)),
        person=person[:PERSON_LAENGE],
        grund=grund[:GRUND_LAENGE],
        quelle=quelle,
        antrag_id=antrag_id,
        datei_hash=datei_hash,
        erstellt_am=jetzt or datetime.now(),
        vorgaenger_hash=vorgaenger,
    )
    zeile.hash = zeilenhash(zeile)
    session.add(zeile)
    session.flush()
    return _version(zeile)


def neueste_versionen(session: Session) -> dict[str, int]:
    """Abschnitt → höchste Versionsnummer."""
    zeilen = session.execute(
        select(EinstellungRow.abschnitt, func.max(EinstellungRow.version)).group_by(
            EinstellungRow.abschnitt
        )
    )
    return {abschnitt: int(nummer) for abschnitt, nummer in zeilen}


def lade_version(
    session: Session, abschnitt: str, version: int
) -> Einstellungsversion | None:
    zeile = session.scalars(
        select(EinstellungRow).where(
            EinstellungRow.abschnitt == abschnitt, EinstellungRow.version == version
        )
    ).first()
    return _version(zeile) if zeile is not None else None


def lade_versionen(
    session: Session, abschnitt: str | None = None, bis: datetime | None = None
) -> list[Einstellungsversion]:
    """Versionen nach Abschnitt und Nummer; ``bis``: nur bis zu diesem Zeitpunkt."""
    abfrage = select(EinstellungRow).order_by(
        EinstellungRow.abschnitt, EinstellungRow.version
    )
    if abschnitt is not None:
        abfrage = abfrage.where(EinstellungRow.abschnitt == abschnitt)
    if bis is not None:
        abfrage = abfrage.where(EinstellungRow.erstellt_am <= bis)
    return [_version(z) for z in session.scalars(abfrage)]


def pruefe_kette(session: Session) -> list[str]:
    """Befunde der Hash-Kette je Abschnitt — leer, wenn alles stimmt."""
    befunde: list[str] = []
    zeilen = session.scalars(
        select(EinstellungRow).order_by(
            EinstellungRow.abschnitt, EinstellungRow.version
        )
    )
    erwartet: dict[str, tuple[int, str]] = {}
    for zeile in zeilen:
        nummer, vorgaenger = erwartet.get(zeile.abschnitt, (1, GENESIS))
        wo = f"{zeile.abschnitt} v{zeile.version}"
        if zeile.version != nummer:
            befunde.append(f"{wo}: Version {nummer} erwartet (Lücke)")
        if zeile.vorgaenger_hash != vorgaenger:
            befunde.append(f"{wo}: Vorgänger passt nicht zur Kette")
        elif zeilenhash(zeile) != zeile.hash:
            befunde.append(f"{wo}: an accounti vorbei verändert (Hash)")
        erwartet[zeile.abschnitt] = (zeile.version + 1, zeile.hash)
    return befunde


def _antrag(zeile: EinstellungsantragRow) -> Antrag:
    return Antrag(
        id=zeile.id,
        aenderungen=json.loads(zeile.aenderungen),
        inhalt_hash=zeile.inhalt_hash,
        grund=zeile.grund,
        antragsteller=zeile.antragsteller,
        erstellt_am=zeile.erstellt_am,
        gueltig_bis=zeile.gueltig_bis,
        kontrolle=zeile.kontrolle,
        recht=zeile.recht,
        felder=json.loads(zeile.felder),
        status=zeile.status,  # type: ignore[arg-type]
        entschieden_von=zeile.entschieden_von,
        entschieden_am=zeile.entschieden_am,
        entscheidungsgrund=zeile.entscheidungsgrund,
        versionen=json.loads(zeile.versionen) if zeile.versionen else None,
    )


def lade_antraege(session: Session, status: str | None = None) -> list[Antrag]:
    abfrage = select(EinstellungsantragRow).order_by(EinstellungsantragRow.id)
    if status is not None:
        abfrage = abfrage.where(EinstellungsantragRow.status == status)
    return [_antrag(z) for z in session.scalars(abfrage)]


def lade_geheimnisse(session: Session) -> list[GeheimnisInfo]:
    """Name und Herkunft je Geheimnis — nie das Chiffrat."""
    zeilen = session.execute(
        select(
            GeheimnisRow.name, GeheimnisRow.gesetzt_am, GeheimnisRow.gesetzt_von
        ).order_by(GeheimnisRow.name)
    )
    return [
        GeheimnisInfo(name=n, gesetzt_am=am, gesetzt_von=von) for n, am, von in zeilen
    ]


def lade_chiffrate(session: Session) -> dict[str, str]:
    """Name → Chiffrat (für den Schnappschuss des Lesers)."""
    zeilen = session.execute(select(GeheimnisRow.name, GeheimnisRow.chiffrat))
    return {name: chiffrat for name, chiffrat in zeilen}
