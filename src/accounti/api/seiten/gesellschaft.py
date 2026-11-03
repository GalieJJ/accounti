"""Gesellschaft wechseln — die Sitzung trägt die aktive Gesellschaft.

``GET /gesellschaft`` (Baustein 10c, Plan P1 Schritt 8) zeigt die Gesellschaften mit
Rolle samt Marke und Zählern (über den Lesezugriff, mit Frist; eine nicht erreichbare
steht als „nicht erreichbar“ da); gewechselt wird mit ``POST /gesellschaft``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from accounti.api.formular import formular
from accounti.api.geruest import gesellschaften_mit_zaehlern
from accounti.api.sitzung import AngemeldetDep, dienste_von
from accounti.api.vorlagen import seite
from accounti.auth.dienst import ereignis, wechsle_gesellschaft
from accounti.i18n import N_, Text

router = APIRouter()


@router.get("/gesellschaft", response_class=HTMLResponse)
async def liste(request: Request, a: AngemeldetDep) -> HTMLResponse:
    zeilen = await gesellschaften_mit_zaehlern(request, a)
    werte = {"titel": N_("Gesellschaft wechseln"), "zeilen": zeilen}
    return await seite(request, "gesellschaften.html", werte, teil="inhalt")


@router.post("/gesellschaft")
async def wechseln(request: Request, a: AngemeldetDep) -> Response:
    kuerzel = (await formular(request)).get("kuerzel", "")
    if kuerzel not in {g.kuerzel for g in a.gesellschaften}:
        raise HTTPException(403, Text("Kein Zugriff auf diese Gesellschaft"))
    dienste = dienste_von(request)

    def speichern() -> None:
        with dienste.system() as s:
            jetzt = dienste.uhr()
            wechsle_gesellschaft(s, a.sitzung, kuerzel, jetzt)
            ereignis(
                s,
                "gesellschaft_gewechselt",
                jetzt,
                a.benutzer.name,
                quelle="web",
                gesellschaft=kuerzel,
            )
            s.commit()

    await run_in_threadpool(speichern)
    return RedirectResponse("/", status_code=303)
