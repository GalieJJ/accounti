"""`accounti kreditkarte …` — Kreditkarten als eigene Konten, Abrechnung, Abgleich.

Die Sammelbelastung auf dem Girokonto muss centgenau der Summe der Einzelumsätze
entsprechen; eine Abweichung ist ein Befund, kein Rundungsposten. `accounti bank
lauf` gleicht die Karten vor dem Kontieren selbst ab. Eine falsche vorläufige
Zuordnung löst `accounti kreditkarte loesen`; bei „mehrdeutig“ trennt
`accounti kreditkarte loesen <ABRECHNUNG> --belastung <UMSATZ>` einen Kandidaten ab.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Annotated

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from accounti.bank.kreditkarte import Kartenabgleich
    from accounti.models import Bankkonto
    from accounti.models.bank import Kreditkarte

NAME = "kreditkarte"
befehl = typer.Typer(
    help="Kreditkarten: eigenes Konto, PDF-Abrechnung, Abgleich der Sammelbelastung.",
    no_args_is_help=True,
)


def _ende(text: str) -> None:
    console.print(f"[red]{escape(text)}[/red]")
    raise typer.Exit(1)


def _datum(wert: str) -> date:
    for format in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(wert.strip(), format).date()
        except ValueError:
            continue
    _ende(f"Kein gültiges Datum: {wert} (TT.MM.JJJJ oder JJJJ-MM-TT)")
    raise AssertionError  # unerreichbar


def _sitzung(db: str) -> Session:
    from accounti.db import init_db, session_factory

    engine, make_session = session_factory(db)
    init_db(engine)
    return make_session()


def _konto(s: Session, karte: Kreditkarte) -> Bankkonto:
    from accounti.db.repository import lade_bankkonten

    return next(k for k in lade_bankkonten(s) if k.id == karte.bankkonto_id)


@befehl.command("einrichten")
def einrichten(
    girokonto: str = typer.Option(..., help="IBAN des Kontos mit der Sammelbelastung"),
    kennung: str | None = typer.Option(
        None, help="Kennung des neuen Kartenkontos, z.B. VISA1234 (keine Kartennummer)"
    ),
    bezeichnung: str | None = typer.Option(None, help="z.B. 'Visa Firmenkarte'"),
    sachkonto: str | None = typer.Option(
        None,
        help="eigenes Sachkonto der Karte, z.B. SKR03 1730 / SKR04 3610 "
        "„Kreditkartenabrechnung“ (mit der Steuerberatung abstimmen)",
    ),
    konto: str | None = typer.Option(
        None, help="vorhandenes Bankkonto als Karte nutzen (statt eines neuen)"
    ),
    provider: str = typer.Option(
        "abrechnung", help="abrechnung (PDF über die Belege) oder datei"
    ),
    feld: Annotated[
        list[str] | None,
        typer.Option(help="Einstellung des Providers, z.B. ordner=./karte"),
    ] = None,
    endziffern: str | None = typer.Option(
        None, help="letzte Ziffern der Kartennummer, stehen in der Sammelbelastung"
    ),
    muster: str | None = typer.Option(
        None, help="eigenes Muster (Regex), an dem die Sammelbelastung erkannt wird"
    ),
    abrechnungstag: int | None = typer.Option(
        None, min=1, max=31, help="Stichtag der Monatsabrechnung (Karten mit Abruf)"
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Kreditkarte als eigenes Konto mit eigenem Sachkonto einrichten."""
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.bank.kreditkarte import (
        PDF_PROVIDER,
        KreditkartenError,
        richte_karte_ein,
    )
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung

    einstellungen = dict(e.partition("=")[::2] for e in feld or [])
    try:
        geldtransit = lade_bank_einstellungen(config).kreditkarte.geldtransit(
            lade_buchhaltung(config).kontenrahmen
        )
    except KonfigurationError as fehler:
        _ende(str(fehler))
        return
    with _sitzung(db) as s:
        try:
            karte, karte_konto = richte_karte_ein(
                s,
                girokonto=girokonto,
                konto=konto,
                kennung=kennung,
                bezeichnung=bezeichnung,
                sachkonto=sachkonto,
                provider=provider,
                einstellungen=einstellungen,
                endziffern=endziffern,
                muster=muster,
                abrechnungstag=abrechnungstag,
            )
        except KreditkartenError as fehler:
            _ende(str(fehler))
            return
        s.commit()
    buchung = (
        f"Sammelbelastung direkt an {karte_konto.sachkonto}"
        if karte_konto.provider == PDF_PROVIDER
        else f"Sammelbelastung und Ausgleich über Geldtransit {geldtransit}"
    )
    console.print(
        f"[green]Eingerichtet:[/green] {escape(karte_konto.bezeichnung)} "
        f"{karte_konto.iban} ({karte_konto.provider}, Sachkonto "
        f"{karte_konto.sachkonto}) — Sammelbelastung von {girokonto}"
        + (f", Endziffern {karte.endziffern}" if karte.endziffern else "")
    )
    console.print(f"[dim]{escape(buchung)}[/dim]")
    if not endziffern and not muster:
        console.print(
            "[yellow]Ohne --endziffern erkennt accounti die Sammelbelastung nur am "
            "Text (Kreditkarte, Visa, Mastercard, Amex …) — Endziffern oder ein "
            "eigenes --muster machen den Abgleich sicherer.[/yellow]"
        )
    if karte_konto.provider == PDF_PROVIDER:
        console.print(
            "[dim]Nächster Schritt: accounti belege import <abrechnung.pdf>, dann "
            "accounti kreditkarte uebernehmen <BELEG>[/dim]"
        )


def _karte(s: Session, schluessel: str | None) -> Kreditkarte:
    from accounti.bank.kreditkarte import PDF_PROVIDER
    from accounti.db.repo_bank import lade_kreditkarte, lade_kreditkarten

    if schluessel is not None:
        try:
            return lade_kreditkarte(s, schluessel)
        except ValueError as fehler:
            _ende(str(fehler))
    pdf = [k for k in lade_kreditkarten(s) if _konto(s, k).provider == PDF_PROVIDER]
    if len(pdf) != 1:
        _ende(
            "Keine Kreditkarte mit PDF-Abrechnung eingerichtet"
            if not pdf
            else "Mehrere Karten — bitte --karte angeben"
        )
    return pdf[0]


@befehl.command("uebernehmen")
def uebernehmen(
    beleg: str = typer.Argument(
        help="ID (Anfang) der erfassten Kreditkartenabrechnung"
    ),
    karte: str | None = typer.Option(None, help="Kennung der Karte"),
    trotzdem: bool = typer.Option(
        False,
        "--trotzdem",
        help="auch wenn die Sammelbelastung schon anders gebucht ist",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """PDF-Abrechnung (erfasster Beleg) als Umsätze ans Kartenkonto übernehmen."""
    from accounti.anzeige import betrag_de, datum_de
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.bank.kreditkarte import KreditkartenError, uebernimm_abrechnung
    from accounti.konfiguration import KonfigurationError

    try:
        einst = lade_bank_einstellungen(config).kreditkarte
    except KonfigurationError as fehler:
        _ende(str(fehler))
        return
    with _sitzung(db) as s:
        k = _karte(s, karte)
        try:
            u = uebernimm_abrechnung(s, beleg, k, einst, trotzdem=trotzdem)
        except KreditkartenError as fehler:
            _ende(str(fehler))
            return
        s.commit()
    a = u.abrechnung
    console.print(
        f"[green]Übernommen:[/green] {a.anzahl} Umsätze ({u.neu} neu, {u.doppelt} "
        f"schon vorhanden), Summe {betrag_de(a.summe)} € zum {datum_de(a.stichtag)}"
        + (f"; {u.ausgleich} Ausgleichszeile(n) ausgelassen" if u.ausgleich else "")
    )
    for warnung in u.warnungen:
        console.print(f"[yellow]Achtung: {escape(warnung)}[/yellow]")
    console.print(
        "[dim]Nächster Schritt: accounti kreditkarte abgleich "
        "(oder accounti bank lauf)[/dim]"
    )


@befehl.command("abrechnen")
def abrechnen(
    karte: str = typer.Option(..., help="Kennung der Karte"),
    stichtag: str = typer.Option(..., help="Abrechnungsdatum (TT.MM.JJJJ)"),
    von: str | None = typer.Option(None, help="erster Tag (sonst nach der letzten)"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Abrechnung aus den abgerufenen Umsätzen einer Karte bilden."""
    from accounti.anzeige import betrag_de, datum_de
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.bank.kreditkarte import KreditkartenError, bilde_abrechnung
    from accounti.konfiguration import KonfigurationError

    tag = _datum(stichtag)
    beginn = _datum(von) if von else None
    try:
        einst = lade_bank_einstellungen(config).kreditkarte
    except KonfigurationError as fehler:
        _ende(str(fehler))
        return
    with _sitzung(db) as s:
        k = _karte(s, karte)
        try:
            a = bilde_abrechnung(s, k, tag, einst, von=beginn)
        except KreditkartenError as fehler:
            _ende(str(fehler))
            return
        s.commit()
    if a is None:
        console.print(f"Keine offenen Umsätze bis {datum_de(tag)}.")
        return
    console.print(
        f"[green]Abrechnung zum {datum_de(a.stichtag)}:[/green] {a.anzahl} Umsätze, "
        f"Summe {betrag_de(a.summe)} €"
    )


def zeige_kartenabgleich(ergebnis: Kartenabgleich, *, still: bool = False) -> None:
    """Ergebnis des Kartenabgleichs — auch für die Ausgabe von `bank lauf`."""
    from accounti.anzeige import betrag_de, datum_de

    def name(karte_id: UUID) -> str:
        return escape(ergebnis.namen.get(karte_id, ""))

    for u in ergebnis.uebernommen:
        console.print(
            f"Übernommen: Abrechnung zum {datum_de(u.abrechnung.stichtag)} "
            f"({u.abrechnung.anzahl} Umsätze)"
        )
    if ergebnis.nachgetragen:
        console.print(
            f"{ergebnis.nachgetragen} spät gelieferte(r) Kartenumsatz/-umsätze in "
            "offene Abrechnungen nachgetragen"
        )
    for a in ergebnis.abgeglichen:
        console.print(
            f"[green]abgeglichen[/green] {name(a.kreditkarte_id)}: "
            f"Abrechnung {datum_de(a.stichtag)} {betrag_de(a.summe)} € = Belastung"
        )
    for a in ergebnis.abweichungen:
        console.print(
            f"[red]Befund[/red] {name(a.kreditkarte_id)}: {escape(a.befund or '')} "
            f"[dim](vorläufig zur Prüfung; falsch zugeordnet: accounti kreditkarte "
            f"loesen {str(a.id)[:8]})[/dim]"
        )
    for tx in ergebnis.geloest:
        console.print(
            f"[yellow]Zuordnung gelöst[/yellow] {datum_de(tx.datum)} "
            f"{betrag_de(tx.betrag)} € {escape(tx.verwendungszweck)} — eine andere "
            "Belastung passt (besser); die vorläufige Buchung ist entfallen"
        )
    for tx in ergebnis.ohne_abrechnung:
        console.print(
            f"[yellow]ohne Abrechnung[/yellow] {datum_de(tx.datum)} "
            f"{betrag_de(tx.betrag)} € {escape(tx.verwendungszweck)} — Abrechnung "
            "übernehmen (accounti kreditkarte uebernehmen) oder Abrechnungstag "
            "einstellen"
        )
    for tx in ergebnis.mehrdeutig:
        bei = ergebnis.mehrdeutig_bei.get(tx.id, [])
        abrechnungen = ", ".join(
            f"{str(a.id)[:8]} ({name(a.kreditkarte_id)}, {datum_de(a.stichtag)})"
            for a in bei
        )
        grund = (
            f"konkurriert mit einer anderen Belastung um Abrechnung {abrechnungen}"
            if len(bei) == 1
            else f"passt zu mehreren Abrechnungen: {abrechnungen}"
        )
        abrechnung = str(bei[0].id)[:8] if len(bei) == 1 else "<ABRECHNUNG>"
        console.print(
            f"[yellow]mehrdeutig[/yellow] {datum_de(tx.datum)} "
            f"{betrag_de(tx.betrag)} € {escape(tx.verwendungszweck)} (Umsatz "
            f"{str(tx.id)[:8]}) — {grund}; nichts zugeordnet. Gehört sie nicht "
            f"dazu: accounti kreditkarte loesen {abrechnung} --belastung "
            f"{str(tx.id)[:8]}"
        )
    if ergebnis.ausgleich_gebucht:
        console.print(
            f"{ergebnis.ausgleich_gebucht} Ausgleichszeile(n) über Geldtransit gebucht"
        )
    for tx in ergebnis.ausgleich_vorlaeufig:
        console.print(
            f"[yellow]Ausgleich zur Prüfung[/yellow] {datum_de(tx.datum)} "
            f"{betrag_de(tx.betrag)} € {escape(tx.verwendungszweck)} — die gleich "
            "hohe Sammelbelastung ist nur vorläufig zugeordnet (Befund); bestätigt "
            "wird der Ausgleich zusammen mit ihr"
        )
    for tx in ergebnis.ausgleich_ohne_belastung:
        console.print(
            f"[yellow]Ausgleich zur Prüfung[/yellow] {datum_de(tx.datum)} "
            f"{betrag_de(tx.betrag)} € {escape(tx.verwendungszweck)} — keine gleich "
            "hohe Sammelbelastung dieser Karte über Geldtransit (anderes Konto, "
            "Einlage, abweichender Betrag?)"
        )
    for hinweis in ergebnis.hinweise:
        console.print(f"[yellow]{escape(hinweis)}[/yellow]")
    if not still and not any(
        [
            ergebnis.uebernommen,
            ergebnis.nachgetragen,
            ergebnis.abgeglichen,
            ergebnis.abweichungen,
            ergebnis.geloest,
            ergebnis.ohne_abrechnung,
            ergebnis.mehrdeutig,
            ergebnis.ausgleich_gebucht,
            ergebnis.ausgleich_ohne_belastung,
            ergebnis.ausgleich_vorlaeufig,
            ergebnis.hinweise,
        ]
    ):
        console.print("[dim]Nichts Neues.[/dim]")


@befehl.command("abgleich")
def abgleich(db: str = DB_OPTION, config: str = KONFIG_OPTION) -> None:
    """Sammelbelastungen gegen die Abrechnungen prüfen und buchen."""
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.bank.kreditkarte import gleiche_sammelbelastungen_ab
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung

    try:
        buchhaltung = lade_buchhaltung(config)
        einst = lade_bank_einstellungen(config).kreditkarte
    except KonfigurationError as fehler:
        _ende(str(fehler))
        return
    from accounti.befehle import laufsperre_oder_ende

    with laufsperre_oder_ende(db), _sitzung(db) as s:
        ergebnis = gleiche_sammelbelastungen_ab(s, buchhaltung, einst)
        s.commit()
    zeige_kartenabgleich(ergebnis)


@befehl.command("loesen")
def loesen(
    abrechnung: str = typer.Argument(help="ID (Anfang) der Abrechnung, siehe liste"),
    belastung: str | None = typer.Option(
        None,
        help="ID (Anfang) eines Umsatzes, der nicht die Sammelbelastung dieser "
        "Abrechnung ist — bei „mehrdeutig“ (die ID steht in der Meldung)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Falsche Zuordnung lösen (Buchung entfällt, kein neuer Vorschlag) — mit
    --belastung auch einen Kandidaten, der noch gar nicht zugeordnet ist."""
    from accounti.anzeige import betrag_de, datum_de
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.bank.kreditkarte import (
        KreditkartenError,
        loese_zuordnung,
        trenne_belastung,
    )
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung

    try:
        buchhaltung = lade_buchhaltung(config)
        einst = lade_bank_einstellungen(config).kreditkarte
    except KonfigurationError as fehler:
        _ende(str(fehler))
        return
    with _sitzung(db) as s:
        try:
            if belastung is None:
                a, tx = loese_zuordnung(s, abrechnung, buchhaltung, einst)
                war_zugeordnet = True
            else:
                a, tx, war_zugeordnet = trenne_belastung(
                    s, abrechnung, belastung, buchhaltung, einst
                )
        except KreditkartenError as fehler:
            _ende(str(fehler))
            return
        s.commit()
    if war_zugeordnet:
        console.print(
            f"[green]Zuordnung gelöst:[/green] Abrechnung zum {datum_de(a.stichtag)} "
            f"und Belastung {betrag_de(tx.betrag)} € vom {datum_de(tx.datum)} — die "
            "Abrechnung ist wieder offen, die Belastung kontiert accounti classify"
        )
    else:
        console.print(
            f"[green]Getrennt:[/green] Belastung {betrag_de(tx.betrag)} € vom "
            f"{datum_de(tx.datum)} gehört nicht zur Abrechnung zum "
            f"{datum_de(a.stichtag)} — accounti schlägt das Paar nicht wieder vor"
        )
    console.print(
        "[dim]Nächster Schritt: accounti kreditkarte abgleich "
        "(oder accounti bank lauf)[/dim]"
    )


@befehl.command("liste")
def liste(db: str = DB_OPTION) -> None:
    """Karten und ihre Abrechnungen mit Status und Befund."""
    from rich.table import Table

    from accounti.anzeige import betrag_de, datum_de
    from accounti.bank.kreditkarte import PDF_PROVIDER
    from accounti.db.repo_bank import lade_abrechnungen, lade_kreditkarten
    from accounti.db.repository import lade_bankkonten

    with _sitzung(db) as s:
        karten = lade_kreditkarten(s)
        konten = {k.id: k for k in lade_bankkonten(s)}
        abrechnungen = lade_abrechnungen(s)
    if not karten:
        console.print(
            "[dim]Keine Kreditkarten — accounti kreditkarte einrichten …[/dim]"
        )
        return
    tabelle = Table(title="Kreditkarten")
    for spalte in ("Kennung", "Bezeichnung", "Sachkonto", "Girokonto", "Quelle"):
        tabelle.add_column(spalte, overflow="fold")
    for k in karten:
        konto, giro = konten[k.bankkonto_id], konten[k.girokonto_id]
        quelle = "PDF" if konto.provider == PDF_PROVIDER else konto.provider
        tabelle.add_row(
            konto.iban, escape(konto.bezeichnung), konto.sachkonto, giro.iban, quelle
        )
    console.print(tabelle)
    if not abrechnungen:
        return
    kennung = {k.id: konten[k.bankkonto_id].iban for k in karten}
    farbe = {"abgeglichen": "green", "abweichung": "red"}
    console.print("[bold]Abrechnungen[/bold]")
    for a in abrechnungen:
        f = farbe.get(a.status.value, "yellow")
        belastung = (
            f"Belastung {betrag_de(a.belastung_betrag)} €"
            if a.belastung_betrag is not None
            else "Belastung noch nicht gefunden"
        )
        console.print(
            f"  {str(a.id)[:8]} {kennung.get(a.kreditkarte_id, '?')} · "
            f"{datum_de(a.stichtag)} · "
            f"{a.anzahl} Umsätze · Summe {betrag_de(a.summe)} € · {belastung} · "
            f"[{f}]{a.status.value}[/{f}]"
        )
        if a.befund:
            console.print(f"    [{f}]{escape(a.befund)}[/{f}]")
