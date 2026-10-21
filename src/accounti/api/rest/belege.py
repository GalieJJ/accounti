"""``POST /api/v1/belege`` — Belege einliefern, wie über den Webhook.

Gelesen wird wie beim Webhook (Rohdaten mit ``X-Dateiname``, ``multipart/form-data``
oder JSON mit Base64); Größe, Anzahl und Typ am Inhalt werden geprüft, **bevor**
etwas gespeichert wird. Danach geht jede Datei über ``belege.pipeline.nimm_auf`` mit
dem Kanal ``api`` ins Archiv der Gesellschaft des Tokens. Aufnahmen sind je
Gesellschaft serialisiert (die Dublettenprüfung liest den Bestand).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from accounti.api.dienste import Dienste
from accounti.api.rest import TokenDb, Zugang, erfordert_recht
from accounti.api.sitzung import dienste_von
from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele import RohBeleg
from accounti.belege.kanaele.pruefung import DateiAbgelehntError
from accounti.belege.pipeline import nimm_auf
from accounti.belege.webhook.anfrage import AnfrageError, lies_anfrage
from accounti.db.repository import lade_beleg
from accounti.models.auth import TokenRecht

router = APIRouter()
KANAL = "api"


async def _koerper(request: Request, grenze: int) -> bytes:
    laenge = request.headers.get("content-length", "")
    if laenge.isdigit() and int(laenge) > grenze:
        raise HTTPException(413, f"Anfrage größer als {grenze // (1024 * 1024)} MB")
    teile: list[bytes] = []
    groesse = 0
    async for stueck in request.stream():
        groesse += len(stueck)
        if groesse > grenze:
            raise HTTPException(413, f"Anfrage größer als {grenze // (1024 * 1024)} MB")
        teile.append(stueck)
    return b"".join(teile)


def _pruefe_dateien(
    zugang: Zugang, dateien: list[tuple[str | None, bytes]]
) -> list[tuple[str, bytes]]:
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.konfiguration import KonfigurationError

    try:
        einstellungen = lade_belegkanaele(zugang.gesellschaft.konfiguration)
    except KonfigurationError as fehler:
        raise HTTPException(500, "Konfiguration der Belegkanäle fehlerhaft") from fehler
    if len(dateien) > einstellungen.webhook.max_dateien:
        msg = f"Höchstens {einstellungen.webhook.max_dateien} Dateien je Anfrage"
        raise HTTPException(413, msg)
    pruefung = einstellungen.pruefung()
    geprueft: list[tuple[str, bytes]] = []
    abgelehnt: list[DateiAbgelehntError] = []
    for name, inhalt in dateien:
        try:
            geprueft.append((pruefung.pruefe(name, inhalt), inhalt))
        except DateiAbgelehntError as fehler:
            abgelehnt.append(fehler)
    if abgelehnt:
        status = 413 if any(f.art == "groesse" for f in abgelehnt) else 415
        if all(f.art == "leer" for f in abgelehnt):
            status = 400
        raise HTTPException(
            status, "; ".join(str(f) for f in abgelehnt) + " — nichts gespeichert"
        )
    return geprueft


def _aufnehmen(
    dienste: Dienste,
    zugang: Zugang,
    s: Any,
    dateien: list[tuple[str, bytes]],
    absender: str | None,
) -> list[dict[str, Any]]:
    archiv = BelegArchiv(zugang.gesellschaft.archiv)
    erkenner = dienste.erkenner(zugang.gesellschaft)
    herkunft = (
        f"API-Token {zugang.token.name}" + (f" von {absender}" if absender else "")
    )[:500]
    ergebnisse: list[dict[str, Any]] = []
    with dienste.einlieferung(zugang.gesellschaft.kuerzel):
        for name, inhalt in dateien:
            roh = RohBeleg(
                dateiname=name, inhalt=inhalt, kanal=KANAL, herkunft=herkunft
            )
            eingang = nimm_auf(s, archiv, roh, erkenner=erkenner)
            s.commit()
            beleg = lade_beleg(s, eingang.beleg_id) if eingang.beleg_id else None
            ergebnisse.append(
                {
                    "dateiname": name,
                    "ergebnis": eingang.ergebnis.value,
                    "beleg_id": str(eingang.beleg_id) if eingang.beleg_id else None,
                    "status": beleg.status.value if beleg else None,
                    "hinweis": (beleg.pruef_grund if beleg else None)
                    or eingang.hinweis,
                }
            )
    return ergebnisse


@router.post("/belege")
async def belege_einliefern(
    request: Request,
    zugang: Annotated[Zugang, Depends(erfordert_recht(TokenRecht.BELEGE_SCHREIBEN))],
    s: TokenDb,
) -> dict[str, Any]:
    dienste = dienste_von(request)
    koerper = await _koerper(request, dienste.server.max_beleg_bytes)
    try:
        upload = lies_anfrage(
            request.headers.get("content-type", ""),
            request.headers,
            request.query_params,
            koerper,
        )
    except AnfrageError as fehler:
        raise HTTPException(400, str(fehler)) from fehler
    dateien = await run_in_threadpool(_pruefe_dateien, zugang, upload.dateien)
    ergebnisse = await run_in_threadpool(
        _aufnehmen, dienste, zugang, s, dateien, upload.absender
    )
    return {"ergebnisse": ergebnisse}
