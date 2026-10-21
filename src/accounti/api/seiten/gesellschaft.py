"""Gesellschaft wechseln — die Sitzung trägt die aktive Gesellschaft."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from accounti.api.formular import formular
from accounti.api.sitzung import AngemeldetDep, dienste_von
from accounti.auth.dienst import ereignis, wechsle_gesellschaft

router = APIRouter()


@router.post("/gesellschaft")
async def wechseln(request: Request, a: AngemeldetDep) -> Response:
    kuerzel = (await formular(request)).get("kuerzel", "")
    if kuerzel not in {g.kuerzel for g in a.gesellschaften}:
        raise HTTPException(403, "Kein Zugriff auf diese Gesellschaft")
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
