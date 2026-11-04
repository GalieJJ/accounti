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
from accounti.api.einmalcode import (
    bestaetige_einmalcode,
    code_variante,
    code_wechsel,
    freigabesperre,
)
from accounti.api.formular import formular
from accounti.api.registry import Bereich, Navigationspunkt
from accounti.api.sitzung import (
    Angemeldet,
    dienste_von,
    erfordert,
    gesellschaft_db,
)
from accounti.api.vorlagen import Seitenfehler, seite
from accounti.db.repo_zahlung import anzahl_laeufe, lade_laeufe, lade_lauf
from accounti.i18n import N_, Text
from accounti.models.auth import Recht
from accounti.models.zahlung import LaufStatus, Zahlungslauf
from accounti.pruefung.person import geprueft_als

router = APIRouter()
ERGEBNIS = N_("Ergebnis der Freigabe")  # Titel der Seite nach einer Freigabe


def laeufe_im_entwurf(s: Session) -> int:
    """Zähler der Navigation: Zahlungsläufe, die auf Freigabe warten (USt-VA: P2)."""
    return anzahl_laeufe(s, [LaufStatus.ENTWURF])


# sichtbar nur mit Freigaberecht (eines genügt); die Seite selbst lesen alle (LESEN)
NAVIGATION = [
    Navigationspunkt(
        N_("Freigaben"),
        "/freigaben",
        Bereich.FREIGABEN,
        "shield-check",
        frozenset({Recht.ZAHLUNG_FREIGEBEN, Recht.STEUER_FREIGEBEN}),
        50,
        zaehler=laeufe_im_entwurf,
    )
]


@router.get("/freigaben", response_class=HTMLResponse)
async def uebersicht(
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
    code: str | None = None,
) -> HTMLResponse:
    from accounti.zahlung.freigabe import freigabe_hash

    variante = code_variante(code)
    laeufe: list[Zahlungslauf] = await run_in_threadpool(
        lade_laeufe, s, [LaufStatus.ENTWURF]
    )
    return await seite(
        request,
        "freigaben.html",
        {
            "titel": N_("Freigaben"),
            "laeufe": laeufe,
            "inhalt": {lauf.nr: freigabe_hash(lauf) for lauf in laeufe},
            "darf_zahlung": a.darf(Recht.ZAHLUNG_FREIGEBEN),
            "darf_steuer": a.darf(Recht.STEUER_FREIGEBEN),
            "mit_einmalcode": dienste_von(request).auth.einmalcode_bestaetigung,
            "code_variante": variante,
            "code_wechsel": code_wechsel("/freigaben", variante),
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
        msg = Text(
            "Zahlungslauf %(nr)s hat sich seit der Anzeige geändert — bitte neu laden "
            "und erneut prüfen",
            nr=nr,
        )
        raise Seitenfehler(409, msg, titel=N_("Inzwischen geändert"))


def _laufnummer(nr: str) -> int:
    """Nummer des Laufs aus dem Pfad — nur ASCII-Ziffern in der Größe einer
    Datenbank-Ganzzahl, sonst 404 (Runde 3: ab 2^63 bzw. mehr als 4300 Ziffern 500)."""
    from accounti.api.seiten.pruefen import ascii_zahl

    wert = ascii_zahl(nr)
    if wert is None:
        raise HTTPException(404, Text("Seite nicht gefunden"))
    return wert


def _zahlungslauf(
    dienste: Dienste,
    a: Angemeldet,
    s: Session,
    nr: int,
    gesehen: str,
    probe: bool = False,
) -> Text:
    # angemeldet und mit frischem Einmalcode: die Person ist geprüft (Journal)
    with geprueft_als(a.benutzer.name):
        return _zahlungslauf_freigeben(dienste, a, s, nr, gesehen, probe)


def _zahlungslauf_freigeben(
    dienste: Dienste,
    a: Angemeldet,
    s: Session,
    nr: int,
    gesehen: str,
    probe: bool = False,
) -> Text:
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
    if probe:
        s.rollback()  # Fachprobe vor dem Einmalcode: nichts bleibt
    else:
        s.commit()
    if lauf.status is LaufStatus.FREIGEGEBEN:
        return Text(
            "Zahlungslauf %(nr)s freigegeben von %(person)s: %(anzahl)s Zahlungen über "
            "%(summe)s €.",
            nr=nr,
            person=a.benutzer.name,
            anzahl=len(lauf.zahlungen),
            summe=betrag_de(lauf.summe),
        )
    return Text(
        "Erste Freigabe von %(person)s — das Vier-Augen-Prinzip verlangt eine zweite "
        "Person.",
        person=a.benutzer.name,
    )


@router.post("/freigaben/zahlungslauf/{nr}", response_class=HTMLResponse)
async def zahlungslauf_freigeben(
    nr: str,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.ZAHLUNG_FREIGEBEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> HTMLResponse:
    """Stand (Freigabe-Hash) prüfen, die Freigabe zur Probe ausführen und
    zurückrollen (409/404 ohne verbrauchten Code), dann unter der Freigabesperre der
    Gesellschaft beides erneut, Einmalcode, Freigabe — wie Storno und Korrektur
    (gw-storno N2/N3): Ein Doppelklick bekommt 409 ohne Fehlversuch (Runde 3)."""
    lauf_nr = _laufnummer(nr)
    dienste = dienste_von(request)
    felder = await formular(request)
    gesehen = felder.get("freigabe_hash", "")
    await run_in_threadpool(_gesehen, s, lauf_nr, gesehen)
    await run_in_threadpool(_zahlungslauf, dienste, a, s, lauf_nr, gesehen, True)

    def abschliessen() -> Text:
        with freigabesperre(a.gesellschaft.datenbank):
            _gesehen(s, lauf_nr, gesehen)
            _zahlungslauf(dienste, a, s, lauf_nr, gesehen, True)
            bestaetige_einmalcode(dienste, a, felder.get("einmalcode", ""))
            return _zahlungslauf(dienste, a, s, lauf_nr, gesehen)

    text = await run_in_threadpool(abschliessen)
    return await seite(
        request,
        "meldung.html",
        {"titel": ERGEBNIS, "ergebnis": text, "zurueck": "/freigaben"},
    )


def _ustva(
    a: Angemeldet, s: Session, zeitraum_text: str, probe: bool = False
) -> dict[str, Any]:
    with geprueft_als(a.benutzer.name):
        return _ustva_freigeben(a, s, zeitraum_text, probe)


def _ustva_freigeben(
    a: Angemeldet, s: Session, zeitraum_text: str, probe: bool = False
) -> dict[str, Any]:
    """Freigabe der Voranmeldung — ``probe``: Zeitraum, Werte und Befunde prüfen,
    zurückrollen; dazu 409, wenn genau diese Werte schon offen freigegeben sind (der
    zweite Klick eines Doppelklicks, Runde 3)."""
    from accounti.elster.freigabe import (
        FreigabeError,
        gib_frei,
        offene_freigabe,
        ustva_inhalt,
    )
    from accounti.elster.konfiguration import lade_elster, lade_oss
    from accounti.elster.ustva import bereite_vor
    from accounti.konfiguration import (
        KonfigurationError,
        lade_buchhaltung,
        lade_ustid_pruefung,
    )
    from accounti.models.elster import Meldeart
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
            oss_aktiv=lade_oss(pfad, zeitraum.von),  # OSS im Quartal des Zeitraums
        )
        if probe:
            try:
                inhalt = ustva_inhalt(v)
                schon = offene_freigabe(s, Meldeart.USTVA, str(zeitraum), inhalt)
            except FreigabeError:
                schon = None
            if schon is not None:
                s.rollback()
                raise HTTPException(
                    409,
                    Text(
                        "Umsatzsteuer-Voranmeldung %(zeitraum)s ist mit genau diesen "
                        "Werten schon freigegeben (von %(person)s) — nichts zu tun",
                        zeitraum=str(zeitraum),
                        person=schon.freigegeben_von,
                    ),
                )
        f = gib_frei(s, v, a.benutzer.name)
    except (ZeitraumError, KonfigurationError) as fehler:
        s.rollback()
        raise HTTPException(422, str(fehler)) from fehler
    except FreigabeError as fehler:
        s.rollback()
        raise HTTPException(409, str(fehler)) from fehler
    if probe:
        s.rollback()  # Fachprobe vor dem Einmalcode: nichts bleibt
    else:
        s.commit()
    return {
        "titel": ERGEBNIS,
        "ergebnis": Text(
            "Umsatzsteuer-Voranmeldung %(zeitraum)s freigegeben von %(person)s — "
            "Kz 83 %(kz83)s €.",
            zeitraum=str(zeitraum),
            person=f.freigegeben_von,
            kz83=betrag_de(v.voranmeldung.kz83),
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
    zeitraum = felder.get("zeitraum", "")
    if not zeitraum.isascii():
        # nur ASCII-Ziffern wie bei Seite und Steuerschlüssel (``Zeitraum.lies`` läse
        # „２０２６-09“ als 2026-09) — abgewiesen vor dem Einmalcode
        raise HTTPException(
            422, Text("Zeitraum unverständlich — erwartet z.B. 2026-08, 2026-Q3")
        )
    # Zeitraum, Werte und Befunde zur Probe (422/409 ohne verbrauchten Code), dann
    # unter der Freigabesperre erneut, Einmalcode, Freigabe (gw-storno N3, Runde 3)
    await run_in_threadpool(_ustva, a, s, zeitraum, True)

    def abschliessen() -> dict[str, Any]:
        with freigabesperre(a.gesellschaft.datenbank):
            _ustva(a, s, zeitraum, True)
            bestaetige_einmalcode(dienste, a, felder.get("einmalcode", ""))
            return _ustva(a, s, zeitraum)

    werte = await run_in_threadpool(abschliessen)
    return await seite(request, "meldung.html", werte)
