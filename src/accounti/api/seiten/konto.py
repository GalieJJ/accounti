"""Mein Konto — Anzeige-Vorlieben am Benutzer (Spec 10c A6, A87; Plan P1, Schritt 9).

``GET /konto`` zeigt Sprache, Darstellung, Fachansicht, „Beträge verbergen“ und
Tastenkürzel als Optionsfelder (auch an/aus: zwei Optionen — ein fehlendes Feld heißt
„unverändert“). ``POST /konto/vorlieben`` ändert nur die gesendeten Felder
(``auth.dienst.setze_vorlieben``, gezieltes UPDATE, kein Ereignis: Ausnahme A113) und
antwortet ohne htmx mit 303 auf ``weiter`` (nur relative Pfade), mit htmx mit
``HX-Refresh`` (Sprache und Darstellung betreffen ``<html>``). Unbekannte Werte: 422 mit
Fehlerliste, nichts gespeichert. Kein Absenden bei der Auswahl (WCAG 3.2.2).
Der alte Pfad ``POST /einstellungen/sprache`` antwortet ein Release lang mit 308 hierher
(Methode und Körper samt CSRF-Token bleiben, geprüft wird am Ziel erneut).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from accounti.api.formular import formular
from accounti.api.htmx import ist_htmx
from accounti.api.seiten.anmeldung import sicheres_ziel
from accounti.api.sitzung import Angemeldet, AngemeldetDep, dienste_von
from accounti.api.vorlagen import seite
from accounti.auth.dienst import DARSTELLUNGEN, Vorlieben, setze_vorlieben
from accounti.i18n import N_, Text

router = APIRouter()

SCHALTER = ("fachansicht", "betraege_verbergen", "tastenkuerzel")
FALSCHE_WAHL = Text("Diese Wahl gibt es nicht")


def vorlieben_aus_formular(
    felder: dict[str, str],
) -> tuple[Vorlieben, list[tuple[str, Text]], dict[str, str]]:
    """Vorlieben aus dem Formular; dazu die Fehler (Feldname, Text) und die gültigen
    Eingaben (für die Seite nach einem 422). Ein fehlendes Feld bleibt unverändert."""
    werte: dict[str, Any] = {}
    fehler: list[tuple[str, Text]] = []
    gueltig: dict[str, str] = {}
    if "sprache" in felder:
        wahl = felder["sprache"]
        if wahl in ("", "auto", "de", "en"):
            sprache: Literal["de", "en"] | None = (
                "de" if wahl == "de" else "en" if wahl == "en" else None
            )
            werte["sprache"] = sprache
            gueltig["sprache"] = wahl or "auto"
        else:
            fehler.append(("sprache", Text("Diese Sprache gibt es nicht")))
    if "darstellung" in felder:
        if felder["darstellung"] in DARSTELLUNGEN:
            werte["darstellung"] = felder["darstellung"]
            gueltig["darstellung"] = felder["darstellung"]
        else:
            fehler.append(("darstellung", FALSCHE_WAHL))
    for name in SCHALTER:
        if name not in felder:
            continue
        if felder[name] in ("an", "aus"):
            werte[name] = felder[name] == "an"
            gueltig[name] = felder[name]
        else:
            fehler.append((name, FALSCHE_WAHL))
    return Vorlieben(**werte), fehler, gueltig


def _aktuell(a: Angemeldet) -> dict[str, str]:
    b = a.benutzer
    return {
        "sprache": b.sprache or "auto",
        "darstellung": b.darstellung,
        **{n: "an" if getattr(b, n) else "aus" for n in SCHALTER},
    }


async def _seite(
    request: Request,
    a: Angemeldet,
    gewaehlt: dict[str, str],
    fehler: list[tuple[str, Text]] | None = None,
    status: int = 200,
) -> HTMLResponse:
    werte = {
        "titel": N_("Mein Konto"),
        "gewaehlt": gewaehlt,
        "feldfehler": dict(fehler or []),
        "fehlerliste": fehler or [],
    }
    return await seite(request, "konto.html", werte, status=status, teil="inhalt")


@router.get("/konto", response_class=HTMLResponse)
async def konto(request: Request, a: AngemeldetDep) -> HTMLResponse:
    return await _seite(request, a, _aktuell(a))


@router.post("/konto/vorlieben")
async def vorlieben(request: Request, a: AngemeldetDep) -> Response:
    felder = await formular(request)
    wahl, fehler, gueltig = vorlieben_aus_formular(felder)
    if fehler:
        return await _seite(request, a, _aktuell(a) | gueltig, fehler, status=422)
    if wahl.gesetzt():
        dienste = dienste_von(request)

        def speichern() -> None:
            with dienste.system() as s:
                setze_vorlieben(s, a.benutzer.id, wahl)
                s.commit()

        await run_in_threadpool(speichern)
    if ist_htmx(request):
        return Response(status_code=200, headers={"HX-Refresh": "true"})
    weiter = felder.get("weiter")
    ziel = "/konto" if weiter is None else sicheres_ziel(weiter)
    return RedirectResponse(ziel, status_code=303)


@router.post("/einstellungen/sprache")
async def alter_sprachpfad(a: AngemeldetDep) -> Response:
    """Lesezeichen und offene Seiten alter Fassung: 308 behält Methode und Körper."""
    return RedirectResponse("/konto/vorlieben", status_code=308)
