"""Beleg-Webhook — tokengeschützter HTTP-Endpunkt für Fremdsysteme und Messenger.

``POST /belege`` nimmt Dateien als Rohdaten, ``multipart/form-data`` oder JSON mit
Base64 an (``anfrage.py``). Reihenfolge der Prüfungen, jeweils bevor etwas
gespeichert wird: Token (401) → Größe der Anfrage, schon beim Lesen gezählt (413) →
Form (400) → Anzahl und Größe der Dateien (413) → Typ am Inhalt (415). Erst wenn
alle Dateien einer Anfrage bestehen, gehen sie über den Kanal ``webhook`` in die
Pipeline — dieselbe wie für jeden anderen Kanal.

TLS gehört in einen Reverse-Proxy davor; ohne Konfiguration lauscht der Dienst nur
auf 127.0.0.1.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele.einstellungen import WebhookEinstellungen
from accounti.belege.kanaele.pruefung import DateiAbgelehntError, Dateipruefung
from accounti.belege.kanaele.webhook import KANAL, WebhookKanal
from accounti.belege.pipeline import Erkenner, nimm_auf
from accounti.belege.webhook.anfrage import AnfrageError, Upload, lies_anfrage
from accounti.belege.webhook.token import pruefe_token
from accounti.db.repo_kanaele import markiere_webhook_token_genutzt, merke_nachricht
from accounti.db.repository import lade_beleg
from accounti.models.kanaele import AbgeholteNachricht, WebhookToken


class AnfrageZuGrossError(ValueError):
    """Der Körper der Anfrage überschreitet die Grenze."""


def _fehler(status: int, text: str, **kopf: str) -> JSONResponse:
    return JSONResponse({"fehler": text}, status_code=status, headers=kopf or None)


def _bearer(kopf: str | None) -> str | None:
    if not kopf:
        return None
    art, _, token = kopf.partition(" ")
    return token.strip() or None if art.lower() == "bearer" else None


async def _lies_begrenzt(request: Request, grenze: int) -> bytes:
    teile: list[bytes] = []
    groesse = 0
    async for stueck in request.stream():
        groesse += len(stueck)
        if groesse > grenze:
            raise AnfrageZuGrossError
        teile.append(stueck)
    return b"".join(teile)


def erstelle_app(
    make_session: sessionmaker[Session],
    archiv: BelegArchiv,
    einstellungen: WebhookEinstellungen | None = None,
    pruefung: Dateipruefung | None = None,
    erkenner: Erkenner | None = None,
) -> FastAPI:
    """Die Webhook-Anwendung (für uvicorn oder den TestClient)."""
    einstellungen = einstellungen or WebhookEinstellungen()
    pruefung = pruefung or Dateipruefung()
    grenze = einstellungen.max_anfrage_bytes
    # Die Dublettenprüfung liest den Bestand: Aufnahmen nacheinander, nicht parallel.
    sperre = threading.Lock()
    app = FastAPI(
        title="accounti Beleg-Webhook", docs_url=None, redoc_url=None, openapi_url=None
    )

    def token_pruefen(token: str) -> WebhookToken | None:
        with make_session() as s:
            return pruefe_token(s, token)

    def aufnehmen(
        token: WebhookToken, dateien: list[tuple[str, bytes]], absender: str | None
    ) -> list[dict[str, Any]]:
        herkunft = f"Webhook {token.name}" + (f" von {absender}" if absender else "")
        ergebnisse: list[dict[str, Any]] = []
        with sperre, make_session() as s:
            for roh in WebhookKanal(dateien, herkunft).abholen():
                eingang = nimm_auf(s, archiv, roh, erkenner=erkenner)
                s.commit()
                beleg = lade_beleg(s, eingang.beleg_id) if eingang.beleg_id else None
                ergebnisse.append(
                    {
                        "dateiname": roh.dateiname,
                        "ergebnis": eingang.ergebnis.value,
                        "beleg_id": str(eingang.beleg_id) if eingang.beleg_id else None,
                        "status": beleg.status.value if beleg else None,
                        "hinweis": (beleg.pruef_grund if beleg else None)
                        or eingang.hinweis,
                    }
                )
            merke_nachricht(
                s,
                AbgeholteNachricht(
                    kanal=KANAL,
                    quelle=token.name,
                    schluessel=str(uuid4()),
                    absender=absender,
                    datei_hashes=[hashlib.sha256(d).hexdigest() for _, d in dateien],
                ),
            )
            markiere_webhook_token_genutzt(s, token.id)
            s.commit()
        return ergebnisse

    @app.get("/gesund")
    def gesund() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/belege")
    async def belege(request: Request) -> JSONResponse:
        klartext = _bearer(request.headers.get("authorization"))
        if klartext is None:
            return _fehler(
                401,
                "Token fehlt (Authorization: Bearer …)",
                **{"WWW-Authenticate": 'Bearer realm="accounti"'},
            )
        token = await run_in_threadpool(token_pruefen, klartext)
        if token is None:
            return _fehler(
                401,
                "Token ungültig oder widerrufen",
                **{
                    "WWW-Authenticate": 'Bearer realm="accounti", error="invalid_token"'
                },
            )
        laenge = request.headers.get("content-length", "")
        if laenge.isdigit() and int(laenge) > grenze:
            return _fehler(
                413, f"Anfrage größer als {einstellungen.max_anfrage_mb:g} MB"
            )
        try:
            koerper = await _lies_begrenzt(request, grenze)
        except AnfrageZuGrossError:
            return _fehler(
                413, f"Anfrage größer als {einstellungen.max_anfrage_mb:g} MB"
            )
        try:
            upload: Upload = lies_anfrage(
                request.headers.get("content-type", ""),
                request.headers,
                request.query_params,
                koerper,
            )
        except AnfrageError as fehler:
            return _fehler(400, str(fehler))
        if len(upload.dateien) > einstellungen.max_dateien:
            return _fehler(
                413, f"Höchstens {einstellungen.max_dateien} Dateien je Anfrage"
            )
        geprueft: list[tuple[str, bytes]] = []
        abgelehnt: list[DateiAbgelehntError] = []
        for name, inhalt in upload.dateien:
            try:
                geprueft.append((pruefung.pruefe(name, inhalt), inhalt))
            except DateiAbgelehntError as fehler:
                abgelehnt.append(fehler)
        if abgelehnt:
            status = 413 if any(f.art == "groesse" for f in abgelehnt) else 415
            if all(f.art == "leer" for f in abgelehnt):
                status = 400
            text = "; ".join(str(f) for f in abgelehnt) + " — nichts gespeichert"
            return _fehler(status, text)
        ergebnisse = await run_in_threadpool(
            aufnehmen, token, geprueft, upload.absender
        )
        return JSONResponse({"ergebnisse": ergebnisse})

    return app
