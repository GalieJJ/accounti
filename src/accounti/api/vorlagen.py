"""Jinja2-Vorlagen der Oberfläche (``accounti/api/vorlagen/``), Autoescape an.

``await seite(request, "name.html", {...})`` rendert mit dem Grundlayout-Kontext:
``angemeldet`` (Benutzer, Gesellschaft, Rechte), ``csrf``, ``geruest`` (Navigation mit
Zählern, ``api.geruest``), ``navigation`` (nur die Punkte, die die Rolle darf),
``version`` und ``sprache``. Die Sprache wählt ``i18n.waehle_sprache`` (Benutzer →
Browser → ``server.sprache``); sie gilt während des Renderns als
``i18n.aktive_sprache`` und wird danach zurückgesetzt. Übersetzt wird mit
``{{ _("…") }}`` (``jinja2.ext.i18n``, Newstyle: Platzhalter werden escaped); Filter
``betrag``, ``datum``, ``euro``, ``prozent``, ``monat`` formatieren je Sprache,
``uebersetzt`` übersetzt eine ``i18n.Text``-Meldung, ``bezeichnung`` zeigt einen
Statuswert (Enum) lesbar.
"""

from __future__ import annotations

import enum
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import (
    Environment,
    PackageLoader,
    StrictUndefined,
    nodes,
    select_autoescape,
)
from jinja2.runtime import Context
from jinja2.utils import pass_context
from markupsafe import Markup, escape
from starlette.routing import Match
from starlette.templating import Jinja2Templates

from accounti import __version__, i18n
from accounti.api.geruest import geruest
from accounti.api.htmx import ist_htmx
from accounti.api.registry import Navigationspunkt
from accounti.api.symbole import symbol_klasse, symbol_url
from accounti.i18n import N_

UMGEBUNG = Environment(
    loader=PackageLoader("accounti.api", "vorlagen"),
    autoescape=select_autoescape(["html"], default_for_string=True, default=True),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    extensions=["jinja2.ext.i18n"],
)


def _sprache(ctx: Context) -> str:
    wert = ctx.get("sprache")
    return wert if isinstance(wert, str) else i18n.aktive_sprache.get()


@pass_context
def _gettext(ctx: Context, text: str) -> str:
    return i18n.gettext(text, _sprache(ctx))


@pass_context
def _ngettext(ctx: Context, einzahl: str, mehrzahl: str, anzahl: int) -> str:
    return i18n.ngettext(einzahl, mehrzahl, anzahl, _sprache(ctx))


UMGEBUNG.install_gettext_callables(  # type: ignore[attr-defined]
    _gettext, _ngettext, newstyle=True
)


def _filter(funktion: Any) -> Any:
    @pass_context
    def anwenden(ctx: Context, wert: Any, *args: Any) -> Any:
        return funktion(wert, *args, sprache=_sprache(ctx))

    return anwenden


# Statuswerte lesbar statt als Enum-Wert („pruefung“, „eingangsrechnung“) — je
# Enum-Klasse, denn str-Enums mit gleichem Wert sind gleich (BuchungStatus und
# BelegStatus „pruefung“). Profilnamen der E-Rechnung bleiben Eigennamen.
BEZEICHNUNGEN: dict[str, dict[str, str]] = {
    "BuchungStatus": {
        "entwurf": N_("Entwurf"),
        "auto": N_("automatisch gebucht"),
        "pruefung": N_("zur Prüfung"),
        "geprueft": N_("geprüft"),
        "korrigiert": N_("korrigiert"),
        "exportiert": N_("exportiert"),
    },
    "Belegart": {
        "eingangsrechnung": N_("Eingangsrechnung"),
        "ausgangsrechnung": N_("Ausgangsrechnung"),
        "quittung": N_("Quittung"),
        "kontoauszug": N_("Kontoauszug"),
        "vertrag": N_("Vertrag"),
        "sonstiges": N_("Sonstiges"),
        "unbekannt": N_("unbekannt"),
    },
    "BelegStatus": {
        "eingegangen": N_("eingegangen"),
        "pruefung": N_("zur Prüfung"),
        "erfasst": N_("erfasst"),
    },
    "AufgabenStatus": {
        "offen": N_("offen"),
        "in_arbeit": N_("in Arbeit"),
        "wartet": N_("wartet"),
        "erledigt": N_("erledigt"),
        "hinfaellig": N_("hinfällig"),
    },
    "Profil": {
        "minimum": "MINIMUM",
        "basic_wl": "BASIC WL",
        "basic": "BASIC",
        "en16931": "EN 16931",
        "extended": "EXTENDED",
        "xrechnung": "XRechnung",
        "unbekannt": N_("unbekannt"),
    },
}


def bezeichnung(wert: Any, sprache: str | None = None) -> str:
    """Lesbarer, übersetzter Name eines Statuswerts; Unbekanntes als Wert."""
    if isinstance(wert, enum.Enum):
        text = BEZEICHNUNGEN.get(type(wert).__name__, {}).get(str(wert.value))
        return i18n.gettext(text, sprache) if text else str(wert.value)
    return "" if wert is None else str(wert)


def betrag_anzeige(
    wert: Any, richtung: str | None = None, sprache: str | None = None
) -> str:
    """Betrag der Komponente ``betrag``: mit Richtung (``einnahme``, ``ausgabe``) mit
    Vorzeichen „+“ bzw. „−“ (U+2212) und schmalem festem Leerzeichen davor, ohne
    Richtung (Summen) ohne Vorzeichen; vor „€“ ein festes Leerzeichen."""
    zeichen = {None: "", "einnahme": "+\u202f", "ausgabe": "\u2212\u202f"}
    if richtung not in zeichen:
        raise ValueError(f"Richtung {richtung!r} gibt es nicht (einnahme, ausgabe)")
    zahl = i18n.euro(abs(wert) if richtung else wert, sprache).replace(" ", "\u00a0")
    return zeichen[richtung] + zahl.replace("-", "\u2212", 1)


UMGEBUNG.filters["betrag"] = _filter(i18n.betrag)
UMGEBUNG.filters["betrag_anzeige"] = _filter(betrag_anzeige)
UMGEBUNG.filters["euro"] = _filter(i18n.euro)
UMGEBUNG.filters["datum"] = _filter(i18n.datum)
UMGEBUNG.filters["prozent"] = _filter(i18n.prozent)
UMGEBUNG.filters["monat"] = _filter(i18n.monat)
UMGEBUNG.filters["uebersetzt"] = _filter(i18n.uebersetze)
UMGEBUNG.filters["bezeichnung"] = _filter(bezeichnung)
UMGEBUNG.filters["prozent_ganz"] = _filter(
    lambda wert, sprache: i18n.prozent(wert, sprache, 0)
)
UMGEBUNG.tests["text"] = lambda wert: isinstance(wert, i18n.Text)
UMGEBUNG.filters["iban"] = lambda wert: " ".join(
    str(wert)[i : i + 4] for i in range(0, len(str(wert)), 4)
)
# Attribute, die Seiten an Komponenten weitergeben (htmx, data-, aria-): nur Namen aus
# dieser Positivliste, die Werte escaped — unabhängig von der Jinja-Fassung, deren
# ``xmlattr`` Schlüssel erst ab 3.1.3/3.1.4 prüft (Plan P1, Entscheidung „Komponenten“)
ERLAUBTE_ATTRIBUTE = re.compile(
    r"hx-(get|post|target|swap|select|push-url|disabled-elt|indicator|vals|confirm)"
    r"|data-[a-z][a-z-]*|aria-[a-z]+|form|formaction|formnovalidate|autofocus"
)


def zusatzattribute(zuordnung: Mapping[str, object] | None) -> Markup:
    """`` name="wert"`` je Eintrag; ``True`` schreibt nur den Namen, ``None`` und
    ``False`` nichts. Ein Name außerhalb der Positivliste lässt das Rendern
    scheitern."""
    teile = []
    for name, wert in (zuordnung or {}).items():
        if not isinstance(name, str) or not ERLAUBTE_ATTRIBUTE.fullmatch(name):
            raise ValueError(f"Attribut {name!r} ist für Komponenten nicht erlaubt")
        if wert is None or wert is False:
            continue
        teile.append(f" {name}" if wert is True else f' {name}="{escape(str(wert))}"')
    return Markup("".join(teile))


@dataclass(frozen=True)
class Spalte:
    """Spaltenkopf der Komponente ``tabelle`` (in Vorlagen ``Spalte(…)``); sortierung
    ``aufsteigend``, ``absteigend`` oder ``keine`` setzt ``aria-sort``, ``href`` den
    Link zum Umsortieren."""

    titel: str
    zahl: bool = False
    sortierung: str | None = None
    href: str | None = None


UMGEBUNG.globals["zusatzattribute"] = zusatzattribute
UMGEBUNG.globals["Spalte"] = Spalte
UMGEBUNG.globals["symbol_url"] = symbol_url
UMGEBUNG.globals["symbol_klasse"] = symbol_klasse
VORLAGEN = Jinja2Templates(env=UMGEBUNG)

# htmx 2.0.11 ohne eval, ohne Skripte aus Antworten, ohne Indikatorstil (CSP), ohne
# Seitenstand im sessionStorage; 409/422 werden eingetauscht (Fragment mit Meldung),
# andere 4xx/5xx nicht (Hinweis aus pruefen.js)
HTMX_KONFIG = json.dumps(
    {
        "allowEval": False,
        "allowScriptTags": False,
        "includeIndicatorStyles": False,
        "historyCacheSize": 0,
        "refreshOnHistoryMiss": True,
        "selfRequestsOnly": True,
        # kein ``style`` übertragen: die Seiten haben keine Inline-Stile (CSP), ein
        # leeres ``style=""`` (etwa von Werkzeugen) erzeugte sonst CSP-Meldungen
        "attributesToSettle": ["class", "width", "height"],
        "responseHandling": [
            {"code": "204", "swap": False},
            {"code": "[23]..", "swap": True},
            {"code": "409|422", "swap": True, "error": False},
            {"code": "[45]..", "swap": False, "error": True},
        ],
    },
    separators=(",", ":"),
)


def sprache_der_anfrage(request: Request) -> str:
    a = getattr(request.state, "angemeldet", None)
    server = getattr(getattr(request.app.state, "dienste", None), "server", None)
    return i18n.waehle_sprache(
        a.benutzer.sprache
        if a is not None
        else getattr(request.state, "benutzersprache", None),
        request.headers.get("accept-language"),
        getattr(server, "sprache", i18n.STANDARD),
    )


def _beantwortet_get(request: Request, pfad: str) -> bool:
    """Gibt es eine Route, die GET auf ``pfad`` annimmt? (Eingehängte Router von
    FastAPI prüfen ihre Routen selbst.)"""
    bereich = {"type": "http", "path": pfad, "root_path": "", "method": "GET"}
    return any(r.matches(bereich)[0] is Match.FULL for r in request.app.router.routes)


# so viele Abschnitte steigt ``ansichtspfad`` höchstens hinauf — die Routen dieser
# Anwendung haben weniger
ABSCHNITTE = 16


def ansichtspfad(request: Request) -> str:
    """Wohin die Sprachwahl zurückführt (``weiter``): bei GET die Seite selbst, nach
    einem POST die nächste Seite darüber, die GET beantwortet
    (``/pruefen/{id}/korrigieren`` → ``/pruefen/{id}``,
    ``/pruefen/regeln/{id}/deaktivieren`` → ``/pruefen/regeln``), sonst ``/`` — nie
    der Pfad des POST (der GET darauf gäbe 405). Immer ein Pfad dieser Anwendung.

    Hinauf nur von einem Pfad mit Route (``scope["route"]``) und höchstens
    ``ABSCHNITTE`` Abschnitte: Jeder Schritt prüft alle Routen — für einen Pfad ohne
    Route mit vielen „/“ (404) war das quadratisch, im Event-Loop, ohne Anmeldung
    (Folgepaket F, Runde 2: gf-betrieb F-B1)."""
    pfad = request.url.path
    if request.method in ("GET", "HEAD"):
        return pfad
    if request.scope.get("route") is None:
        return "/"
    teile = pfad.rstrip("/").split("/", ABSCHNITTE + 1)
    if len(teile) > ABSCHNITTE + 1:
        return "/"
    while len(teile) > 2:
        teile.pop()
        kandidat = "/".join(teile)
        if _beantwortet_get(request, kandidat):
            return kandidat
    return "/"


# Vorlagen mit Fragment (``teil``), die schon geprüft sind: (Umgebung, Name, Block)
_GEPRUEFT: set[tuple[int, str, str]] = set()


def pruefe_teilvorlage(umgebung: Environment, name: str, teil: str) -> None:
    """Eine Vorlage, deren Block ``teil`` allein gerendert wird (htmx-Fragment), darf
    auf oberster Ebene nur ``extends`` und Blöcke haben, und im Block steht kein
    ``super()``: Ein Block allein läuft ohne den Code oben — Importe und ``{% set %}``
    fehlten dort (Plan P1, B19). Sonst ``RuntimeError``, schon beim Rendern der ganzen
    Seite; geprüft wird einmal je Vorlage."""
    schluessel = (id(umgebung), name, teil)
    if schluessel in _GEPRUEFT:
        return
    if umgebung.loader is None:
        raise RuntimeError(f"{name}: keine Vorlagen geladen")
    quelle = umgebung.loader.get_source(umgebung, name)[0]
    baum = umgebung.parse(quelle)
    for knoten in baum.body:
        if isinstance(knoten, nodes.Extends | nodes.Block):
            continue
        if isinstance(knoten, nodes.Output) and all(
            isinstance(n, nodes.TemplateData) and not n.data.strip()
            for n in knoten.nodes
        ):
            continue
        raise RuntimeError(
            f"{name}: mit teil={teil!r} stehen auf oberster Ebene nur extends und "
            f"Blöcke — Importe und set gehören in den Block {teil!r}"
        )
    bloecke = {b.name: b for b in baum.find_all(nodes.Block)}
    if teil not in bloecke:
        raise RuntimeError(f"{name}: der Block {teil!r} fehlt")
    for aufruf in bloecke[teil].find_all(nodes.Call):
        if isinstance(aufruf.node, nodes.Name) and aufruf.node.name == "super":
            raise RuntimeError(f"{name}: kein super() im Block {teil!r}")
    _GEPRUEFT.add(schluessel)


def rendere_teil(
    umgebung: Environment, name: str, teil: str, kontext: dict[str, Any]
) -> str:
    """Nur den Block ``teil`` der Vorlage rendern (ohne Gerüst)."""
    vorlage = umgebung.get_template(name)
    return "".join(vorlage.blocks[teil](vorlage.new_context(kontext)))


async def seite(
    request: Request,
    vorlage: str,
    werte: dict[str, Any] | None = None,
    status: int = 200,
    *,
    zaehler: bool = True,
    teil: str | None = None,
) -> HTMLResponse:
    """Seite mit dem Grundlayout-Kontext und dem Gerüst (``geruest``). Mit ``teil``
    (neue Seiten ab Baustein 10c) liefert eine htmx-Anfrage ohne Verlaufsabruf nur
    diesen Block als Fragment, sonst die ganze Seite (eine Route, zwei Formen; AK58).
    Die Zähler der Navigation gibt es nur für ganze Seiten mit Status < 400 ohne
    ``HX-Request`` und mit ``zaehler`` (die Fehlerwege setzen ``zaehler=False``)."""
    a = getattr(request.state, "angemeldet", None)
    punkte: list[Navigationspunkt] = getattr(request.app.state, "navigation", [])
    sprache = sprache_der_anfrage(request)
    csrf = a.csrf if a else ""
    fragment = ist_htmx(request)
    g = await geruest(request, a, zaehler=zaehler and status < 400 and not fragment)
    kontext: dict[str, Any] = {
        "angemeldet": a,
        "csrf": csrf,
        "geruest": g,
        "navigation": [p for p in punkte if a is not None and p.erlaubt(a.rechte)],
        "version": __version__,
        "titel": "accounti",
        "meldung": None,
        "fehler": None,
        "sprache": sprache,
        "sprachen": i18n.NAMEN,
        "benutzersprache": a.benutzer.sprache if a is not None else None,
        "pfad": ansichtspfad(request),
        "htmx_konfig": HTMX_KONFIG,
        "hx_kopf": json.dumps({"X-CSRF-Token": csrf}),
        # Darstellung an <html> (data-theme, color-scheme) aus den Vorlieben; /muster
        # überschreibt sie mit ?theme=
        "darstellung": g.darstellung,
        "color_scheme": g.color_scheme,
    }
    kontext.update(werte or {})
    if teil is not None:
        pruefe_teilvorlage(UMGEBUNG, vorlage, teil)
    # Starlette rendert im Konstruktor — die Sprache gilt genau so lange
    with i18n.sprache_aktiv(sprache):
        if teil is not None and fragment:
            antwort = HTMLResponse(
                rendere_teil(UMGEBUNG, vorlage, teil, {**kontext, "request": request}),
                status_code=status,
            )
        else:
            antwort = VORLAGEN.TemplateResponse(
                request, vorlage, kontext, status_code=status
            )
    antwort.headers["Vary"] = "Accept-Language"
    return antwort
