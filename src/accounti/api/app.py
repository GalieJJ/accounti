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
from http import HTTPStatus
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from accounti.api import rest, seiten
from accounti.api.dienste import Dienste
from accounti.api.einstellungsstand import Einstellungsstand
from accounti.api.geruest import zurueck_pfad
from accounti.api.htmx import aktueller_pfad, ist_htmx
from accounti.api.lesezugriff import Lesezugriff
from accounti.api.registry import endpunkte, navigation, routermodule
from accounti.api.seiten.anmeldung import sicheres_ziel
from accounti.api.sicherheit import FEHLER, Sicherheit, protokollpfad
from accounti.api.sitzung import (
    NichtAngemeldetError,
    Verweigerung,
    merke_benutzersprache,
    vielleicht_angemeldet,
)
from accounti.api.vorlagen import seite
from accounti.i18n import N_, Text
from accounti.models.auth import RECHT_TEXT

BESCHAEFTIGT = Text("Ein Lauf schreibt gerade — bitte gleich noch einmal")
# Starlette meldet Routing-Fehler mit der englischen Statusphrase („Not Found“) —
# in der Oberfläche übersetzt, in der REST-API unverändert
STATUSTEXTE = {
    400: N_("Ungültige Anfrage"),
    404: N_("Seite nicht gefunden"),
    405: N_("Diese Seite lässt sich so nicht aufrufen (Methode nicht erlaubt)"),
}


def fehlertext(fehler: StarletteHTTPException) -> object:
    """``detail`` für die Seite: die Statusphrase von Starlette als ``Text``."""
    try:
        phrase = HTTPStatus(fehler.status_code).phrase
    except ValueError:
        return fehler.detail
    if fehler.detail != phrase:
        return fehler.detail
    if fehler.status_code in STATUSTEXTE:
        return Text(STATUSTEXTE[fehler.status_code])
    return Text(
        "Die Anfrage ist fehlgeschlagen (HTTP %(status)s)", status=fehler.status_code
    )


# h1 je Status (Spec 10c A9; Plan P1, Entscheidung „Fehlerseiten“). P1 Runde 2: 403
# und 409 neutral — „Keine Berechtigung“ nur bei fehlender Rolle (Verweigerung) oder
# Gesellschaft, „Inzwischen geändert“ nur bei geänderten Daten (Seitenfehler mit titel);
# falscher Einmalcode, fehlendes CSRF-Token, Fachfehler der Freigabe: „Nicht ausgeführt“
FEHLERTITEL = {
    403: N_("Nicht ausgeführt"),
    404: N_("Nicht gefunden"),
    409: N_("Nicht ausgeführt"),
    413: N_("Zu groß"),
    422: N_("Angaben prüfen"),
    503: N_("Gerade beschäftigt"),
}


async def fehlerseite(
    request: Request,
    status: int,
    meldung: object,
    verweigerung: Verweigerung | None = None,
    titel: str | None = None,
) -> Response:
    """Fehlerseite im Gerüst ohne Zähler; mit ``HX-Request`` als Fragment (Hinweis mit
    ``role="alert"``, AK58). ``titel`` (msgid) vor dem Titel des Status."""
    fragment = ist_htmx(request) and status in FEHLERTITEL
    if titel is None and verweigerung is not None:
        titel = N_("Keine Berechtigung")
    werte = {
        "titel": titel or FEHLERTITEL.get(status, N_("Fehler")),
        "fehlermeldung": meldung,
        "verweigerung": verweigerung,
        "recht_text": RECHT_TEXT,
        "zurueck": zurueck_pfad(request, getattr(request.state, "angemeldet", None)),
        "fragment": fragment,
    }
    vorlage = "_fehler.html" if fragment else "fehler.html"
    return await seite(request, vorlage, werte, status=status, zaehler=False)


def datenbank_beschaeftigt(fehler: OperationalError) -> bool:
    """SQLite „database is locked“/„busy“, PostgreSQL Sperr-Zeitüberschreitung."""
    text_ = str(getattr(fehler, "orig", fehler)).lower()
    code = getattr(getattr(fehler, "orig", None), "sqlstate", None)
    return (
        "database is locked" in text_
        or "database is busy" in text_
        or "lock timeout" in text_
        or code in ("55P03", "40P01")
    )


def _ist_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def erstelle_app(dienste: Dienste) -> FastAPI:
    @asynccontextmanager
    async def lebenszeit(_: FastAPI) -> AsyncIterator[None]:
        yield
        lesezugriff.schliesse()
        dienste.schliesse()

    app = FastAPI(
        title="accounti",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lebenszeit,
    )
    app.state.dienste = dienste
    # Zähler der Navigation: nur lesend, eigene Fristen und eigener Pool (Plan P1, B14)
    lesezugriff = Lesezugriff()
    app.state.lesezugriff = lesezugriff
    seitenmodule = routermodule(seiten)
    app.state.navigation = navigation(seitenmodule)
    # innen der Stand der Einstellungen je Anfrage, außen Sicherheit mit der 500-Seite
    # (in Starlette liegt die zuletzt hinzugefügte Middleware außen; G-N1)
    app.add_middleware(Einstellungsstand)
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
        if request.headers.get("hx-request", "").lower() == "true":
            # htmx folgte einer 303 still und tauschte die Anmeldeseite ins Fragment;
            # HX-Redirect lädt die ganze Seite — zurück zur Seite, die der Browser zeigt
            weiter = sicheres_ziel(aktueller_pfad(request))
            return Response(
                status_code=200,
                headers={"HX-Redirect": f"/anmelden?weiter={quote(weiter)}"},
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
        if fehler.status_code == 404 and not hasattr(request.state, "angemeldet"):
            # ohne Route: mit gültiger Sitzung im Gerüst (Datenbankfehler → schlicht)
            await vielleicht_angemeldet(request)
        else:
            await merke_benutzersprache(request)
        detail = fehler.detail
        if isinstance(detail, Verweigerung):
            antwort = await fehlerseite(request, 403, detail.text, detail)
        else:
            antwort = await fehlerseite(
                request,
                fehler.status_code,
                fehlertext(fehler),
                titel=getattr(fehler, "titel", None),
            )
        antwort.headers.update(kopf)
        return antwort

    @app.exception_handler(RequestValidationError)
    async def ungueltig(request: Request, fehler: RequestValidationError) -> Response:
        felder = ", ".join(
            ".".join(str(x) for x in e.get("loc", ())[1:]) or "Anfrage"
            for e in fehler.errors()
        )
        meldung = Text("Ungültige Angaben: %(felder)s", felder=felder)
        if _ist_api(request):
            return JSONResponse({"fehler": str(meldung)}, status_code=422)
        return await fehlerseite(request, 422, meldung)

    @app.exception_handler(OperationalError)
    async def beschaeftigt(request: Request, fehler: OperationalError) -> Response:
        """Ein Lauf hält die Schreibsperre länger, als eine Aktion wartet (SQLite 30 s,
        PostgreSQL Sperr-Zeitüberschreitung): 503 mit Hinweis statt „Interner
        Fehler“. Andere Datenbankfehler bleiben 500 (Middleware)."""
        if not datenbank_beschaeftigt(fehler):
            raise fehler
        FEHLER.warning(
            "Datenbank beschäftigt bei %s %s",
            request.method,
            protokollpfad(request.scope),
        )
        kopf = {"Retry-After": "5"}
        if _ist_api(request):
            return JSONResponse(
                {"fehler": str(BESCHAEFTIGT)}, status_code=503, headers=kopf
            )
        antwort = await fehlerseite(request, 503, BESCHAEFTIGT)
        antwort.headers.update(kopf)
        return antwort

    @app.get("/gesund", include_in_schema=False)
    async def gesund() -> dict[str, Any]:
        def pruefe() -> None:
            with dienste.system() as s:
                s.execute(text("SELECT 1"))

        await run_in_threadpool(pruefe)
        return {"status": "ok"}

    return app
