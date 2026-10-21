"""Sicherheitskopfzeilen und Zugriffsprotokoll ohne personenbezogene Inhalte.

Jede Antwort bekommt eine strenge Content-Security-Policy (nur eigene Skripte und
Stile — Inline-Skripte sind gesperrt, HTMX-Attribute nicht), ``nosniff``, keine
Einbettung in fremde Seiten und ``no-store`` außerhalb von ``/statisch``.
Das Protokoll schreibt Methode, die **Vorlage** der Route (etwa
``/freigaben/zahlungslauf/{nr}`` — keine IDs, keine Abfrage), Status und Dauer —
keine IP-Adresse, keinen Benutzer. Pfade ohne Route (404) erscheinen als
``(unbekannt)``: ein Name oder ein ``%0A`` im Pfad schreibt so nichts ins Protokoll.

Unbehandelte Ausnahmen fängt die Middleware: Antwort 500, im Protokoll nur die
Art der Ausnahme — keine Meldung, kein Traceback (dort stünden SQL und Werte).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

ZUGRIFF = logging.getLogger("accounti.zugriff")
FEHLER = logging.getLogger("accounti.api")
UNBEKANNT = "(unbekannt)"


def protokollpfad(scope: Scope) -> str:
    """Vorlage der Route; statische Dateien mit maskierten Steuerzeichen."""
    route: Any = scope.get("route")
    vorlage = getattr(route, "path", None)
    if isinstance(vorlage, str) and vorlage:
        return vorlage
    pfad: str = scope.get("path", "")
    if pfad.startswith("/statisch/"):
        return pfad.encode("unicode_escape").decode("ascii")
    return UNBEKANNT


CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "object-src 'self'; frame-src 'self'; frame-ancestors 'self'; form-action 'self'; "
    "base-uri 'none'"
)
KOPFZEILEN = [
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"referrer-policy", b"same-origin"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


class Sicherheit:
    """Reine ASGI-Middleware: Kopfzeilen setzen, Zugriff protokollieren."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        beginn = time.perf_counter()
        pfad: str = scope.get("path", "")
        status = 500
        begonnen = False

        async def senden(nachricht: Message) -> None:
            nonlocal status, begonnen
            if nachricht["type"] == "http.response.start":
                begonnen = True
                status = nachricht["status"]
                kopf = list(nachricht.get("headers", []))
                vorhanden = {k.lower() for k, _ in kopf}
                kopf += [(k, v) for k, v in KOPFZEILEN if k not in vorhanden]
                if (
                    not pfad.startswith("/statisch/")
                    and b"cache-control" not in vorhanden
                ):
                    kopf.append((b"cache-control", b"no-store"))
                nachricht["headers"] = kopf
            await send(nachricht)

        try:
            await self.app(scope, receive, senden)
        except Exception as fehler:  # noqa: BLE001 - jede Ausnahme, nur ihre Art
            status = 500
            FEHLER.error(
                "Unbehandelte Ausnahme %s bei %s %s",
                type(fehler).__name__,
                scope.get("method", "?"),
                protokollpfad(scope),
            )
            if not begonnen:
                antwort: Response
                if pfad.startswith("/api/"):
                    antwort = JSONResponse({"fehler": "Interner Fehler"}, 500)
                else:
                    antwort = PlainTextResponse("Interner Fehler", 500)
                await antwort(scope, receive, senden)
        finally:
            ZUGRIFF.info(
                "%s %s %s %.0f ms",
                scope.get("method", "?"),
                protokollpfad(scope),
                status,
                (time.perf_counter() - beginn) * 1000,
            )
