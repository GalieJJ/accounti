"""``accounti abschluss …`` — Jahresabschluss (Baustein 12)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

# Jahressperre: das ORM-Ereignis auf ``buchungssaetze`` hängt am Import dieses Moduls.
# Die CLI lädt jede Befehlsgruppe beim Start — so greift die Sperre auch in Befehlen,
# die ``init_db`` nicht aufrufen (``bestaetige``, ``korrigiere``, ``classify`` …).
import accounti.db.tabellen_abschluss  # noqa: F401
from accounti.befehle import DB_OPTION, KONFIG_OPTION, console, handelnde_person
from accounti.befehle._anlagen_abschluss import betrag, datum, ende, lade, sitzung

NAME = "abschluss"
befehl = typer.Typer(
    help="Jahresabschluss: Prüfungen, Salden, Abgrenzungen, EÜR, Saldovortrag."
)

CSV_OPTION = typer.Option("--csv", help="zusätzlich als CSV")


def _einstellungen(config: str):  # type: ignore[no-untyped-def]
    from accounti.abschluss.konfiguration import lade_abschluss

    return lade(lade_abschluss, config)


@befehl.command("saldo")
def saldo(
    konto: str = typer.Option(..., "--konto", help="IBAN des eingerichteten Kontos"),
    stichtag: str = typer.Option(..., "--stichtag", help="z.B. 2026-12-31"),
    saldo_text: str = typer.Option(..., "--saldo", help="Saldo laut Kontoauszug"),
    von: str | None = typer.Option(None, help="Wer erfasst"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,  # noqa: ARG001
) -> None:
    """Saldo laut Kontoauszug zum Stichtag erfassen (für die Bank-Abstimmung)."""
    from accounti.abschluss.pruefungen import erfasse_kontoauszugssaldo
    from accounti.anzeige import betrag_de

    tag = datum(stichtag, "--stichtag")
    wert = betrag(saldo_text, "--saldo")
    with sitzung(db)() as s:
        try:
            erfasse_kontoauszugssaldo(s, konto, tag, wert, von)
        except ValueError as fehler:
            ende(str(fehler))
        s.commit()
    console.print(
        f"[green]Erfasst:[/green] {escape(konto)} Saldo {betrag_de(wert)} € zum "
        f"{tag:%d.%m.%Y}"
    )


def _befunde_ausgeben(befunde: list) -> None:  # type: ignore[type-arg]
    from accounti.abschluss.pruefungen import Schwere

    farben = {Schwere.FEHLER: "red", Schwere.WARNUNG: "yellow", Schwere.HINWEIS: "dim"}
    for b in befunde:
        f = farben[b.schwere]
        console.print(
            f"[{f}]{b.schwere.value.upper()}[/{f}] {b.pruefung}: {escape(b.text)}"
        )


@befehl.command("pruefen")
def pruefen(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Abschlussprüfungen — Fehler blockieren den Saldovortrag."""
    from accounti.abschluss.pruefungen import blockiert, kontext, pruefe_abschluss

    with sitzung(db)() as s:
        try:
            befunde = pruefe_abschluss(kontext(s, jahr, config))
        except ValueError as fehler:
            ende(str(fehler))
    _befunde_ausgeben(befunde)
    if blockiert(befunde):
        console.print(f"[red]Abschluss {jahr} gesperrt — Fehler beheben.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Abschluss {jahr}: keine Fehler.[/green]")


@befehl.command("susa")
def susa(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    bis: str | None = typer.Option(None, help="Stichtag (31.12.)"),
    csv: Annotated[Path | None, CSV_OPTION] = None,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Summen- und Saldenliste (nur freigegebene Buchungen)."""
    from accounti.abschluss.ausgabe import susa_csv
    from accounti.abschluss.salden import summen_und_salden
    from accounti.anzeige import betrag_de

    einst = _einstellungen(config)
    with sitzung(db)() as s:
        liste = summen_und_salden(
            s,
            jahr,
            einst.lade_kontenrahmen(),
            einst.gewinnermittlung,
            datum(bis, "--bis") if bis else None,
        )
    t = Table(title=f"Summen- und Saldenliste {jahr} (bis {liste.bis:%d.%m.%Y})")
    t.add_column("Konto")
    t.add_column("Bezeichnung", overflow="fold")
    for spalte in ("EB", "Soll", "Haben", "Saldo"):
        t.add_column(spalte, justify="right", no_wrap=True)
    for z in liste.zeilen:
        t.add_row(
            z.konto,
            escape(z.bezeichnung),
            betrag_de(z.eb),
            betrag_de(z.soll),
            betrag_de(z.haben),
            betrag_de(z.saldo),
        )
    t.add_row(
        "", "Summe", "", betrag_de(liste.summe_soll), betrag_de(liste.summe_haben), ""
    )
    console.print(t)
    console.print(f"Ergebnis (Erfolgskonten): {betrag_de(liste.ergebnis)} €")
    if csv is not None:
        csv.write_text(susa_csv(liste), encoding="utf-8")
        console.print(f"[green]CSV:[/green] {csv}")


def _buchung_zeigen(b) -> None:  # type: ignore[no-untyped-def]
    from accounti.anzeige import betrag_de

    console.print(
        f"[yellow]{str(b.id)[:8]}[/yellow] {b.datum:%d.%m.%Y} {b.soll_konto} an "
        f"{b.haben_konto} {betrag_de(b.betrag_netto)} — {escape(b.buchungstext)}"
    )


def _abgrenzung_zeigen(a) -> None:  # type: ignore[no-untyped-def]
    from accounti.anzeige import betrag_de

    console.print(
        f"[yellow]Nr. {a.nr}[/yellow] {a.art.value.upper()} {a.konto} → "
        f"{a.rap_konto} {betrag_de(a.betrag)} € [dim]({escape(a.rechenweg)})[/dim]"
    )


@befehl.command("eroeffnung")
def eroeffnung(
    jahr: int = typer.Option(..., help="erstes Geschäftsjahr in accounti"),
    konto: str = typer.Option(..., "--konto", help="Bestandskonto, z.B. 1200"),
    saldo_text: str = typer.Option(
        ..., "--saldo", help="Eröffnungssaldo — Soll positiv, Haben negativ"
    ),
    von: str = typer.Option("supervisor", help="Wer erfasst"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Eröffnungssaldo eines Bestandskontos (nur im ersten Jahr; sonst Vortrag)."""
    from accounti.abschluss.vortrag import AbschlussError, erfasse_eroeffnung
    from accounti.anzeige import betrag_de
    from accounti.db.tabellen_abschluss import JahrGesperrtError

    einst = _einstellungen(config)
    wert = betrag(saldo_text, "--saldo")
    with sitzung(db)() as s:
        try:
            b = erfasse_eroeffnung(s, jahr, konto, wert, von, einst)
        except (AbschlussError, JahrGesperrtError) as fehler:
            ende(str(fehler))
        s.commit()
    if b is None:
        console.print(f"Eröffnungssaldo {konto} {jahr}: unverändert")
        return
    console.print(f"[green]Eröffnungssaldo {konto} {jahr}:[/green] {betrag_de(wert)} €")
    _buchung_zeigen(b)


@befehl.command("buchen")
def buchen(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Abschlussbuchungen als Vorschläge: AfA des Jahres und Abgrenzungen."""
    from accounti.abschluss.abgrenzung import schlage_abgrenzungen_vor
    from accounti.anlagen.konfiguration import lade_anlagen
    from accounti.anlagen.lauf import afa_lauf
    from accounti.anzeige import betrag_de
    from accounti.db.tabellen_abschluss import JahrGesperrtError

    einst = _einstellungen(config)
    anlagen = lade(lade_anlagen, config)
    with sitzung(db)() as s:
        try:
            afa = afa_lauf(s, jahr, anlagen, 12)
            lauf = schlage_abgrenzungen_vor(s, jahr, einst, anlagen.rechtsstand())
        except (ValueError, JahrGesperrtError) as fehler:
            ende(str(fehler))
        s.commit()
    if afa.buchungen:
        console.print(f"[bold]AfA {jahr}[/bold] (zur Prüfung)")
        for p in afa.positionen:
            console.print(
                f"  {escape(p.bezeichnung)}: {betrag_de(p.differenz)} "
                f"[dim]({escape(p.rechenweg)})[/dim]"
            )
        for b in afa.buchungen:
            _buchung_zeigen(b)
        console.print(f"freigeben: accounti anlagen freigeben --jahr {jahr}")
    else:
        console.print(f"AfA {jahr}: nichts zu buchen")
    if lauf.vorschlaege:
        console.print(f"[bold]Abgrenzungen {jahr}[/bold] (Vorschläge, nichts gebucht)")
        for a in lauf.vorschlaege:
            _abgrenzung_zeigen(a)
        console.print("entscheiden: accounti abschluss bestaetigen|ablehnen <Nr>")
    else:
        console.print(f"Abgrenzungen {jahr}: keine neuen Vorschläge")
    for hinweis in lauf.hinweise:
        console.print(f"[dim]{escape(hinweis)}[/dim]")


@befehl.command("abgrenzungen")
def abgrenzungen(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,  # noqa: ARG001
) -> None:
    """Abgrenzungsvorschläge des Jahres mit Status und Rechenweg."""
    from accounti.anzeige import betrag_de
    from accounti.db.repo_abschluss import lade_abgrenzungen

    with sitzung(db)() as s:
        liste = lade_abgrenzungen(s, jahr)
    t = Table(title=f"Rechnungsabgrenzungen {jahr}")
    for spalte in ("Nr", "Art", "Konto", "RAP", "Betrag", "Zeitraum", "Status"):
        t.add_column(spalte, no_wrap=spalte != "Zeitraum")
    t.add_column("Rechenweg", overflow="fold")
    for a in liste:
        t.add_row(
            str(a.nr),
            a.art.value.upper(),
            a.konto,
            a.rap_konto,
            betrag_de(a.betrag),
            f"{a.von:%d.%m.%Y}–{a.bis:%d.%m.%Y}",
            a.status.value,
            escape(a.rechenweg),
        )
    console.print(t)


@befehl.command("abgrenzen")
def abgrenzen(
    buchung: str = typer.Argument(help="Buchungs-ID (Anfang genügt)"),
    von_text: str = typer.Option(..., "--von", help="Leistungszeitraum ab"),
    bis_text: str = typer.Option(..., "--bis", help="Leistungszeitraum bis"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Abgrenzung für eine Buchung vorschlagen, deren Zeitraum nicht im Text steht."""
    from accounti.abschluss.abgrenzung import AbgrenzungError, grenze_ab
    from accounti.db.tabellen_abschluss import JahrGesperrtError

    einst = _einstellungen(config)
    von, bis = datum(von_text, "--von"), datum(bis_text, "--bis")
    with sitzung(db)() as s:
        try:
            a = grenze_ab(s, buchung, von, bis, einst)
        except (AbgrenzungError, JahrGesperrtError) as fehler:
            ende(str(fehler))
        s.commit()
    _abgrenzung_zeigen(a)
    console.print("entscheiden: accounti abschluss bestaetigen|ablehnen <Nr>")


@befehl.command("bestaetigen")
def bestaetigen(
    nr: str = typer.Argument(help="Nummer der Abgrenzung"),
    von: str = typer.Option("supervisor", help="Wer entscheidet"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,  # noqa: ARG001
) -> None:
    """Abgrenzung bestätigen: bucht Abgrenzung (31.12.) und Auflösung(en) (01.01.)."""
    from accounti.abschluss.abgrenzung import AbgrenzungError, bestaetige_abgrenzung
    from accounti.db.repository import lade_buchungen
    from accounti.db.tabellen_abschluss import JahrGesperrtError

    with sitzung(db)() as s:
        try:
            a = bestaetige_abgrenzung(s, nr, von)
        except (AbgrenzungError, JahrGesperrtError) as fehler:
            ende(str(fehler))
        s.commit()
        beleg = f"RAP-{a.jahr}-{a.nr}"
        gebucht = sorted(
            (b for b in lade_buchungen(s) if b.beleg_nummer == beleg),
            key=lambda b: b.datum,
        )
    console.print(f"[green]Abgrenzung Nr. {a.nr} bestätigt[/green]")
    for b in gebucht:
        _buchung_zeigen(b)


@befehl.command("ablehnen")
def ablehnen(
    nr: str = typer.Argument(help="Nummer der Abgrenzung"),
    von: str = typer.Option("supervisor", help="Wer entscheidet"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,  # noqa: ARG001
) -> None:
    """Abgrenzung ablehnen — nichts wird gebucht, der Vorschlag kommt nicht wieder."""
    from accounti.abschluss.abgrenzung import AbgrenzungError, lehne_abgrenzung_ab

    with sitzung(db)() as s:
        try:
            a = lehne_abgrenzung_ab(s, nr, von)
        except AbgrenzungError as fehler:
            ende(str(fehler))
        s.commit()
    console.print(f"Abgrenzung Nr. {a.nr} abgelehnt")


@befehl.command("euer")
def euer(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    csv: Annotated[Path | None, CSV_OPTION] = None,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Einnahmenüberschussrechnung nach Zeilen und Kennzahlen der Anlage EÜR."""
    from accounti.abschluss.euer import EuerError, erstelle_euer, euer_csv
    from accounti.abschluss.salden import summen_und_salden
    from accounti.anzeige import betrag_de

    einst = _einstellungen(config)
    kr = einst.lade_kontenrahmen()
    with sitzung(db)() as s:
        liste = summen_und_salden(s, jahr, kr, einst.gewinnermittlung)
    try:
        e = erstelle_euer(liste, kr)
    except EuerError as fehler:
        ende(str(fehler))
    t = Table(title=f"Einnahmenüberschussrechnung {jahr} (Vordruck {e.vordruck_jahr})")
    t.add_column("Zeile", justify="right")
    t.add_column("Kz")
    t.add_column("Bezeichnung", overflow="fold")
    t.add_column("Betrag", justify="right", no_wrap=True)
    t.add_column("Konten", overflow="fold")

    def zeile(z, text: str | None = None) -> None:  # type: ignore[no-untyped-def]
        konten = ", ".join(sorted(z.konten))
        t.add_row(
            str(z.zeile or ""),
            z.kz or "",
            escape(text or z.text),
            betrag_de(z.betrag),
            konten,
        )

    for z in e.einnahmen:
        zeile(z)
    for z in e.nicht_zugeordnet:
        if z.text == "Einnahmen":
            zeile(z, "Nicht zugeordnete Einnahmen")
    t.add_row(
        str(e.summe_einnahmen_zeile),
        "159",
        "[bold]Summe Betriebseinnahmen[/bold]",
        betrag_de(e.summe_einnahmen),
        "",
    )
    for z in e.ausgaben:
        zeile(z)
    for z in e.nicht_zugeordnet:
        if z.text == "Ausgaben":
            zeile(z, "Nicht zugeordnete Ausgaben")
    for z in e.nicht_abziehbar:
        zeile(z)
    t.add_row(
        str(e.summe_ausgaben_zeile),
        "199",
        "[bold]Summe Betriebsausgaben[/bold]",
        betrag_de(e.summe_ausgaben),
        "",
    )
    console.print(t)
    console.print(
        f"Gewinn (Zeile {e.gewinn_zeilen[0]}/{e.gewinn_zeilen[1]}): "
        f"{betrag_de(e.gewinn)} €"
    )
    if e.summe_nicht_abziehbar:
        console.print(
            f"Nicht abziehbare Betriebsausgaben (nicht in der Summe): "
            f"{betrag_de(e.summe_nicht_abziehbar)} €"
        )
    for z in e.ausserhalb:
        console.print(
            f"{escape(z.text)}: {betrag_de(z.betrag)} € (Konten "
            f"{', '.join(sorted(z.konten))})"
        )
    console.print(
        f"Ergebnis laut Summen- und Saldenliste: {betrag_de(liste.ergebnis)} € "
        "(= Gewinn − nicht abziehbare Betriebsausgaben"
        + (" − Konten außerhalb der EÜR)" if e.ausserhalb else ")")
    )
    console.print(
        f"Entnahmen (Zeile {e.entnahmen_zeile}): {betrag_de(e.entnahmen)} € · "
        f"Einlagen (Zeile {e.einlagen_zeile}): {betrag_de(e.einlagen)} €"
    )
    for hinweis in e.hinweise:
        console.print(f"[yellow]{escape(hinweis)}[/yellow]")
    console.print(f"[dim]{escape(e.quelle)}[/dim]")
    if csv is not None:
        csv.write_text(euer_csv(e), encoding="utf-8")
        console.print(f"[green]CSV:[/green] {csv}")


@befehl.command("vortrag")
def vortrag(
    jahr: int = typer.Option(..., help="abzuschließendes Geschäftsjahr"),
    von: str = typer.Option(..., help="Wer schließt ab (steht im Protokoll)"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Saldovortrag ins Folgejahr — nur ohne Fehler-Befund; sperrt das Jahr."""
    from accounti.abschluss.pruefungen import kontext
    from accounti.abschluss.vortrag import AbschlussGesperrtError, trage_vor
    from accounti.anzeige import betrag_de
    from accounti.db.tabellen_abschluss import JahrGesperrtError
    from accounti.models.auth import Recht

    # Jahressperre: Buchungen freigeben (buchhalter, freigeber) und Einmalcode — im
    # Protokoll und im Journal (auch an den EB-Buchungen) steht dann der Benutzer
    with (
        handelnde_person(db, config, Recht.BUCHUNG_FREIGEBEN, von) as person,
        sitzung(db)() as s,
    ):
        try:
            v = trage_vor(s, kontext(s, jahr, config), person or von)
        except AbschlussGesperrtError as fehler:
            _befunde_ausgeben(fehler.befunde)
            ende(
                f"Saldovortrag {jahr} nicht möglich — erst die Fehler beheben "
                f"(accounti abschluss pruefen --jahr {jahr})"
            )
        except (ValueError, JahrGesperrtError) as fehler:
            ende(str(fehler))
        s.commit()
    _befunde_ausgeben(v.befunde)
    for b in v.buchungen:
        _buchung_zeigen(b)
    if not v.buchungen:
        console.print(f"Eröffnungswerte {jahr + 1}: unverändert")
    console.print(f"Ergebnis {jahr}: {betrag_de(v.ergebnis)} €")
    console.print(
        f"[green]Geschäftsjahr {jahr} abgeschlossen und gesperrt[/green] — "
        f"{len(v.buchungen)} Eröffnungsbuchung(en) zum 01.01.{jahr + 1}"
    )


@befehl.command("oeffnen")
def oeffnen(
    jahr: int = typer.Option(..., help="abgeschlossenes Geschäftsjahr"),
    grund: str = typer.Option(..., help="Warum das Jahr geöffnet wird (Protokoll)"),
    von: str = typer.Option(..., help="Wer öffnet (Protokoll)"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Abgeschlossenes Jahr wieder öffnen — danach erneut vortragen."""
    from accounti.abschluss.vortrag import AbschlussError, oeffne
    from accounti.models.auth import Recht

    if not grund.strip():
        ende("Grund für das Öffnen fehlt")
    # die Jahressperre aufheben: Buchungen freigeben, mit Einmalcode und Grund
    with (
        handelnde_person(db, config, Recht.BUCHUNG_FREIGEBEN, von) as person,
        sitzung(db)() as s,
    ):
        try:
            oeffne(s, jahr, person or von, grund)
        except AbschlussError as fehler:
            ende(str(fehler))
        s.commit()
    console.print(
        f"[yellow]Geschäftsjahr {jahr} geöffnet[/yellow] (protokolliert) — nach der "
        f"Änderung erneut: accounti abschluss vortrag --jahr {jahr}"
    )
