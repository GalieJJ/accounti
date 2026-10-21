"""Freigaben im Browser — dieselben Funktionen wie ``accounti zahlung freigeben`` und
``accounti ustva freigeben``, gebunden an Rolle **und** frischen Einmalcode.

Freigebende Person ist der angemeldete Benutzer; mit ``zahlung.vier_augen`` braucht
ein Lauf zwei verschiedene Benutzer, ``zahlung.freigeber`` gilt wie in der CLI, und
wer den Lauf angelegt hat, gibt ihn nicht frei (``zahlung.ersteller_darf_freigeben``).
Der Einmalcode (``auth.einmalcode_bestaetigung``) bindet jede einzelne Freigabe an
den zweiten Faktor — eine offene Sitzung allein genügt nicht.

Die Seite zeigt jede Zahlung (Empfänger, IBAN, Betrag, Verwendungszweck) und schickt
den Freigabe-Hash des angezeigten Inhalts mit; hat sich der Entwurf bis zum Klick
geändert, gibt es 409 statt einer Freigabe für etwas Ungesehenes.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from accounti.anzeige import betrag_de
from accounti.api.dienste import Dienste
from accounti.api.formular import formular
from accounti.api.registry import Navigationspunkt
from accounti.api.sitzung import (
    Angemeldet,
    dienste_von,
    erfordert,
    gesellschaft_db,
)
from accounti.api.vorlagen import seite
from accounti.auth.dienst import pruefe_zweiten_faktor
from accounti.auth.fehler import AnmeldungError, AuthError
from accounti.bank.tresor import TresorError
from accounti.db.repo_auth import lade_benutzer_id
from accounti.db.repo_zahlung import lade_laeufe, lade_lauf
from accounti.models.auth import Recht
from accounti.models.zahlung import LaufStatus, Zahlungslauf

router = APIRouter()
NAVIGATION = [Navigationspunkt("Freigaben", "/freigaben", Recht.LESEN, 50)]


def bestaetige_einmalcode(dienste: Dienste, a: Angemeldet, einmalcode: str) -> None:
    """Frischer zweiter Faktor für genau diese Freigabe (zählt Fehlversuche)."""
    if not dienste.auth.einmalcode_bestaetigung:
        return
    with dienste.system() as s:
        b = lade_benutzer_id(s, a.benutzer.id)
        if b is None:
            raise HTTPException(403, "Benutzer unbekannt")
        try:
            pruefe_zweiten_faktor(
                s,
                b,
                einmalcode,
                dienste.schluessel(),
                dienste.auth,
                dienste.uhr(),
                quelle="web",
            )
        except AnmeldungError as fehler:
            raise HTTPException(403, "Einmalcode falsch oder schon benutzt") from fehler
        except (AuthError, TresorError) as fehler:
            raise HTTPException(403, str(fehler)) from fehler
        s.commit()


@router.get("/freigaben", response_class=HTMLResponse)
async def uebersicht(
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> HTMLResponse:
    from accounti.zahlung.freigabe import freigabe_hash

    laeufe: list[Zahlungslauf] = await run_in_threadpool(
        lade_laeufe, s, [LaufStatus.ENTWURF]
    )
    return seite(
        request,
        "freigaben.html",
        {
            "titel": "Freigaben",
            "laeufe": laeufe,
            "inhalt": {lauf.nr: freigabe_hash(lauf) for lauf in laeufe},
            "darf_zahlung": a.darf(Recht.ZAHLUNG_FREIGEBEN),
            "darf_steuer": a.darf(Recht.STEUER_FREIGEBEN),
            "mit_einmalcode": dienste_von(request).auth.einmalcode_bestaetigung,
        },
    )


def _gesehen(s: Session, nr: int, gesehen: str) -> None:
    """Vor dem Einmalcode: zeigt die Seite noch den aktuellen Entwurf? (409)"""
    from accounti.zahlung.freigabe import freigabe_hash

    try:
        lauf = lade_lauf(s, nr)
    except ValueError as fehler:
        raise HTTPException(404, str(fehler)) from fehler
    finally:
        s.rollback()
    if not gesehen or freigabe_hash(lauf) != gesehen:
        msg = (
            f"Zahlungslauf {nr} hat sich seit der Anzeige geändert — bitte neu laden "
            "und erneut prüfen"
        )
        raise HTTPException(409, msg)


def _zahlungslauf(
    dienste: Dienste, a: Angemeldet, s: Session, nr: int, gesehen: str
) -> str:
    from accounti.konfiguration import KonfigurationError
    from accounti.zahlung import freigabe
    from accounti.zahlung.konfiguration import lade_zahlung

    try:
        einstellungen = lade_zahlung(a.gesellschaft.konfiguration)
        lauf = freigabe.freigeben(
            s,
            nr,
            a.benutzer.name,
            einstellungen,
            date.today(),
            gesehen=gesehen,
            ersteller_ausgeschlossen=not einstellungen.ersteller_darf_freigeben,
        )
    except freigabe.LaufGesperrtError as fehler:
        s.rollback()
        raise HTTPException(409, str(fehler)) from fehler
    except (freigabe.LaufError, KonfigurationError) as fehler:
        s.rollback()
        raise HTTPException(409, str(fehler)) from fehler
    except ValueError as fehler:  # Lauf unbekannt
        s.rollback()
        raise HTTPException(404, str(fehler)) from fehler
    s.commit()
    if lauf.status is LaufStatus.FREIGEGEBEN:
        return (
            f"Zahlungslauf {nr} freigegeben von {a.benutzer.name}: "
            f"{len(lauf.zahlungen)} Zahlungen über {betrag_de(lauf.summe)} €."
        )
    return (
        f"Erste Freigabe von {a.benutzer.name} — das Vier-Augen-Prinzip verlangt "
        "eine zweite Person."
    )


@router.post("/freigaben/zahlungslauf/{nr}", response_class=HTMLResponse)
async def zahlungslauf_freigeben(
    nr: int,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.ZAHLUNG_FREIGEBEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> HTMLResponse:
    dienste = dienste_von(request)
    felder = await formular(request)
    gesehen = felder.get("freigabe_hash", "")
    await run_in_threadpool(_gesehen, s, nr, gesehen)
    await run_in_threadpool(
        bestaetige_einmalcode, dienste, a, felder.get("einmalcode", "")
    )
    text = await run_in_threadpool(_zahlungslauf, dienste, a, s, nr, gesehen)
    return seite(request, "meldung.html", {"meldung": text, "zurueck": "/freigaben"})


def _ustva(a: Angemeldet, s: Session, zeitraum_text: str) -> dict[str, Any]:
    from accounti.elster.freigabe import FreigabeError, gib_frei
    from accounti.elster.konfiguration import lade_elster, lade_oss
    from accounti.elster.ustva import bereite_vor
    from accounti.konfiguration import (
        KonfigurationError,
        lade_buchhaltung,
        lade_ustid_pruefung,
    )
    from accounti.steuer.zeitraum import Zeitraum, ZeitraumError

    pfad = a.gesellschaft.konfiguration
    try:
        zeitraum = Zeitraum.lies(zeitraum_text)
        v = bereite_vor(
            s,
            zeitraum,
            buchhaltung=lade_buchhaltung(pfad),
            einstellungen=lade_elster(pfad),
            ustid_max_alter_tage=lade_ustid_pruefung(pfad).max_alter_tage,
            oss_aktiv=lade_oss(pfad),
        )
        f = gib_frei(s, v, a.benutzer.name)
    except (ZeitraumError, KonfigurationError) as fehler:
        s.rollback()
        raise HTTPException(422, str(fehler)) from fehler
    except FreigabeError as fehler:
        s.rollback()
        raise HTTPException(409, str(fehler)) from fehler
    s.commit()
    return {
        "meldung": (
            f"Umsatzsteuer-Voranmeldung {zeitraum} freigegeben von "
            f"{f.freigegeben_von} — Kz 83 {betrag_de(v.voranmeldung.kz83)} €."
        ),
        "zurueck": "/freigaben",
    }


@router.post("/freigaben/ustva", response_class=HTMLResponse)
async def ustva_freigeben(
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.STEUER_FREIGEBEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> HTMLResponse:
    dienste = dienste_von(request)
    felder = await formular(request)
    await run_in_threadpool(
        bestaetige_einmalcode, dienste, a, felder.get("einmalcode", "")
    )
    werte = await run_in_threadpool(_ustva, a, s, felder.get("zeitraum", ""))
    return seite(request, "meldung.html", werte)
