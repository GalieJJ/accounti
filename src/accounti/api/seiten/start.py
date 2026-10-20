"""Startseite: Kennzahlen der aktiven Gesellschaft (Grundlage, keine Fachansicht)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from accounti.api.registry import Navigationspunkt
from accounti.api.sitzung import Angemeldet, erfordert, gesellschaft_db
from accounti.api.vorlagen import seite
from accounti.db.repo_zahlung import lade_laeufe
from accounti.db.repository import lade_belege, lade_kontakte, lade_posten
from accounti.models import BelegStatus, BuchungStatus
from accounti.models.auth import Recht
from accounti.models.zahlung import LaufStatus
from accounti.opos.auswertung import offene_posten

router = APIRouter()
NAVIGATION = [Navigationspunkt("Übersicht", "/", Recht.LESEN, 0)]


def kennzahlen(s: Session, heute: date) -> dict[str, Any]:
    from sqlalchemy import func, select

    from accounti.db.tabellen import BuchungssatzRow

    posten = offene_posten(lade_posten(s))
    kontakte = {k.id: k.name for k in lade_kontakte(s)}
    pruefung = s.scalar(
        select(func.count())
        .select_from(BuchungssatzRow)
        .where(BuchungssatzRow.status == BuchungStatus.ZUR_PRUEFUNG.value)
    )
    return {
        "offene_posten": len(posten),
        "offene_summe": sum((p.restbetrag for p in posten), start=Decimal(0)),
        "buchungen_pruefung": pruefung or 0,
        "belege_pruefung": len(lade_belege(s, {BelegStatus.ZUR_PRUEFUNG})),
        "zahlungslaeufe": len(lade_laeufe(s, [LaufStatus.ENTWURF])),
        "posten": [
            {
                "faellig_am": p.faellig_am,
                "kontakt": kontakte.get(p.kontakt_id, "?"),
                "belegnummer": p.belegnummer,
                "restbetrag": p.restbetrag,
            }
            for p in posten
            if p.faellig_am <= heute
        ][:20],
    }


@router.get("/", response_class=HTMLResponse)
async def start(
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> HTMLResponse:
    werte = await run_in_threadpool(kennzahlen, s, date.today())
    return seite(request, "start.html", {"titel": "Übersicht", **werte})
