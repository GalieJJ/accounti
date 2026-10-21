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

Wiederhergestellt wird nur in eine **leere** Umgebung, in einer Transaktion: Erst wenn
alle Zeilenzahlen und Hashes zum Manifest passen, wird festgeschrieben und das
Archiv an seinen Platz gelegt; sonst bleibt nichts zurück.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import IO, Any
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
_ARCHIVPFAD = re.compile(
    r"^([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})(\.[a-z0-9]{1,10})?$"
)
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


def _zeilen(verbindung: Connection, tabelle: Table) -> Iterator[bytes]:
    reihenfolge = list(tabelle.primary_key.columns) or list(tabelle.columns)
    for zeile in verbindung.execute(select(tabelle).order_by(*reihenfolge)):
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


def erstelle(
    db: str,
    archiv: Path | None,
    ziel: Path,
    schluessel: bytes,
    gesellschaft: str | None = None,
) -> Ergebnis:
    """Schreibt die Sicherung atomar nach ``ziel`` (Rechte 0600)."""
    if ziel.exists():
        msg = f"{ziel} gibt es schon — eine Sicherung wird nie überschrieben"
        raise SicherungError(msg)
    metadaten = _metadaten()
    engine, _ = session_factory(db)
    ergebnis = Ergebnis()
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "accounti": __version__,
        "erstellt_am": datetime.now().isoformat(timespec="seconds"),
        "gesellschaft": gesellschaft,
        "datenbank": engine.dialect.name,
        "tabellen": {},
        "dateien": {},
        "mit_archiv": archiv is not None,
    }
    ziel.parent.mkdir(parents=True, exist_ok=True)
    vorlaeufig = ziel.with_name(f".{ziel.name}.{os.getpid()}.tmp")
    try:
        with (
            open(vorlaeufig, "wb", opener=lambda p, f: os.open(p, f, 0o600)) as datei,
            engine.connect() as verbindung,
        ):
            schreiber = VerschluesselnderSchreiber(datei, schluessel)
            vorhanden = set(inspect(verbindung).get_table_names())
            with tarfile.open(
                fileobj=schreiber, mode="w|", format=tarfile.PAX_FORMAT
            ) as tar:  # type: ignore[call-overload]
                tabellen = [
                    t
                    for t in metadaten.sorted_tables
                    if t.name in vorhanden and t.name not in AUSGELASSEN
                ]
                if ALEMBIC in vorhanden:
                    tabellen.append(_alembic_tabelle(metadaten))
                for tabelle in tabellen:
                    with tempfile.SpooledTemporaryFile(
                        max_size=16 * 1024 * 1024
                    ) as puffer:
                        pruefsumme = hashlib.sha256()
                        anzahl = 0
                        for zeile in _zeilen(verbindung, tabelle):
                            puffer.write(zeile)
                            pruefsumme.update(zeile)
                            anzahl += 1
                        groesse = puffer.tell()
                        puffer.seek(0)
                        _fuege_hinzu(
                            tar, f"datenbank/{tabelle.name}.jsonl", puffer, groesse
                        )
                    manifest["tabellen"][tabelle.name] = {
                        "zeilen": anzahl,
                        "sha256": pruefsumme.hexdigest(),
                    }
                    ergebnis.tabellen[tabelle.name] = anzahl
                for rel, pfad in archivdateien(archiv) if archiv is not None else []:
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
        os.replace(vorlaeufig, ziel)
    except BaseException:
        vorlaeufig.unlink(missing_ok=True)
        raise
    finally:
        engine.dispose()
    ergebnis.manifest = manifest
    return ergebnis


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


def stelle_wieder_her(
    quelle: Path, db: str, archiv: Path | None, schluessel: bytes
) -> Ergebnis:
    """Spielt die Sicherung in eine leere Datenbank und ein leeres Archiv zurück."""
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
            if archiv is not None and not manifest.get("mit_archiv", True):
                msg = (
                    "Die Sicherung enthält kein Belegarchiv — mit --ohne-archiv "
                    "zurückspielen"
                )
                raise SicherungError(msg)
            _sequenzen_nachziehen(verbindung, metadaten)
            verbindung.commit()
        if zwischen is not None and archiv is not None:
            if archiv.exists():
                archiv.rmdir()
            os.replace(zwischen, archiv)
            zwischen = None
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
