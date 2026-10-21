"""Anmelden und Abmelden — Passwort und zweiter Faktor in einem Formular.

Das Anmeldeformular ist gegen Login-CSRF geschützt (Double-Submit: Zufallswert im
Cookie und im Formular). Nach Erfolg gibt es eine **neue** Sitzung; Abmelden beendet
sie serverseitig. Die Fehlermeldung sagt nie, was falsch war.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from accounti.api.dienste import Dienste
from accounti.api.formular import formular
from accounti.api.sitzung import AngemeldetDep, cookie_name, dienste_von
from accounti.api.vorlagen import seite
from accounti.auth.dienst import (
    beende_sitzung,
    gesellschaften_von,
    oeffne_sitzung,
    pruefe_anmeldung,
)
from accounti.auth.fehler import AnmeldungError
from accounti.bank.tresor import TresorError

router = APIRouter()


def anmelde_cookie(dienste: Dienste) -> str:
    """Wie beim Sitzungscookie mit TLS ``__Host-``: keine Subdomain kann es setzen."""
    if dienste.server.cookie_sicher:
        return "__Host-accounti_anmeldung"
    return "accounti_anmeldung"


def sicheres_ziel(weiter: str | None) -> str:
    """Nur relative Pfade dieser Anwendung — keine offene Weiterleitung."""
    if (
        not weiter
        or not weiter.startswith("/")
        or weiter.startswith("//")
        or "\\" in weiter
        or any(ord(z) < 32 for z in weiter)
    ):
        return "/"
    return weiter


def _formular(
    request: Request, weiter: str, fehler: str | None, status: int
) -> Response:
    dienste = dienste_von(request)
    wert = secrets.token_urlsafe(32)
    antwort = seite(
        request,
        "anmelden.html",
        {"titel": "Anmelden", "anmeldung": wert, "weiter": weiter, "fehler": fehler},
        status=status,
    )
    antwort.set_cookie(
        anmelde_cookie(dienste),
        wert,
        max_age=900,
        path="/",
        secure=dienste.server.cookie_sicher,
        httponly=True,
        samesite="strict",
    )
    return antwort


@router.get("/anmelden", response_class=HTMLResponse)
async def anmelden_formular(request: Request, weiter: str = "/") -> Response:
    return _formular(request, sicheres_ziel(weiter), None, 200)


UEBERLASTET = "überlastet"


def _anmelden(dienste: Dienste, felder: dict[str, str]) -> str | None:
    """Sitzungstoken, ``None`` oder ``UEBERLASTET`` — die Fehlversuche zählt
    ``pruefe_anmeldung``. Höchstens ``server.anmeldungen_gleichzeitig`` Prüfungen
    laufen zugleich (scrypt braucht je 128 MiB; Befund A-M2)."""
    if not dienste.anmeldeplatz():
        return UEBERLASTET
    try:
        return _pruefe(dienste, felder)
    finally:
        dienste.anmeldeplatz_frei()


def _pruefe(dienste: Dienste, felder: dict[str, str]) -> str | None:
    with dienste.system() as s:
        try:
            b = pruefe_anmeldung(
                s,
                felder.get("benutzer", ""),
                felder.get("passwort", ""),
                felder.get("einmalcode", ""),
                dienste.schluessel(),
                dienste.auth,
                jetzt=dienste.uhr(),
                quelle="web",
            )
        except (AnmeldungError, TresorError):
            s.rollback()
            return None
        erlaubt = sorted(set(gesellschaften_von(s, b.id)) & set(dienste.gesellschaften))
        if not erlaubt:
            s.rollback()
            return None
        token, _ = oeffne_sitzung(s, b, erlaubt[0], dienste.auth, dienste.uhr())
        s.commit()
    return token


@router.post("/anmelden")
async def anmelden(request: Request) -> Response:
    dienste = dienste_von(request)
    felder = await formular(request)
    weiter = sicheres_ziel(felder.get("weiter"))
    cookie = request.cookies.get(anmelde_cookie(dienste), "")
    gesendet = felder.get("anmeldung", "")
    if not cookie or not hmac.compare_digest(cookie.encode(), gesendet.encode()):
        return _formular(
            request, weiter, "Das Formular ist abgelaufen — bitte erneut senden.", 403
        )
    token = await run_in_threadpool(_anmelden, dienste, felder)
    if token == UEBERLASTET:
        return _formular(
            request,
            weiter,
            "Gerade melden sich viele an — bitte gleich noch einmal versuchen.",
            503,
        )
    if token is None:
        return _formular(request, weiter, "Anmeldung fehlgeschlagen.", 401)
    antwort = RedirectResponse(weiter, status_code=303)
    antwort.set_cookie(
        cookie_name(dienste),
        token,
        max_age=int(dienste.auth.sitzung_hoechstdauer_stunden * 3600),
        path="/",
        secure=dienste.server.cookie_sicher,
        httponly=True,
        samesite="strict",
    )
    antwort.delete_cookie(
        anmelde_cookie(dienste),
        path="/",
        secure=dienste.server.cookie_sicher,
        httponly=True,
        samesite="strict",
    )
    return antwort


@router.post("/abmelden")
async def abmelden(request: Request, _: AngemeldetDep) -> Response:
    dienste = dienste_von(request)
    token = request.cookies.get(cookie_name(dienste), "")

    def beenden() -> None:
        with dienste.system() as s:
            beende_sitzung(s, token, dienste.uhr())
            s.commit()

    await run_in_threadpool(beenden)
    antwort = RedirectResponse("/anmelden", status_code=303)
    antwort.delete_cookie(
        cookie_name(dienste),
        path="/",
        secure=dienste.server.cookie_sicher,
        httponly=True,
        samesite="strict",
    )
    return antwort
