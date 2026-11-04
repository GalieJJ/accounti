"""Hilfe (Spec 10c A8, AK47; Plan P1, Schritt 10): ``/hilfe`` mit Themen und Begriffen,
``/hilfe/{thema}`` je Bereich bzw. für Anmeldung und Konto.

Ohne Anmeldung erreichbar (der Hilfe-Link der Anmeldeseite muss gehen): statischer
Inhalt aus ``api/hilfe_inhalt.py``, keine Daten einer Gesellschaft. Mit gültiger Sitzung
erscheint das Gerüst mit Navigation (``vielleicht_angemeldet``); scheitert das an der
Systemdatenbank, gilt die Anfrage als nicht angemeldet (schlicht, nie 500). ``thema``
kommt als ``str`` und wird auf ``Hilfethema`` abgebildet: unbekannt oder ohne Eintrag
404 (nie 422 aus der Validierung). Mit ``HX-Request`` nur der Inhalt.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from accounti.api.hilfe_inhalt import BEGRIFFE, HILFE, Hilfethema
from accounti.api.sitzung import vielleicht_angemeldet
from accounti.api.vorlagen import seite
from accounti.i18n import N_

router = APIRouter()


@router.get("/hilfe", response_class=HTMLResponse)
async def hilfe(request: Request) -> HTMLResponse:
    await vielleicht_angemeldet(request)
    werte = {
        "titel": N_("Hilfe"),
        "themen": [(t, h) for t, h in HILFE.items()],
        "begriffe": BEGRIFFE,
    }
    return await seite(request, "hilfe/index.html", werte, teil="inhalt")


@router.get("/hilfe/{thema}", response_class=HTMLResponse)
async def hilfe_thema(request: Request, thema: str) -> HTMLResponse:
    try:
        gewaehlt = Hilfethema(thema)
    except ValueError:
        raise HTTPException(404) from None
    if gewaehlt not in HILFE:
        raise HTTPException(404)
    await vielleicht_angemeldet(request)
    werte = {"titel": N_("Hilfe"), "hilfe": HILFE[gewaehlt]}
    return await seite(request, "hilfe/thema.html", werte, teil="inhalt")
