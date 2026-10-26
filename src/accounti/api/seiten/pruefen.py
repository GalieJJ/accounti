"""Supervisions-Queue: unsichere Buchungen prüfen, korrigieren, freigeben,
zurückstellen — links der Beleg, rechts der Vorschlag mit Herkunft und Begründung.

Dieselben Fachfunktionen wie ``accounti review``, ``bestaetige``, ``korrigiere
[--lernen]`` und ``aufgaben rueckfrage`` (``buchung.pruefschlange``,
``klassifikation.lernen``). Jede Aktion trägt den ``stand`` der angezeigten Buchung —
hat sie sich inzwischen geändert, gibt es 409 statt einer Entscheidung über etwas
Ungesehenes; die Queue-Wege nehmen nur Vorschläge an (Storno nur auf
``/buchungen/{id}`` mit Einmalcode). Ohne JavaScript: Formulare und 303 auf den
nächsten Eintrag; mit htmx: das Fragment der Arbeitsfläche (409/422 mit Meldung und
markiertem Feld, sonst der nächste Eintrag und ``HX-Push-Url``).
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from accounti.api.belegantwort import Art, BelegdateiError, lies, tiff_seiten
from accounti.api.formular import formular
from accounti.api.handeln import im_namen
from accounti.api.htmx import ist_htmx
from accounti.api.registry import Navigationspunkt
from accounti.api.sitzung import (
    Angemeldet,
    AngemeldetDep,
    dienste_von,
    erfordert,
    gesellschaft_db,
)
from accounti.api.vorlagen import seite
from accounti.buchung.pruefschlange import (
    Aenderung,
    Ansicht,
    Arbeitsflaeche,
    BuchungFehltError,
    LernWunsch,
    PruefschlangeError,
    RegelBestaetigenError,
    freigeben,
    korrigieren,
    lade_eintrag,
    lade_pruefschlange,
    naechster,
    position,
    zurueckstellen,
)
from accounti.i18n import N_, Text
from accounti.models import Buchungssatz
from accounti.models.auth import Recht
from accounti.steuer.kennziffern import STEUERSCHLUESSEL

router = APIRouter()
NAVIGATION = [Navigationspunkt(N_("Prüfen"), "/pruefen", Recht.LESEN, 10)]

QUELLEN = {
    "regelwerk": N_("Regelwerk"),
    "llm": N_("KI-Vorschlag (LLM)"),
    "beleg": N_("Beleg"),
    "kontakt": N_("Kontakt"),
    "standard": N_("Standardkonto"),
    "opos": N_("Offene Posten"),
    "kreditkarte": N_("Kreditkartenabgleich"),
    "anlagen": N_("Anlagen"),
    "marktplatz": N_("Marktplatz"),
    "korrektur": N_("Korrektur"),
    "storno": N_("Storno"),
}
ERLEDIGT = {
    "freigegeben": N_("Buchung freigegeben."),
    "korrigiert": N_("Buchung korrigiert."),
    "zurueckgestellt": N_(
        "Buchung zurückgestellt — die Rückfrage steht in den Aufgaben."
    ),
}


def confidence_prozent(confidence: float) -> int:
    """Confidence abgerundet in ganzen Prozent — ohne Gleitkommafehler (0,57 · 100
    ist 56,99…; ``int()`` zeigte „56 %“)."""
    return math.floor(round(confidence * 100, 6))


def auto_schwelle() -> float:
    from accounti.buchung.mapper import zu_buchungssatz

    wert = inspect.signature(zu_buchungssatz).parameters["auto_schwelle"].default
    return float(wert)


def _ansicht(wert: str | None) -> Ansicht:
    return (
        Ansicht.ZURUECKGESTELLT
        if wert == Ansicht.ZURUECKGESTELLT.value
        else Ansicht.OFFEN
    )


def _ziel(
    buchung_id: UUID | None, ansicht: Ansicht, erledigt: str | None = None
) -> str:
    abfrage = {"ansicht": ansicht.value}
    if erledigt:
        abfrage["erledigt"] = erledigt
    pfad = f"/pruefen/{buchung_id}" if buchung_id is not None else "/pruefen"
    return f"{pfad}?{urlencode(abfrage)}"


# --- Daten der Arbeitsfläche ----------------------------------------------------------


@dataclass
class Fehlerbild:
    """Eine abgelehnte Aktion: Status, Meldung (Fachmeldung deutsch), Feld."""

    status: int
    meldung: Any
    feld: str | None = None
    fachlich: bool = True  # Meldung eines Fachmoduls (bleibt deutsch)
    vorschau: Any = None  # Regelvorschau, deren Warnung zu bestätigen ist


@dataclass
class Belegansicht:
    art: Art | None = None
    seiten: int = 0
    rechnung: Any = None  # erechnung.modell.Rechnung
    abweichungen: list[str] = field(default_factory=list)
    fehler: Any = None


def belegansicht(a: Angemeldet, beleg: Any, max_bytes: int) -> Belegansicht:
    """Was links angezeigt werden kann — Typ aus dem Inhalt, Fehler als Hinweis."""
    from accounti.erechnung import ERechnungError
    from accounti.erechnung import lies as lies_erechnung

    if beleg is None:
        return Belegansicht()
    try:
        datei = lies(a.gesellschaft.archiv, beleg, max_bytes)
    except BelegdateiError as fehler:
        texte = {
            404: N_("Die Belegdatei fehlt im Archiv."),
            409: N_("Die Belegdatei im Archiv passt nicht zum gespeicherten Prüfwert."),
            413: N_("Die Belegdatei ist zu groß für die Vorschau."),
        }
        return Belegansicht(fehler=texte.get(fehler.status, N_("Keine Vorschau.")))
    ansicht = Belegansicht(art=datei.art)
    if datei.art is Art.TIFF:
        try:
            ansicht.seiten = tiff_seiten(datei.inhalt)
        except BelegdateiError:
            ansicht.art = Art.UNBEKANNT
    if datei.xml is not None:
        try:
            ansicht.rechnung = lies_erechnung(datei.xml)
        except ERechnungError:
            ansicht.fehler = N_("Die E-Rechnung ist nicht lesbar.")
        else:
            ansicht.abweichungen = abweichungen(beleg, ansicht.rechnung)
    return ansicht


def abweichungen(beleg: Any, rechnung: Any) -> list[str]:
    """Nummer, Datum, Brutto: Belegfelder gegen den strukturierten Teil."""
    from accounti.i18n import betrag as fmt_betrag

    gefunden = []
    if rechnung.nummer and beleg.belegnummer and rechnung.nummer != beleg.belegnummer:
        gefunden.append(f"Nummer: {beleg.belegnummer} ≠ {rechnung.nummer}")
    if rechnung.datum and beleg.belegdatum and rechnung.datum != beleg.belegdatum:
        gefunden.append(
            f"Datum: {beleg.belegdatum:%d.%m.%Y} ≠ {rechnung.datum:%d.%m.%Y}"
        )
    brutto = rechnung.summen.brutto
    if brutto is not None and beleg.brutto is not None and brutto != beleg.brutto:
        gefunden.append(
            f"Brutto: {fmt_betrag(beleg.brutto, 'de')} ≠ {fmt_betrag(brutto, 'de')}"
        )
    return gefunden


def kontonamen(a: Angemeldet, konten: list[str]) -> dict[str, str]:
    from accounti.abschluss.konfiguration import lade_abschluss
    from accounti.abschluss.kontenrahmen import KontenrahmenError
    from accounti.buchung.konten import kontobezeichnung
    from accounti.konfiguration import KonfigurationError
    from accounti.pruefung.einstellungen import lade_pruefung

    try:
        kr = lade_abschluss(a.gesellschaft.konfiguration).lade_kontenrahmen()
        pruefung = lade_pruefung(a.gesellschaft.konfiguration)
    except (KonfigurationError, KontenrahmenError, ValueError):
        return {}
    return {k: kontobezeichnung(k, kr, pruefung) for k in konten}


def steuernamen() -> dict[int, str]:
    return {nr: r.bezeichnung for nr, r in STEUERSCHLUESSEL.items()}


def _pruefeinstellungen(a: Angemeldet) -> Any:
    from accounti.konfiguration import KonfigurationError
    from accounti.pruefung.einstellungen import lade_pruefung

    try:
        return lade_pruefung(a.gesellschaft.konfiguration)
    except (KonfigurationError, ValueError):
        return None


def _buchhaltung(a: Angemeldet) -> Any:
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung

    try:
        return lade_buchhaltung(a.gesellschaft.konfiguration)
    except (KonfigurationError, ValueError):
        return None


def flaechenwerte(
    s: Session,
    a: Angemeldet,
    buchung_id: str,
    ansicht: Ansicht,
    max_bytes: int,
    *,
    eingaben: dict[str, str] | None = None,
    fehler: Fehlerbild | None = None,
    meldungen: list[Any] | None = None,
    vorschau: Any = None,
) -> dict[str, Any]:
    from accounti.klassifikation.lernen import vorschlag_muster

    try:
        e: Arbeitsflaeche = lade_eintrag(
            s, buchung_id, pruefung=_pruefeinstellungen(a), buchhaltung=_buchhaltung(a)
        )
    except BuchungFehltError as f:
        raise HTTPException(404, Text("Buchung nicht gefunden")) from f
    b = e.buchung
    pos = position(s, b.id, ansicht)
    konten = [b.soll_konto, b.haben_konto] + [
        k for x in e.geschwister for k in (x.soll_konto, x.haben_konto)
    ]
    werte = {
        "titel": N_("Prüfen"),
        "e": e,
        "b": b,
        "pos": pos,
        "ansicht": ansicht.value,
        "beleg": belegansicht(a, e.beleg, max_bytes),
        "kontonamen": kontonamen(a, konten),
        "steuernamen": steuernamen(),
        "quellen": QUELLEN,
        "schwelle": auto_schwelle(),
        "confidence_prozent": confidence_prozent(b.confidence),
        "eingaben": eingaben or {},
        "aktion_fehler": fehler,
        "aktion_meldungen": meldungen or [],
        "vorschau": vorschau,
        "muster_vorschlag": vorschlag_muster(e.umsatz) if e.umsatz else "",
        "darf_freigeben": a.darf(Recht.BUCHUNG_FREIGEBEN),
        "darf_buchen": a.darf(Recht.BUCHEN),
        "darf_lernen": a.darf(Recht.REGELN_LERNEN),
        "darf_zurueckstellen": a.darf(Recht.BUCHEN) or a.darf(Recht.BUCHUNG_FREIGEBEN),
        "brutto": b.betrag_netto + (b.steuer_betrag or 0),
    }
    return werte


def _antwort(
    request: Request,
    werte: dict[str, Any],
    status: int = 200,
    push: str | None = None,
) -> Response:
    if ist_htmx(request):
        antwort = seite(request, "pruefen/_arbeitsflaeche.html", werte, status=status)
        if push:
            antwort.headers["HX-Push-Url"] = push
        return antwort
    return seite(request, "pruefen/arbeitsflaeche.html", werte, status=status)


def _max_bytes(request: Request) -> int:
    return dienste_von(request).server.max_beleg_bytes


# --- Liste ----------------------------------------------------------------------------


@router.get("/pruefen", response_class=HTMLResponse)
async def liste(
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
    ansicht: str = "offen",
    erledigt: str | None = None,
) -> HTMLResponse:
    nummer = request.query_params.get("seite", "1")
    seite_wert = int(nummer) if nummer.isdigit() else 1
    gewaehlt = _ansicht(ansicht)
    daten = await run_in_threadpool(lade_pruefschlange, s, gewaehlt, seite_wert)
    return seite(
        request,
        "pruefen/liste.html",
        {
            "titel": N_("Prüfen"),
            "liste": daten,
            "ansicht": gewaehlt.value,
            "quellen": QUELLEN,
            "meldung": ERLEDIGT.get(erledigt or ""),
            "confidence_prozent": confidence_prozent,
        },
    )


# --- Gelernte Regeln --------------------------------------------------------------


@router.get("/pruefen/regeln", response_class=HTMLResponse)
async def regeln(
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
    erledigt: str | None = None,
) -> HTMLResponse:
    from accounti.klassifikation.lernen import lade_gelernte_regeln

    gelernt = await run_in_threadpool(lade_gelernte_regeln, s)
    return seite(
        request,
        "pruefen/regeln.html",
        {
            "titel": N_("Gelernte Regeln"),
            "regeln": gelernt,
            "darf_lernen": a.darf(Recht.REGELN_LERNEN),
            "meldung": N_("Regel deaktiviert.") if erledigt == "deaktiviert" else None,
        },
    )


@router.post(
    "/pruefen/regeln/{regel_id:uuid}/deaktivieren", response_class=HTMLResponse
)
async def regel_deaktivieren(
    regel_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.REGELN_LERNEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    from accounti.db.repo_kontierung import lade_kontierungsregel
    from accounti.klassifikation.lernen import RegelError, deaktiviere

    felder = await formular(request)

    def ausfuehren() -> Fehlerbild | None:
        try:
            lade_kontierungsregel(s, regel_id)
        except ValueError as f:
            raise HTTPException(404, Text("Regel nicht gefunden")) from f
        with im_namen(a) as person:
            try:
                deaktiviere(s, regel_id, person, felder.get("grund", ""))
                s.commit()
            except RegelError as f:
                s.rollback()
                return Fehlerbild(422 if f.feld == "grund" else 409, str(f), f.feld)
        return None

    fehler = await run_in_threadpool(ausfuehren)
    if fehler is None:
        return RedirectResponse("/pruefen/regeln?erledigt=deaktiviert", status_code=303)
    from accounti.klassifikation.lernen import lade_gelernte_regeln

    gelernt = await run_in_threadpool(lade_gelernte_regeln, s)
    return seite(
        request,
        "pruefen/regeln.html",
        {
            "titel": N_("Gelernte Regeln"),
            "regeln": gelernt,
            "darf_lernen": True,
            "aktion_fehler": fehler,
        },
        status=fehler.status,
    )


# --- Arbeitsfläche ------------------------------------------------------------------


@router.get("/pruefen/{buchung_id:uuid}", response_class=HTMLResponse)
async def arbeitsflaeche(
    buchung_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
    ansicht: str = "offen",
    erledigt: str | None = None,
) -> Response:
    meldung = ERLEDIGT.get(erledigt or "")
    werte = await run_in_threadpool(
        flaechenwerte,
        s,
        a,
        str(buchung_id),
        _ansicht(ansicht),
        _max_bytes(request),
        meldungen=[meldung] if meldung else None,
    )
    return _antwort(request, werte)


def _fehlerbild(fehler: Exception) -> Fehlerbild:
    from accounti.aufgaben import AufgabenError
    from accounti.db.tabellen import UnveraenderbarError
    from accounti.db.tabellen_abschluss import JahrGesperrtError
    from accounti.klassifikation.lernen import RegelError
    from accounti.pruefung.storno import StornoError

    if isinstance(fehler, RegelBestaetigenError):
        return Fehlerbild(
            fehler.status, fehler.meldung, fehler.feld, vorschau=fehler.vorschau
        )
    if isinstance(fehler, PruefschlangeError):
        return Fehlerbild(fehler.status, fehler.meldung, fehler.feld)
    if isinstance(fehler, StornoError):
        return Fehlerbild(422 if fehler.feld else 409, fehler.meldung, fehler.feld)
    if isinstance(fehler, RegelError):
        return Fehlerbild(422, str(fehler), fehler.feld or "muster")
    if isinstance(fehler, AufgabenError):
        return Fehlerbild(422, str(fehler), "an")
    if isinstance(fehler, (JahrGesperrtError, UnveraenderbarError)):
        return Fehlerbild(409, str(fehler))
    raise fehler


def _fachfehler() -> tuple[type[Exception], ...]:
    from accounti.abschluss.kontenrahmen import KontenrahmenError
    from accounti.aufgaben import AufgabenError
    from accounti.db.tabellen import UnveraenderbarError
    from accounti.db.tabellen_abschluss import JahrGesperrtError
    from accounti.klassifikation.lernen import RegelError
    from accounti.konfiguration import KonfigurationError
    from accounti.pruefung.storno import StornoError

    return (
        PruefschlangeError,
        StornoError,
        RegelError,
        AufgabenError,
        JahrGesperrtError,
        UnveraenderbarError,
        KonfigurationError,
        KontenrahmenError,
    )


async def _aktion(
    request: Request,
    a: Angemeldet,
    s: Session,
    buchung_id: UUID,
    felder: dict[str, str],
    ausfuehren: Any,
    erledigt: str,
) -> Response:
    """Gemeinsamer Ablauf: ausführen (im Namen der Person, mit Commit), bei Fehler
    die Arbeitsfläche mit Meldung (409/422), sonst der nächste Eintrag."""
    ansicht = _ansicht(felder.get("ansicht"))
    max_bytes = _max_bytes(request)

    def lauf() -> tuple[Any, Fehlerbild | None]:
        with im_namen(a) as person:
            try:
                ergebnis = ausfuehren(s, person)
                s.commit()
                return ergebnis, None
            except _fachfehler() as fehler:
                s.rollback()
                from accounti.konfiguration import KonfigurationError

                if isinstance(fehler, KonfigurationError):
                    return None, Fehlerbild(409, str(fehler))
                return None, _fehlerbild(fehler)

    ergebnis, fehler = await run_in_threadpool(lauf)
    if fehler is not None:
        werte = await run_in_threadpool(
            flaechenwerte,
            s,
            a,
            str(buchung_id),
            ansicht,
            max_bytes,
            eingaben=felder,
            fehler=fehler,
            vorschau=fehler.vorschau,
        )
        return _antwort(request, werte, status=fehler.status)
    meldungen = [ERLEDIGT[erledigt], *(ergebnis or [])]

    def weiter() -> tuple[UUID | None, dict[str, Any] | None]:
        from accounti.db.repository import finde_buchung

        b: Buchungssatz = finde_buchung(s, str(buchung_id))
        nach = naechster(s, b, ansicht)
        if nach is None or not ist_htmx(request):
            return nach, None
        return nach, flaechenwerte(
            s, a, str(nach), ansicht, max_bytes, meldungen=meldungen
        )

    nach, naechste = await run_in_threadpool(weiter)
    if not ist_htmx(request):
        return RedirectResponse(_ziel(nach, ansicht, erledigt), status_code=303)
    if naechste is None:  # Ansicht leer: zurück zur Liste (ganze Seite)
        return Response(
            status_code=200,
            headers={"HX-Redirect": _ziel(None, ansicht, erledigt)},
        )
    return _antwort(request, naechste, push=_ziel(nach, ansicht))


def _bestaetigt(felder: dict[str, str]) -> bool:
    """Der Haken „trotzdem speichern“ der Regelvorschau gilt nur für das Muster, für
    das er gesetzt wurde (sein Wert ist dieses Muster)."""
    wert = " ".join((felder.get("regel_bestaetigt") or "").split())
    return bool(wert) and wert == " ".join((felder.get("muster") or "").split())


def _steuerangabe(wert: str) -> tuple[int | None, bool]:
    wert = (wert or "").strip()
    if not wert:
        return None, False
    if wert == "ohne":
        return None, True
    if wert.isdigit() and int(wert) in STEUERSCHLUESSEL:
        return int(wert), False
    raise PruefschlangeError("Unbekannter Steuerschlüssel", feld="steuer")


@router.post("/pruefen/{buchung_id:uuid}/freigeben", response_class=HTMLResponse)
async def freigeben_seite(
    buchung_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.BUCHUNG_FREIGEBEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    from accounti.pruefung.storno import lade_korrekturumgebung

    felder = await formular(request)
    g = a.gesellschaft

    def ausfuehren(s: Session, person: str) -> list[Any]:
        freigeben(
            s,
            buchung_id,
            person,
            felder.get("stand", ""),
            umgebung=lade_korrekturumgebung(g.konfiguration),
        )
        return []

    return await _aktion(request, a, s, buchung_id, felder, ausfuehren, "freigegeben")


@router.post("/pruefen/{buchung_id:uuid}/korrigieren", response_class=HTMLResponse)
async def korrigieren_seite(
    buchung_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.BUCHEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    from accounti.klassifikation.lernen import FELDER
    from accounti.pruefung.storno import lade_korrekturumgebung

    felder = await formular(request)
    mit_regel = felder.get("regel") == "1"
    if mit_regel and not a.darf(Recht.REGELN_LERNEN):
        raise HTTPException(
            403,
            Text(
                "Ihre Rolle in %(gesellschaft)s erlaubt das nicht",
                gesellschaft=a.gesellschaft.name,
            ),
        )
    g = a.gesellschaft

    def ausfuehren(s: Session, person: str) -> list[Any]:
        steuer, ohne = _steuerangabe(felder.get("steuer", ""))
        feld = felder.get("feld") or None
        if feld is not None and feld not in FELDER:
            raise PruefschlangeError("Unbekanntes Feld für die Regel", feld="feld")
        ergebnis = korrigieren(
            s,
            buchung_id,
            Aenderung(
                felder.get("soll", ""),
                felder.get("haben", ""),
                steuer,
                ohne,
                (felder.get("grund") or "").strip() or None,
                None,
            ),
            person,
            felder.get("stand", ""),
            lade_korrekturumgebung(g.konfiguration),
            lernen=LernWunsch(felder.get("muster") or None, feld, _bestaetigt(felder))
            if mit_regel
            else None,
        )
        meldungen: list[Any] = list(ergebnis.korrektur.warnungen)
        if ergebnis.regel is not None:
            meldungen.append(
                Text(
                    "Regel %(name)s gelernt — sie greift beim nächsten Lauf.",
                    name=ergebnis.regel.name,
                )
            )
        if ergebnis.gelernt:
            meldungen.append(ergebnis.gelernt)
        return meldungen

    return await _aktion(request, a, s, buchung_id, felder, ausfuehren, "korrigiert")


@router.post("/pruefen/{buchung_id:uuid}/zurueckstellen", response_class=HTMLResponse)
async def zurueckstellen_seite(
    buchung_id: UUID,
    request: Request,
    a: AngemeldetDep,
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    from accounti.aufgaben import lade_aufgaben_einstellungen

    if not (a.darf(Recht.BUCHEN) or a.darf(Recht.BUCHUNG_FREIGEBEN)):
        raise HTTPException(
            403,
            Text(
                "Ihre Rolle in %(gesellschaft)s erlaubt das nicht",
                gesellschaft=a.gesellschaft.name,
            ),
        )
    felder = await formular(request)
    g = a.gesellschaft

    def ausfuehren(s: Session, person: str) -> list[Any]:
        zurueckstellen(
            s,
            buchung_id,
            felder.get("text", ""),
            person,
            an=(felder.get("an") or "").strip() or None,
            einstellungen=lade_aufgaben_einstellungen(g.konfiguration),
        )
        return []

    return await _aktion(
        request, a, s, buchung_id, felder, ausfuehren, "zurueckgestellt"
    )


@router.post("/pruefen/{buchung_id:uuid}/regelvorschau", response_class=HTMLResponse)
async def regelvorschau(
    buchung_id: UUID,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.REGELN_LERNEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> Response:
    """Was die Regel träfe — per POST (Muster sind Lieferantennamen: nicht in URLs,
    Verlauf und Proxy-Protokolle)."""
    felder = await formular(request)
    g = a.gesellschaft
    ansicht = _ansicht(felder.get("ansicht"))

    def berechnen() -> tuple[Any, Fehlerbild | None]:
        from accounti.abschluss.konfiguration import lade_abschluss
        from accounti.klassifikation.lernen import (
            FELDER,
            RegelError,
            entwurf_fuer,
            lade_regelwerk,
            pruefe_entwurf,
        )
        from accounti.konfiguration import KonfigurationError, lade_buchhaltung

        e = lade_eintrag(s, str(buchung_id))
        if e.umsatz is None:
            return None, Fehlerbild(
                422, Text("Eine Regel gibt es nur für Buchungen mit Umsatz")
            )
        try:
            steuer, ohne = _steuerangabe(felder.get("steuer", ""))
        except PruefschlangeError as f:
            return None, _fehlerbild(f)
        if not steuer and not ohne:
            steuer = e.buchung.steuer_schluessel
        feld = felder.get("feld") or None
        if feld is not None and feld not in FELDER:
            feld = None
        bh = lade_buchhaltung(g.konfiguration)
        try:
            entwurf = entwurf_fuer(
                e.umsatz,
                felder.get("soll") or e.buchung.soll_konto,
                felder.get("haben") or e.buchung.haben_konto,
                None if ohne else steuer,
                bh,
                muster=felder.get("muster") or None,
                feld=feld,
            )
        except RegelError as f:
            return None, _fehlerbild(f)
        try:
            kr = lade_abschluss(g.konfiguration).lade_kontenrahmen()
        except Exception:  # noqa: BLE001 — nur für den Hinweis „Konto unbekannt“
            kr = None
        try:
            # dasselbe Regelwerk wie classify: gelernt → Regeldatei → Standardregeln
            # im Kontenrahmen der Gesellschaft
            werk = lade_regelwerk(s, g.regeln, bh.gelernte_regeln, buchhaltung=bh)
        except KonfigurationError:
            werk = None  # Regeldatei fehlerhaft: „verdrängt Regel …“ bleibt offen
        v = pruefe_entwurf(
            s,
            entwurf,
            e.umsatz,
            werk,
            einstellung=bh.gelernte_regeln,
            kontenrahmen=kr,
            heute=date.today(),
        )
        s.rollback()
        return v, None

    try:
        vorschau, fehler = await run_in_threadpool(berechnen)
    except BuchungFehltError as f:
        raise HTTPException(404, Text("Buchung nicht gefunden")) from f
    if ist_htmx(request):
        return seite(
            request,
            "pruefen/_regelvorschau.html",
            {"vorschau": vorschau, "vorschau_fehler": fehler},
            status=fehler.status if fehler else 200,
        )
    werte = await run_in_threadpool(
        flaechenwerte,
        s,
        a,
        str(buchung_id),
        ansicht,
        _max_bytes(request),
        eingaben={**felder, "regel": "1"},
        fehler=fehler,
        vorschau=vorschau,
    )
    return seite(
        request,
        "pruefen/arbeitsflaeche.html",
        werte,
        status=fehler.status if fehler else 200,
    )
