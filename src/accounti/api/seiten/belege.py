"""Belegvorschau: Beleg der aktiven Gesellschaft, Datei aus ihrem Archiv.

* ``/belege/{id}`` — Angaben, Vorschau, Buchungen, Rückfragen.
* ``/belege/{id}/datei`` — nur PDF, PNG, JPEG inline (Typ aus dem Inhalt, fester
  Dateiname ``beleg-<uuid>.<endung>``, ``nosniff``, ``no-store``, CORP same-origin,
  CSP der Seite mit ``form-action 'none'`` — Browser-Spike im Plan).
* ``/belege/{id}/seite/{n}.png`` — TIFF seitenweise als PNG (Pixelgrenze je Seite).
* ``/belege/{id}/download`` — das Original als Anhang, ``application/octet-stream``,
  CSP ``default-src 'none'; sandbox``.

Kein Wert aus der Anfrage erreicht das Archiv außer der UUID des Belegs; der Name
des Absenders erscheint nie in einer Kopfzeile.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from accounti.api.belegantwort import (
    ENDUNG,
    INLINE,
    MEDIENTYP,
    Art,
    Belegdatei,
    BelegdateiError,
    lies,
    tiff_seite_als_png,
)
from accounti.api.seiten.pruefen import belegansicht
from accounti.api.sicherheit import CSP
from accounti.api.sitzung import Angemeldet, dienste_von, erfordert, gesellschaft_db
from accounti.api.vorlagen import seite
from accounti.i18n import N_, Text
from accounti.models import Beleg
from accounti.models.auth import Recht

router = APIRouter()

# Browser-Spike (Plan): Seiten-CSP, aber kein Formularversand aus dem PDF-Betrachter
CSP_DATEI = CSP.replace("form-action 'self'", "form-action 'none'")
CSP_DOWNLOAD = "default-src 'none'; sandbox"
SICHER = {"Cross-Origin-Resource-Policy": "same-origin", "Cache-Control": "no-store"}

FEHLERTEXT = {
    404: N_("Die Belegdatei fehlt im Archiv"),
    409: N_(
        "Beleg im Archiv verändert — der Inhalt passt nicht zum gespeicherten Prüfwert"
    ),
    413: N_("Die Belegdatei ist zu groß"),
    415: N_("Keine Vorschau für diesen Dateityp — bitte herunterladen"),
}


def _beleg(s: Session, beleg_id: UUID) -> Beleg:
    from accounti.db.repository import lade_beleg

    b = lade_beleg(s, beleg_id)
    if b is None:
        raise HTTPException(404, Text("Beleg nicht gefunden"))
    return b


def _datei(request: Request, a: Angemeldet, beleg: Beleg) -> Belegdatei:
    try:
        return lies(
            a.gesellschaft.archiv, beleg, dienste_von(request).server.max_beleg_bytes
        )
    except BelegdateiError as fehler:
        raise HTTPException(fehler.status, Text(FEHLERTEXT[fehler.status])) from fehler


def _dateiname(beleg: Beleg, art: Art, endung: str | None = None) -> str:
    return f"beleg-{beleg.id}.{endung or ENDUNG[art]}"


@router.get("/belege/{beleg_id:uuid}", response_class=HTMLResponse)
async def beleg_seite(
    beleg_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> HTMLResponse:
    from accounti.aufgaben import kommentare_zu
    from accounti.db.repository import lade_belegbuchungen
    from accounti.models.aufgaben import KommentarArt, Objekt

    max_bytes = dienste_von(request).server.max_beleg_bytes

    def laden() -> dict[str, Any]:
        b = _beleg(s, beleg_id)
        return {
            "titel": N_("Beleg"),
            "belegdaten": b,
            "bid": b.id,
            "ansicht_beleg": belegansicht(a, b, max_bytes),
            "buchungen": lade_belegbuchungen(s, b.id),
            "rueckfragen": [
                k
                for k in kommentare_zu(s, Objekt("beleg", b.id))
                if k.art is KommentarArt.RUECKFRAGE
            ],
        }

    return seite(request, "belege/beleg.html", await run_in_threadpool(laden))


@router.get("/belege/{beleg_id:uuid}/datei")
async def datei(
    beleg_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    def laden() -> tuple[Beleg, Belegdatei]:
        b = _beleg(s, beleg_id)
        return b, _datei(request, a, b)

    beleg, d = await run_in_threadpool(laden)
    if d.art not in INLINE:
        raise HTTPException(415, Text(FEHLERTEXT[415]))
    return FileResponse(
        d.pfad,
        media_type=MEDIENTYP[d.art],
        filename=_dateiname(beleg, d.art),
        content_disposition_type="inline",
        headers={**SICHER, "Content-Security-Policy": CSP_DATEI},
    )


@router.get("/belege/{beleg_id:uuid}/seite/{n}.png")
async def tiff_seite(
    beleg_id: UUID,
    n: str,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    from accounti.api.seiten.pruefen import ascii_zahl

    # Seitennummer nur aus ASCII-Ziffern, höchstens 18 Stellen — der Konverter
    # ``{n:int}`` gab mit mehr als 4300 Ziffern 500, vor der Anmeldung (Runde 3)
    seite_nr = ascii_zahl(n)
    if seite_nr is None:
        raise HTTPException(404, Text("Seite nicht gefunden"))
    grenze = dienste_von(request).server.max_vorschau_megapixel

    def umwandeln() -> bytes:
        b = _beleg(s, beleg_id)
        d = _datei(request, a, b)
        if d.art is not Art.TIFF:
            raise HTTPException(415, Text(FEHLERTEXT[415]))
        try:
            return tiff_seite_als_png(d.inhalt, seite_nr, grenze)
        except BelegdateiError as fehler:
            raise HTTPException(
                fehler.status, Text(FEHLERTEXT[fehler.status])
            ) from fehler

    inhalt = await run_in_threadpool(umwandeln)
    return Response(
        inhalt,
        media_type="image/png",
        headers={**SICHER, "Content-Security-Policy": CSP_DATEI},
    )


@router.get("/belege/{beleg_id:uuid}/download")
async def download(
    beleg_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    def laden() -> tuple[Beleg, Belegdatei]:
        b = _beleg(s, beleg_id)
        return b, _datei(request, a, b)

    beleg, d = await run_in_threadpool(laden)
    return FileResponse(
        d.pfad,
        media_type="application/octet-stream",
        filename=_dateiname(beleg, d.art),
        content_disposition_type="attachment",
        headers={**SICHER, "Content-Security-Policy": CSP_DOWNLOAD},
    )
