"""HTML-Formulare lesen — ``application/x-www-form-urlencoded`` ohne Zusatzpaket.

Starlettes ``request.form()`` braucht ``python-multipart``; für einfache Formulare
genügt ``urllib.parse``. Multipart (Datei-Uploads) liest
``accounti.belege.webhook.anfrage`` mit dem ``email``-Parser der Standardbibliothek.
Das Ergebnis wird an der Anfrage zwischengespeichert, damit die CSRF-Prüfung und die
Seite dasselbe Formular lesen.
"""

from __future__ import annotations

from urllib.parse import parse_qsl

from fastapi import HTTPException, Request

_SCHLUESSEL = "accounti_formular"


async def formular(request: Request) -> dict[str, str]:
    """Felder des Formulars (bei Mehrfachnennung gilt das erste)."""
    zwischen = getattr(request.state, _SCHLUESSEL, None)
    if isinstance(zwischen, dict):
        return zwischen
    art = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    felder: dict[str, str] = {}
    if art == "application/x-www-form-urlencoded":
        grenze = request.app.state.dienste.server.max_formular_bytes
        laenge = request.headers.get("content-length", "")
        if laenge.isdigit() and int(laenge) > grenze:
            raise HTTPException(413, "Formular zu groß")
        koerper = b""
        async for stueck in request.stream():
            koerper += stueck
            if len(koerper) > grenze:
                raise HTTPException(413, "Formular zu groß")
        try:
            paare = parse_qsl(
                koerper.decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=False,
                max_num_fields=200,
            )
        except (UnicodeDecodeError, ValueError) as fehler:
            raise HTTPException(400, "Formular nicht lesbar") from fehler
        for name, wert in paare:
            felder.setdefault(name, wert)
    setattr(request.state, _SCHLUESSEL, felder)
    return felder
