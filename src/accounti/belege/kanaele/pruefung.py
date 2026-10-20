"""Dateiprüfung der Kanäle — Typ am Inhalt, Größe, sicherer Dateiname.

Geprüft wird die Signatur der Datei, nicht ihre Endung und nicht der Content-Type,
den ein Absender behauptet. Zugelassen sind die Formate, die die Erkennung lesen
kann (PDF, XML, JPEG, PNG, TIFF); alles andere gehört nicht ins Belegarchiv.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Literal

# Typ → zulässige Endungen; die erste ist die übliche.
DATEITYPEN: dict[str, tuple[str, ...]] = {
    "pdf": (".pdf",),
    "xml": (".xml",),
    "jpeg": (".jpg", ".jpeg"),
    "png": (".png",),
    "tiff": (".tif", ".tiff"),
}
STANDARD_MAX_BYTES = 25 * 1024 * 1024
MAX_NAMENSLAENGE = 200

_BOM_LEER = b"\xef\xbb\xbf \t\r\n"
_FREMDE_SIGNATUREN: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "ZIP/Office"),
    (b"GIF8", "GIF"),
    (b"Rar!", "RAR"),
    (b"\x1f\x8b", "GZIP"),
    (b"7z\xbc\xaf", "7-Zip"),
    (b"\xd0\xcf\x11\xe0", "Office (alt)"),
)

Ablehnung = Literal["leer", "groesse", "typ"]


class DateiAbgelehntError(ValueError):
    """Die Datei wird nicht als Beleg angenommen."""

    def __init__(self, grund: str, art: Ablehnung) -> None:
        super().__init__(grund)
        self.art: Ablehnung = art


def _xml_wurzel(inhalt: bytes) -> str | None:
    """Name des Wurzelelements einer wohlgeformten XML-Datei ohne DTD."""
    if b"<!doctype" in inhalt[:4096].lower():
        return None  # DTDs und Entities lehnt auch der E-Rechnungs-Parser ab
    try:
        for _, element in ET.iterparse(io.BytesIO(inhalt), events=("start",)):
            tag: str = element.tag
            return tag.rpartition("}")[2]
    except ET.ParseError:
        return None
    return None


def erkenne_dateityp(inhalt: bytes) -> str | None:
    """Belegtyp nach der Signatur — ``None``, wenn es kein zugelassenes Format ist."""
    kopf = inhalt[:1024].lstrip(_BOM_LEER)
    if kopf.startswith(b"%PDF-"):
        return "pdf"
    if inhalt.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if inhalt.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if inhalt.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if kopf.startswith(b"<"):
        wurzel = _xml_wurzel(inhalt)
        if wurzel and wurzel.lower() != "html":
            return "xml"
    return None


def _bezeichne_fremd(inhalt: bytes) -> str:
    for signatur, name in _FREMDE_SIGNATUREN:
        if inhalt.startswith(signatur):
            return name
    if inhalt[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
        return "HEIC"
    if inhalt.startswith(b"RIFF") and inhalt[8:12] == b"WEBP":
        return "WebP"
    if b"<html" in inhalt[:1024].lower():
        return "HTML"
    return "unbekannt"


_STEUERZEICHEN = re.compile(r"[\x00-\x1f\x7f]")


def _bereinige(name: str | None) -> str:
    """Nur der letzte Pfadteil, ohne Steuerzeichen und führende Punkte."""
    roh = _STEUERZEICHEN.sub("", name or "")
    return re.split(r"[\\/]", roh)[-1].strip().lstrip(".").strip()


def sicherer_dateiname(name: str | None, typ: str, ersatz: str = "beleg") -> str:
    """Dateiname ohne Pfadanteile und Steuerzeichen, mit zum Typ passender Endung."""
    roh = _bereinige(name)
    endungen = DATEITYPEN[typ]
    if not roh:
        roh = f"{ersatz}{endungen[0]}"
    if not roh.lower().endswith(endungen):
        roh = f"{roh}{endungen[0]}"
    if len(roh) > MAX_NAMENSLAENGE:
        endung = next(e for e in endungen if roh.lower().endswith(e))
        roh = roh[: MAX_NAMENSLAENGE - len(endung)] + roh[-len(endung) :]
    return roh


@dataclass(frozen=True)
class Dateipruefung:
    """Größe und Typ einer eingehenden Datei — gleich für alle Kanäle."""

    max_bytes: int = STANDARD_MAX_BYTES
    typen: frozenset[str] = field(default_factory=lambda: frozenset(DATEITYPEN))

    def pruefe(self, dateiname: str | None, inhalt: bytes) -> str:
        """Prüft die Datei und gibt den sicheren Dateinamen zurück."""
        anzeige = _bereinige(dateiname) or "Datei ohne Namen"
        if not inhalt:
            raise DateiAbgelehntError(f"{anzeige}: leere Datei", "leer")
        if len(inhalt) > self.max_bytes:
            msg = (
                f"{anzeige}: {len(inhalt) / 1024 / 1024:.1f} MB, erlaubt sind "
                f"höchstens {self.max_bytes / 1024 / 1024:.0f} MB"
            )
            raise DateiAbgelehntError(msg, "groesse")
        typ = erkenne_dateityp(inhalt)
        if typ is None:
            msg = (
                f"{anzeige}: Dateityp nicht erlaubt (erkannt: "
                f"{_bezeichne_fremd(inhalt)}; erlaubt: {', '.join(sorted(self.typen))})"
            )
            raise DateiAbgelehntError(msg, "typ")
        if typ not in self.typen:
            msg = (
                f"{anzeige}: Dateityp {typ} ist abgeschaltet "
                f"(erlaubt: {', '.join(sorted(self.typen))})"
            )
            raise DateiAbgelehntError(msg, "typ")
        return sicherer_dateiname(dateiname, typ)
