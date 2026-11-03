"""``accounti db upgrade`` — Migrationen, auch für Datenbanken ohne Versionsvermerk.

Datenbanken aus ``accounti db init`` bzw. dem ersten Befehl (``init_db``) älterer
Fassungen haben keine Tabelle ``alembic_version``: ``alembic upgrade head`` begänne bei
der ersten Migration und bräche an „table … already exists“ ab (Befund Betrieb B2).

Ohne Vermerk leitet ``aktualisiere`` den Stand aus dem Schema ab: Die Migrationen laufen
Schritt für Schritt in einer Wegwerf-Datenbank (SQLite); jeder Schritt hinterlässt
Merkmale — neue oder entfernte Tabellen und Spalten, bei einem Schritt ohne solche seine
Indizes. Der Stand ist die letzte Revision, deren Merkmale (und die aller Vorgänger) die
Datenbank zeigt; darauf wird gestempelt, dann folgt ``upgrade head``. Hat ``init_db``
des neuen Codes schon neue Tabellen angelegt, aber keine Spalten an alten Tabellen
ergänzt (der Fall aus B2), zählt der Schritt als offen — seine Migration muss dann mit
vorhandenen Tabellen umgehen (wie ``ddc9a184ddb4``). Schritte, die nur Daten oder
Trigger ändern, lassen sich am Schema nicht erkennen (bisher gibt es keine).

Eine Schemaprüfung (``fehlendes_schema``) für alle Fälle: Vor dem Upgrade, wenn nichts
offen ist, und nach ``upgrade head`` vergleicht ``aktualisiere`` das Schema mit den
Tabellen und Spalten des Codes. Fehlt etwas, passt der Vermerk nicht zum Schema — eine
Datenbank vom Vorabstand von 10b-1 (Vermerk e7153706b43a, die Migrationen von main
fehlen; gw-migration N-1) oder von einem Zweig mit anderer Reihenfolge der Migrationen
(Paket C: Vermerk 46371a6681c2 direkt hinter ddc9a184ddb4, Nachprüfung Merge N-2):
Abbruch mit dem aus dem Schema abgeleiteten Stand und dem verlustfreien Weg.
``aus_schema`` (``accounti db upgrade --aus-schema``) geht ihn: Stand aus dem Schema
ableiten, ist er älter als der Vermerk, darauf stempeln (``alembic stamp --purge``),
dann ``upgrade head`` — die Migrationen übernehmen schon vorhandene Tabellen und
Spalten. Von Hand geht dasselbe mit ``alembic stamp --purge <Stand>`` und noch einmal
``db upgrade``.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Connection, Engine, create_engine, inspect, make_url
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from alembic.config import Config

Merkmal = tuple[str, ...]

# alembic.ini: im Quellbaum neben src/, im Docker-Abbild unter /app
_KANDIDATEN = (
    Path(__file__).resolve().parents[3] / "alembic.ini",
    Path("/app/alembic.ini"),
)


class UpgradeError(RuntimeError):
    """Die Datenbank lässt sich so nicht aktualisieren."""


@dataclass
class Ergebnis:
    vorher: str | None
    abgeleitet: bool
    nachher: str | None
    revisionen: list[str] = field(default_factory=list)
    vermerk: str | None = None  # Vermerk vor dem Upgrade, wenn er neu gestempelt wurde


def finde_alembic_ini(angabe: str | None = None) -> Path:
    """``angabe``, sonst die ``alembic.ini`` des Quellbaums bzw. des Docker-Abbilds."""
    if angabe:
        pfad = Path(angabe)
        if not pfad.is_file():
            raise UpgradeError(f"{pfad} gibt es nicht")
        return pfad
    for pfad in _KANDIDATEN:
        if pfad.is_file():
            return pfad
    msg = "alembic.ini nicht gefunden — --alembic-ini angeben"
    raise UpgradeError(msg)


def _konfig(ini: Path, verbindung: Connection) -> Config:
    from alembic.config import Config

    cfg = Config(str(ini))
    cfg.attributes["connection"] = verbindung  # alembic/env.py nimmt sie
    return cfg


def _merkmale(verbindung: Connection) -> set[Merkmal]:
    pruefer = inspect(verbindung)
    merkmale: set[Merkmal] = set()
    for tabelle in pruefer.get_table_names():
        if tabelle == "alembic_version":
            continue
        merkmale.add(("tabelle", tabelle))
        for spalte in pruefer.get_columns(tabelle):
            merkmale.add(("spalte", tabelle, spalte["name"]))
        for index in pruefer.get_indexes(tabelle):
            spalten = ",".join(str(s) for s in index["column_names"])
            merkmale.add(("index", tabelle, str(index["name"]), spalten))
    return merkmale


def _struktur(merkmale: set[Merkmal]) -> set[Merkmal]:
    return {m for m in merkmale if m[0] != "index"}


@dataclass(frozen=True)
class Schritt:
    revision: str
    neu: frozenset[Merkmal]
    weg: frozenset[Merkmal]

    def passt(self, vorhanden: set[Merkmal]) -> bool:
        """Zeigt die Datenbank diesen Schritt? Tabellen und Spalten entscheiden; nur
        ein Schritt ohne sie wird an seinen Indizes erkannt."""
        neu, weg = set(self.neu), set(self.weg)
        if _struktur(neu) or _struktur(weg):
            neu, weg = _struktur(neu), _struktur(weg)
        return neu <= vorhanden and not weg & vorhanden


def _revisionen(ini: Path) -> list[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    skripte = ScriptDirectory.from_config(Config(str(ini)))
    if len(skripte.get_heads()) != 1:
        msg = f"Die Migrationen haben mehrere Köpfe ({', '.join(skripte.get_heads())})"
        raise UpgradeError(msg)
    return [r.revision for r in reversed(list(skripte.walk_revisions()))]


@contextmanager
def _wegwerf_verbindung() -> Iterator[str]:
    with tempfile.TemporaryDirectory(prefix="accounti-upgrade-") as ordner:
        yield f"sqlite:///{Path(ordner) / 'stand.db'}"


def schritte(ini: Path) -> list[Schritt]:
    """Die Merkmale jeder Migration — gemessen in einer Wegwerf-Datenbank."""
    from alembic import command

    ergebnis: list[Schritt] = []
    with _wegwerf_verbindung() as url:
        engine = create_engine(url)
        try:
            vorher: set[Merkmal] = set()
            for revision in _revisionen(ini):
                with engine.begin() as v:
                    command.upgrade(_konfig(ini, v), revision)
                with engine.connect() as v:
                    jetzt = _merkmale(v)
                neu, weg = frozenset(jetzt - vorher), frozenset(vorher - jetzt)
                ergebnis.append(Schritt(revision, neu, weg))
                vorher = jetzt
        finally:
            engine.dispose()
    return ergebnis


def leite_stand_ab(verbindung: Connection, ini: Path) -> str | None:
    """Revision, die das Schema der Datenbank zeigt — ``None`` ohne Tabellen."""
    vorhanden = _merkmale(verbindung)
    if not _struktur(vorhanden):
        return None
    stand = None
    for schritt in schritte(ini):
        if not schritt.passt(vorhanden):
            break
        stand = schritt.revision
    if stand is None:
        msg = "Keine Tabellen von accounti erkannt — --db prüfen (nichts geändert)"
        raise UpgradeError(msg)
    return stand


def _pruefe_datei(db: str) -> None:
    """Eine SQLite-Datei, die es nicht gibt, ist meist ein Tippfehler in ``--db`` —
    ``upgrade head`` legte sonst eine neue Datenbank an, die echte bliebe alt
    (Nachprüfung N4). Neu anlegen ist ``db init``."""
    try:
        url = make_url(db)
    except SQLAlchemyError as fehler:
        raise UpgradeError(f"--db: {fehler}") from fehler
    name = url.database
    if not url.drivername.startswith("sqlite") or not name or name == ":memory:":
        return
    if name.startswith("file:") or Path(name).exists():
        return
    msg = (
        f"{name} gibt es nicht — --db prüfen; eine neue Datenbank legt "
        "'accounti db init' an (nichts geändert)"
    )
    raise UpgradeError(msg)


def fehlendes_schema(verbindung: Connection) -> list[str]:
    """Tabellen und Spalten des Codes (``Base.metadata``), die der Datenbank fehlen —
    erst die Tabellen, dann die Spalten vorhandener Tabellen; nach ``upgrade head``
    ein Zeichen, dass der Versionsvermerk nicht zum Schema passt. Fehlende Tabellen
    zählen mit: ``init_db`` legt sie zwar an, ihre Migration liefe aber nie mehr (im
    Vorabstand fehlte so ``verrechnungen``)."""
    from accounti.db import Base, registriere_tabellen

    registriere_tabellen()
    pruefer = inspect(verbindung)
    vorhanden = set(pruefer.get_table_names())
    tabellen: list[str] = []
    spalten: list[str] = []
    for name, tabelle in sorted(Base.metadata.tables.items()):
        if name not in vorhanden:
            tabellen.append(f"Tabelle {name}")
            continue
        da = {s["name"] for s in pruefer.get_columns(name)}
        spalten += [
            f"Spalte {name}.{s.name}" for s in tabelle.columns if s.name not in da
        ]
    return tabellen + spalten


def _schema_passt_nicht(
    verbindung: Connection,
    ini: Path,
    fehlt: list[str],
    geaendert: bool,
    vermerk: str | None = None,
) -> str:
    """Die eine Meldung für einen Vermerk, der nicht zum Schema passt — mit dem Stand,
    den das Schema zeigt, und beiden verlustfreien Wegen (``--aus-schema`` bzw. von
    Hand ``alembic stamp --purge``)."""
    try:
        abgeleitet = leite_stand_ab(verbindung, ini)
    except UpgradeError:
        abgeleitet = None
    liste = ", ".join(fehlt[:8]) + (
        f" und {len(fehlt) - 8} weitere" if len(fehlt) > 8 else ""
    )
    jetzt = _stand_von(verbindung)
    vermerk = vermerk or jetzt
    stand = f" (laut Schema {abgeleitet})" if abgeleitet else ""
    nach = f", nach den Migrationen jetzt {jetzt}" if jetzt != vermerk else ""
    hand = (
        f"; von Hand: 'alembic stamp --purge {abgeleitet}' (der Stand, den das Schema "
        "zeigt) und noch einmal 'accounti db upgrade'"
        if abgeleitet
        else ""
    )
    return (
        f"Das Schema passt nicht zum Versionsvermerk {vermerk}{stand}{nach}: es "
        f"fehlen {liste}. Meist eine Datenbank vom Vorabstand von 10b-1 oder von "
        "einem Zweig mit anderer Reihenfolge der Migrationen. Verlustfrei: Sicherung "
        "erstellen (accounti sicherung erstellen), dann 'accounti db upgrade "
        "--aus-schema' — der Stand kommt aus dem Schema, die fehlenden Migrationen "
        f"laufen nach{hand} (docs/betrieb.md, Upgrades)."
        + ("" if geaendert else " Nichts geändert.")
    )


def _koepfe(verbindung: Connection) -> tuple[str, ...]:
    """Alle Zeilen des Versionsvermerks (mehr als eine nach ``alembic upgrade heads``
    mit zwei Köpfen)."""
    from alembic.runtime.migration import MigrationContext

    return tuple(MigrationContext.configure(verbindung).get_current_heads())


def _stand_von(verbindung: Connection) -> str | None:
    from alembic.runtime.migration import MigrationContext

    return MigrationContext.configure(verbindung).get_current_revision()


def _stand(engine: Engine) -> str | None:
    from alembic.runtime.migration import MigrationContext

    with engine.connect() as v:
        return MigrationContext.configure(v).get_current_revision()


def _stand_nach_fehler(engine: Engine) -> str:
    try:
        return _stand(engine) or "ohne Versionsvermerk"
    except SQLAlchemyError:
        return "unbekannt (keine Verbindung)"


def aktualisiere(db: str, ini: Path, *, aus_schema: bool = False) -> Ergebnis:
    """Stand ermitteln (ohne Vermerk: aus dem Schema, dann gestempelt) und
    ``upgrade head``. Fehler der Datenbank werden zum ``UpgradeError`` mit dem
    erreichten Stand (Nachprüfung N4: sonst ein Traceback). Fehlen danach Tabellen
    oder Spalten des Codes, ebenfalls ``UpgradeError`` mit dem verlustfreien Weg
    (``aus_schema``: den Stand auch bei vorhandenem Vermerk aus dem Schema
    ableiten)."""
    _pruefe_datei(db)
    engine = create_engine(db)
    try:
        return _aktualisiere(engine, ini, aus_schema)
    except SQLAlchemyError as fehler:
        ursache = getattr(fehler, "orig", None) or fehler
        grund = (str(ursache).strip().splitlines() or [type(ursache).__name__])[0]
        stand = _stand_nach_fehler(engine)
        msg = f"Upgrade abgebrochen: {grund} — Stand jetzt: {stand}"
        if engine.dialect.name == "sqlite":
            msg += (
                ". Unter SQLite kann ein Schritt halb ausgeführt sein: die Sicherung "
                "von vor dem Update zurückspielen (docs/betrieb.md, Upgrades)"
            )
        raise UpgradeError(msg) from fehler
    finally:
        engine.dispose()


def _aktualisiere(engine: Engine, ini: Path, aus_schema: bool = False) -> Ergebnis:
    alle = _revisionen(ini)
    vermerk: str | None = None
    with engine.connect() as v:
        koepfe = _koepfe(v)
        if len(koepfe) > 1 and not aus_schema:
            msg = (
                f"Der Versionsvermerk nennt mehrere Stände ({', '.join(koepfe)}) — "
                "meist ein 'alembic upgrade heads' mit zwei Köpfen. Verlustfrei: "
                "Sicherung erstellen, dann 'accounti db upgrade --aus-schema' (der "
                "Stand kommt aus dem Schema). Nichts geändert."
            )
            raise UpgradeError(msg)
        vorher = koepfe[0] if len(koepfe) == 1 else None
        abgeleitet = vorher is None and bool(_struktur(_merkmale(v)))
        if len(koepfe) > 1:
            # zwei Zeilen im Vermerk (Zweikopf-Zustand): der Stand nur aus dem Schema
            vermerk, abgeleitet = ", ".join(koepfe), True
            vorher = leite_stand_ab(v, ini)
        elif abgeleitet:
            vorher = leite_stand_ab(v, ini)
        elif aus_schema and vorher in alle and _struktur(_merkmale(v)):
            # nur zurück: ein jüngerer Stand laut Schema (init_db des neuen Codes vor
            # der Migration) bliebe beim Vermerk — dessen Migrationen holen nach
            schema = leite_stand_ab(v, ini)
            if schema is not None and alle.index(schema) < alle.index(vorher):
                vermerk, vorher, abgeleitet = vorher, schema, True
    if vorher is not None and vorher not in alle:
        msg = f"Unbekannter Stand {vorher} — passt die alembic.ini zum Code?"
        raise UpgradeError(msg)
    return _lauf(engine, ini, alle, vorher, abgeleitet, vermerk)


def _lauf(
    engine: Engine,
    ini: Path,
    alle: list[str],
    vorher: str | None,
    abgeleitet: bool,
    vermerk: str | None,
) -> Ergebnis:
    """Stempeln (abgeleitet; ``vermerk``: der alte Vermerk, ``--purge``), ``upgrade
    head`` und die Schemaprüfung davor (nichts offen) und danach."""
    from alembic import command

    offen = alle[alle.index(vorher) + 1 :] if vorher in alle else alle
    if vermerk is None:
        with engine.connect() as v:
            if not abgeleitet and not offen and (fehlt := fehlendes_schema(v)):
                # nichts zu migrieren, aber Tabellen fehlen: vor jeder Änderung
                raise UpgradeError(_schema_passt_nicht(v, ini, fehlt, False))
    with engine.begin() as v:
        if abgeleitet and vorher is not None:
            command.stamp(_konfig(ini, v), vorher, purge=vermerk is not None)
        command.upgrade(_konfig(ini, v), "head")
    with engine.connect() as v:
        if fehlt := fehlendes_schema(v):
            raise UpgradeError(
                _schema_passt_nicht(v, ini, fehlt, bool(offen), vermerk or vorher)
            )
    return Ergebnis(vorher, abgeleitet, _stand(engine), offen, vermerk)
