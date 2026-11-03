"""HTMX-Anfragen erkennen — eine Route, zwei Formen (Fragment oder ganze Seite).

Mit ``HX-Request`` liefert eine Seite das Fragment (und ``HX-Push-Url``), sonst die
ganze Seite bzw. eine Weiterleitung. Verlaufsabrufe (``HX-History-Restore-Request``)
bekommen die ganze Seite — htmx ersetzt dann den ganzen ``body``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request


def ist_verlaufsabruf(request: Request) -> bool:
    return request.headers.get("hx-history-restore-request", "").lower() == "true"


def ist_htmx(request: Request) -> bool:
    """HTMX-Anfrage, die ein Fragment erwartet (kein Verlaufsabruf)."""
    return request.headers.get(
        "hx-request", ""
    ).lower() == "true" and not ist_verlaufsabruf(request)


def aktueller_pfad(request: Request) -> str:
    """Pfad (mit Abfrage) aus ``HX-Current-URL`` — nur von dieser Anwendung, sonst
    ``/``. Für ``weiter`` nach der Anmeldung."""
    roh = request.headers.get("hx-current-url", "")
    try:
        teile = urlsplit(roh)
    except ValueError:
        return "/"
    if teile.netloc and teile.netloc != request.url.netloc:
        return "/"
    if teile.scheme and teile.scheme not in ("http", "https"):
        return "/"
    pfad = teile.path or "/"
    return f"{pfad}?{teile.query}" if teile.query else pfad
