"""``accounti benutzer`` — Benutzer, Rollen, zweiter Faktor (Spec 4.1, 4.7).

Benutzer liegen in der Systemdatenbank, Rollen gelten je Gesellschaft
(``accounti -g K benutzer rolle …``). Der erste Benutzer muss Verwalter sein.
Sobald ein Verwalter seinen zweiten Faktor eingerichtet hat, verlangen alle
Befehle hier einen Verwalter mit Einmalcode (Passwort, 2FA und Codes des eigenen
Kontos darf jeder selbst ändern); eine Gesellschaft, die noch nie einen Verwalter
hatte, richtet ein Verwalter einer anderen ein. Den letzten Verwalter einer
Gesellschaft sperrt oder entrechtet niemand (``auth.cli.pruefe_verwaltung``). Ein
Konto verwaltet nur, wer in **jeder** Gesellschaft Verwalter ist, in der es Rollen
hat. ``anlegen`` und ``rolle`` binden die Gesellschafts-Datenbanken an diese
Systemdatenbank (Merker, ``auth.cli``).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from accounti.models.auth import Benutzer, Rolle

NAME = "benutzer"
befehl = typer.Typer(
    help="Benutzer, Rollen und zweiter Faktor (Anmeldung im Browser).",
    no_args_is_help=True,
)

ROLLE_OPTION = typer.Option(
    ..., "--rolle", help="betrachter, buchhalter, freigeber oder verwalter (mehrfach)"
)


def _ende(text: str) -> typer.Exit:
    console.print(f"[red]{escape(text)}[/red]", soft_wrap=True)
    return typer.Exit(1)


def _rollen(werte: list[str]) -> list[Rolle]:
    from accounti.models.auth import Rolle

    try:
        return [Rolle(w.strip().lower()) for w in werte]
    except ValueError as fehler:
        raise _ende(
            f"Unbekannte Rolle — erlaubt: {', '.join(r.value for r in Rolle)}"
        ) from fehler


def _gesellschaft() -> str:
    from accounti.auth.cli import gesellschaft_fuer_rechte
    from accounti.auth.fehler import AuthError

    try:
        return gesellschaft_fuer_rechte()
    except AuthError as fehler:
        raise _ende(str(fehler)) from fehler


def _nicht_letzter_verwalter(
    s: Session, b: Benutzer, gesellschaft: str | None = None
) -> None:
    """Den letzten Verwalter weder sperren noch entrechten (Betrieb B8)."""
    from accounti.auth.cli import pruefe_nicht_letzter_verwalter
    from accounti.auth.fehler import AuthError

    try:
        pruefe_nicht_letzter_verwalter(s, b, gesellschaft)
    except AuthError as fehler:
        raise _ende(str(fehler)) from fehler


def _benutzer(s: Session, name: str) -> Benutzer:
    from accounti.db.repo_auth import lade_benutzer

    b = lade_benutzer(s, name.strip().lower())
    if b is None:
        raise _ende(f"Benutzer {name!r} gibt es nicht (accounti benutzer liste)")
    return b


def _neues_passwort(name: str, config: str) -> str:
    from accounti.auth.cli import auth_einstellungen
    from accounti.auth.passwort import PasswortRegelError, pruefe_regeln

    mindestlaenge = auth_einstellungen(config).passwort_mindestlaenge
    passwort: str = typer.prompt(
        f"Passwort für {name} (mindestens {mindestlaenge} Zeichen)",
        hide_input=True,
        confirmation_prompt=True,
    )
    try:
        pruefe_regeln(passwort, name, mindestlaenge)
    except PasswortRegelError as fehler:
        raise _ende(str(fehler)) from fehler
    return passwort


@befehl.command("anlegen")
def anlegen(
    name: str = typer.Argument(help="Anmeldename, z.B. jan"),
    rolle: list[str] = ROLLE_OPTION,
    anzeigename: str | None = typer.Option(None, help="z.B. Jan Muster"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Benutzer mit Rollen in der aktiven Gesellschaft anlegen (Passwort verdeckt)."""
    from accounti.auth.cli import (
        auth_einstellungen,
        bindung_oder_ende,
        systemsitzung,
        verwaltung_oder_ende,
    )
    from accounti.auth.dienst import lege_benutzer_an
    from accounti.auth.passwort import PasswortRegelError
    from accounti.db.repo_auth import anzahl_benutzer
    from accounti.models.auth import Rolle, pruefe_name

    rollen = _rollen(rolle)
    gesellschaft = _gesellschaft()
    try:
        pruefe_name(name)
    except ValueError as fehler:
        raise _ende(str(fehler)) from fehler
    durch = verwaltung_oder_ende(db, config)
    bindung_oder_ende(db, alle=True)  # keine Gesellschaft gehört einer anderen
    with systemsitzung(db) as s:
        if anzahl_benutzer(s) == 0 and Rolle.VERWALTER not in rollen:
            raise _ende(
                "Der erste Benutzer braucht die Rolle verwalter — sonst kann "
                "niemand Benutzer verwalten"
            )
    passwort = _neues_passwort(name, config)
    with systemsitzung(db) as s:
        try:
            lege_benutzer_an(
                s,
                name,
                passwort,
                [(gesellschaft, r) for r in rollen],
                auth_einstellungen(config),
                anzeigename=anzeigename,
                durch=durch,
            )
        except (ValueError, PasswortRegelError) as fehler:
            raise _ende(str(fehler)) from fehler
        s.commit()
    bindung_oder_ende(db, alle=True, binden=True)
    console.print(
        f"[green]Benutzer {escape(name)} angelegt[/green] "
        f"({', '.join(r.value for r in rollen)} in {escape(gesellschaft)}). "
        f"Zweiter Faktor: accounti benutzer 2fa {escape(name)}",
        soft_wrap=True,
    )


@befehl.command("2fa")
def zweiter_faktor(
    name: str = typer.Argument(help="Benutzer"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Zweiten Faktor (TOTP-App) einrichten und Wiederherstellungscodes erzeugen."""
    from accounti.auth.cli import (
        auth_einstellungen,
        systemsitzung,
        verwaltung_oder_ende,
    )
    from accounti.auth.dienst import bestaetige_2fa
    from accounti.auth.fehler import AuthError
    from accounti.auth.totp import base32, neues_geheimnis, otpauth_uri
    from accounti.bank.tresor import TresorError, lade_schluessel

    ziel = name.strip().lower()
    verwaltung_oder_ende(db, config, selbst=ziel, ziel=ziel)
    einstellungen = auth_einstellungen(config)
    try:
        schluessel = lade_schluessel()
    except TresorError as fehler:
        raise _ende(str(fehler)) from fehler
    with systemsitzung(db) as s:
        b = _benutzer(s, name)
    geheimnis = neues_geheimnis()
    lesbar = base32(geheimnis)
    console.print(
        "In der Authenticator-App einen Schlüssel hinzufügen (QR-Code aus dieser "
        "Adresse oder den Schlüssel abtippen):",
        soft_wrap=True,
    )
    console.print(
        otpauth_uri(geheimnis, b.name, einstellungen.aussteller),
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
    console.print(
        " ".join(lesbar[i : i + 4] for i in range(0, len(lesbar), 4)),
        markup=False,
        highlight=False,
    )
    code: str = typer.prompt("Code aus der App")
    with systemsitzung(db) as s:
        try:
            codes = bestaetige_2fa(s, b, geheimnis, code, schluessel, einstellungen)
        except (AuthError, TresorError) as fehler:
            raise _ende(str(fehler)) from fehler
        s.commit()
    console.print(
        f"[green]Zweiter Faktor für {escape(b.name)} eingerichtet.[/green] "
        "Wiederherstellungscodes — jeder gilt genau einmal, jetzt sicher ablegen:",
        soft_wrap=True,
    )
    for c in codes:
        console.print(f"  {c}", markup=False, highlight=False)


@befehl.command("codes")
def codes(
    name: str = typer.Argument(help="Benutzer"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Neue Wiederherstellungscodes — die alten werden ungültig."""
    from accounti.auth.cli import (
        auth_einstellungen,
        systemsitzung,
        verwaltung_oder_ende,
    )
    from accounti.auth.dienst import neue_wiederherstellungscodes
    from accounti.bank.tresor import TresorError, lade_schluessel

    ziel = name.strip().lower()
    durch = verwaltung_oder_ende(db, config, selbst=ziel, ziel=ziel)
    try:
        schluessel = lade_schluessel()
    except TresorError as fehler:
        raise _ende(str(fehler)) from fehler
    with systemsitzung(db) as s:
        b = _benutzer(s, name)
        if not b.totp_aktiv:
            raise _ende(
                f"Erst den zweiten Faktor einrichten: accounti benutzer 2fa {name}"
            )
        neu = neue_wiederherstellungscodes(
            s, b, auth_einstellungen(config), schluessel=schluessel, durch=durch
        )
        s.commit()
    console.print("Neue Wiederherstellungscodes — jeder gilt genau einmal:")
    for c in neu:
        console.print(f"  {c}", markup=False, highlight=False)


@befehl.command("liste")
def liste(db: str = DB_OPTION, config: str = KONFIG_OPTION) -> None:
    """Benutzer mit Rollen je Gesellschaft, zweitem Faktor und Status."""
    from accounti.auth.cli import systemsitzung, verwaltung_oder_ende
    from accounti.db.repo_auth import lade_alle_benutzer, rollen_von

    verwaltung_oder_ende(db, config)
    jetzt = datetime.now()
    with systemsitzung(db) as s:
        alle = [(b, rollen_von(s, b.id)) for b in lade_alle_benutzer(s)]
    if not alle:
        console.print(
            "[dim]Keine Benutzer — accounti benutzer anlegen NAME --rolle "
            "verwalter[/dim]"
        )
        return
    tabelle = Table(title="Benutzer")
    for spalte in ("Name", "Rollen", "2FA", "Status", "Letzte Anmeldung"):
        tabelle.add_column(spalte, overflow="fold")
    for b, rollen in alle:
        status = "aktiv"
        if not b.aktiv:
            status = "[red]gesperrt[/red]"
        elif b.gesperrt(jetzt) and b.gesperrt_bis:
            status = f"[yellow]Browser gesperrt bis {b.gesperrt_bis:%d.%m.%Y %H:%M}"
            status += "[/yellow]"
        if b.aktiv and b.cli_gesperrt(jetzt) and b.cli_gesperrt_bis:
            status += f" [yellow]CLI gesperrt bis {b.cli_gesperrt_bis:%d.%m.%Y %H:%M}"
            status += "[/yellow]"
        tabelle.add_row(
            escape(b.name) + (f" ({escape(b.anzeigename)})" if b.anzeigename else ""),
            escape(", ".join(f"{z.gesellschaft}: {z.rolle.value}" for z in rollen))
            or "—",
            "✓" if b.totp_aktiv else "[yellow]fehlt[/yellow]",
            status,
            f"{b.letzte_anmeldung_am:%d.%m.%Y %H:%M}" if b.letzte_anmeldung_am else "—",
        )
    console.print(tabelle)


@befehl.command("rolle")
def rolle(
    name: str = typer.Argument(help="Benutzer"),
    rolle: list[str] = ROLLE_OPTION,
    entfernen: bool = typer.Option(False, "--entfernen", help="Rolle wegnehmen"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Rolle in der aktiven Gesellschaft geben oder nehmen (Sitzungen enden)."""
    from accounti.auth.cli import (
        bindung_oder_ende,
        systemsitzung,
        verwaltung_oder_ende,
    )
    from accounti.auth.dienst import entferne_rolle, fuege_rolle_hinzu
    from accounti.models.auth import Rolle

    rollen = _rollen(rolle)
    gesellschaft = _gesellschaft()
    durch = verwaltung_oder_ende(db, config, ziel=name.strip().lower())
    if not entfernen:
        bindung_oder_ende(db)
    with systemsitzung(db) as s:
        b = _benutzer(s, name)
        if entfernen and Rolle.VERWALTER in rollen:
            _nicht_letzter_verwalter(s, b, gesellschaft)
        for r in rollen:
            if entfernen:
                entferne_rolle(s, b, gesellschaft, r, None, durch)
            else:
                fuege_rolle_hinzu(s, b, gesellschaft, r, None, durch)
        s.commit()
    if not entfernen:
        bindung_oder_ende(db, binden=True)
    wort = "entfernt" if entfernen else "gegeben"
    console.print(
        f"[green]{', '.join(r.value for r in rollen)} in {escape(gesellschaft)} "
        f"{wort}[/green] — {escape(b.name)} meldet sich neu an.",
        soft_wrap=True,
    )


@befehl.command("passwort")
def passwort(
    name: str = typer.Argument(help="Benutzer"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Neues Passwort setzen (verdeckt) — alle Sitzungen des Benutzers enden."""
    from accounti.auth.cli import (
        auth_einstellungen,
        systemsitzung,
        verwaltung_oder_ende,
    )
    from accounti.auth.dienst import aendere_passwort
    from accounti.auth.passwort import PasswortRegelError

    ziel = name.strip().lower()
    durch = verwaltung_oder_ende(db, config, selbst=ziel, ziel=ziel)
    with systemsitzung(db) as s:
        b = _benutzer(s, name)
    neu = _neues_passwort(b.name, config)
    with systemsitzung(db) as s:
        try:
            aendere_passwort(s, b, neu, auth_einstellungen(config), None, durch)
        except PasswortRegelError as fehler:
            raise _ende(str(fehler)) from fehler
        s.commit()
    console.print(f"[green]Passwort für {escape(b.name)} geändert.[/green]")


@befehl.command("sperren")
def sperren(
    name: str = typer.Argument(help="Benutzer"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Benutzer sofort sperren (dauerhaft, bis entsperrt) — Sitzungen enden."""
    from accounti.auth.cli import systemsitzung, verwaltung_oder_ende
    from accounti.auth.dienst import setze_aktiv

    durch = verwaltung_oder_ende(db, config, ziel=name.strip().lower())
    with systemsitzung(db) as s:
        b = _benutzer(s, name)
        _nicht_letzter_verwalter(s, b)
        setze_aktiv(s, b, False, None, durch)
        s.commit()
    console.print(f"[green]{escape(b.name)} gesperrt.[/green]")


@befehl.command("entsperren")
def entsperren(
    name: str = typer.Argument(help="Benutzer"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Sperre aufheben — auch die nach zu vielen Fehlversuchen.

    Wer im Browser nach Fehlversuchen gesperrt ist, entsperrt sich auf der
    Server-Shell selbst (mit seinem Einmalcode; die CLI zählt getrennt vom Netz).
    Ein von einem Verwalter gesperrtes Konto (``benutzer sperren``) öffnet nur ein
    Verwalter wieder."""
    from accounti.auth.cli import systemsitzung, verwaltung_oder_ende
    from accounti.auth.dienst import entsperre, setze_aktiv

    ziel = name.strip().lower()
    durch = verwaltung_oder_ende(db, config, selbst=ziel, ziel=ziel)
    with systemsitzung(db) as s:
        b = _benutzer(s, name)
        if not b.aktiv:
            if durch == b.name:
                raise _ende(
                    f"{b.name} ist stillgelegt (benutzer sperren) — wieder aktivieren "
                    "kann nur ein Verwalter; nichts geändert"
                )
            b = setze_aktiv(s, b, True, None, durch)
        entsperre(s, b, None, durch)
        s.commit()
    console.print(f"[green]{escape(b.name)} entsperrt.[/green]")


@befehl.command("protokoll")
def protokoll(
    name: str | None = typer.Option(None, "--benutzer", help="nur dieser Benutzer"),
    anzahl: int = typer.Option(50, "--anzahl", help="die letzten so viele"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Anmeldungen, Fehlversuche, Sperren, Rollen- und Tokenänderungen — mit
    mehreren Gesellschaften die, in denen der Handelnde Verwalter ist, und die ohne
    Gesellschaft (Befund Betrieb B9)."""
    from accounti.auth.cli import systemsitzung, verwaltung_oder_ende
    from accounti.betrieb.kontext import aktueller_kontext
    from accounti.db.repo_auth import lade_benutzer, lade_ereignisse, rollen_von
    from accounti.models.auth import Rolle

    durch = verwaltung_oder_ende(db, config)
    kontext = aktueller_kontext()
    with systemsitzung(db) as s:
        sicht: set[str] | None = None
        b = lade_benutzer(s, durch)
        if kontext.registry.eintraege and b is not None:
            sicht = {
                z.gesellschaft
                for z in rollen_von(s, b.id)
                if z.rolle is Rolle.VERWALTER
            }
            if kontext.gesellschaft is not None:  # dort Verwalter oder Einrichtung
                sicht.add(kontext.gesellschaft.kuerzel)
        # die neuesten — absteigend mit LIMIT gelesen (Befund A-M5)
        ereignisse = lade_ereignisse(
            s, name, grenze=max(anzahl, 1), neueste=True, gesellschaften=sicht
        )
    tabelle = Table(title="Anmeldeprotokoll")
    for spalte in ("Zeitpunkt", "Ereignis", "Benutzer", "Ges.", "Quelle", "Hinweis"):
        tabelle.add_column(spalte, overflow="fold")
    for e in ereignisse:
        tabelle.add_row(
            f"{e.zeitpunkt:%d.%m.%Y %H:%M:%S}",
            e.art if e.ok else f"[red]{e.art}[/red]",
            escape(e.benutzer or "—"),
            escape(e.gesellschaft or ""),
            e.quelle,
            escape(e.hinweis or ""),
        )
    console.print(tabelle)
