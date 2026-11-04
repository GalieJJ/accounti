"""„Mehr“ (``/menue``) — die Navigation für schmale Bildschirme ohne Skript (Spec 10c
A4, AK6; Plan P1 Schritt 8, Leinwand „Handy-Mehr“): alle erlaubten Bereiche mit
Zählern, die Gesellschaften des Benutzers (Wechsel per POST mit CSRF) und „Mein
Konto“ mit Hilfe und Abmelden (``#konto``, Ziel des Benutzersymbols im schmalen Kopf).
Mit ``HX-Request`` nur der Inhalt."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from accounti.api.geruest import gesellschaften_mit_zaehlern
from accounti.api.sitzung import AngemeldetDep
from accounti.api.vorlagen import seite
from accounti.i18n import N_

router = APIRouter()


@router.get("/menue", response_class=HTMLResponse)
async def menue(request: Request, a: AngemeldetDep) -> HTMLResponse:
    zeilen = await gesellschaften_mit_zaehlern(request, a)
    return await seite(
        request, "menue.html", {"titel": N_("Mehr"), "zeilen": zeilen}, teil="inhalt"
    )
