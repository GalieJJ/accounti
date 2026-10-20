"""Sicherheitskopfzeilen und Zugriffsprotokoll ohne personenbezogene Inhalte.

Jede Antwort bekommt eine strenge Content-Security-Policy (nur eigene Skripte und
Stile — Inline-Skripte sind gesperrt, HTMX-Attribute nicht), ``nosniff``, keine
Einbettung in fremde Seiten und ``no-store`` außerhalb von ``/statisch``.
Das Protokoll schreibt Methode, Pfad **ohne Abfrage**, Status und Dauer — keine
IP-Adresse, keinen Benutzer, keine Abfrageparameter (dort könnten Namen stehen).
"""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

ZUGRIFF = logging.getLogger("accounti.zugriff")

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

        async def senden(nachricht: Message) -> None:
            nonlocal status
            if nachricht["type"] == "http.response.start":
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
        finally:
            ZUGRIFF.info(
                "%s %s %s %.0f ms",
                scope.get("method", "?"),
                pfad,
                status,
                (time.perf_counter() - beginn) * 1000,
            )
