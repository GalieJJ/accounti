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
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Connection, create_engine, inspect

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


def aktualisiere(db: str, ini: Path) -> Ergebnis:
    """Stand ermitteln (ohne Vermerk: aus dem Schema, dann gestempelt) und
    ``upgrade head``."""
    from alembic import command
    from alembic.runtime.migration import MigrationContext

    engine = create_engine(db)
    try:
        with engine.connect() as v:
            vorher = MigrationContext.configure(v).get_current_revision()
            abgeleitet = vorher is None and bool(_struktur(_merkmale(v)))
            if abgeleitet:
                vorher = leite_stand_ab(v, ini)
        alle = _revisionen(ini)
        offen = alle[alle.index(vorher) + 1 :] if vorher in alle else alle
        if vorher is not None and vorher not in alle:
            msg = f"Unbekannter Stand {vorher} — passt die alembic.ini zum Code?"
            raise UpgradeError(msg)
        with engine.begin() as v:
            if abgeleitet and vorher is not None:
                command.stamp(_konfig(ini, v), vorher)
            command.upgrade(_konfig(ini, v), "head")
        with engine.connect() as v:
            nachher = MigrationContext.configure(v).get_current_revision()
    finally:
        engine.dispose()
    return Ergebnis(vorher, abgeleitet, nachher, offen)
