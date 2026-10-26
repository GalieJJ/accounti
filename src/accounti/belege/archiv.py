"""Belegarchiv — Originaldateien unverändert, content-adressiert, ohne Löschpfad."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import date
from pathlib import Path

from accounti.betrieb.aufbewahrung import Unterlage, frist_ende

_ENDUNG = re.compile(r"[a-z0-9]{1,10}")


def bereinige_endung(endung: str) -> str:
    """``.pdf`` o. Ä. — Leerzeichen und Großbuchstaben aus Dateinamen wie
    „Quittung 12.03. Shell“ werden entfernt; was dann keine Endung ist, entfällt."""
    rein = "".join(endung.lower().split()).rsplit(".", 1)[-1]
    return f".{rein}" if _ENDUNG.fullmatch(rein) else ""


def aufbewahrungsende(
    entstanden: date, unterlage: Unterlage = Unterlage.BUCHUNGSBELEG
) -> date:
    """Letzter Tag der Aufbewahrungsfrist — Frist aus ``betrieb.aufbewahrung`` (eine
    Quelle für Archiv, Bericht und Verfahrensdokumentation).

    Buchungsbelege und Rechnungen 8 Jahre (§ 147 Abs. 1 Nr. 4, Abs. 3 AO i. d. F. des
    BEG IV; § 14b Abs. 1 UStG), Protokolle als Aufzeichnungen (``Unterlage.BUCH``) 10
    Jahre. Beginn mit dem Schluss des Kalenderjahres, in dem der Beleg entstanden bzw.
    die Rechnung ausgestellt ist (§ 147 Abs. 4 AO, § 14b Abs. 1 Satz 3 UStG) — also
    ab dem Belegdatum, ohne Belegdatum ab dem Eingang.
    """
    return frist_ende(unterlage, entstanden)


class BelegArchiv:
    """Legt Dateien unter ihrem SHA-256 ab: ``<wurzel>/ab/cd/<hash><endung>``.

    Abgelegte Dateien werden schreibgeschützt und nie überschrieben. Eine
    Löschmethode gibt es bewusst nicht — Aussondern nach Fristablauf ist ein
    eigener, protokollierter Vorgang.
    """

    def __init__(self, wurzel: str | Path) -> None:
        self.wurzel = Path(wurzel)

    def _ordner(self, datei_hash: str) -> Path:
        return self.wurzel / datei_hash[:2] / datei_hash[2:4]

    def pfad(self, datei_hash: str) -> Path:
        treffer = sorted(self._ordner(datei_hash).glob(f"{datei_hash}*"))
        if treffer:
            return treffer[0]
        msg = f"Beleg {datei_hash} ist nicht im Archiv."
        raise FileNotFoundError(msg)

    def enthaelt(self, datei_hash: str) -> bool:
        return any(self._ordner(datei_hash).glob(f"{datei_hash}*"))

    def lese(self, datei_hash: str) -> bytes:
        return self.pfad(datei_hash).read_bytes()

    def ablegen(self, inhalt: bytes, endung: str = "") -> str:
        """Legt den Inhalt ab und gibt seinen Hash zurück. Idempotent."""
        datei_hash = hashlib.sha256(inhalt).hexdigest()
        if self.enthaelt(datei_hash):
            return datei_hash
        endung = bereinige_endung(endung)
        ordner = self._ordner(datei_hash)
        ordner.mkdir(parents=True, exist_ok=True)
        ziel = ordner / f"{datei_hash}{endung}"
        tmp = ziel.with_name(f".{ziel.name}.tmp")
        tmp.unlink(missing_ok=True)
        tmp.write_bytes(inhalt)
        os.chmod(tmp, 0o444)
        tmp.replace(ziel)
        return datei_hash
