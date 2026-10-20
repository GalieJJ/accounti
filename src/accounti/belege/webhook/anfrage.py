"""Eine Webhook-Anfrage lesen — Rohdaten, multipart/form-data oder JSON.

``multipart/form-data`` (RFC 7578) liest der ``email``-Parser der
Standardbibliothek byte-genau; FastAPIs eigene Formularverarbeitung bräuchte
``python-multipart``.
"""

from __future__ import annotations

import base64
import binascii
import email.policy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from email.message import Message
from email.parser import BytesParser
from urllib.parse import unquote

from pydantic import BaseModel, ValidationError

# Felder einer Multipart-Anfrage, die auch ohne Dateinamen als Datei zählen
_DATEIFELDER = frozenset({"datei", "dateien", "file", "files", "beleg", "belege"})


class AnfrageError(ValueError):
    """Die Anfrage ist so nicht lesbar (HTTP 400)."""


@dataclass
class Upload:
    dateien: list[tuple[str | None, bytes]] = field(default_factory=list)
    absender: str | None = None


class _JsonDatei(BaseModel):
    dateiname: str | None = None
    inhalt_base64: str


class _JsonAnfrage(BaseModel):
    absender: str | None = None
    dateien: list[_JsonDatei]


def _kopf(kopfzeilen: Mapping[str, str], name: str) -> str | None:
    wert = kopfzeilen.get(name)
    return unquote(wert).strip() or None if wert else None


def _lies_json(koerper: bytes) -> Upload:
    try:
        anfrage = _JsonAnfrage.model_validate(json.loads(koerper))
    except (ValueError, ValidationError) as fehler:
        msg = (
            'JSON erwartet: {"absender": "…", "dateien": [{"dateiname": "…", '
            '"inhalt_base64": "…"}]}'
        )
        raise AnfrageError(msg) from fehler
    upload = Upload(absender=anfrage.absender)
    for datei in anfrage.dateien:
        try:
            inhalt = base64.b64decode(datei.inhalt_base64, validate=True)
        except (binascii.Error, ValueError) as fehler:
            msg = f"{datei.dateiname or 'Datei'}: inhalt_base64 ist kein Base64"
            raise AnfrageError(msg) from fehler
        upload.dateien.append((datei.dateiname, inhalt))
    return upload


def _lies_multipart(content_type: str, koerper: bytes) -> Upload:
    kopf = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode(
        "latin-1", "replace"
    )
    nachricht = BytesParser(policy=email.policy.HTTP).parsebytes(kopf + koerper)
    teile = nachricht.get_payload()
    if not nachricht.is_multipart() or not isinstance(teile, list) or not teile:
        msg = "multipart/form-data ohne lesbare Teile (boundary?)"
        raise AnfrageError(msg)
    upload = Upload()
    for teil in teile:
        if not isinstance(teil, Message):
            continue
        feld = teil.get_param("name", header="content-disposition")
        feldname = str(feld) if isinstance(feld, str) else None
        dateiname = teil.get_filename()
        inhalt = teil.get_payload(decode=True)
        if not isinstance(inhalt, bytes):
            continue
        if dateiname is not None or (feldname or "").lower() in _DATEIFELDER:
            upload.dateien.append((dateiname, inhalt))
        elif feldname == "absender":
            upload.absender = inhalt.decode("utf-8", "replace").strip() or None
    return upload


def lies_anfrage(
    content_type: str,
    kopfzeilen: Mapping[str, str],
    parameter: Mapping[str, str],
    koerper: bytes,
) -> Upload:
    """Dateien und Absender aus einer Anfrage.

    - ``multipart/form-data``: jedes Feld mit Dateinamen (oder Feld ``datei``) ist
      eine Datei, das Feld ``absender`` der Absender.
    - ``application/json``: ``{"absender", "dateien": [{"dateiname",
      "inhalt_base64"}]}``.
    - alles andere: der Körper ist die Datei; Name aus ``X-Dateiname`` oder
      ``?dateiname=``, Absender aus ``X-Absender`` (beide URL-kodiert erlaubt).
    """
    art = content_type.split(";", 1)[0].strip().lower()
    if art == "multipart/form-data":
        upload = _lies_multipart(content_type, koerper)
    elif art == "application/json":
        upload = _lies_json(koerper)
    else:
        if not koerper:
            raise AnfrageError("Leerer Körper — keine Datei übertragen")
        name = _kopf(kopfzeilen, "x-dateiname") or parameter.get("dateiname") or None
        upload = Upload([(name, koerper)], _kopf(kopfzeilen, "x-absender"))
    if not upload.dateien:
        raise AnfrageError("Keine Datei in der Anfrage")
    if upload.absender:
        upload.absender = upload.absender[:200]
    return upload
