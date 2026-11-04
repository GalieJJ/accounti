"""Stand der Einstellungen je Anfrage (Baustein 10c P4, D4).

Reine ASGI-Middleware: Jede HTTP-Anfrage bekommt einen neuen, **ungebundenen** Stand
(``web=True``) und gibt ihn am Ende zurück. Binden tun ``angemeldet`` (Sitzung) und
``api_zugang`` (Token) — an die Gesellschaft, deren Rechte sie prüfen
(``leser.binde_gesellschaft``); der Schnappschuss entsteht beim ersten Lesen eines
Datenbank-Abschnitts, die Bindung öffnet die Datenbank nicht (eine nicht erreichbare
hält ``/gesellschaft``, Wechsel und Abmelden nicht auf). Gebunden wird das Stand-Objekt
selbst; so sieht auch ein Endpunkt im Threadpool (kopierter Kontext) die Bindung. Liest
eine Anfrage ohne Bindung oder aus einer anderen Konfiguration einen
Datenbank-Abschnitt, folgt ``EinstellungsquelleFehlt`` — die 500-Seite der
Sicherheits-Middleware (D5).

Registriert vor ``Sicherheit``: In Starlette liegt die zuletzt hinzugefügte Middleware
außen, Sicherheit bleibt so die äußerste (Absprache mit P1, G-N1).
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from accounti.einstellungen.leser import Stand, ruecksetzen, setze_stand


class Einstellungsstand:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = setze_stand(Stand(web=True))
        try:
            await self.app(scope, receive, send)
        finally:
            ruecksetzen(token)
