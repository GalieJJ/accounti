"""``accounti token`` — API-Token für Fremdsysteme (Integrationen, Akzeptanz 7).

Ein Token gehört zu genau einer Gesellschaft (``accounti -g K token anlegen …``) und
trägt ausdrücklich genannte Rechte. Freigeben kann kein Token. Der Name ist unter den
aktiven Token einer Gesellschaft eindeutig; ``liste`` und ``widerrufen`` wirken nur in
der gewählten Gesellschaft.
"""

from __future__ import annotations

from datetime import date, datetime

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

NAME = "token"
befehl = typer.Typer(
    help="API-Token für die REST-API (/api/v1) mit Berechtigungen.",
    no_args_is_help=True,
)


def _ende(text: str) -> typer.Exit:
    console.print(f"[red]{escape(text)}[/red]", soft_wrap=True)
    return typer.Exit(1)


def _gesellschaft() -> str:
    from accounti.auth.cli import gesellschaft_fuer_rechte
    from accounti.auth.fehler import AuthError

    try:
        return gesellschaft_fuer_rechte()
    except AuthError as fehler:
        raise _ende(str(fehler)) from fehler


RECHT_OPTION = typer.Option(
    ...,
    "--recht",
    help="opos:lesen, buchungen:lesen, belege:schreiben, laeufe:starten (mehrfach)",
)


@befehl.command("anlegen")
def anlegen(
    name: str = typer.Argument(help="Wer das Token nutzt, z.B. erp oder n8n"),
    recht: list[str] = RECHT_OPTION,
    gueltig_bis: str | None = typer.Option(
        None, "--gueltig-bis", help="letzter gültiger Tag JJJJ-MM-TT"
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Token erzeugen — der Klartext wird nur dieses eine Mal angezeigt."""
    from accounti.auth.cli import systemsitzung, verwaltung_oder_ende
    from accounti.auth.token import lege_api_token_an
    from accounti.models.auth import TokenRecht

    try:
        rechte = [TokenRecht(r.strip().lower()) for r in recht]
    except ValueError as fehler:
        erlaubt = ", ".join(r.value for r in TokenRecht)
        raise _ende(f"Unbekanntes Recht — erlaubt: {erlaubt}") from fehler
    bis = None
    if gueltig_bis is not None:
        try:
            bis = date.fromisoformat(gueltig_bis)
        except ValueError as fehler:
            raise _ende("--gueltig-bis: Datum im Format JJJJ-MM-TT") from fehler
    gesellschaft = _gesellschaft()
    durch = verwaltung_oder_ende(db, config)
    with systemsitzung(db) as s:
        try:
            klartext = lege_api_token_an(
                s, name, gesellschaft, rechte, durch, gueltig_bis=bis
            )
        except ValueError as fehler:
            raise _ende(str(fehler)) from fehler
        s.commit()
    console.print(
        f"Token für {escape(name)} ({escape(gesellschaft)}: "
        f"{', '.join(r.value for r in rechte)}) — jetzt sicher ablegen, gespeichert "
        "wird nur sein Hash:",
        soft_wrap=True,
    )
    console.print(klartext, soft_wrap=True, markup=False, highlight=False)
    console.print(
        "[dim]Aufruf: curl -H 'Authorization: Bearer <TOKEN>' "
        "https://<host>/api/v1/offene-posten[/dim]",
        soft_wrap=True,
    )


@befehl.command("liste")
def liste(db: str = DB_OPTION, config: str = KONFIG_OPTION) -> None:
    """Token der Gesellschaft mit Rechten und letzter Nutzung (ohne Klartext)."""
    from accounti.auth.cli import systemsitzung, verwaltung_oder_ende
    from accounti.db.repo_auth import lade_api_tokens

    gesellschaft = _gesellschaft()
    verwaltung_oder_ende(db, config)
    jetzt = datetime.now()
    with systemsitzung(db) as s:
        tokens = [t for t in lade_api_tokens(s) if t.gesellschaft == gesellschaft]
    if not tokens:
        console.print("[dim]Keine Token — accounti token anlegen NAME --recht …[/dim]")
        return
    tabelle = Table(title="API-Token")
    for spalte in ("Name", "Gesellschaft", "Rechte", "Gültig bis", "Genutzt", "Status"):
        tabelle.add_column(spalte, overflow="fold")
    for t in tokens:
        status = "aktiv" if t.gilt(jetzt) else "abgelaufen"
        if t.widerrufen_am:
            status = f"widerrufen {t.widerrufen_am:%d.%m.%Y}"
        tabelle.add_row(
            escape(t.name),
            t.gesellschaft,
            ", ".join(r.value for r in t.rechte),
            f"{t.gueltig_bis:%d.%m.%Y}" if t.gueltig_bis else "—",
            f"{t.zuletzt_genutzt_am:%d.%m.%Y %H:%M}" if t.zuletzt_genutzt_am else "—",
            status,
        )
    console.print(tabelle)


@befehl.command("widerrufen")
def widerrufen(
    name: str = typer.Argument(help="Name des Tokens"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Token der gewählten Gesellschaft sofort sperren."""
    from accounti.auth.cli import systemsitzung, verwaltung_oder_ende
    from accounti.auth.dienst import ereignis
    from accounti.db.repo_auth import widerrufe_api_token

    gesellschaft = _gesellschaft()
    durch = verwaltung_oder_ende(db, config)
    jetzt = datetime.now()
    with systemsitzung(db) as s:
        try:
            # nur das Token dieser Gesellschaft — Namen sind je Gesellschaft eindeutig
            widerrufe_api_token(s, name, jetzt, gesellschaft)
        except ValueError as fehler:
            raise _ende(str(fehler)) from fehler
        ereignis(
            s, "token_widerrufen", jetzt, durch, gesellschaft=gesellschaft, hinweis=name
        )
        s.commit()
    console.print(f"[green]Widerrufen:[/green] {escape(name)}")
