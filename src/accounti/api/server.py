"""``accounti serve`` — Uvicorn mit der App-Fabrik.

TLS gehört in einen Reverse-Proxy davor (``docs/betrieb.md``). ``X-Forwarded-For``
und ``-Proto`` glaubt Uvicorn nur den Adressen aus
``server.vertrauenswuerdige_proxies``. Das Zugriffsprotokoll von Uvicorn ist aus —
es enthielte IP-Adressen und Abfrageparameter; die App protokolliert selbst ohne
personenbezogene Inhalte.
"""

from __future__ import annotations

from typing import Any

from accounti.api.app import erstelle_app
from accounti.api.dienste import Dienste


def uvicorn_optionen(dienste: Dienste, host: str, port: int) -> dict[str, Any]:
    return {
        "host": host,
        "port": port,
        "access_log": False,
        "proxy_headers": True,
        "forwarded_allow_ips": ",".join(dienste.server.vertrauenswuerdige_proxies),
        "server_header": False,
        "log_config": None,
    }


def starte(dienste: Dienste, host: str, port: int) -> None:  # pragma: no cover
    import uvicorn

    from accounti.betrieb.protokoll import richte_protokoll_ein

    richte_protokoll_ein()
    uvicorn.run(erstelle_app(dienste), **uvicorn_optionen(dienste, host, port))


def starte_aus_cli(
    host: str | None, port: int | None, db: str, archiv: str, config: str
) -> None:
    """Dienste aus Registry oder Optionen; Hinweise, wenn noch etwas fehlt."""
    import os

    import typer
    from rich.console import Console
    from rich.markup import escape

    from accounti.api.dienste import dienste_aus_kontext
    from accounti.bank.tresor import UMGEBUNG
    from accounti.betrieb.kontext import aktueller_kontext
    from accounti.db.repo_auth import anzahl_benutzer
    from accounti.konfiguration import KonfigurationError

    console = Console(stderr=True)
    try:
        dienste = dienste_aus_kontext(aktueller_kontext(), db, archiv, config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(2) from fehler
    with dienste.system() as s:
        if anzahl_benutzer(s) == 0:
            console.print(
                "[yellow]Noch keine Benutzer — niemand kann sich anmelden: "
                "accounti benutzer anlegen NAME --rolle verwalter[/yellow]",
                soft_wrap=True,
            )
    if not os.environ.get(UMGEBUNG):
        console.print(
            f"[yellow]{UMGEBUNG} fehlt — ohne ihn lässt sich der zweite Faktor "
            "nicht prüfen, keine Anmeldung möglich[/yellow]",
            soft_wrap=True,
        )
    adresse = host or dienste.server.host
    nummer = port or dienste.server.port
    namen = ", ".join(g.name for g in dienste.gesellschaften.values())
    console.print(f"accounti auf http://{adresse}:{nummer} — {escape(namen)}")
    starte(dienste, adresse, nummer)
