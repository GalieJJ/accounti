"""Lesen: offene Posten und Buchungen der Gesellschaft des Tokens."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from accounti.api.rest import TokenDb, Zugang, ZugangDep, betrag, erfordert_recht
from accounti.db.repository import lade_buchungen, lade_kontakte, lade_posten
from accounti.models import BuchungStatus, PostenRichtung
from accounti.models.auth import TokenRecht
from accounti.opos.auswertung import offene_posten as nur_offene

router = APIRouter()


@router.get("/ich")
async def ich(zugang: ZugangDep) -> dict[str, Any]:
    """Name, Gesellschaft und Rechte des Tokens."""
    return {
        "token": zugang.token.name,
        "gesellschaft": zugang.gesellschaft.kuerzel,
        "rechte": [r.value for r in zugang.token.rechte],
        "gueltig_bis": zugang.token.gueltig_bis,
    }


@router.get("/offene-posten")
async def offene_posten(
    _: Annotated[Zugang, Depends(erfordert_recht(TokenRecht.OPOS_LESEN))],
    s: TokenDb,
    richtung: str | None = None,
    faellig_bis: date | None = None,
) -> dict[str, Any]:
    """Nicht ausgeglichene Posten; ``richtung`` = verbindlichkeit | forderung."""
    try:
        filter_richtung = PostenRichtung(richtung) if richtung else None
    except ValueError as fehler:
        raise HTTPException(422, "richtung: verbindlichkeit oder forderung") from fehler

    def lesen() -> list[dict[str, Any]]:
        kontakte = {k.id: k for k in lade_kontakte(s)}
        ergebnis = []
        for p in nur_offene(lade_posten(s), faellig_bis, filter_richtung):
            k = kontakte.get(p.kontakt_id)
            konto = None
            if k is not None:
                konto = (
                    k.kreditor_konto
                    if p.richtung is PostenRichtung.VERBINDLICHKEIT
                    else k.debitor_konto
                )
            ergebnis.append(
                {
                    "id": str(p.id),
                    "richtung": p.richtung.value,
                    "kontakt": {
                        "id": str(p.kontakt_id),
                        "name": k.name if k else None,
                        "konto": konto,
                    },
                    "beleg_id": str(p.beleg_id),
                    "belegnummer": p.belegnummer,
                    "belegdatum": p.belegdatum.isoformat(),
                    "faellig_am": p.faellig_am.isoformat(),
                    "betrag": betrag(p.betrag),
                    "restbetrag": betrag(p.restbetrag),
                    "skonto_bis": p.skonto_bis.isoformat() if p.skonto_bis else None,
                    "skonto_betrag": betrag(p.skonto_betrag),
                    "status": p.status.value,
                    "mahnstufe": p.mahnstufe,
                }
            )
        return ergebnis

    posten = await run_in_threadpool(lesen)
    return {"anzahl": len(posten), "offene_posten": posten}


@router.get("/buchungen")
async def buchungen(
    _: Annotated[Zugang, Depends(erfordert_recht(TokenRecht.BUCHUNGEN_LESEN))],
    s: TokenDb,
    von: date | None = None,
    bis: date | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Buchungssätze, optional nach Datum (von/bis einschließlich) und Status."""
    try:
        filter_status = {BuchungStatus(status)} if status else None
    except ValueError as fehler:
        erlaubt = ", ".join(x.value for x in BuchungStatus)
        raise HTTPException(422, f"status: {erlaubt}") from fehler

    def lesen() -> list[dict[str, Any]]:
        alle = sorted(
            lade_buchungen(s, filter_status), key=lambda b: (b.datum, str(b.id))
        )
        return [
            {
                "id": str(b.id),
                "datum": b.datum.isoformat(),
                "soll_konto": b.soll_konto,
                "haben_konto": b.haben_konto,
                "betrag_netto": betrag(b.betrag_netto),
                "steuer_schluessel": b.steuer_schluessel,
                "steuer_betrag": betrag(b.steuer_betrag),
                "buchungstext": b.buchungstext,
                "beleg_nummer": b.beleg_nummer,
                "beleg_id": str(b.beleg_id) if b.beleg_id else None,
                "transaktion_id": str(b.transaktion_id) if b.transaktion_id else None,
                "status": b.status.value,
                "confidence": b.confidence,
            }
            for b in alle
            if (von is None or b.datum >= von) and (bis is None or b.datum <= bis)
        ]

    liste = await run_in_threadpool(lesen)
    return {"anzahl": len(liste), "buchungen": liste}
