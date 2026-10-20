"""Befehlsgruppe ``accounti marktplatz`` — Amazon, eBay, PayPal, Shopify.

Die Fachlogik liegt in ``accounti.integrationen``, die Formate in
``accounti.importers``.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from accounti.integrationen.auszahlung import Abgleich
    from accounti.models.integrationen import Abrechnung, Befund

NAME = "marktplatz"
befehl = typer.Typer(
    help="Marktplatz-Abrechnungen einlesen, buchen und gegen die Bank abgleichen.",
    no_args_is_help=True,
)

ARCHIV_STANDARD = "archiv/belege"
_FARBE = {"fehler": "red", "warnung": "yellow", "hinweis": "dim"}


def _zahl(text: str | None, name: str) -> Decimal | None:
    if text is None:
        return None
    try:
        return Decimal(text.replace(".", "").replace(",", ".") if "," in text else text)
    except InvalidOperation as fehler:
        console.print(f"[red]{name} {text!r} ist keine Zahl[/red]")
        raise typer.Exit(1) from fehler


def _eur(betrag: Decimal) -> str:
    from accounti.integrationen.buchung import eur_text

    return eur_text(betrag)


def _befunde(befunde: list[Befund]) -> None:
    for b in befunde:
        if b.erledigt:
            console.print(f"  [dim]{b.code} (erledigt): {escape(b.text)}[/dim]")
            continue
        farbe = _FARBE.get(b.schweregrad.value, "white")
        console.print(f"  [{farbe}]{b.code}[/{farbe}]: {escape(b.text)}")


def _abgleich_text(a: Abrechnung, abgleich: list[Abgleich]) -> str:
    from accounti.models.integrationen import Postenart

    teile = []
    for p in a.posten:
        if p.art not in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG):
            continue
        betrag = -(p.betrag_eur if p.betrag_eur is not None else p.betrag)
        art = "Auszahlung" if p.art is Postenart.AUSZAHLUNG else "Einzahlung"
        treffer = next(
            (x for x in abgleich if x.posten.id == p.id and x.transaktion), None
        )
        if treffer is not None and treffer.transaktion is not None:
            teile.append(
                f"{art} {_eur(betrag)} € abgeglichen mit dem Bankumsatz vom "
                f"{treffer.transaktion.datum:%d.%m.%Y}"
            )
        elif p.bank_transaktion_id is None:
            teile.append(f"{art} {_eur(betrag)} € offen")
    return "; ".join(teile)


@befehl.command("import")
def marktplatz_import(
    markt: str = typer.Argument(help="amazon, ebay, paypal oder shopify"),
    datei: str = typer.Argument(help="Abrechnung, Transaktionsbericht oder Export"),
    laender: str | None = typer.Option(
        None, help="Bestell-/USt-Bericht mit Bestimmungsland je Bestellung"
    ),
    kurs: str | None = typer.Option(
        None, help="Kurs bei Fremdwährung: Einheiten je 1 EUR (EZB-Referenzkurs)"
    ),
    auszahlung: str | None = typer.Option(
        None, help="Auszahlungsbetrag laut Marktplatz, wenn er nicht in der Datei steht"
    ),
    db: str = DB_OPTION,
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    config: str = KONFIG_OPTION,
) -> None:
    """Abrechnung einlesen, archivieren, buchen und die Auszahlung abgleichen."""
    from accounti.belege.archiv import BelegArchiv
    from accounti.db import init_db, session_factory
    from accounti.importers.marktplatz import MarktplatzFormatError, lies_laenderdatei
    from accounti.integrationen.buchung import ANZEIGE
    from accounti.integrationen.einstellungen import lade_kontext
    from accounti.integrationen.lauf import IntegrationError, importiere
    from accounti.konfiguration import KonfigurationError

    try:
        kontext = lade_kontext(config)
        angaben = lies_laenderdatei(Path(laender).read_bytes()) if laender else None
        engine, make_session = session_factory(db)
        init_db(engine)
        with make_session() as s:
            ergebnisse = importiere(
                s,
                BelegArchiv(archiv),
                kontext,
                markt,
                Path(datei).read_bytes(),
                Path(datei).name,
                laender=angaben,
                kurs=_zahl(kurs, "Kurs"),
                auszahlung=_zahl(auszahlung, "Auszahlung"),
            )
            s.commit()
    except (
        IntegrationError,
        MarktplatzFormatError,
        KonfigurationError,
        OSError,
    ) as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler

    for e in ergebnisse:
        a = e.abrechnung
        markt_name = ANZEIGE.get(a.marktplatz, a.marktplatz)
        kopf = (
            f"[bold]{markt_name} {escape(a.nummer)}[/bold] "
            f"({a.von:%d.%m.}–{a.bis:%d.%m.%Y})"
        )
        if e.widerspruch is not None:
            console.print(
                f"{kopf}: schon bekannt — der Bericht widerspricht ihr, nichts "
                "nachgetragen."
            )
            _befunde([e.widerspruch])
            continue
        if e.nachgetragen:
            console.print(
                f"{kopf}: schon bekannt — {e.nachgetragen} Posten nachgetragen, "
                f"{e.buchungen} Buchungen."
            )
        elif not e.neu:
            console.print(f"{kopf}: schon importiert — nichts gebucht.")
            continue
        else:
            zusatz = f", {e.umsaetze} neue PayPal-Umsätze" if e.umsaetze else ""
            console.print(f"{kopf}: {e.buchungen} Buchungen{zusatz}.")
        abgleich = _abgleich_text(a, e.abgleich)
        if abgleich:
            console.print(f"  {abgleich}")
        _befunde(a.befunde)


@befehl.command("liste")
def marktplatz_liste(db: str = DB_OPTION) -> None:
    """Importierte Abrechnungen mit Status und Befunden."""
    from accounti.db import init_db, session_factory
    from accounti.db.repo_integrationen import lade_abrechnungen
    from accounti.integrationen.buchung import ANZEIGE

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        abrechnungen = lade_abrechnungen(s)
    if not abrechnungen:
        console.print("Keine Abrechnungen importiert.")
        return
    tabelle = Table(title="Marktplatz-Abrechnungen")
    for spalte in (
        "Marktplatz",
        "Nummer",
        "Zeitraum",
        "Auszahlung",
        "Status",
        "Befunde",
    ):
        tabelle.add_column(spalte)
    for a in abrechnungen:
        tabelle.add_row(
            ANZEIGE.get(a.marktplatz, a.marktplatz),
            a.nummer,
            f"{a.von:%d.%m.}–{a.bis:%d.%m.%Y}",
            f"{_eur(a.auszahlung)} {a.waehrung}" if a.auszahlung is not None else "—",
            a.status.value,
            str(len(a.offene_befunde)),
        )
    console.print(tabelle)


@befehl.command("zeigen")
def marktplatz_zeigen(
    nummer: str = typer.Argument(help="Abrechnungsnummer oder Anfang der ID"),
    db: str = DB_OPTION,
) -> None:
    """Summen je Bestandteil, Auszahlung und Befunde einer Abrechnung."""
    from accounti.db import init_db, session_factory
    from accounti.db.repo_integrationen import lade_abrechnung
    from accounti.models.integrationen import Postenart

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        try:
            a = lade_abrechnung(s, nummer)
        except ValueError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
    console.print(
        f"[bold]{escape(a.nummer)}[/bold] {a.marktplatz}, {a.von:%d.%m.%Y}–"
        f"{a.bis:%d.%m.%Y}, Status {a.status.value}, Datei {escape(a.dateiname)}"
    )
    if a.anfangssaldo is not None:
        console.print(
            f"Guthaben {_eur(a.anfangssaldo)} → {_eur(a.endsaldo or Decimal(0))} EUR"
        )
    for art in Postenart:
        posten = [p for p in a.posten if p.art is art]
        if posten:
            summe = sum((p.betrag for p in posten), Decimal("0"))
            console.print(f"  {art.value} {_eur(summe)} ({len(posten)} Posten)")
    _befunde(a.befunde)


@befehl.command("abgleichen")
def marktplatz_abgleichen(db: str = DB_OPTION, config: str = KONFIG_OPTION) -> None:
    """Offene Auszahlungen erneut gegen die Bankumsätze abgleichen."""
    from accounti.db import init_db, session_factory
    from accounti.integrationen.auszahlung import gleiche_auszahlungen_ab
    from accounti.integrationen.einstellungen import lade_kontext
    from accounti.konfiguration import KonfigurationError

    try:
        kontext = lade_kontext(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        ergebnisse = gleiche_auszahlungen_ab(s, kontext)
        s.commit()
    gefunden = [e for e in ergebnisse if e.transaktion is not None]
    console.print(
        f"[green]{len(gefunden)}[/green] Auszahlungen abgeglichen, "
        f"{len(ergebnisse) - len(gefunden)} offen."
    )
    for e in ergebnisse:
        if e.befund is not None:
            _befunde([e.befund])


@befehl.command("oss")
def marktplatz_oss(
    quartal: str = typer.Option(..., help="Meldezeitraum, z.B. 2026-Q3"),
    db: str = DB_OPTION,
    csv: str | None = typer.Option(None, help="Meldung zusätzlich als CSV schreiben"),
    config: str = KONFIG_OPTION,
) -> None:
    """OSS-Quartalsmeldung aus den gebuchten EU-Fernverkäufen (steuer.oss)."""
    import re

    from accounti.db import init_db, session_factory
    from accounti.integrationen.einstellungen import lade_kontext
    from accounti.integrationen.oss import (
        oss_buchungen,
        oss_meldung,
        steuerabgleich,
        ungepruefte,
    )
    from accounti.konfiguration import KonfigurationError

    treffer = re.fullmatch(r"(\d{4})-?Q([1-4])", quartal.strip().upper())
    if treffer is None:
        console.print(f"[red]Quartal {quartal!r}: Format JJJJ-Q1 … JJJJ-Q4[/red]")
        raise typer.Exit(1)
    try:
        kontext = lade_kontext(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    e = kontext.einstellungen
    jahr, nr = int(treffer[1]), int(treffer[2])
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        meldung = oss_meldung(s, jahr, nr, kontext.firmen_land, e)
        offen = ungepruefte(oss_buchungen(s, jahr, nr, e))
        differenzen = steuerabgleich(s, meldung, kontext.firmen_land)
    tabelle = Table(title=f"OSS-Meldung {meldung.quartal}")
    for spalte in ("Land", "Satz", "Bemessungsgrundlage", "Steuer", "Anzahl"):
        tabelle.add_column(spalte)
    negativ = []
    for land in sorted(meldung.laender, key=lambda x: x.land_code):
        for satz, basis, steuer, anzahl in (
            (
                land.steuersatz_normal,
                land.bemessungsgrundlage_normal,
                land.steuer_normal,
                land.anzahl_normal,
            ),
            (
                land.steuersatz_ermaessigt,
                land.bemessungsgrundlage_ermaessigt,
                land.steuer_ermaessigt,
                land.anzahl_ermaessigt,
            ),
        ):
            if not (anzahl or basis):
                continue
            if basis < 0:
                negativ.append(land.land_code)
            tabelle.add_row(
                f"{land.land_code} {land.land_name}",
                f"{satz.normalize():f} %",
                _eur(basis),
                _eur(steuer),
                str(anzahl),
            )
    tabelle.add_row(
        "Gesamt",
        "",
        _eur(meldung.bemessungsgrundlage_gesamt),
        _eur(meldung.steuer_gesamt),
        str(meldung.anzahl_transaktionen),
    )
    console.print(tabelle)
    if meldung.korrekturen:
        korrektur = Table(title="Korrekturen früherer Meldezeiträume")
        for spalte in ("Zeitraum", "Land", "Satz", "Bemessungsgrundlage", "Steuer"):
            korrektur.add_column(spalte)
        for k in meldung.korrekturen:
            korrektur.add_row(
                k.zeitraum,
                k.land_code,
                f"{k.steuersatz.normalize():f} %",
                _eur(k.bemessungsgrundlage),
                _eur(k.steuer),
            )
        console.print(korrektur)
        console.print(
            "Korrekturen im BZSt-Portal beim ursprünglichen Meldezeitraum angeben "
            "(ursprünglicher und berichtigter Steuerbetrag), nicht als Minusbetrag."
        )
    console.print(f"Abgabe beim BZSt bis {meldung.abgabefrist:%d.%m.%Y} (§ 18j UStG).")
    if negativ:
        console.print(
            f"[red]Negative Länderzeile ({', '.join(negativ)}): Erstattungen ohne "
            "auffindbaren Erlös — Ursprungsquartal klären und als Korrektur melden, "
            "das BZSt nimmt keine negativen Beträge an.[/red]"
        )
    for d in differenzen:
        console.print(
            f"[yellow]OSS-Steuerkonto {d.konto}: gebucht {_eur(d.gebucht)} €, "
            f"gemeldet {_eur(d.gemeldet)} € (Differenz {_eur(d.differenz)} €) — "
            "Rundung je Buchung oder OSS-Erlöse außerhalb der OSS-Erlöskonten "
            "(Befunde oss_ermaessigt, oss_konto_fehlt) prüfen.[/yellow]"
        )
    if offen:
        console.print(
            f"[yellow]{offen} OSS-Buchungen liegen noch zur Prüfung — Meldung "
            "vorläufig.[/yellow]"
        )
    if csv:
        Path(csv).write_text("\n".join(meldung.als_csv_zeilen()) + "\n", "utf-8")
        console.print(f"CSV: {csv}")
