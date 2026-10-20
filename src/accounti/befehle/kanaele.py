"""Befehlsgruppe ``kanaele`` — Postfächer, Webhook und Connectoren der Belegerfassung.

Abgeholt wird mit ``accounti belege abholen --kanal email|connector``; hier liegen
Zugänge, das Gedächtnis der verarbeiteten Nachrichten und der Webhook.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import typer

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from accounti.belege.kanaele import BelegKanal

NAME = "kanaele"
befehl = typer.Typer(
    help="Beleg-Kanäle: E-Mail-Postfächer, Webhook und Connectoren einrichten."
)


def _ende(text: str) -> None:
    from rich.markup import escape

    console.print(f"[red]{escape(text)}[/red]")
    raise typer.Exit(1)


def _sitzungen(db: str) -> sessionmaker[Session]:
    from accounti.db import init_db, session_factory

    engine, make_session = session_factory(db)
    init_db(engine)
    return make_session


def eigene_firma_vorgabe(
    config: str, ust_ids: list[str], firma: str | None
) -> tuple[list[str], str | None]:
    """Eigene USt-IdNr. und Firma: was per Option kam, sonst ``mandant`` aus der
    Konfiguration — wie beim Webhook, damit eine Rechnungskopie im Belegpostfach
    über jeden Kanal als Ausgangsrechnung erkannt wird."""
    from accounti.konfiguration import lade_eigene_firma

    eigen = lade_eigene_firma(config)
    if eigen is None:
        return ust_ids, firma
    return (ust_ids or ([eigen.ust_id] if eigen.ust_id else [])), firma or eigen.name


def hole_ab(
    kanal: str,
    quelle: str | None,
    config: str,
    db: str,
    aufnehmen: Callable[[BelegKanal], None],
) -> None:
    """Alle konfigurierten Quellen eines Kanals abholen (für ``belege abholen``).

    Scheitert eine Quelle, geht es mit der nächsten weiter; der Befehl endet dann
    mit Exit-Code 1.
    """
    from rich.markup import escape

    from accounti.belege.kanaele.abholung import KanalError
    from accounti.belege.kanaele.aufbau import baue_kanaele, pruefe_abholbar
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.konfiguration import KonfigurationError

    try:
        pruefe_abholbar(kanal)  # vor dem Anlegen der Datenbank
        kanaele = baue_kanaele(kanal, lade_belegkanaele(config), _sitzungen(db), quelle)
    except KonfigurationError as fehler:
        _ende(str(fehler))
        return
    gescheitert = 0
    for k in kanaele:
        console.print(f"[bold]{escape(k.bezeichnung)}[/bold]")
        try:
            aufnehmen(k)
        except KanalError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            gescheitert += 1
        for hinweis in k.hinweise:
            console.print(f"  [yellow]Hinweis:[/yellow] {escape(hinweis)}")
    if gescheitert:
        raise typer.Exit(1)


@befehl.command("zugang")
def zugang(
    kanal: str = typer.Argument(help="email oder connector"),
    name: str = typer.Argument(help="Name des Postfachs bzw. Connectors"),
    config: str = KONFIG_OPTION,
    db: str = DB_OPTION,
) -> None:
    """Passwort bzw. API-Schlüssel verdeckt abfragen und verschlüsselt speichern."""
    from rich.markup import escape

    from accounti.bank.tresor import TresorError, lade_schluessel
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.belege.kanaele.zugaenge import speichere_zugang
    from accounti.konfiguration import KonfigurationError

    try:
        einstellungen = lade_belegkanaele(config)
        if kanal == "email":
            einstellungen.postfach(name)
        elif kanal == "connector":
            einstellungen.connector(name)
        else:
            _ende(f"Zugänge gibt es für 'email' und 'connector', nicht für '{kanal}'")
        schluessel = lade_schluessel()
    except (KonfigurationError, TresorError) as fehler:
        _ende(str(fehler))
        return
    frage = "Passwort" if kanal == "email" else "API-Schlüssel"
    geheimnis = typer.prompt(frage, hide_input=True)
    make_session = _sitzungen(db)
    with make_session() as s:
        speichere_zugang(s, kanal, name, geheimnis, schluessel)
        s.commit()
    console.print(
        f"[green]Gespeichert:[/green] Zugang für {kanal} {escape(name)} "
        "— verschlüsselt (ACCOUNTI_SCHLUESSEL)"
    )


@befehl.command("nachrichten")
def nachrichten(
    kanal: str | None = typer.Option(None, help="email, connector oder webhook"),
    quelle: str | None = typer.Option(None, help="Postfach, Connector oder Token"),
    anzahl: int = typer.Option(50, help="höchstens so viele, die jüngsten zuerst"),
    db: str = DB_OPTION,
) -> None:
    """Verarbeitete Nachrichten mit Absender — der Hinweis auf den Kreditor."""
    from rich.markup import escape
    from rich.table import Table

    from accounti.db.repo_kanaele import lade_nachrichten

    with _sitzungen(db)() as s:
        liste = lade_nachrichten(s, kanal=kanal, quelle=quelle, limit=anzahl)
    if not liste:
        console.print("[dim]Keine verarbeiteten Nachrichten.[/dim]")
        return
    tabelle = Table(title="Verarbeitete Nachrichten")
    for spalte in ("Abgeholt", "Kanal", "Quelle", "Absender", "Betreff", "Dateien"):
        tabelle.add_column(spalte, overflow="fold")
    tabelle.add_column("Hinweis", overflow="fold")
    for n in liste:
        absender = n.absender or ""
        if n.absender_name:
            absender = (
                f"{n.absender_name} <{absender}>" if absender else n.absender_name
            )
        tabelle.add_row(
            f"{n.abgeholt_am:%d.%m.%Y %H:%M}",
            n.kanal,
            escape(n.quelle),
            escape(absender or "—"),
            escape(n.betreff or ""),
            str(len(n.datei_hashes)),
            escape(n.hinweis or ""),
        )
    console.print(tabelle)


@befehl.command("connectoren")
def connectoren(config: str = KONFIG_OPTION) -> None:
    """Connector-Typen und die konfigurierten Connectoren mit Prüfergebnis."""
    from rich.markup import escape

    from accounti.belege.kanaele.connector import BELEG_CONNECTOREN, baue_connector
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.konfiguration import KonfigurationError

    console.print("[bold]Connector-Typen:[/bold]")
    for typ, klasse in sorted(BELEG_CONNECTOREN.items()):
        console.print(f"  • {typ:8} [dim]{escape(klasse.beschreibung)}[/dim]")
    try:
        einstellungen = lade_belegkanaele(config)
    except KonfigurationError as fehler:
        _ende(str(fehler))
        return
    if not einstellungen.connectoren:
        console.print(
            "[dim]Kein Connector konfiguriert (belegkanaele.connectoren).[/dim]"
        )
        return
    console.print("[bold]Konfiguriert:[/bold]")
    fehlerhaft = False
    for eintrag in einstellungen.connectoren:
        try:
            baue_connector(eintrag, lambda: None)
            zustand = "[green]in Ordnung[/green]"
        except KonfigurationError as fehler:
            zustand = f"[red]{escape(str(fehler))}[/red]"
            fehlerhaft = True
        console.print(f"  • {escape(eintrag.name)} ({escape(eintrag.typ)}): {zustand}")
    if fehlerhaft:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
webhook = typer.Typer(help="Tokengeschützter HTTP-Endpunkt für Fremdsysteme.")
befehl.add_typer(webhook, name="webhook")

ARCHIV_STANDARD = "archiv/belege"


@webhook.command("token")
def webhook_token(
    name: str = typer.Argument(help="Wer das Token nutzt, z.B. n8n oder telegram"),
    db: str = DB_OPTION,
) -> None:
    """Neues Token erzeugen — der Klartext wird nur dieses eine Mal angezeigt."""
    from accounti.belege.webhook.token import lege_token_an

    with _sitzungen(db)() as s:
        try:
            token = lege_token_an(s, name)
        except ValueError as fehler:
            _ende(str(fehler))
            return
        s.commit()
    console.print(
        "Token — jetzt sicher ablegen, gespeichert wird nur sein Hash:", soft_wrap=True
    )
    console.print(token, soft_wrap=True, markup=False, highlight=False)
    console.print(
        "[dim]Aufruf: curl -H 'Authorization: Bearer <TOKEN>' "
        "-F datei=@rechnung.pdf http://127.0.0.1:8410/belege[/dim]",
        soft_wrap=True,
    )


@webhook.command("tokens")
def webhook_tokens(db: str = DB_OPTION) -> None:
    """Tokens mit Status und letzter Nutzung (ohne Klartext)."""
    from rich.markup import escape
    from rich.table import Table

    from accounti.db.repo_kanaele import lade_webhook_tokens

    with _sitzungen(db)() as s:
        tokens = lade_webhook_tokens(s)
    if not tokens:
        console.print("[dim]Keine Tokens — accounti kanaele webhook token NAME[/dim]")
        return
    tabelle = Table(title="Webhook-Tokens")
    for spalte in ("Name", "Erstellt", "Zuletzt genutzt", "Status"):
        tabelle.add_column(spalte)
    for t in tokens:
        tabelle.add_row(
            escape(t.name),
            f"{t.erstellt_am:%d.%m.%Y %H:%M}",
            f"{t.zuletzt_genutzt_am:%d.%m.%Y %H:%M}" if t.zuletzt_genutzt_am else "—",
            "aktiv"
            if t.aktiv
            else f"widerrufen {t.widerrufen_am:%d.%m.%Y}"
            if t.widerrufen_am
            else "widerrufen",
        )
    console.print(tabelle)


@webhook.command("widerrufen")
def webhook_widerrufen(
    name: str = typer.Argument(help="Name des Tokens"),
    db: str = DB_OPTION,
) -> None:
    """Token sofort sperren."""
    from rich.markup import escape

    from accounti.db.repo_kanaele import widerrufe_webhook_token

    with _sitzungen(db)() as s:
        try:
            widerrufe_webhook_token(s, name)
        except ValueError as fehler:
            _ende(str(fehler))
            return
        s.commit()
    console.print(f"[green]Widerrufen:[/green] {escape(name)}")


@webhook.command("starten")
def webhook_starten(
    host: str | None = typer.Option(None, help="Standard: belegkanaele.webhook.host"),
    port: int | None = typer.Option(None, help="Standard: belegkanaele.webhook.port"),
    db: str = DB_OPTION,
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    config: str = KONFIG_OPTION,
    erkennen: bool = typer.Option(
        True, "--erkennen/--ohne-erkennung", help="Belege direkt lesen"
    ),
    ocr_sprache: str = typer.Option("deu", help="Tesseract-Sprache(n)"),
) -> None:
    """Webhook-Dienst starten (POST /belege, GET /gesund)."""
    import uvicorn

    from accounti.belege.archiv import BelegArchiv
    from accounti.belege.erkennung import BelegErkenner
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.belege.ocr.tesseract import TesseractEngine
    from accounti.belege.webhook import erstelle_app
    from accounti.db.repo_kanaele import lade_webhook_tokens
    from accounti.konfiguration import KonfigurationError, lade_eigene_firma

    try:
        einstellungen = lade_belegkanaele(config)
        firma = lade_eigene_firma(config)
    except KonfigurationError as fehler:
        _ende(str(fehler))
        return
    make_session = _sitzungen(db)
    with make_session() as s:
        if not any(t.aktiv for t in lade_webhook_tokens(s)):
            console.print(
                "[yellow]Noch kein aktives Token — jede Anfrage wird abgewiesen. "
                "accounti kanaele webhook token NAME[/yellow]"
            )
    erkenner = None
    if erkennen:
        erkenner = BelegErkenner(
            ocr=TesseractEngine(sprache=ocr_sprache),
            eigene_ust_ids={firma.ust_id} if firma and firma.ust_id else set(),
            eigene_firma=firma.name if firma else None,
        )
    app = erstelle_app(
        make_session,
        BelegArchiv(archiv),
        einstellungen.webhook,
        einstellungen.pruefung(),
        erkenner,
    )
    adresse = host or einstellungen.webhook.host
    nummer = port or einstellungen.webhook.port
    console.print(f"Beleg-Webhook auf http://{adresse}:{nummer}/belege")
    uvicorn.run(app, host=adresse, port=nummer, log_level="info")
