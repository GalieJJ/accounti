"""Verschlüsselte Sicherung von Datenbank **und** Belegarchiv — und Wiederherstellung.

Inhalt (Tar-Strom, verschlüsselt mit ``betrieb.verschluesselung``)::

    datenbank/<tabelle>.jsonl   eine Zeile je Datensatz, Werte typgetreu
    archiv/ab/cd/<sha256>.<e>   die Originaldateien des Belegarchivs
    manifest.json               zuletzt: Zeilenzahl und SHA-256 je Tabelle,
                                SHA-256 je Archivdatei, Format, Zeitpunkt

Die Tabellen kommen über SQLAlchemy Core statt ``pg_dump``: dieselbe Sicherung lässt
sich in SQLite und PostgreSQL zurückspielen, und das Abbild braucht keine
Datenbankwerkzeuge. Zeilen kommen bytegleich zurück — Hash-Ketten (USt-IdNr.-,
Übermittlungs-, Zahlungslauf-, Abschlussprotokoll, Kontoauszüge) bleiben gültig.
Sitzungen werden nicht gesichert.

Alle Tabellen werden in **einer** Lese-Transaktion gelesen (PostgreSQL: ``REPEATABLE
READ READ ONLY``) — die Sicherung ist ein Stand, auch wenn ``app`` und ``lauf``
währenddessen schreiben. Eine SQLite-Datei wird zuerst mit der Backup-API von SQLite
in eine Temporärdatei kopiert (ein Schritt, kurze Lesesperre) und dann aus der Kopie
gelesen — Schreiber warten so nur Augenblicke statt der ganzen Sicherung. Belege,
deren Datei im Archiv fehlt, nennt das Manifest; fehlt das Archiv ganz, obwohl Belege
darauf verweisen, bricht die Sicherung ab (falscher ``--archiv``-Pfad).

Wiederhergestellt wird nur in eine **leere** Umgebung, in einer Transaktion: Erst wenn
alle Zeilenzahlen und Hashes zum Manifest passen, wird das Archiv an seinen Platz
gelegt und danach festgeschrieben; sonst bleibt nichts zurück.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import IO, Any, BinaryIO
from uuid import UUID

from sqlalchemy import (
    Column,
    Connection,
    MetaData,
    String,
    Table,
    func,
    insert,
    inspect,
    make_url,
    select,
    text,
)
from sqlalchemy.exc import SQLAlchemyError

from accounti import __version__
from accounti.betrieb.verschluesselung import (
    EntschluesselnderLeser,
    ManipuliertError,
    SicherungsschluesselError,
    VerschluesselnderSchreiber,
)
from accounti.db import Base, init_db, registriere_tabellen, session_factory

FORMAT = 1
AUSGELASSEN = frozenset(
    {"auth_sitzungen"}
)  # flüchtig, nach der Wiederherstellung wertlos
ALEMBIC = "alembic_version"
# Endung: heute bereinigt (``BelegArchiv.ablegen``); ältere Ablagen tragen auch
# Leerzeichen o. Ä. — erlaubt ist alles außer Schrägstrichen und Steuerzeichen
_ARCHIVPFAD = re.compile(
    r"^([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})(\.[^/\\\x00-\x1f\x7f]{1,64})?$"
)
SYSTEM = "system"
GESELLSCHAFT = "gesellschaft"
_STAPEL = 500


class SicherungError(RuntimeError):
    """Sicherung oder Wiederherstellung ist so nicht möglich."""


@dataclass
class Ergebnis:
    tabellen: dict[str, int] = field(default_factory=dict)
    dateien: int = 0
    bytes_archiv: int = 0
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def zeilen(self) -> int:
        return sum(self.tabellen.values())

    @property
    def fehlende(self) -> int:
        """Belege, deren Datei beim Sichern nicht im Archiv lag."""
        return len(self.manifest.get("fehlende_archivdateien", []))

    @property
    def system(self) -> bool:
        return self.manifest.get("inhalt") == SYSTEM


# ---------------------------------------------------------------------------
# Werte typgetreu als JSON
# ---------------------------------------------------------------------------


def kodiere(wert: Any) -> Any:
    if wert is None or isinstance(wert, bool | int | float | str):
        return wert
    if isinstance(wert, Decimal):
        return {"$": "dec", "v": str(wert)}
    if isinstance(wert, datetime):
        return {"$": "dt", "v": wert.isoformat()}
    if isinstance(wert, date):
        return {"$": "d", "v": wert.isoformat()}
    if isinstance(wert, time):
        return {"$": "t", "v": wert.isoformat()}
    if isinstance(wert, bytes):
        return {"$": "b", "v": base64.b64encode(wert).decode()}
    if isinstance(wert, UUID):
        return {"$": "uuid", "v": str(wert)}
    if isinstance(wert, dict | list):
        return {"$": "json", "v": wert}
    msg = f"Typ {type(wert).__name__} lässt sich nicht sichern"
    raise SicherungError(msg)


def dekodiere(wert: Any) -> Any:
    if not isinstance(wert, dict):
        return wert
    art = wert.get("$")
    inhalt: Any = wert.get("v")
    if art == "dec":
        return Decimal(inhalt)
    if art == "dt":
        return datetime.fromisoformat(inhalt)
    if art == "d":
        return date.fromisoformat(inhalt)
    if art == "t":
        return time.fromisoformat(inhalt)
    if art == "b":
        return base64.b64decode(inhalt)
    if art == "uuid":
        return UUID(inhalt)
    if art == "json":
        return inhalt
    msg = f"Unbekannter Wert in der Sicherung: {art!r}"
    raise SicherungError(msg)


# ---------------------------------------------------------------------------
# Erstellen
# ---------------------------------------------------------------------------


def _metadaten() -> MetaData:
    registriere_tabellen()
    return Base.metadata


def _alembic_tabelle(metadaten: MetaData) -> Table:
    if ALEMBIC in metadaten.tables:
        return metadaten.tables[ALEMBIC]
    return Table(
        ALEMBIC, MetaData(), Column("version_num", String(32), primary_key=True)
    )


@contextmanager
def lesetransaktion(verbindung: Connection) -> Iterator[Connection]:
    """Eine Lese-Transaktion über alle folgenden Abfragen — ein Stand der Datenbank.

    PostgreSQL: ``REPEATABLE READ READ ONLY`` (ein Schnappschuss ab der ersten
    Abfrage, Schreiber werden nicht aufgehalten). SQLite: pysqlite beginnt vor
    ``SELECT`` keine Transaktion, also ausdrücklich ``BEGIN`` — im WAL-Modus ein
    Schnappschuss, sonst hält die Lesesperre Schreiber bis zum Ende auf.
    """
    if verbindung.dialect.name == "postgresql":
        verbindung = verbindung.execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        )
        verbindung.begin()
    elif verbindung.dialect.name == "sqlite":
        verbindung.exec_driver_sql("BEGIN")
    else:  # pragma: no cover - andere Datenbanken nutzt accounti nicht
        verbindung = verbindung.execution_options(isolation_level="REPEATABLE READ")
        verbindung.begin()
    try:
        yield verbindung
    finally:
        verbindung.rollback()


@contextmanager
def lesequelle(db: str) -> Iterator[str]:
    """Woraus gelesen wird: eine SQLite-Datei als Kopie über die Backup-API von
    SQLite (``sqlite3.Connection.backup`` in einem Schritt — ein Stand, die
    Lesesperre hält nur so lange wie das Kopieren der Seiten), alles andere direkt.

    Die Kopie liegt mit Rechten 0600 **neben der Datenbank** — nicht im
    Temporärordner (im Container ein tmpfs im Speicher) und nicht im
    Sicherungsordner (oft ein entferntes Laufwerk) — und wird gleich gelöscht.
    Eine SQLite-Datei, die es nicht gibt, wird nicht angelegt: Abbruch (Cron aus
    einem anderen Arbeitsverzeichnis, Tippfehler)."""
    url = make_url(db)
    pfad = url.database or ""
    if (
        url.get_backend_name() != "sqlite"
        or pfad in ("", ":memory:")
        or pfad.startswith("file:")
    ):
        yield db
        return
    if not Path(pfad).is_file():
        msg = (
            f"Die Datenbank {Path(pfad).resolve()} gibt es nicht — --db bzw. das "
            "Arbeitsverzeichnis prüfen (es wurde nichts angelegt)"
        )
        raise SicherungError(msg)
    griff, kopie = tempfile.mkstemp(
        prefix=".accounti-sicherung-", suffix=".db", dir=Path(pfad).resolve().parent
    )
    os.close(griff)
    os.chmod(kopie, 0o600)
    try:
        quelle = sqlite3.connect(pfad)
        try:
            ziel = sqlite3.connect(kopie)
            try:
                quelle.backup(ziel)
            finally:
                ziel.close()
        finally:
            quelle.close()
        yield f"sqlite:///{kopie}"
    finally:
        Path(kopie).unlink(missing_ok=True)


def _verwiesene_dateien(verbindung: Connection, metadaten: MetaData) -> set[str]:
    """Hashes der Archivdateien, auf die Belege verweisen."""
    belege = metadaten.tables.get("belege")
    if belege is None:
        return set()
    return {
        wert
        for (wert,) in verbindung.execute(
            select(belege.c.datei_hash)
            .where(belege.c.datei_hash.is_not(None))
            .distinct()
        )
        if wert
    }


def _zeilen(verbindung: Connection, tabelle: Table) -> Iterator[bytes]:
    """Zeilen als JSON — nur Spalten, die es in der Datenbank gibt: Eine Datenbank
    vor der Migration (z. B. ohne ``buchungssaetze.storno_von``) lässt sich so mit dem
    neuen Code sichern; fehlende Spalten bleiben beim Zurückspielen leer bzw. auf
    ihrem Standard."""
    vorhanden = {s["name"] for s in inspect(verbindung).get_columns(tabelle.name)}
    spalten = [c for c in tabelle.columns if c.name in vorhanden]
    reihenfolge = [c for c in tabelle.primary_key.columns if c in spalten] or spalten
    for zeile in verbindung.execute(select(*spalten).order_by(*reihenfolge)):
        werte = {k: kodiere(v) for k, v in zeile._mapping.items()}
        yield (json.dumps(werte, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _fuege_hinzu(
    tar: tarfile.TarFile, name: str, inhalt: IO[bytes], groesse: int
) -> None:
    info = tarfile.TarInfo(name)
    info.size = groesse
    info.mode = 0o400
    info.mtime = int(datetime.now().timestamp())
    tar.addfile(info, inhalt)


def archivdateien(archiv: Path) -> list[tuple[str, Path]]:
    """Die Dateien des Belegarchivs (ohne halbe ``.tmp``-Dateien), sortiert."""
    if not archiv.is_dir():
        return []
    gefunden = []
    for pfad in sorted(archiv.rglob("*")):
        if not pfad.is_file() or pfad.name.startswith("."):
            continue
        rel = pfad.relative_to(archiv).as_posix()
        if not _ARCHIVPFAD.match(rel):
            msg = f"Fremde Datei im Belegarchiv: {rel} — nicht gesichert, bitte prüfen"
            raise SicherungError(msg)
        gefunden.append((rel, pfad))
    return gefunden


def _pruefe_archiv(
    archiv: Path, dateien: list[tuple[str, Path]], verwiesen: set[str]
) -> list[str]:
    """Fehlende Archivdateien — fehlt das Archiv ganz, ist das ein Fehler."""
    if verwiesen and not dateien:
        zustand = "ist leer" if archiv.is_dir() else "fehlt"
        msg = (
            f"Das Belegarchiv {archiv} fehlt oder ist leer ({zustand}), aber "
            f"{len(verwiesen)} Belege verweisen auf Archivdateien — --archiv prüfen "
            "(Arbeitsverzeichnis?) oder bewusst --ohne-archiv sichern"
        )
        raise SicherungError(msg)
    vorhanden = {rel.split("/")[-1][:64] for rel, _ in dateien}
    return sorted(verwiesen - vorhanden)


def erstelle(
    db: str,
    archiv: Path | None,
    ziel: Path,
    schluessel: bytes,
    gesellschaft: str | None = None,
    *,
    system: bool = False,
) -> Ergebnis:
    """Schreibt die Sicherung atomar nach ``ziel`` (Rechte 0600).

    ``system``: Sicherung der Systemdatenbank (Benutzer, Rollen, Token) — ohne
    Archiv und ohne Gesellschaft; zurück nur mit ``system=True``.
    """
    if ziel.exists():
        msg = f"{ziel} gibt es schon — eine Sicherung wird nie überschrieben"
        raise SicherungError(msg)
    if system and archiv is not None:
        raise SicherungError("Die Systemdatenbank wird ohne Belegarchiv gesichert")
    metadaten = _metadaten()
    with lesequelle(db) as quelle:
        return _erstelle(
            quelle, archiv, ziel, schluessel, gesellschaft, system, metadaten
        )


def _erstelle(
    db: str,
    archiv: Path | None,
    ziel: Path,
    schluessel: bytes,
    gesellschaft: str | None,
    system: bool,
    metadaten: MetaData,
) -> Ergebnis:
    engine, _ = session_factory(db)
    ergebnis = Ergebnis()
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "accounti": __version__,
        "erstellt_am": datetime.now().isoformat(timespec="seconds"),
        "inhalt": SYSTEM if system else GESELLSCHAFT,
        "gesellschaft": None if system else gesellschaft,
        "datenbank": engine.dialect.name,
        "tabellen": {},
        "dateien": {},
        "mit_archiv": archiv is not None,
    }
    ziel.parent.mkdir(parents=True, exist_ok=True)
    vorlaeufig = ziel.with_name(f".{ziel.name}.{os.getpid()}.tmp")
    try:
        with (
            engine.connect() as roh,
            lesetransaktion(roh) as verbindung,
        ):
            vorhanden = set(inspect(verbindung).get_table_names())
            if not vorhanden & set(metadaten.tables):
                msg = (
                    "Die Datenbank hat keine Tabellen von accounti — --db prüfen "
                    "(nichts gesichert)"
                )
                raise SicherungError(msg)
            liste: list[tuple[str, Path]] = []
            if archiv is not None:
                liste = archivdateien(archiv)
                verwiesen = (
                    _verwiesene_dateien(verbindung, metadaten)
                    if "belege" in vorhanden
                    else set()
                )
                manifest["fehlende_archivdateien"] = _pruefe_archiv(
                    archiv, liste, verwiesen
                )
            tabellen = [
                t
                for t in metadaten.sorted_tables
                if t.name in vorhanden and t.name not in AUSGELASSEN
            ]
            if ALEMBIC in vorhanden:
                tabellen.append(_alembic_tabelle(metadaten))
            with open(
                vorlaeufig, "wb", opener=lambda p, f: os.open(p, f, 0o600)
            ) as datei:
                _schreibe(
                    datei,
                    schluessel,
                    verbindung,
                    tabellen,
                    liste,
                    manifest,
                    ergebnis,
                    ziel.parent,
                )
        os.replace(vorlaeufig, ziel)
    except BaseException:
        vorlaeufig.unlink(missing_ok=True)
        raise
    finally:
        engine.dispose()
    ergebnis.manifest = manifest
    return ergebnis


def _tabelle_schreiben(
    tar: tarfile.TarFile, verbindung: Connection, tabelle: Table, ordner: Path
) -> dict[str, Any]:
    with tempfile.SpooledTemporaryFile(
        max_size=16 * 1024 * 1024, dir=str(ordner)
    ) as puffer:
        pruefsumme = hashlib.sha256()
        anzahl = 0
        for zeile in _zeilen(verbindung, tabelle):
            puffer.write(zeile)
            pruefsumme.update(zeile)
            anzahl += 1
        groesse = puffer.tell()
        puffer.seek(0)
        _fuege_hinzu(tar, f"datenbank/{tabelle.name}.jsonl", puffer, groesse)
    return {"zeilen": anzahl, "sha256": pruefsumme.hexdigest()}


def _schreibe(
    datei: BinaryIO,
    schluessel: bytes,
    verbindung: Connection,
    tabellen: list[Table],
    archiv: list[tuple[str, Path]],
    manifest: dict[str, Any],
    ergebnis: Ergebnis,
    ordner: Path,
) -> None:
    """Tar-Strom aus Tabellen, Archivdateien und Manifest — verschlüsselt; große
    Tabellen werden in ``ordner`` (neben der Sicherung) ausgelagert."""
    schreiber = VerschluesselnderSchreiber(datei, schluessel)
    with tarfile.open(fileobj=schreiber, mode="w|", format=tarfile.PAX_FORMAT) as tar:  # type: ignore[call-overload]
        for tabelle in tabellen:
            angabe = _tabelle_schreiben(tar, verbindung, tabelle, ordner)
            manifest["tabellen"][tabelle.name] = angabe
            ergebnis.tabellen[tabelle.name] = angabe["zeilen"]
        for rel, pfad in archiv:
            inhalt = pfad.read_bytes()
            wert = hashlib.sha256(inhalt).hexdigest()
            if not rel.split("/")[-1].startswith(wert):
                msg = f"Archivdatei {rel} passt nicht zu ihrem Hash"
                raise SicherungError(msg)
            _fuege_hinzu(tar, f"archiv/{rel}", io.BytesIO(inhalt), len(inhalt))
            manifest["dateien"][rel] = wert
            ergebnis.dateien += 1
            ergebnis.bytes_archiv += len(inhalt)
        roh = json.dumps(manifest, ensure_ascii=False, indent=1).encode()
        _fuege_hinzu(tar, "manifest.json", io.BytesIO(roh), len(roh))
    schreiber.close()
    datei.flush()
    os.fsync(datei.fileno())


# ---------------------------------------------------------------------------
# Lesen, Prüfen, Wiederherstellen
# ---------------------------------------------------------------------------


def _leser(quelle: Path, schluessel: bytes) -> tuple[IO[bytes], EntschluesselnderLeser]:
    datei = open(quelle, "rb")  # noqa: SIM115 - wird vom Aufrufer geschlossen
    try:
        return datei, EntschluesselnderLeser(datei, schluessel)
    except BaseException:
        datei.close()
        raise


def _pruefe_manifest(
    manifest: dict[str, Any],
    ergebnis: Ergebnis,
    gesehen: dict[str, str],
    dateien: dict[str, str],
) -> None:
    if manifest.get("format") != FORMAT:
        msg = f"Format {manifest.get('format')!r} der Sicherung wird nicht unterstützt"
        raise SicherungError(msg)
    erwartet = manifest.get("tabellen", {})
    if set(erwartet) != set(gesehen):
        msg = "Tabellen der Sicherung passen nicht zum Manifest"
        raise ManipuliertError(msg)
    for name, angabe in erwartet.items():
        if (
            angabe["sha256"] != gesehen[name]
            or angabe["zeilen"] != ergebnis.tabellen[name]
        ):
            msg = f"Tabelle {name} passt nicht zum Manifest"
            raise ManipuliertError(msg)
    if manifest.get("dateien", {}) != dateien:
        raise ManipuliertError("Archivdateien passen nicht zum Manifest")


def _durchlaufe(
    tar: tarfile.TarFile,
    tabelle_fuer: Any,
    schreibe_zeilen: Any,
    schreibe_datei: Any,
) -> tuple[Ergebnis, dict[str, Any]]:
    """Ein Durchgang durch den Strom; ruft für Zeilen und Dateien die Ziele auf."""
    ergebnis = Ergebnis()
    hashes: dict[str, str] = {}
    dateien: dict[str, str] = {}
    manifest: dict[str, Any] | None = None
    for mitglied in tar:
        if manifest is not None:
            raise ManipuliertError("Daten hinter dem Manifest")
        name = mitglied.name
        quelle = tar.extractfile(mitglied) if mitglied.isfile() else None
        if quelle is None:
            raise ManipuliertError(f"Unerwarteter Eintrag {name!r}")
        if name == "manifest.json":
            manifest = json.loads(quelle.read())
            continue
        teile = PurePosixPath(name).parts
        if len(teile) == 2 and teile[0] == "datenbank" and name.endswith(".jsonl"):
            tabelle = tabelle_fuer(teile[1][: -len(".jsonl")])
            pruefsumme = hashlib.sha256()
            stapel: list[dict[str, Any]] = []
            anzahl = 0
            for zeile in quelle:
                pruefsumme.update(zeile)
                stapel.append({k: dekodiere(v) for k, v in json.loads(zeile).items()})
                anzahl += 1
                if len(stapel) >= _STAPEL:
                    schreibe_zeilen(tabelle, stapel)
                    stapel = []
            if stapel:
                schreibe_zeilen(tabelle, stapel)
            hashes[tabelle.name] = pruefsumme.hexdigest()
            ergebnis.tabellen[tabelle.name] = anzahl
            continue
        if teile and teile[0] == "archiv":
            rel = "/".join(teile[1:])
            treffer = _ARCHIVPFAD.match(rel)
            if treffer is None or rel != PurePosixPath(*teile[1:]).as_posix():
                raise ManipuliertError(f"Unerlaubter Archivpfad {name!r}")
            inhalt = quelle.read()
            wert = hashlib.sha256(inhalt).hexdigest()
            if wert != treffer.group(3) or not wert.startswith(
                treffer.group(1) + treffer.group(2)
            ):
                raise ManipuliertError(f"Archivdatei {rel} passt nicht zu ihrem Hash")
            schreibe_datei(rel, inhalt)
            dateien[rel] = wert
            ergebnis.dateien += 1
            ergebnis.bytes_archiv += len(inhalt)
            continue
        raise ManipuliertError(f"Unerwarteter Eintrag {name!r}")
    if manifest is None:
        raise ManipuliertError("Manifest fehlt — Sicherung unvollständig")
    _pruefe_manifest(manifest, ergebnis, hashes, dateien)
    ergebnis.manifest = manifest
    return ergebnis, manifest


def pruefe(quelle: Path, schluessel: bytes) -> Ergebnis:
    """Entschlüsselt und prüft alles gegen das Manifest — schreibt nichts."""
    metadaten = _metadaten()

    def tabelle_fuer(name: str) -> Table:
        if name == ALEMBIC:
            return _alembic_tabelle(metadaten)
        if name not in metadaten.tables:
            raise SicherungError(f"Unbekannte Tabelle {name!r} in der Sicherung")
        return metadaten.tables[name]

    datei, leser = _leser(quelle, schluessel)
    with datei:
        with tarfile.open(fileobj=leser, mode="r|") as tar:  # type: ignore[call-overload]
            ergebnis, _ = _durchlaufe(
                tar, tabelle_fuer, lambda t, z: None, lambda r, i: None
            )
        leser.lies_bis_zum_ende()
    return ergebnis


def _ist_leer(verbindung: Connection, metadaten: MetaData) -> list[str]:
    belegt = []
    vorhanden = set(inspect(verbindung).get_table_names())
    for tabelle in metadaten.sorted_tables:
        if (
            tabelle.name in vorhanden
            and verbindung.execute(select(func.count()).select_from(tabelle)).scalar()
        ):
            belegt.append(tabelle.name)
    return belegt


def _sequenzen_nachziehen(verbindung: Connection, metadaten: MetaData) -> None:
    if verbindung.dialect.name != "postgresql":
        return
    for tabelle in metadaten.sorted_tables:
        for spalte in tabelle.primary_key.columns:
            if spalte.autoincrement is True:
                verbindung.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{tabelle.name}', "
                        f"'{spalte.name}'), COALESCE(MAX({spalte.name}), 1), "
                        f"MAX({spalte.name}) IS NOT NULL) FROM {tabelle.name}"
                    )
                )


def pruefe_art(
    manifest: dict[str, Any],
    *,
    system: bool = False,
    gesellschaft: str | None = None,
    fremde: bool = False,
) -> None:
    """Passt die Sicherung zum Ziel? Systemdatenbank nur als solche, eine
    Gesellschaft nur in dieselbe (``fremde``: bewusst in eine andere)."""
    ist_system = manifest.get("inhalt") == SYSTEM
    if system and not ist_system:
        msg = (
            "Das ist keine Sicherung der Systemdatenbank — ohne --system zurückspielen"
        )
        raise SicherungError(msg)
    if ist_system and not system:
        msg = (
            "Das ist eine Sicherung der Systemdatenbank (Benutzer, Rollen, Token) — "
            "mit --system zurückspielen"
        )
        raise SicherungError(msg)
    herkunft = manifest.get("gesellschaft")
    if (
        not system
        and not fremde
        and gesellschaft is not None
        and herkunft is not None
        and herkunft != gesellschaft
    ):
        msg = (
            f"Die Sicherung gehört zur Gesellschaft {herkunft}, nicht {gesellschaft} — "
            "mit --fremde-gesellschaft bewusst übernehmen"
        )
        raise SicherungError(msg)


def _lege_archiv_hin(zwischen: Path, archiv: Path) -> None:
    """Zwischenordner → Archiv (das leer ist oder fehlt)."""
    if archiv.exists():
        archiv.rmdir()
    os.replace(zwischen, archiv)


def stelle_wieder_her(
    quelle: Path,
    db: str,
    archiv: Path | None,
    schluessel: bytes,
    *,
    gesellschaft: str | None = None,
    fremde: bool = False,
    system: bool = False,
) -> Ergebnis:
    """Spielt die Sicherung in eine leere Datenbank und ein leeres Archiv zurück.

    Das Archiv kommt **vor** dem Festschreiben an seinen Platz: Scheitert das
    Umbenennen, ist auch die Datenbank unverändert; scheitert das Festschreiben,
    wird das Archiv wieder entfernt.
    """
    metadaten = _metadaten()
    if archiv is not None and archiv.exists() and any(archiv.iterdir()):
        msg = f"Das Belegarchiv {archiv} ist nicht leer — nur in eine leere Umgebung"
        raise SicherungError(msg)
    engine, _ = session_factory(db)
    init_db(engine)
    zwischen: Path | None = None
    if archiv is not None:
        archiv.parent.mkdir(parents=True, exist_ok=True)
        zwischen = Path(tempfile.mkdtemp(prefix=f".{archiv.name}-", dir=archiv.parent))
    try:
        with engine.connect() as verbindung:
            belegt = _ist_leer(verbindung, metadaten)
            if belegt:
                msg = (
                    "Die Datenbank ist nicht leer (z.B. "
                    + ", ".join(belegt[:3])
                    + ") — nur in eine leere Umgebung"
                )
                raise SicherungError(msg)
            alembic = _alembic_tabelle(metadaten)

            def tabelle_fuer(name: str) -> Table:
                if name == ALEMBIC:
                    alembic.create(verbindung, checkfirst=True)
                    return alembic
                if name not in metadaten.tables:
                    raise SicherungError(
                        f"Unbekannte Tabelle {name!r} in der Sicherung"
                    )
                return metadaten.tables[name]

            def schreibe_zeilen(tabelle: Table, zeilen: list[dict[str, Any]]) -> None:
                if (
                    tabelle is alembic
                    and verbindung.execute(
                        select(func.count()).select_from(alembic)
                    ).scalar()
                ):
                    # Der Vermerk beschreibt das Schema des Ziels (init_db legt es
                    # nach diesem Code an und stempelt es), nicht die Daten: eine
                    # ältere Revision aus der Sicherung ließe alembic Tabellen ein
                    # zweites Mal anlegen (Befund Betrieb B2)
                    return
                verbindung.execute(insert(tabelle), zeilen)

            def schreibe_datei(rel: str, inhalt: bytes) -> None:
                if zwischen is None:
                    return
                ziel = zwischen / rel
                ziel.parent.mkdir(parents=True, exist_ok=True)
                ziel.write_bytes(inhalt)
                os.chmod(ziel, 0o444)

            datei, leser = _leser(quelle, schluessel)
            with datei:
                with tarfile.open(fileobj=leser, mode="r|") as tar:  # type: ignore[call-overload]
                    ergebnis, manifest = _durchlaufe(
                        tar, tabelle_fuer, schreibe_zeilen, schreibe_datei
                    )
                leser.lies_bis_zum_ende()
            pruefe_art(
                manifest, system=system, gesellschaft=gesellschaft, fremde=fremde
            )
            if archiv is not None and not manifest.get("mit_archiv", True):
                msg = (
                    "Die Sicherung enthält kein Belegarchiv — mit --ohne-archiv "
                    "zurückspielen"
                )
                raise SicherungError(msg)
            _sequenzen_nachziehen(verbindung, metadaten)
            hingelegt = False
            if zwischen is not None and archiv is not None:
                _lege_archiv_hin(zwischen, archiv)
                zwischen, hingelegt = None, True
            try:
                verbindung.commit()
            except BaseException:
                if hingelegt and archiv is not None:
                    shutil.rmtree(archiv, ignore_errors=True)
                raise
        return ergebnis
    except (SicherungError, ManipuliertError, SicherungsschluesselError):
        raise
    except tarfile.TarError as fehler:
        raise ManipuliertError(f"Sicherung beschädigt: {fehler}") from fehler
    except SQLAlchemyError as fehler:
        # der Text enthielte SQL und Werte — nur die Art nennen
        msg = (
            f"Die Datenbank lehnt die Sicherung ab ({type(fehler).__name__}) — "
            "nichts wurde übernommen"
        )
        raise SicherungError(msg) from fehler
    finally:
        if zwischen is not None:
            shutil.rmtree(zwischen, ignore_errors=True)
        engine.dispose()
