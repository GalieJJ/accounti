"""App-Fabrik der Web-Oberfläche und REST-API.

``erstelle_app(dienste)`` hängt alle Router aus ``accounti.api.seiten`` (HTML mit
Sitzung) und ``accounti.api.rest`` (JSON unter ``/api/v1`` mit Token) ein, setzt
Sicherheitskopfzeilen, liefert ``/statisch`` aus und beantwortet ``/gesund`` für die
Gesundheitsprüfung des Containers. Keine OpenAPI-Seiten: die Schnittstelle steht in
``docs/betrieb.md``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from accounti.api import rest, seiten
from accounti.api.dienste import Dienste
from accounti.api.registry import endpunkte, navigation, routermodule
from accounti.api.sicherheit import Sicherheit
from accounti.api.sitzung import NichtAngemeldetError
from accounti.api.vorlagen import seite


def _ist_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def erstelle_app(dienste: Dienste) -> FastAPI:
    @asynccontextmanager
    async def lebenszeit(_: FastAPI) -> AsyncIterator[None]:
        yield
        dienste.schliesse()

    app = FastAPI(
        title="accounti",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lebenszeit,
    )
    app.state.dienste = dienste
    seitenmodule = routermodule(seiten)
    app.state.navigation = navigation(seitenmodule)
    app.add_middleware(Sicherheit)
    app.mount(
        "/statisch",
        StaticFiles(packages=[("accounti.api", "statisch")]),
        name="statisch",
    )
    restmodule = routermodule(rest)
    for modul in seitenmodule:
        app.include_router(modul.router)
    for modul in restmodule:
        app.include_router(modul.router, prefix="/api/v1")
    app.state.endpunkte = endpunkte(seitenmodule) + endpunkte(restmodule, "/api/v1")

    @app.exception_handler(NichtAngemeldetError)
    async def nicht_angemeldet(request: Request, _: NichtAngemeldetError) -> Response:
        if _ist_api(request):
            return JSONResponse(
                {"fehler": "Nicht angemeldet"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="accounti"'},
            )
        weiter = request.url.path if request.method == "GET" else "/"
        return RedirectResponse(f"/anmelden?weiter={quote(weiter)}", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def http_fehler(request: Request, fehler: StarletteHTTPException) -> Response:
        kopf: dict[str, str] = dict(fehler.headers or {})
        if _ist_api(request):
            return JSONResponse(
                {"fehler": str(fehler.detail)},
                status_code=fehler.status_code,
                headers=kopf,
            )
        return seite(
            request,
            "meldung.html",
            {"titel": "Fehler", "fehler": str(fehler.detail)},
            status=fehler.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def ungueltig(request: Request, fehler: RequestValidationError) -> Response:
        felder = ", ".join(
            ".".join(str(x) for x in e.get("loc", ())[1:]) or "Anfrage"
            for e in fehler.errors()
        )
        text_ = f"Ungültige Angaben: {felder}"
        if _ist_api(request):
            return JSONResponse({"fehler": text_}, status_code=422)
        return seite(request, "meldung.html", {"fehler": text_}, status=422)

    @app.get("/gesund", include_in_schema=False)
    async def gesund() -> dict[str, Any]:
        def pruefe() -> None:
            with dienste.system() as s:
                s.execute(text("SELECT 1"))

        await run_in_threadpool(pruefe)
        return {"status": "ok"}

    return app
