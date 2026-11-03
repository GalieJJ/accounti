"""Musterseite ``/muster`` — jede Komponente in ihren Zuständen (Spec 10c A101; Plan P1
Schritt 4, L9).

Nachbildung der Zeichenfläche „Bausteine“ der Design-Leinwand: ohne Parameter hell und
dunkel nebeneinander (Themenrahmen ``.thema-hell``/``.thema-dunkel``), mit
``?theme=hell|dunkel|auto`` ein Rahmen ohne Themenklasse, und die Seite trägt
``data-theme`` und ``color-scheme`` der Wahl — so prüft die Browserprobe jeden Modus mit
dem echten Gerüst. Andere Werte werden ignoriert. Angemeldet mit ``LESEN``, kein
Navigationspunkt; die Beispieldaten sind erfunden (keine Daten der Gesellschaft).
``/muster/beispiel`` liefert mit ``HX-Request`` den Abschnitt „Austausch“ (Fokus nach
dem Austausch, ``data-fokus``), ohne 303 zurück auf die Musterseite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from accounti.api.geruest import Geruest, Marke, NavEintrag
from accounti.api.htmx import ist_htmx
from accounti.api.sitzung import Angemeldet, erfordert
from accounti.api.vorlagen import seite
from accounti.i18n import N_
from accounti.models.auth import Recht

router = APIRouter()

# Wahl → color-scheme der Seite (wie am Benutzer, Plan P1 „Hell/dunkel“)
DARSTELLUNGEN = {"hell": "light", "dunkel": "dark", "auto": "light dark"}


@dataclass(frozen=True)
class Thema:
    vorsilbe: str  # für eindeutige ids je Rahmen (hell-iban, dunkel-iban)
    klasse: str  # Themenklasse; leer mit ?theme=
    titel: str


BEIDE = (
    Thema("hell", "thema-hell", N_("Hell")),
    Thema("dunkel", "thema-dunkel", N_("Dunkel")),
)
EINZELN = {
    "hell": Thema("muster", "", N_("Hell")),
    "dunkel": Thema("muster", "", N_("Dunkel")),
    "auto": Thema("muster", "", N_("Automatisch")),
}

# die zwölf Farbfelder der Zeichenfläche
FARBEN = (
    ("grund", N_("Grund")),
    ("flaeche", N_("Fläche")),
    ("flaeche-2", N_("Fläche 2")),
    ("linie", N_("Linie")),
    ("text", N_("Text")),
    ("text-2", N_("Nebentext")),
    ("akzent", N_("Akzent (Petrol)")),
    ("fokus", N_("Fokus (Bernstein)")),
    ("ok", N_("Erfolg")),
    ("warn", N_("Warnung")),
    ("fehler", N_("Fehler")),
    ("info", N_("Hinweis")),
)

# erfundene Gesellschaften für die sechs Kennfarben
MARKEN = tuple(
    Marke(f"beispiel-{farbe}", name, farbe, monogramm)
    for farbe, (name, monogramm) in enumerate(
        (
            ("Galerie Demo GmbH", "GD"),
            ("Kunsthandel UG", "KU"),
            ("Rahmenwerk KG", "RK"),
            ("Atelier Nord e. K.", "AN"),
            ("Papier & Co. OHG", "PC"),
            ("Studio Süd GbR", "SS"),
        ),
        start=1,
    )
)


@dataclass(frozen=True)
class Beispiel:
    einnahme: Decimal = Decimal("780.25")
    ausgabe: Decimal = Decimal("-1204.90")
    summe: Decimal = Decimal("11111.11")
    telefon: Decimal = Decimal("239.94")
    buero: Decimal = Decimal("412.37")
    datum: date = date(2026, 10, 15)
    konten: tuple[tuple[str, str], ...] = (
        ("Telefon (4920)", "239,94 €"),
        ("Bürobedarf (4930)", "412,37 €"),
    )


# Ausschnitte von Seitenleiste und unterer Leiste (Gerüst aus Konstanten)
GERUEST = Geruest(
    bereiche=(
        NavEintrag(N_("Übersicht"), "/muster", "house"),
        NavEintrag(
            N_("Prüfen"),
            "/muster",
            "square-check-big",
            zaehler=12,
            betont=True,
            aktiv=True,
        ),
        NavEintrag(N_("Freigaben"), "/muster", "shield-check", zaehler=2),
    ),
    einstellungen=NavEintrag(N_("Einstellungen"), "/muster", "settings"),
    unten=(
        NavEintrag(N_("Übersicht"), "/muster", "house"),
        NavEintrag(N_("Prüfen"), "/muster", "square-check-big", zaehler=12, aktiv=True),
        NavEintrag(N_("Freigaben"), "/muster", "shield-check", zaehler=2),
        NavEintrag(N_("Mehr"), "/muster", "menu"),
    ),
)

LeseDep = Annotated[Angemeldet, Depends(erfordert(Recht.LESEN))]


@router.get("/muster", response_class=HTMLResponse)
async def muster(request: Request, a: LeseDep, theme: str | None = None) -> Response:
    wahl = theme if theme in DARSTELLUNGEN else None
    werte: dict[str, object] = {
        "wahl": wahl,
        "themen": BEIDE if wahl is None else (EINZELN[wahl],),
        "farben": FARBEN,
        "marken": MARKEN,
        "beispiel": Beispiel(),
        "geruest": GERUEST,
    }
    if wahl is not None:
        werte |= {"darstellung": wahl, "color_scheme": DARSTELLUNGEN[wahl]}
    return seite(request, "muster.html", werte, teil="inhalt")


@router.get("/muster/beispiel", response_class=HTMLResponse)
async def beispiel(request: Request, a: LeseDep) -> Response:
    if not ist_htmx(request):
        return RedirectResponse("/muster#austausch", status_code=303)
    return seite(request, "_muster_beispiel.html")
