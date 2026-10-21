"""Befehlsgruppe ``accounti datev`` — Stammdaten, Belege und Kontoauszüge für DATEV.

Der Buchungsstapel ohne Belege bleibt ``accounti export datev``; ``datev belege``
schreibt für denselben Zeitraum einen Buchungsstapel *mit* Beleglink und das
zugehörige Belegpaket — beides zusammen importieren, nicht zusätzlich zum alten Stapel.
``datev kontoauszuege`` schreibt die Monatsauszüge eines Finanzkontos fest und gibt
sie als MT940 mit Saldenverlauf aus.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from decimal import Decimal
from pathlib import Path

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

NAME = "datev"
befehl = typer.Typer(
    help="DATEV-Übergabe: Debitoren/Kreditoren, Belege mit Beleglink, Kontoauszüge.",
    no_args_is_help=True,
)

ARCHIV_STANDARD = "archiv/belege"
BERATER_OPTION = typer.Option(
    None, help="DATEV-Beraternummer (sonst datev.berater_nummer)"
)
MANDANT_OPTION = typer.Option(
    None, help="DATEV-Mandantennummer (sonst datev.mandanten_nummer)"
)


def zeitraum(text: str) -> tuple[date, date]:
    """``JJJJ-MM`` → erster und letzter Tag des Monats."""
    treffer = re.fullmatch(r"(\d{4})-(\d{2})", text.strip())
    if treffer is None or not 1 <= int(treffer[2]) <= 12:
        console.print(f"[red]Zeitraum {text!r}: Format JJJJ-MM, z.B. 2026-08[/red]")
        raise typer.Exit(1)
    jahr, monat = int(treffer[1]), int(treffer[2])
    return date(jahr, monat, 1), date(jahr, monat, monthrange(jahr, monat)[1])


def automatikkonten_aus(config: str) -> dict[str, int]:
    """DATEV-Automatikkonten aus der Kontenrahmen-Datei der Konfiguration
    (``pruefung.kontenrahmen_datei``, SKR03: mitgelieferte ``pruefung/skr03.yaml``)."""
    from accounti.konfiguration import lade_buchhaltung
    from accounti.pruefung.einstellungen import lade_pruefung
    from accounti.pruefung.regeln.richtigkeit import automatikkonten

    return automatikkonten(lade_buchhaltung(config), lade_pruefung(config))


def _fehler(fehler: Exception) -> typer.Exit:
    console.print(f"[red]{escape(str(fehler))}[/red]")
    return typer.Exit(1)


@befehl.command("stammdaten")
def datev_stammdaten(
    period: str | None = typer.Option(
        None, help="nur Personenkonten mit Buchungen in JJJJ-MM"
    ),
    ausgabe: str = typer.Option("./export", help="Ausgabeverzeichnis"),
    berater: str | None = BERATER_OPTION,
    mandant: str | None = MANDANT_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Debitoren und Kreditoren im DATEV-Format (Kategorie 16, Version 5)."""
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_buchungen, lade_kontakte
    from accounti.export.datev_format import DatevFormatError
    from accounti.export.datev_stammdaten import (
        exportiere_stammdaten,
        lade_datev_mandant,
    )
    from accounti.konfiguration import KonfigurationError
    from accounti.models import KontaktStatus

    von_bis = zeitraum(period) if period else None
    try:
        stichtag = von_bis[0] if von_bis else date.today()
        datev = lade_datev_mandant(config, stichtag, berater, mandant)
    except (KonfigurationError, ValueError) as fehler:
        raise _fehler(fehler) from fehler
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        kontakte = lade_kontakte(s)
        if von_bis:
            von, bis = von_bis
            konten = {
                konto
                for b in lade_buchungen(s)
                if von <= b.datum <= bis
                for konto in (b.soll_konto, b.haben_konto)
            }
            kontakte = [
                k
                for k in kontakte
                if k.debitor_konto in konten or k.kreditor_konto in konten
            ]
    try:
        pfad, anzahl = exportiere_stammdaten(kontakte, datev, ausgabe)
    except DatevFormatError as fehler:
        raise _fehler(fehler) from fehler
    offen = sum(1 for k in kontakte if k.status is KontaktStatus.ZUR_PRUEFUNG)
    console.print(f"[green]Stammdaten:[/green] {pfad} ({anzahl} Personenkonten)")
    if offen:
        console.print(
            f"[yellow]{offen} Kontakte sind noch nicht bestätigt (accounti kontakte "
            "liste) — sie sind trotzdem enthalten.[/yellow]"
        )


@befehl.command("belege")
def datev_belege(
    period: str = typer.Option(..., help="Zeitraum JJJJ-MM"),
    ausgabe: str = typer.Option(..., help="Belegpaket, z.B. ./belege-08.zip"),
    berater: str | None = BERATER_OPTION,
    mandant: str | None = MANDANT_OPTION,
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    alle: bool = typer.Option(
        False, "--alle", help="Auch ungeprüfte Buchungen exportieren"
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Belegpaket (document.xml) und Buchungsstapel mit Beleglink für DATEV."""
    from accounti.belege.archiv import BelegArchiv
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_buchungen
    from accounti.export.datev_belege import (
        FREIGEGEBEN,
        BelegexportError,
        exportiere_belegpaket,
    )
    from accounti.export.datev_format import DatevFormatError
    from accounti.export.datev_stammdaten import lade_datev_mandant
    from accounti.konfiguration import KonfigurationError
    from accounti.pruefung.storno import markiere_exportiert

    von, bis = zeitraum(period)
    try:
        datev = lade_datev_mandant(config, von, berater, mandant)
        automatik = automatikkonten_aus(config)
        engine, make_session = session_factory(db)
        init_db(engine)
        with make_session() as s:
            ergebnis = exportiere_belegpaket(
                s,
                BelegArchiv(archiv),
                datev,
                von,
                bis,
                Path(ausgabe),
                alle=alle,
                automatikkonten=automatik,
            )
            # Baustein 7: exportierte Buchungen vermerken, Export ins Journal
            exportiert = [
                b
                for b in lade_buchungen(s, status=None if alle else FREIGEGEBEN)
                if von <= b.datum <= bis
            ]
            markiere_exportiert(s, exportiert, ergebnis.stapel_pfad, "datev_belege")
            s.commit()
    except (KonfigurationError, BelegexportError, DatevFormatError) as fehler:
        raise _fehler(fehler) from fehler
    if ergebnis.zip_pfad is None:
        console.print("[yellow]Kein Belegpaket: keine verknüpfbaren Belege.[/yellow]")
    else:
        console.print(
            f"[green]Belegpaket:[/green] {ergebnis.zip_pfad} ({ergebnis.belege} "
            "Belege) — mit DATEV Belegtransfer hochladen, nicht entpacken"
        )
    console.print(
        f"[green]Buchungsstapel:[/green] {ergebnis.stapel_pfad} "
        f"({ergebnis.verknuepft} von {ergebnis.buchungen} Buchungen verknüpft)"
    )
    for befund in ergebnis.befunde:
        console.print(f"  [yellow]{escape(befund)}[/yellow]")


def _betrag(text: str | None, name: str) -> Decimal | None:
    from accounti.importers.marktplatz import (
        MarktplatzFormatError,
        erkenne_dezimal,
        lies_betrag,
    )

    if text is None:
        return None
    try:
        return lies_betrag(text, erkenne_dezimal([text]))
    except MarktplatzFormatError as fehler:
        console.print(f"[red]{name}: {escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler


def _euro(betrag: Decimal) -> str:
    text = f"{betrag:,.2f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


@befehl.command("kontoauszuege")
def datev_kontoauszuege(
    period: str = typer.Option(
        ..., help="Monat JJJJ-MM — fehlende Auszüge bis dahin werden festgeschrieben"
    ),
    konto: str | None = typer.Option(
        None, help="Finanzkonto (sonst buchhaltung.bank_konto), z.B. 1210 für PayPal"
    ),
    ab: str | None = typer.Option(
        None, help="nur beim ersten Auszug: erster Monat JJJJ-MM (sonst --period)"
    ),
    anfangssaldo: str | None = typer.Option(
        None, help="nur beim ersten Auszug: Saldo laut Bank zu Monatsbeginn"
    ),
    kontrollsaldo: str | None = typer.Option(
        None, help="Saldo laut Bank zum Monatsende — bei Abweichung kein Auszug"
    ),
    kontobezeichnung: str | None = typer.Option(
        None, help="Feld :25: (BLZ/Konto oder IBAN), wenn kein Bankkonto eingerichtet"
    ),
    ausgabe: str = typer.Option("./export", help="Ausgabeverzeichnis"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Kontoauszüge: lückenlos nummeriert, MT940 und Saldenverlauf (CSV)."""
    from accounti.db import init_db, session_factory
    from accounti.db.repo_export import lade_kontoauszuege
    from accounti.export.kontoauszuege import (
        KontoauszugError,
        erstelle_auszuege,
        lade_umsaetze,
        mt940,
        pruefe_auszuege,
        pruefe_kontobezeichnung,
        saldenverlauf_csv,
    )
    from accounti.export.kontoauszuege import kontobezeichnung as bezeichnung_fuer
    from accounti.integrationen.einstellungen import lade_kontext
    from accounti.konfiguration import KonfigurationError

    von, bis = zeitraum(period)
    ab_monat = zeitraum(ab)[0] if ab else None
    anfang = _betrag(anfangssaldo, "Anfangssaldo")
    kontrolle = _betrag(kontrollsaldo, "Kontrollsaldo")
    try:
        kontext = lade_kontext(config)
    except KonfigurationError as fehler:
        raise _fehler(fehler) from fehler
    bank_konto = kontext.buchhaltung.bank_konto
    finanzkonto = konto or bank_konto
    paypal = kontext.einstellungen.marktplaetze.get("paypal")
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        try:
            bezeichnung = pruefe_kontobezeichnung(
                kontobezeichnung
                or bezeichnung_fuer(
                    finanzkonto,
                    None,
                    paypal.verrechnungskonto if paypal else "",
                    kontext.einstellungen.paypal_kontobezeichnung,
                    session=s,
                )
            )
            lauf = erstelle_auszuege(
                s,
                finanzkonto,
                bis,
                standard_konto=bank_konto,
                anfangssaldo=anfang,
                kontrollsaldo=kontrolle,
                ab=ab_monat,
            )
        except KontoauszugError as fehler:
            s.rollback()
            raise _fehler(fehler) from fehler
        s.commit()
        alle = lade_kontoauszuege(s, finanzkonto)
        neu = {a.id for a in lauf.neu}
        auszuege = [a for a in alle if a.id in neu or a.von == von]
        if not auszuege:
            erster = f"{alle[0].von:%Y-%m}" if alle else "—"
            console.print(
                f"[red]Für {period} gibt es keinen Auszug (erster Auszug: "
                f"{erster}).[/red]"
            )
            raise typer.Exit(1)
        jahr = [a for a in alle if a.jahr == von.year and a.von <= von]
        umsaetze = lade_umsaetze(s, alle)
        pruefung = pruefe_auszuege(s, finanzkonto)
        try:
            inhalt = mt940(auszuege, umsaetze, bezeichnung)
        except KontoauszugError as fehler:
            raise _fehler(fehler) from fehler
        verlauf = saldenverlauf_csv(jahr, umsaetze)

    if pruefung:
        # eine Datei mit geänderten Umsätzen zwischen festen Salden wäre
        # inkonsistent — dann lieber gar keine
        for befund in lauf.befunde:
            console.print(f"  [yellow]{escape(befund.text)}[/yellow]")
        console.print("[red]Prüfung der Auszugskette:[/red]")
        for befund in pruefung:
            console.print(f"  [red]{escape(befund.text)}[/red]")
        console.print("[red]Es wurden keine Dateien geschrieben.[/red]")
        raise typer.Exit(1)

    ordner = Path(ausgabe)
    ordner.mkdir(parents=True, exist_ok=True)
    spanne = f"{auszuege[0].von:%Y%m}"
    if len(auszuege) > 1:
        spanne += f"-{auszuege[-1].von:%Y%m}"
    mt_pfad = ordner / f"MT940_{finanzkonto}_{spanne}.sta"
    mt_pfad.write_bytes(inhalt)
    csv_pfad = ordner / f"Saldenverlauf_{finanzkonto}_{von:%Y}.csv"
    csv_pfad.write_bytes(verlauf)

    for a in auszuege:
        markierung = "neu" if a.id in neu else "schon festgeschrieben"
        console.print(
            f"Auszug {a.nummer}/{a.jahr}  {a.von:%d.%m.}–{a.bis:%d.%m.%Y}  "
            f"Anfang {_euro(a.anfangssaldo)}  Ende {_euro(a.endsaldo)}  "
            f"{len(a.umsaetze)} Umsätze ({markierung})"
        )
    console.print(f"[green]MT940:[/green] {mt_pfad} (Feld :25: {bezeichnung})")
    console.print(f"[green]Saldenverlauf:[/green] {csv_pfad}")
    for befund in lauf.befunde:
        console.print(f"  [yellow]{escape(befund.text)}[/yellow]")
    console.print("Prüfung der Auszugskette: keine Befunde.")
