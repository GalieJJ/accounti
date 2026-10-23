"""Jinja2-Vorlagen der Oberfläche (``accounti/api/vorlagen/``), Autoescape an.

``seite(request, "name.html", {...})`` rendert mit dem Grundlayout-Kontext:
``angemeldet`` (Benutzer, Gesellschaft, Rechte), ``csrf``, ``navigation`` (nur die
Punkte, die die Rolle darf), ``gesellschaften`` (für den Wechsel), ``version`` und
``sprache``. Die Sprache wählt ``i18n.waehle_sprache`` (Benutzer → Browser →
``server.sprache``); sie gilt während des Renderns als ``i18n.aktive_sprache`` und wird
danach zurückgesetzt. Übersetzt wird mit ``{{ _("…") }}`` (``jinja2.ext.i18n``,
Newstyle: Platzhalter werden escaped); Filter ``betrag``, ``datum``, ``euro``,
``prozent``, ``monat`` formatieren je Sprache, ``uebersetzt`` übersetzt eine
``i18n.Text``-Meldung.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from jinja2.runtime import Context
from jinja2.utils import pass_context
from starlette.templating import Jinja2Templates

from accounti import __version__, i18n
from accounti.api.registry import Navigationspunkt

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


UMGEBUNG.filters["betrag"] = _filter(i18n.betrag)
UMGEBUNG.filters["euro"] = _filter(i18n.euro)
UMGEBUNG.filters["datum"] = _filter(i18n.datum)
UMGEBUNG.filters["prozent"] = _filter(i18n.prozent)
UMGEBUNG.filters["monat"] = _filter(i18n.monat)
UMGEBUNG.filters["uebersetzt"] = _filter(i18n.uebersetze)
UMGEBUNG.filters["prozent_ganz"] = _filter(
    lambda wert, sprache: i18n.prozent(wert, sprache, 0)
)
UMGEBUNG.tests["text"] = lambda wert: isinstance(wert, i18n.Text)
UMGEBUNG.filters["iban"] = lambda wert: " ".join(
    str(wert)[i : i + 4] for i in range(0, len(str(wert)), 4)
)
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
        a.benutzer.sprache if a is not None else None,
        request.headers.get("accept-language"),
        getattr(server, "sprache", i18n.STANDARD),
    )


def seite(
    request: Request,
    vorlage: str,
    werte: dict[str, Any] | None = None,
    status: int = 200,
) -> HTMLResponse:
    a = getattr(request.state, "angemeldet", None)
    punkte: list[Navigationspunkt] = getattr(request.app.state, "navigation", [])
    sprache = sprache_der_anfrage(request)
    csrf = a.csrf if a else ""
    kontext: dict[str, Any] = {
        "angemeldet": a,
        "csrf": csrf,
        "navigation": [p for p in punkte if a is not None and a.darf(p.recht)],
        "version": __version__,
        "titel": "accounti",
        "meldung": None,
        "fehler": None,
        "sprache": sprache,
        "sprachen": i18n.NAMEN,
        "benutzersprache": a.benutzer.sprache if a is not None else None,
        "pfad": request.url.path,
        "htmx_konfig": HTMX_KONFIG,
        "hx_kopf": json.dumps({"X-CSRF-Token": csrf}),
    }
    kontext.update(werte or {})
    # Starlette rendert im Konstruktor — die Sprache gilt genau so lange
    with i18n.sprache_aktiv(sprache):
        antwort: HTMLResponse = VORLAGEN.TemplateResponse(
            request, vorlage, kontext, status_code=status
        )
    antwort.headers["Vary"] = "Accept-Language"
    return antwort
