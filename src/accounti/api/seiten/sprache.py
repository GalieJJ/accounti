"""Sprache der Oberfläche wählen — gespeichert am Benutzer (gilt auf jedem Gerät).

``automatisch`` (leer) folgt wieder dem Browser (``Accept-Language``), sonst gilt
``de`` oder ``en``. Wie jede ändernde Anfrage mit CSRF-Token.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from accounti.api.formular import formular
from accounti.api.seiten.anmeldung import sicheres_ziel
from accounti.api.sitzung import AngemeldetDep, dienste_von
from accounti.auth.dienst import setze_sprache
from accounti.i18n import SPRACHEN, Text

router = APIRouter()


@router.post("/einstellungen/sprache")
async def sprache_waehlen(request: Request, a: AngemeldetDep) -> Response:
    felder = await formular(request)
    wahl = felder.get("sprache", "")
    if wahl not in ("", *SPRACHEN):
        raise HTTPException(422, Text("Diese Sprache gibt es nicht"))
    dienste = dienste_von(request)

    def speichern() -> None:
        with dienste.system() as s:
            setze_sprache(s, a.benutzer.id, wahl or None)
            s.commit()

    await run_in_threadpool(speichern)
    return RedirectResponse(sicheres_ziel(felder.get("weiter")), status_code=303)
