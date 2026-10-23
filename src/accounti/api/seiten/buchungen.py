"""Buchungsansicht mit Storno-Kette und Journal — und Korrektur freigegebener
Buchungen nur per Storno und Neubuchung, mit frischem Einmalcode.

Dieselben Daten wie ``accounti buchung zeige`` (``repo_pruefung.korrektur_zu``,
``journal.lade_journal``) und dieselben Funktionen wie ``accounti korrigiere`` bzw.
``accounti buchung storniere`` (``buchung.pruefschlange``, ``pruefung.storno``). Ein
Storno ist endgültig, betrifft oft schon gemeldete Zeiträume und ist selten — deshalb
hier zusätzlich zur Sitzung der Einmalcode (``auth.einmalcode_bestaetigung``), wie bei
Zahlungslauf und USt-VA. Liegt die Buchung in einem gesperrten Zeitraum, ist das Datum
Pflicht und nicht vorbelegt (Baustein 7: keine stille Wahl).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from accounti.api.einmalcode import bestaetige_einmalcode
from accounti.api.formular import formular
from accounti.api.handeln import im_namen
from accounti.api.seiten.pruefen import (
    QUELLEN,
    Fehlerbild,
    _fachfehler,
    _fehlerbild,
    _steuerangabe,
    kontonamen,
    steuernamen,
)
from accounti.api.sitzung import Angemeldet, dienste_von, erfordert, gesellschaft_db
from accounti.api.vorlagen import seite
from accounti.buchung.pruefschlange import (
    Aenderung,
    PruefschlangeError,
    herkunft,
    korrigieren,
    stand,
    stornieren,
)
from accounti.i18n import N_, Text
from accounti.models import Buchungssatz
from accounti.models.auth import Recht

router = APIRouter()


def _lade(s: Session, buchung_id: UUID) -> Buchungssatz:
    from accounti.db.repository import finde_buchung

    try:
        return finde_buchung(s, str(buchung_id))
    except ValueError as fehler:
        raise HTTPException(404, Text("Buchung nicht gefunden")) from fehler


def buchungswerte(
    s: Session,
    a: Angemeldet,
    buchung_id: UUID,
    *,
    eingaben: dict[str, str] | None = None,
    fehler: Fehlerbild | None = None,
    meldungen: list[Any] | None = None,
    mit_einmalcode: bool = True,
) -> dict[str, Any]:
    from accounti.belege.zuordnung import beleg_zur_buchung
    from accounti.db.repo_pruefung import korrektur_zu
    from accounti.db.repository import lade_buchungen, lade_transaktion
    from accounti.pruefung.journal import lade_journal
    from accounti.pruefung.perioden import sperre_am
    from accounti.pruefung.storno import VORSCHLAG, ist_freigegeben, steuer_optionen

    b = _lade(s, buchung_id)
    korrektur = korrektur_zu(s, b.id)
    beteiligte: dict[str, Buchungssatz] = {}
    if korrektur is not None:
        ids = {
            str(x)
            for x in (
                korrektur.original_id,
                korrektur.storno_id,
                korrektur.neubuchung_id,
            )
            if x is not None
        }
        beteiligte = {str(x.id): x for x in lade_buchungen(s) if str(x.id) in ids}
    korrigierbar = (
        ist_freigegeben(b)
        and b.storniert_durch is None
        and b.storno_von is None
        and a.darf(Recht.BUCHEN)
    )
    konten = [b.soll_konto, b.haben_konto] + [
        k for x in beteiligte.values() for k in (x.soll_konto, x.haben_konto)
    ]
    return {
        "titel": N_("Buchung"),
        "b": b,
        "stand": stand(s, b.id),
        "herkunft": herkunft(s, b),
        "quellen": QUELLEN,
        "korrektur": korrektur,
        "beteiligte": beteiligte,
        "journal": lade_journal(s, objekt_id=str(b.id)),
        "beleg": beleg_zur_buchung(s, b),
        "umsatz": lade_transaktion(s, b.transaktion_id) if b.transaktion_id else None,
        "sperre": sperre_am(s, b.datum),
        "steuer": steuer_optionen(b),
        "kontonamen": kontonamen(a, konten),
        "steuernamen": steuernamen(),
        "korrigierbar": korrigierbar,
        "vorschlag": b.status in VORSCHLAG,
        "mit_einmalcode": mit_einmalcode,
        "eingaben": eingaben or {},
        "aktion_fehler": fehler,
        "aktion_meldungen": meldungen or [],
        "brutto": b.betrag_netto + (b.steuer_betrag or 0),
    }


@router.get("/buchungen/{buchung_id:uuid}", response_class=HTMLResponse)
async def buchung_seite(
    buchung_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> HTMLResponse:
    code = dienste_von(request).auth.einmalcode_bestaetigung
    werte = await run_in_threadpool(
        lambda: buchungswerte(s, a, buchung_id, mit_einmalcode=code)
    )
    return seite(request, "buchungen/buchung.html", werte)


def _datum(text: str) -> date | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as fehler:
        raise PruefschlangeError(
            "Kein gültiges Datum (JJJJ-MM-TT)", feld="datum"
        ) from fehler


async def _storno_aktion(
    request: Request,
    a: Angemeldet,
    s: Session,
    buchung_id: UUID,
    felder: dict[str, str],
    vorab: Any,
    ausfuehren: Any,
) -> Response:
    """Stand prüfen (409 ohne verbrauchten Code), Pflichtangaben prüfen (422), dann
    Einmalcode (403), dann ausführen — im Namen der Person, mit Commit."""
    dienste = dienste_von(request)
    code = dienste.auth.einmalcode_bestaetigung

    def anzeige(
        fehler: Fehlerbild | None, meldungen: list[Any] | None = None
    ) -> dict[str, Any]:
        return buchungswerte(
            s,
            a,
            buchung_id,
            eingaben=felder if fehler else None,
            fehler=fehler,
            meldungen=meldungen,
            mit_einmalcode=code,
        )

    def pruefen() -> Fehlerbild | None:
        _lade(s, buchung_id)
        try:
            if stand(s, buchung_id) != felder.get("stand", ""):
                raise PruefschlangeError(
                    "Die Buchung wurde inzwischen geändert — bitte die aktuelle "
                    "Fassung prüfen"
                )
            vorab()
        except PruefschlangeError as fehler:
            return Fehlerbild(
                409 if fehler.feld is None else 422, fehler.meldung, fehler.feld
            )
        finally:
            s.rollback()
        return None

    fehler = await run_in_threadpool(pruefen)
    if fehler is not None:
        werte = await run_in_threadpool(anzeige, fehler)
        return seite(request, "buchungen/buchung.html", werte, status=fehler.status)
    await run_in_threadpool(
        bestaetige_einmalcode, dienste, a, felder.get("einmalcode", "")
    )

    def lauf() -> tuple[list[Any], Fehlerbild | None]:
        with im_namen(a) as person:
            try:
                meldungen = ausfuehren(s, person)
                s.commit()
                return meldungen, None
            except _fachfehler() as f:
                s.rollback()
                from accounti.konfiguration import KonfigurationError

                if isinstance(f, KonfigurationError):
                    return [], Fehlerbild(409, str(f))
                return [], _fehlerbild(f)

    meldungen, fehler = await run_in_threadpool(lauf)
    werte = await run_in_threadpool(anzeige, fehler, meldungen)
    return seite(
        request,
        "buchungen/buchung.html",
        werte,
        status=fehler.status if fehler else 200,
    )


@router.post("/buchungen/{buchung_id:uuid}/korrigieren", response_class=HTMLResponse)
async def korrigieren_seite(
    buchung_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.BUCHEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    from accounti.pruefung.storno import lade_korrekturumgebung

    felder = await formular(request)
    g = a.gesellschaft

    def vorab() -> None:
        _steuerangabe(felder.get("steuer", ""))
        _datum(felder.get("datum", ""))

    def ausfuehren(s: Session, person: str) -> list[Any]:
        steuer, ohne = _steuerangabe(felder.get("steuer", ""))
        e = korrigieren(
            s,
            buchung_id,
            Aenderung(
                felder.get("soll", ""),
                felder.get("haben", ""),
                steuer,
                ohne,
                (felder.get("grund") or "").strip() or None,
                _datum(felder.get("datum", "")),
            ),
            person,
            felder.get("stand", ""),
            lade_korrekturumgebung(g.konfiguration),
            nur_vorschlaege=False,
        )
        k = e.korrektur
        meldung = (
            Text("Buchung korrigiert.")
            if k.storno is None
            else Text(
                "Storniert durch Storno %(storno)s, Neubuchung %(neu)s — Original, "
                "Storno und Neubuchung bleiben sichtbar.",
                storno=str(k.storno.id)[:8],
                neu=str(k.neu.id)[:8] if k.neu else "—",
            )
        )
        return [meldung, *k.warnungen]

    return await _storno_aktion(request, a, s, buchung_id, felder, vorab, ausfuehren)


@router.post("/buchungen/{buchung_id:uuid}/stornieren", response_class=HTMLResponse)
async def stornieren_seite(
    buchung_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.BUCHEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    from accounti.pruefung.storno import lade_korrekturumgebung

    felder = await formular(request)
    g = a.gesellschaft

    def vorab() -> None:
        if not (felder.get("grund") or "").strip():
            raise PruefschlangeError("Grund für das Storno fehlt", feld="grund")
        _datum(felder.get("datum", ""))

    def ausfuehren(s: Session, person: str) -> list[Any]:
        k = stornieren(
            s,
            buchung_id,
            felder.get("grund", ""),
            person,
            felder.get("stand", ""),
            lade_korrekturumgebung(g.konfiguration),
            _datum(felder.get("datum", "")),
        )
        meldungen: list[Any] = [
            Text(
                "Storniert durch Storno %(storno)s — beide Buchungen bleiben sichtbar.",
                storno=str(k.storno.id)[:8] if k.storno else "—",
            )
        ]
        if k.original.transaktion_id is not None:
            meldungen.append(
                Text(
                    "Der Umsatz ist wieder offen und wird beim nächsten Lauf neu "
                    "kontiert (gegebenenfalls über eine gelernte Regel)."
                )
            )
        return [*meldungen, *k.warnungen]

    return await _storno_aktion(request, a, s, buchung_id, felder, vorab, ausfuehren)
