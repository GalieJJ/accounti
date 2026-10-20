"""Sitzung, Rollenprüfung und CSRF als FastAPI-Dependencies.

- ``angemeldet``: gültige Sitzung (Cookie) mit Benutzer, aktiver Gesellschaft und
  ihren Rechten — sonst ``NichtAngemeldetError`` (Seiten: Weiterleitung zur
  Anmeldung, API: 401). Bei jeder nicht lesenden Anfrage prüft sie das CSRF-Token
  (Formularfeld ``csrf`` oder Kopf ``X-CSRF-Token``).
- ``erfordert(Recht.X)``: wie ``angemeldet``, dazu 403 ohne das Recht.
- ``gesellschaft_db``: Datenbanksitzung der aktiven Gesellschaft — der einzige Weg
  an ihre Daten; der Wechsel der Gesellschaft schaltet damit alle Seiten um.

Die Mitgliedschaft in der Gesellschaft wird bei jeder Anfrage neu gelesen: Wer eine
Rolle verliert, verliert sie sofort.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from accounti.api.dienste import Dienste
from accounti.api.formular import formular
from accounti.auth.dienst import (
    gesellschaften_von,
    pruefe_sitzung,
    rechte_in,
    wechsle_gesellschaft,
)
from accounti.betrieb.gesellschaften import Gesellschaft
from accounti.models.auth import Benutzer, Recht, Sitzung

SICHERE_METHODEN = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_FELD = "csrf"
CSRF_KOPF = "x-csrf-token"


class NichtAngemeldetError(Exception):
    """Keine gültige Sitzung."""


def dienste_von(request: Request) -> Dienste:
    dienste: Dienste = request.app.state.dienste
    return dienste


def cookie_name(dienste: Dienste) -> str:
    """Mit TLS ``__Host-``: nur Secure, Path=/, ohne Domain (OWASP)."""
    return (
        "__Host-accounti_sitzung"
        if dienste.server.cookie_sicher
        else "accounti_sitzung"
    )


def csrf_token(sitzungstoken: str) -> str:
    """CSRF-Token aus dem geheimen Sitzungstoken — nichts zu speichern."""
    return hmac.new(
        sitzungstoken.encode("utf-8"), b"accounti-csrf", hashlib.sha256
    ).hexdigest()


@dataclass(frozen=True)
class Angemeldet:
    benutzer: Benutzer
    sitzung: Sitzung
    gesellschaft: Gesellschaft
    gesellschaften: tuple[Gesellschaft, ...]
    rechte: frozenset[Recht]
    csrf: str

    def darf(self, recht: Recht) -> bool:
        return recht in self.rechte


def _lade(dienste: Dienste, token: str) -> Angemeldet | None:
    with dienste.system() as s:
        jetzt = dienste.uhr()
        treffer = pruefe_sitzung(s, token, dienste.auth, jetzt)
        if treffer is None:
            s.commit()
            return None
        sitzung, b = treffer
        erlaubt = sorted(set(gesellschaften_von(s, b.id)) & set(dienste.gesellschaften))
        if not erlaubt:
            s.commit()
            return None
        if sitzung.gesellschaft not in erlaubt:
            sitzung = wechsle_gesellschaft(s, sitzung, erlaubt[0], jetzt)
        rechte = frozenset(rechte_in(s, b.id, sitzung.gesellschaft))
        s.commit()
    return Angemeldet(
        benutzer=b,
        sitzung=sitzung,
        gesellschaft=dienste.gesellschaften[sitzung.gesellschaft],
        gesellschaften=tuple(dienste.gesellschaften[k] for k in erlaubt),
        rechte=rechte,
        csrf=csrf_token(token),
    )


async def pruefe_csrf(request: Request, erwartet: str) -> None:
    gesendet = request.headers.get(CSRF_KOPF) or (await formular(request)).get(
        CSRF_FELD, ""
    )
    if not gesendet or not hmac.compare_digest(gesendet.encode(), erwartet.encode()):
        raise HTTPException(403, "CSRF-Token fehlt oder passt nicht — Seite neu laden")
    # zusätzlich: Browser melden fremde Absender (Fetch Metadata)
    if request.headers.get("sec-fetch-site", "") == "cross-site":
        raise HTTPException(403, "Anfrage von einer fremden Seite abgewiesen")


async def angemeldet(request: Request) -> Angemeldet:
    dienste = dienste_von(request)
    token = request.cookies.get(cookie_name(dienste))
    if not token:
        raise NichtAngemeldetError
    a = await run_in_threadpool(_lade, dienste, token)
    if a is None:
        raise NichtAngemeldetError
    if request.method not in SICHERE_METHODEN:
        await pruefe_csrf(request, a.csrf)
    request.state.angemeldet = a
    return a


AngemeldetDep = Annotated[Angemeldet, Depends(angemeldet)]


def erfordert(recht: Recht) -> Callable[..., Awaitable[Angemeldet]]:
    """Dependency: angemeldet **und** das Recht in der aktiven Gesellschaft."""

    async def abhaengigkeit(a: AngemeldetDep) -> Angemeldet:
        if not a.darf(recht):
            raise HTTPException(
                403, f"Ihre Rolle in {a.gesellschaft.name} erlaubt das nicht"
            )
        return a

    abhaengigkeit.__name__ = f"erfordert_{recht.value}"
    return abhaengigkeit


def gesellschaft_db(request: Request, a: AngemeldetDep) -> Iterator[Session]:
    """Datenbanksitzung der aktiven Gesellschaft (der Aufrufer committet selbst)."""
    with dienste_von(request).datenbank(a.gesellschaft.kuerzel) as s:
        yield s
