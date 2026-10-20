"""Jinja2-Vorlagen der Oberfläche (``accounti/api/vorlagen/``), Autoescape an.

``seite(request, "name.html", {...})`` rendert mit dem Grundlayout-Kontext:
``angemeldet`` (Benutzer, Gesellschaft, Rechte), ``csrf``, ``navigation`` (nur die
Punkte, die die Rolle darf), ``gesellschaften`` (für den Wechsel) und ``version``.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from starlette.templating import Jinja2Templates

from accounti import __version__
from accounti.anzeige import betrag_de, datum_de
from accounti.api.registry import Navigationspunkt

UMGEBUNG = Environment(
    loader=PackageLoader("accounti.api", "vorlagen"),
    autoescape=select_autoescape(["html"], default_for_string=True, default=True),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
UMGEBUNG.filters["betrag"] = betrag_de
UMGEBUNG.filters["datum"] = datum_de
VORLAGEN = Jinja2Templates(env=UMGEBUNG)


def seite(
    request: Request,
    vorlage: str,
    werte: dict[str, Any] | None = None,
    status: int = 200,
) -> HTMLResponse:
    a = getattr(request.state, "angemeldet", None)
    punkte: list[Navigationspunkt] = getattr(request.app.state, "navigation", [])
    kontext: dict[str, Any] = {
        "angemeldet": a,
        "csrf": a.csrf if a else "",
        "navigation": [p for p in punkte if a is not None and a.darf(p.recht)],
        "version": __version__,
        "titel": "accounti",
        "meldung": None,
        "fehler": None,
    }
    kontext.update(werte or {})
    antwort: HTMLResponse = VORLAGEN.TemplateResponse(
        request, vorlage, kontext, status_code=status
    )
    return antwort
