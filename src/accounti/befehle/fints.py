"""`accounti fints …` — FinTS-Zugänge einrichten und Freigaben der Bank erteilen.

Abgerufen wird wie bei jedem Provider mit `accounti bank abrufen` bzw. `bank lauf`
— ohne Rückfrage. Verlangt die Bank eine Freigabe, steht das Konto danach auf
``freigabe_noetig``; `accounti fints freigeben` fragt dann nach der TAN oder
wartet auf die Bestätigung in der App und holt die Umsätze. Lehnt die Bank die
Anmeldung ab, steht es auf ``zugang_abgelehnt``; `accounti fints zugang` nimmt die
neue PIN. Bis dahin ruft der Cron beide Konten nicht ab.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

NAME = "fints"
befehl = typer.Typer(
    help="FinTS-Bankzugänge einrichten (Produkt-ID, PIN, TAN) und freigeben.",
    no_args_is_help=True,
)

if TYPE_CHECKING:  # Importe zur Laufzeit erst im Befehl — schneller Start
    from sqlalchemy.orm import Session

    from accounti.bank.fints import TanVerfahren
    from accounti.bank.lauf import KontoAbruf
    from accounti.bank.provider import Freigabeanfrage
    from accounti.models import Bankkonto


def _ende(text: str) -> None:
    console.print(f"[red]{escape(text)}[/red]")
    raise typer.Exit(1)


def konsolen_freigabe(anfrage: Freigabeanfrage) -> str | None:
    """Rückfrage auf der Konsole: TAN eintippen oder in der App bestätigen."""
    console.print(
        f"[bold]{escape(anfrage.konto.bezeichnung)}[/bold] {anfrage.konto.iban}: "
        "Die Bank verlangt eine Freigabe."
    )
    if anfrage.text:
        console.print(f"  {escape(anfrage.text)}")
    if anfrage.hinweis:
        console.print(f"  [yellow]{escape(anfrage.hinweis)}[/yellow]")
    if anfrage.app:
        console.print(
            "  Bitte in der App bestätigen — accounti fragt die Bank in Abständen, "
            "ob die Freigabe da ist …"
        )
        return ""
    tan = str(typer.prompt("TAN (leer = abbrechen)", default="", show_default=False))
    return tan.strip() or None


def _waehle_verfahren(verfahren: list[TanVerfahren]) -> str:
    console.print("Die Bank bietet diese TAN-Verfahren an:")
    for nr, v in enumerate(verfahren, start=1):
        console.print(f"  {nr}  {escape(v.name)} ({v.kennung})")
    while True:
        nr = int(typer.prompt("TAN-Verfahren (Nummer)", type=int))
        if 1 <= nr <= len(verfahren):
            return verfahren[nr - 1].kennung
        console.print("[yellow]Bitte eine der Nummern wählen.[/yellow]")


def _waehle_medium(medien: list[str]) -> str:
    console.print("TAN-Medien (z.B. Geräte für die App oder SMS):")
    for nr, m in enumerate(medien, start=1):
        console.print(f"  {nr}  {escape(m)}")
    while True:
        nr = int(typer.prompt("TAN-Medium (Nummer)", type=int))
        if 1 <= nr <= len(medien):
            return medien[nr - 1]
        console.print("[yellow]Bitte eine der Nummern wählen.[/yellow]")


@befehl.command("einrichten")
def einrichten(
    iban: str = typer.Option(..., help="IBAN des Kontos"),
    bezeichnung: str = typer.Option(..., help="z.B. 'Giro Sparkasse'"),
    blz: str = typer.Option(..., help="Bankleitzahl"),
    server: str = typer.Option(..., help="FinTS-Adresse der Bank (PIN/TAN, https)"),
    sachkonto: str = typer.Option("1200", help="Finanzkonto im Kontenrahmen"),
    kunden_id: str | None = typer.Option(
        None, help="Kunden-ID, falls die Bank eine eigene verlangt"
    ),
    produkt_id: str | None = typer.Option(
        None,
        help="Produkt-ID am Konto speichern — sonst ACCOUNTI_FINTS_PRODUKT_ID "
        "oder bank.fints.produkt_id",
    ),
    format: str = typer.Option("auto", help="auto (camt bevorzugt), camt oder mt940"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Zugang einrichten: PIN, TAN-Verfahren, erste Freigabe — danach ohne Eingabe."""
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.bank.fints import FORMATE, KUNDEN_ID, pruefe_server, richte_fints_ein
    from accounti.bank.provider import FreigabeNoetigError, ProviderError
    from accounti.bank.tresor import TresorError, lade_schluessel, verschluessele
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_bankkonten, speichere_bankkonto
    from accounti.konfiguration import KonfigurationError
    from accounti.models import Bankkonto

    if format not in FORMATE:
        _ende(f"Unbekanntes Format '{format}' (erlaubt: {', '.join(FORMATE)})")
    try:
        pruefe_server(server)
        schluessel = lade_schluessel()
        einstellungen = lade_bank_einstellungen(config).fints
    except (ProviderError, TresorError, KonfigurationError) as fehler:
        _ende(str(fehler))
        return
    werte = {"blz": blz.strip(), "server": server.strip(), "format": format}
    if produkt_id:
        werte["produkt_id"] = produkt_id.strip()
    konto = Bankkonto(
        iban=re.sub(r"\s", "", iban).upper(),
        bezeichnung=bezeichnung,
        sachkonto=sachkonto,
        provider="fints",
        einstellungen=werte,
    )
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        if any(k.iban == konto.iban for k in lade_bankkonten(s)):
            _ende(
                f"Konto {konto.iban} ist schon eingerichtet — neue PIN oder "
                f"Benutzerkennung: accounti fints zugang --konto {konto.iban}"
            )
    zugang = {
        "benutzerkennung": str(typer.prompt("Benutzerkennung (Anmeldename)")),
        "pin": str(typer.prompt("PIN", hide_input=True)),
    }
    if kunden_id:  # oft gleich der Benutzerkennung — gehört in den Tresor
        zugang[KUNDEN_ID] = kunden_id.strip()
    try:
        konto, zugang = richte_fints_ein(
            konto,
            zugang,
            waehle_verfahren=_waehle_verfahren,
            waehle_medium=_waehle_medium,
            freigabe=konsolen_freigabe,
            einstellungen=einstellungen,
        )
    except (ProviderError, FreigabeNoetigError) as fehler:
        _ende(f"Nicht eingerichtet: {fehler}")
        return
    konto = konto.model_copy(
        update={"zugang": verschluessele(zugang, schluessel, str(konto.id))}
    )
    with make_session() as s:
        speichere_bankkonto(s, konto)
        s.commit()
    console.print(
        f"[green]Eingerichtet:[/green] {escape(konto.bezeichnung)} {konto.iban} "
        f"(fints, Sachkonto {konto.sachkonto}, TAN-Verfahren "
        f"{escape(konto.einstellungen.get('tan_verfahren', '—'))}) — Zugang und "
        "Sitzung verschlüsselt gespeichert"
    )
    console.print("[dim]Nächster Schritt: accounti bank abrufen (auch per Cron)[/dim]")


def _ausgabe(abrufe: list[KontoAbruf]) -> None:
    for a in abrufe:
        farbe = {"bereit": "green", "freigabe_noetig": "yellow"}.get(
            a.zustand.value, "red"
        )
        text = f"{a.neu} neu, {a.doppelt} schon vorhanden"
        if a.meldung:
            text = f"{a.zustand.value}: {a.meldung}"
        console.print(
            f"[{farbe}]{escape(a.konto.bezeichnung)}[/{farbe}] {a.konto.iban} — "
            f"{escape(text)}"
        )


@befehl.command("freigeben")
def freigeben(
    konto: str | None = typer.Option(None, help="Nur dieses Konto (IBAN)"),
    db: str = DB_OPTION,
) -> None:
    """Freigabe der Bank erteilen (TAN oder App) und Umsätze abrufen."""
    from accounti.bank.lauf import rufe_ab
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_bankkonten, lade_bankkonto
    from accounti.models import KontoZustand

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        if konto is not None:
            try:
                konten = [lade_bankkonto(s, konto)]
            except ValueError as fehler:
                _ende(str(fehler))
                return
        else:
            konten = [k for k in lade_bankkonten(s) if k.provider == "fints"]
            if not konten:
                console.print(
                    "[dim]Keine FinTS-Konten — accounti fints einrichten …[/dim]"
                )
                return
            abgelehnt = [
                k for k in konten if k.zustand is KontoZustand.ZUGANG_ABGELEHNT
            ]
            for k in abgelehnt:  # jeder Versuch mit der alten PIN kann sperren
                console.print(
                    f"[red]{escape(k.bezeichnung)}[/red] {k.iban} — Zugang abgelehnt, "
                    f"nicht versucht: accounti fints zugang --konto {k.iban}"
                )
            konten = [k for k in konten if k not in abgelehnt]
        abrufe = rufe_ab(s, konten=konten, freigabe=konsolen_freigabe) if konten else []
        s.commit()
    _ausgabe(abrufe)


def _fints_konto(s: Session, schluessel: str) -> Bankkonto:
    from accounti.db.repository import lade_bankkonto

    try:
        konto = lade_bankkonto(s, schluessel)
    except ValueError as fehler:
        _ende(str(fehler))
        raise AssertionError from fehler  # unerreichbar
    if konto.provider != "fints":
        _ende(f"Konto {konto.iban} ruft nicht über FinTS ab ({konto.provider})")
    return konto


@befehl.command("zugang")
def zugang(
    konto: str = typer.Option(..., help="IBAN des FinTS-Kontos"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Zugang erneuern (neue PIN, entsperrt): PIN, TAN-Verfahren, erste Freigabe."""
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.bank.fints import ABRUFFORMAT, FORMAT_AB, KUNDEN_ID, richte_fints_ein
    from accounti.bank.provider import FreigabeNoetigError, ProviderError
    from accounti.bank.tresor import (
        TresorError,
        entschluessele,
        lade_schluessel,
        verschluessele,
    )
    from accounti.db import init_db, session_factory
    from accounti.db.repository import aktualisiere_bankkonto
    from accounti.konfiguration import KonfigurationError
    from accounti.models import KontoZustand

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        bankkonto = _fints_konto(s, konto)
    try:
        schluessel = lade_schluessel()
        einstellungen = lade_bank_einstellungen(config).fints
        alt = (
            entschluessele(bankkonto.zugang, schluessel, str(bankkonto.id))
            if bankkonto.zugang
            else {}
        )
    except (TresorError, KonfigurationError) as fehler:
        _ende(str(fehler))
        return
    kennung = str(
        typer.prompt(
            "Benutzerkennung (leer = unverändert)", default="", show_default=False
        )
    ).strip()
    neu = {
        # Format und Kundennummer bleiben — sonst wechselte der Abruf das Format
        **{n: alt[n] for n in (ABRUFFORMAT, FORMAT_AB, KUNDEN_ID) if alt.get(n)},
        "benutzerkennung": kennung or alt.get("benutzerkennung", ""),
        "pin": str(typer.prompt("PIN", hide_input=True)),
    }
    try:
        bankkonto_neu, neu = richte_fints_ein(
            bankkonto,
            neu,
            waehle_verfahren=_waehle_verfahren,
            waehle_medium=_waehle_medium,
            freigabe=konsolen_freigabe,
            einstellungen=einstellungen,
        )
    except (ProviderError, FreigabeNoetigError) as fehler:
        _ende(f"Zugang nicht erneuert: {fehler}")
        return
    bankkonto_neu = bankkonto_neu.model_copy(
        update={
            "zugang": verschluessele(neu, schluessel, str(bankkonto.id)),
            "zustand": KontoZustand.BEREIT,
            "meldung": None,
        }
    )
    with make_session() as s:
        aktualisiere_bankkonto(s, bankkonto_neu)
        s.commit()
    console.print(
        f"[green]Zugang erneuert:[/green] {escape(bankkonto.bezeichnung)} "
        f"{bankkonto.iban} — der nächste Abruf läuft wieder ohne Eingabe"
    )


@befehl.command("format")
def format_befehl(
    format: str = typer.Argument(help="camt, mt940 oder auto"),
    konto: str = typer.Option(..., help="IBAN des FinTS-Kontos"),
    db: str = DB_OPTION,
) -> None:
    """Format der Umsätze ausdrücklich wechseln (sonst bleibt es fest)."""
    from accounti.anzeige import datum_de
    from accounti.bank.fints import FORMATE
    from accounti.db import init_db, session_factory
    from accounti.db.repository import aktualisiere_bankkonto

    if format not in FORMATE:
        _ende(f"Unbekanntes Format '{format}' (erlaubt: {', '.join(FORMATE)})")
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        bankkonto = _fints_konto(s, konto)
        einstellungen = {**bankkonto.einstellungen, "format": format}
        aktualisiere_bankkonto(
            s, bankkonto.model_copy(update={"einstellungen": einstellungen})
        )
        s.commit()
    stand = bankkonto.abrufstand
    console.print(
        f"[green]Format {format}[/green] für {escape(bankkonto.bezeichnung)} "
        f"{bankkonto.iban}"
        + (
            f" — nach einem Wechsel ohne Überlappung: Umsätze bis {datum_de(stand)} "
            "(Abrufstand) kommen nicht noch einmal"
            if stand
            else ""
        )
    )
