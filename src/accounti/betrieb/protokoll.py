"""Protokollierung ohne personenbezogene Inhalte und ohne Zugangsdaten.

Zwei Schichten: Der Code schreibt keine Belegtexte, Namen, Passwörter oder Token
ins Protokoll (das Zugriffsprotokoll der App enthält nur Methode, Pfad ohne Abfrage,
Status, Dauer). Zusätzlich schwärzt ein Filter an jedem Handler, was als Muster
erkennbar ist: IBAN, E-Mail-Adressen, accounti-Token, Bearer-Token und verbreitete
Zugangstoken, Benutzer und Passwort in URLs (auch zerschnitten), Geheimnis-Parameter
(``passwort=…``, ``token=…``), „Passwort: …“ sowie PIN und TAN als Zahl. Namen erkennt
kein Muster — sie dürfen gar nicht erst geschrieben werden.

Stufe und Format aus ``ACCOUNTI_PROTOKOLL_STUFE`` (``INFO``) und
``ACCOUNTI_PROTOKOLL_FORMAT`` (``text`` oder ``json``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import IO

_SCHEMA = r"[A-Za-z][A-Za-z0-9+.\-]*://"
_MUSTER: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"accounti_(?:api|wh)_[A-Za-z0-9_\-]+"), "[Token]"),
    # verbreitete Zugangstoken (GitHub, GitLab, Slack) — auch ohne „token=“
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
            r"glpat-[A-Za-z0-9_\-]{20,}|xox[abeprs]-[A-Za-z0-9\-]{10,})"
        ),
        "[Token]",
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]+"), "Bearer [Token]"),
    # Zugangsdaten jeder URL (scheme://benutzer:passwort@): die ganze userinfo, auch
    # mit unkodiertem # oder ? im Passwort (Runde 6, g5w-konten N1)
    (re.compile(rf"({_SCHEMA})[^/\s@]+@"), r"\1***@"),
    # … und abgeschnitten (Zeilenumbruch, kaputte Adresse): „scheme://benutzer:etwas“
    # ohne @ — außer einem Port (nur Ziffern)
    (
        re.compile(rf"({_SCHEMA}[^/\s:@?#\[\]]+):(?!\d+(?:[/?#\s]|$))[^/\s@]+"),
        r"\1:***",
    ),
    (
        re.compile(
            r"(?i)\b(passwor[td]|pin|tan|token|secret|geheimnis|schluessel|key|"
            r"einmalcode|code|csrf|anmeldung)=([^&\s\"']+)"
        ),
        r"\1=***",
    ),
    # „Passwort: …“, „Kennwort = …“ (Text statt Parameter)
    (
        re.compile(
            r"(?i)\b(passwor[td]|kennwort|secret|geheimnis)(\s*[:=]\s*)[^\s\"',;]+"
        ),
        r"\1\2***",
    ),
    # PIN und TAN als Zahl („PIN: 12345“, „TAN 123456“)
    (re.compile(r"(?i)\b(pin|tan)(\s*[:=]?\s*)\d{4,8}\b"), r"\1\2***"),
    # E-Mail — und der Rest einer zerschnittenen Adresse („…geheim@host“)
    (re.compile(r"[\w.+\-#?%!$&*=^~]+@[\w\-]+(?:\.[\w\-]+)+"), "[E-Mail]"),
    (
        re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b"),
        "[IBAN]",
    ),
]


def schwaerze(text: str) -> str:
    for muster, ersatz in _MUSTER:
        text = muster.sub(ersatz, text)
    return text


class Schwaerzung(logging.Filter):
    """Ersetzt erkennbare Geheimnisse und Personendaten in jeder Meldung."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except (TypeError, ValueError):
            text = str(record.msg)
        record.msg = schwaerze(text)
        record.args = None
        if record.exc_info and record.exc_info[1] is not None:
            # der Stack bleibt (Betrieb braucht ihn), seine Texte werden geschwärzt
            record.exc_text = schwaerze(
                logging.Formatter().formatException(record.exc_info)
            )
        return True


class JsonFormat(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "zeit": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "stufe": record.levelname,
                "logger": record.name,
                "text": record.getMessage(),
            },
            ensure_ascii=False,
        )


def richte_protokoll_ein(
    stufe: str | None = None,
    format_: str | None = None,
    ziel: IO[str] | None = None,
) -> logging.Handler:
    """Ein Handler am Wurzel-Logger mit Schwärzung; Uvicorn schreibt dorthin."""
    stufe = (stufe or os.environ.get("ACCOUNTI_PROTOKOLL_STUFE") or "INFO").upper()
    format_ = format_ or os.environ.get("ACCOUNTI_PROTOKOLL_FORMAT") or "text"
    handler = logging.StreamHandler(ziel or sys.stderr)
    handler.addFilter(Schwaerzung())
    handler.setFormatter(
        JsonFormat()
        if format_ == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    wurzel = logging.getLogger()
    wurzel.handlers = [handler]
    wurzel.setLevel(stufe)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    # HTTP-Bibliotheken schreiben ganze Adressen (Webhook-URLs tragen oft Token)
    for name in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return handler
