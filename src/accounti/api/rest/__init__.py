"""REST-API ``/api/v1`` — jedes Modul mit ``router`` wird eingehängt.

Zugang nur mit API-Token (``Authorization: Bearer accounti_api_…``), nie mit dem
Sitzungs-Cookie — so braucht die API keinen CSRF-Schutz. Ein Token gehört zu einer
Gesellschaft und trägt Rechte: fehlt das Token oder ist es ungültig → 401, fehlt das
Recht → 403 mit ``WWW-Authenticate: Bearer error="insufficient_scope"`` (RFC 6750).
Beträge stehen als Zeichenkette mit Punkt (``"1190.00"``), damit nichts gerundet wird.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from accounti.api.dienste import Dienste
from accounti.api.sitzung import dienste_von
from accounti.auth.token import pruefe_api_token
from accounti.betrieb.gesellschaften import Gesellschaft
from accounti.models.auth import ApiToken, TokenRecht


@dataclass(frozen=True)
class Zugang:
    token: ApiToken
    gesellschaft: Gesellschaft

    @property
    def person(self) -> str:
        """Wer im Journal steht (Baustein 7): das Token, nicht der Server-Benutzer."""
        return f"API-Token {self.token.name}"[:100]

    def journal(self) -> AbstractContextManager[object]:
        """Journal-Kontext: das Token ist geprüft (Hash, Gültigkeit, Rechte)."""
        from accounti.pruefung.person import journal_kontext

        return journal_kontext(person=self.person, geprueft=True)


def _bearer(kopf: str | None) -> str | None:
    if not kopf:
        return None
    art, _, token = kopf.partition(" ")
    return token.strip() or None if art.lower() == "bearer" else None


def _pruefe(dienste: Dienste, klartext: str) -> ApiToken | None:
    with dienste.system() as s:
        token = pruefe_api_token(s, klartext, dienste.uhr())
        s.commit()
    return token


async def api_zugang(request: Request) -> Zugang:
    dienste = dienste_von(request)
    klartext = _bearer(request.headers.get("authorization"))
    if klartext is None:
        raise HTTPException(
            401,
            "Token fehlt (Authorization: Bearer …)",
            headers={"WWW-Authenticate": 'Bearer realm="accounti"'},
        )
    token = await run_in_threadpool(_pruefe, dienste, klartext)
    if token is None or token.gesellschaft not in dienste.gesellschaften:
        raise HTTPException(
            401,
            "Token ungültig, abgelaufen oder widerrufen",
            headers={
                "WWW-Authenticate": 'Bearer realm="accounti", error="invalid_token"'
            },
        )
    return Zugang(token, dienste.gesellschaften[token.gesellschaft])


ZugangDep = Annotated[Zugang, Depends(api_zugang)]


def erfordert_recht(recht: TokenRecht) -> Callable[..., Awaitable[Zugang]]:
    async def abhaengigkeit(zugang: ZugangDep) -> Zugang:
        if recht not in zugang.token.rechte:
            raise HTTPException(
                403,
                f"Dem Token fehlt das Recht {recht.value}",
                headers={
                    "WWW-Authenticate": (
                        f'Bearer realm="accounti", error="insufficient_scope", '
                        f'scope="{recht.value}"'
                    )
                },
            )
        return zugang

    abhaengigkeit.__name__ = f"token_{recht.name.lower()}"
    return abhaengigkeit


def token_db(request: Request, zugang: ZugangDep) -> Iterator[Session]:
    """Datenbank der Gesellschaft des Tokens — eine andere erreicht es nicht."""
    with dienste_von(request).datenbank(zugang.gesellschaft.kuerzel) as s:
        yield s


TokenDb = Annotated[Session, Depends(token_db)]


def betrag(wert: object) -> str | None:
    return None if wert is None else str(wert)
