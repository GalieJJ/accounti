"""Belegdateien für die Vorschau — nur aus dem Archiv der Gesellschaft, Typ aus dem
Inhalt, nie aus Dateiname oder Endung.

* Zugriff nur über ``Beleg.datei_hash`` aus der Datenbank (Format geprüft), Pfad unter
  der Archivwurzel, Größe begrenzt (``server.max_beleg_mb``), Inhalt gegen den Hash
  geprüft (``BelegVeraendertError`` statt manipulierter Daten).
* ``erkenne``: ``belege.erkennung.erkenne_format`` (wie bei der Belegaufnahme), für
  Bilder die Art nach Signatur. Inline zeigt die Oberfläche nur PDF, PNG und JPEG;
  TIFF wird seitenweise in PNG umgewandelt — nur mit dem TIFF-Decoder von Pillow
  (``formats=["TIFF"]``, kein EPS/Ghostscript) und mit einer Pixelgrenze je Seite
  **vor** dem Dekodieren. XML, SVG, HTML, Text, Office: nie inline.
"""

from __future__ import annotations

import enum
import hashlib
import io
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from accounti.belege.archiv import BelegArchiv
from accounti.belege.erkennung import Format, erkenne_format
from accounti.belege.kanaele import RohBeleg
from accounti.models import Beleg

HASH = re.compile(r"^[0-9a-f]{64}$")
MAX_SEITEN = 20


class BelegdateiError(Exception):
    status = 404


class BelegdateiFehltError(BelegdateiError):
    status = 404


class BelegVeraendertError(BelegdateiError):
    status = 409


class BelegZuGrossError(BelegdateiError):
    status = 413


class KeineVorschauError(BelegdateiError):
    status = 415


class Art(str, enum.Enum):
    PDF = "pdf"
    ZUGFERD = "zugferd"  # PDF mit eingebetteter E-Rechnung
    ERECHNUNG = "erechnung"  # XRechnung als XML
    PNG = "png"
    JPEG = "jpeg"
    TIFF = "tiff"
    UNBEKANNT = "unbekannt"


MEDIENTYP = {
    Art.PDF: "application/pdf",
    Art.ZUGFERD: "application/pdf",
    Art.PNG: "image/png",
    Art.JPEG: "image/jpeg",
}
ENDUNG = {
    Art.PDF: "pdf",
    Art.ZUGFERD: "pdf",
    Art.ERECHNUNG: "xml",
    Art.PNG: "png",
    Art.JPEG: "jpg",
    Art.TIFF: "tif",
    Art.UNBEKANNT: "bin",
}
INLINE = frozenset(MEDIENTYP)


@dataclass(frozen=True)
class Belegdatei:
    pfad: Path
    inhalt: bytes
    art: Art
    xml: bytes | None = None  # E-Rechnung (XML oder in ZUGFeRD eingebettet)
    syntax: str | None = None


def bildart(inhalt: bytes) -> Art:
    if inhalt.startswith(b"\xff\xd8\xff"):
        return Art.JPEG
    if inhalt.startswith(b"\x89PNG\r\n\x1a\n"):
        return Art.PNG
    if inhalt.startswith((b"II*\x00", b"MM\x00*")):
        return Art.TIFF
    return Art.UNBEKANNT


def erkenne(inhalt: bytes) -> tuple[Art, bytes | None, str | None]:
    befund = erkenne_format(
        RohBeleg(dateiname="beleg", inhalt=inhalt, kanal="web", herkunft="vorschau")
    )
    if befund.format is Format.ZUGFERD_PDF:
        return Art.ZUGFERD, befund.xml, befund.syntax
    if befund.format is Format.PDF:
        return Art.PDF, None, None
    if befund.format is Format.ERECHNUNG_XML:
        return Art.ERECHNUNG, befund.xml, befund.syntax
    if befund.format is Format.BILD:
        return bildart(inhalt), None, None
    return Art.UNBEKANNT, None, None


def lies(archiv: str | Path, beleg: Beleg, max_bytes: int) -> Belegdatei:
    """Datei des Belegs aus dem Archiv der Gesellschaft — geprüft."""
    datei_hash = beleg.datei_hash or ""
    if not HASH.match(datei_hash):
        raise BelegdateiFehltError
    wurzel = Path(archiv).resolve()
    try:
        pfad = BelegArchiv(wurzel).pfad(datei_hash).resolve()
    except FileNotFoundError as fehler:
        raise BelegdateiFehltError from fehler
    if not pfad.is_relative_to(wurzel) or not pfad.is_file():
        raise BelegdateiFehltError
    if pfad.stat().st_size > max_bytes:
        raise BelegZuGrossError
    inhalt = pfad.read_bytes()
    if hashlib.sha256(inhalt).hexdigest() != datei_hash:
        raise BelegVeraendertError
    art, xml, syntax = erkenne(inhalt)
    return Belegdatei(pfad, inhalt, art, xml, syntax)


# --- TIFF ---------------------------------------------------------------------------


def _zaehle_seiten(bild: Any, grenze: int) -> int:
    """Seiten per ``seek`` zählen, höchstens ``grenze`` — ``n_frames`` liefe über die
    ganze Verzeichniskette, bei einem TIFF aus fremder Hand mit 40 000 Seiten (4 MB)
    überlinear 12 s je Aufruf."""
    anzahl = 1
    while anzahl < grenze:
        try:
            bild.seek(anzahl)
        except EOFError:
            break
        anzahl += 1
    bild.seek(0)
    return anzahl


def tiff_seiten(inhalt: bytes) -> int:
    """Seitenzahl (höchstens ``MAX_SEITEN``) — ohne zu dekodieren und ohne mehr als
    ``MAX_SEITEN`` Verzeichnisse zu lesen."""
    from PIL import Image, UnidentifiedImageError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(inhalt), formats=["TIFF"]) as bild:
                return _zaehle_seiten(bild, MAX_SEITEN)
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
    ) as fehler:
        raise KeineVorschauError from fehler


def tiff_seite_als_png(inhalt: bytes, nummer: int, max_megapixel: float) -> bytes:
    """Seite ``nummer`` (ab 1) als PNG — Pixelgrenze **vor** ``load()``."""
    from PIL import Image, UnidentifiedImageError

    grenze = int(max_megapixel * 1_000_000)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(inhalt), formats=["TIFF"]) as bild:
                if not 1 <= nummer <= MAX_SEITEN:
                    raise BelegdateiFehltError
                try:  # liest nur die Verzeichnisse bis zu dieser Seite
                    bild.seek(nummer - 1)
                except EOFError as fehler:
                    raise BelegdateiFehltError from fehler
                breite, hoehe = bild.size
                if breite * hoehe > grenze:
                    raise KeineVorschauError
                bild.load()
                seite: Image.Image = bild
                if seite.mode not in ("RGB", "L"):
                    ziel = "L" if seite.mode in ("1", "I;16", "I", "F") else "RGB"
                    seite = seite.convert(ziel)
                ausgabe = io.BytesIO()
                seite.save(ausgabe, format="PNG")
                return ausgabe.getvalue()
    except BelegdateiError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
        EOFError,
    ) as fehler:
        raise KeineVorschauError from fehler
