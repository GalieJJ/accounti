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

Nach dem Upgrade fehlt einer vorhandenen Tabelle keine Spalte des Codes — sonst passt
der Vermerk nicht zum Schema (eine Datenbank, die auf einem Entwicklungszweig mit
anderer Reihenfolge der Migrationen auf dessen Kopf kam, Nachprüfung Merge N-2), und
``db upgrade`` bricht mit dem verlustfreien Weg ab: ``alembic stamp --purge`` auf den
Stand, den das Schema zeigt, dann noch einmal ``db upgrade``. Fehlende Tabellen zählen
nicht (``init_db`` legt Tabellen ohne Migration selbst an).
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


def _stand(engine: Engine) -> str | None:
    from alembic.runtime.migration import MigrationContext

    with engine.connect() as v:
        return MigrationContext.configure(v).get_current_revision()


def _stand_nach_fehler(engine: Engine) -> str:
    try:
        return _stand(engine) or "ohne Versionsvermerk"
    except SQLAlchemyError:
        return "unbekannt (keine Verbindung)"


def aktualisiere(db: str, ini: Path) -> Ergebnis:
    """Stand ermitteln (ohne Vermerk: aus dem Schema, dann gestempelt) und
    ``upgrade head``. Fehler der Datenbank werden zum ``UpgradeError`` mit dem
    erreichten Stand (Nachprüfung N4: sonst ein Traceback)."""
    _pruefe_datei(db)
    engine = create_engine(db)
    try:
        ergebnis = _aktualisiere(engine, ini)
        _pruefe_spalten(engine, ini, ergebnis)
        return ergebnis
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


def _aktualisiere(engine: Engine, ini: Path) -> Ergebnis:
    from alembic import command
    from alembic.runtime.migration import MigrationContext

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
    return Ergebnis(vorher, abgeleitet, _stand(engine), offen)


def _fehlt(verbindung: Connection) -> tuple[list[str], list[str]]:
    """(Spalten des Codes, die vorhandenen Tabellen fehlen; fehlende Tabellen) —
    gemessen an ``Base.metadata``."""
    from accounti.db import Base, registriere_tabellen

    registriere_tabellen()
    vorhanden = _merkmale(verbindung)
    spalten, tabellen = [], []
    for tabelle in Base.metadata.sorted_tables:
        if ("tabelle", tabelle.name) not in vorhanden:
            tabellen.append(tabelle.name)
            continue
        spalten += [
            f"{tabelle.name}.{spalte.name}"
            for spalte in tabelle.columns
            if ("spalte", tabelle.name, spalte.name) not in vorhanden
        ]
    return spalten, tabellen


def _pruefe_spalten(engine: Engine, ini: Path, ergebnis: Ergebnis) -> None:
    """Vermerk und Schema passen zusammen — sonst ``UpgradeError`` mit dem Weg.
    Fehlende Tabellen allein zählen nicht (``init_db`` legt sie an)."""
    with engine.connect() as v:
        spalten, tabellen = _fehlt(v)
        if not spalten:
            return
        stand = leite_stand_ab(v, ini)
    liste = ", ".join(spalten[:8])
    if len(spalten) > 8:
        liste += f" und {len(spalten) - 8} weitere"
    if tabellen:
        liste += f" (Tabellen: {', '.join(tabellen[:8])})"
    msg = (
        f"Stand {ergebnis.nachher} laut Versionsvermerk, aber es fehlen Spalten: "
        f"{liste} — der Vermerk passt nicht zum Schema (z. B. auf einem Zweig mit "
        "anderer Reihenfolge der Migrationen migriert)."
    )
    if stand is not None and stand != ergebnis.nachher:
        msg += (
            f" Verlustfrei: Sicherung erstellen, dann 'alembic stamp --purge {stand}' "
            "(der Stand, den das Schema zeigt) und noch einmal 'accounti db upgrade' — "
            "Migrationen, deren Spalten es schon gibt, übernehmen sie "
            "(docs/betrieb.md, Upgrades)"
        )
    raise UpgradeError(msg)
