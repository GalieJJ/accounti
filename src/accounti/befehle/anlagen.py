"""``accounti anlagen …`` — Anlagenbuchhaltung (Baustein 12)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console
from accounti.befehle._anlagen_abschluss import betrag, datum, ende, lade, sitzung

NAME = "anlagen"
befehl = typer.Typer(
    help="Anlagenbuchhaltung: Anlagegüter, AfA, Abgang, Anlagenspiegel."
)


def _einstellungen(config: str):  # type: ignore[no-untyped-def]
    from accounti.anlagen.konfiguration import lade_anlagen

    return lade(lade_anlagen, config)


@befehl.command("tabelle")
def tabelle(
    db: str = DB_OPTION,  # noqa: ARG001 — einheitliche Optionen
    config: str = KONFIG_OPTION,
) -> None:
    """Hinterlegte AfA-Tabelle (Nutzungsdauern mit Fundstelle)."""
    einst = _einstellungen(config)
    t = Table(title="AfA-Tabelle (Vorschläge, immer änderbar)")
    for spalte in ("Typ", "Bezeichnung", "Jahre", "Fundstelle", "Konto"):
        t.add_column(spalte, overflow="fold")
    for typ, e in sorted(einst.rechtsstand().afa_tabelle.items()):
        t.add_row(
            typ,
            escape(e.bezeichnung),
            str(e.nutzungsdauer),
            escape(e.fundstelle),
            e.konto.get(einst.kontenrahmen, "—"),
        )
    console.print(t)


@befehl.command("anlegen")
def anlegen(
    bezeichnung: str | None = typer.Option(None, help="Bezeichnung des Anlageguts"),
    datum_text: str | None = typer.Option(None, "--datum", help="Anschaffungsdatum"),
    kosten: str | None = typer.Option(None, help="Anschaffungskosten netto"),
    nutzungsdauer: int | None = typer.Option(None, help="Jahre (Vorrang vor --typ)"),
    art: str | None = typer.Option(
        None,
        help="linear, degressiv, gwg, sammelposten, digital, e_fahrzeug, keine",
    ),
    typ: str | None = typer.Option(None, help="Schlüssel der AfA-Tabelle, z.B. pkw"),
    konto: str | None = typer.Option(None, help="Anlagekonto, z.B. 0420"),
    afa_konto: str | None = typer.Option(None, help="abweichendes AfA-Konto"),
    beleg: str | None = typer.Option(None, help="Belegnummer oder Beleg-ID"),
    umbuchen: bool = typer.Option(
        False,
        "--umbuchen",
        help="Umbuchung vorschlagen, wenn der Beleg als Aufwand steht",
    ),
    immateriell: bool = typer.Option(False, "--immateriell"),
    kein_wechsel: bool = typer.Option(
        False, "--kein-wechsel", help="degressiv: nicht zur linearen AfA wechseln"
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Anlagegut anlegen — Nutzungsdauer und AfA-Art werden vorgeschlagen."""
    from accounti.anlagen.afa import AfaRegelError
    from accounti.anlagen.dienst import AnlageError, lege_an
    from accounti.anzeige import betrag_de
    from accounti.models.anlagen import AfaArt

    einst = _einstellungen(config)
    try:
        afa_art = AfaArt(art) if art else None
    except ValueError:
        ende(f"Unbekannte AfA-Art '{art}'")
    with sitzung(db)() as s:
        try:
            e = lege_an(
                s,
                einst,
                bezeichnung=bezeichnung,
                datum=datum(datum_text, "--datum") if datum_text else None,
                kosten=betrag(kosten, "--kosten") if kosten else None,
                konto=konto,
                nutzungsdauer=nutzungsdauer,
                art=afa_art,
                typ=typ,
                beleg=beleg,
                umbuchen=umbuchen,
                immateriell=immateriell,
                wechsel_linear=not kein_wechsel,
                afa_konto=afa_konto,
            )
        except (AnlageError, AfaRegelError) as fehler:
            ende(str(fehler))
        s.commit()
    a = e.anlage
    console.print(
        f"[green]Angelegt:[/green] Nr. {a.nr} {escape(a.bezeichnung)} — "
        f"{betrag_de(a.anschaffungskosten)} am {a.anschaffungsdatum:%d.%m.%Y}, "
        f"Konto {a.konto}, {a.afa_art.value}"
        + (f", {a.nutzungsdauer} Jahre" if a.nutzungsdauer else "")
    )
    for hinweis in e.hinweise:
        console.print(f"[dim]{escape(hinweis)}[/dim]")


@befehl.command("liste")
def liste(
    jahr: int = typer.Option(date.today().year, help="Restbuchwert zum 31.12."),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Anlagegüter mit Restbuchwert zum Jahresende."""
    from accounti.anlagen.afa import plane
    from accounti.anzeige import betrag_de, datum_de
    from accounti.db.repo_anlagen import lade_anlagen

    rs = _einstellungen(config).rechtsstand()
    with sitzung(db)() as s:
        anlagen = lade_anlagen(s)
    if not anlagen:
        console.print("[dim]Keine Anlagegüter — accounti anlagen anlegen …[/dim]")
        return
    t = Table(title=f"Anlagegüter (Restbuchwert 31.12.{jahr})")
    t.add_column("Nr")
    t.add_column("Bezeichnung", overflow="fold")
    t.add_column("Konto")
    t.add_column("Anschaffung", no_wrap=True)
    t.add_column("AK", justify="right", no_wrap=True)
    t.add_column("AfA", overflow="fold")
    t.add_column("RBW", justify="right", no_wrap=True)
    for a in anlagen:
        rbw = plane(a, rs).restbuchwert(jahr, 12)
        art = a.afa_art.value + (f" {a.nutzungsdauer} J." if a.nutzungsdauer else "")
        if a.abgang_datum is not None and a.abgang_datum.year <= jahr:
            rbw = rbw - rbw  # nicht mehr im Bestand
            art += f", Abgang {datum_de(a.abgang_datum)}"
        t.add_row(
            str(a.nr),
            escape(a.bezeichnung),
            a.konto,
            datum_de(a.anschaffungsdatum),
            betrag_de(a.anschaffungskosten),
            art,
            betrag_de(rbw),
        )
    console.print(t)


@befehl.command("plan")
def plan(
    nr: str = typer.Argument(help="Inventarnummer"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """AfA-Plan eines Anlageguts bis zum Ende."""
    from accounti.anlagen.afa import AfaRegelError, plane
    from accounti.anzeige import betrag_de
    from accounti.db.repo_anlagen import lade_anlage

    rs = _einstellungen(config).rechtsstand()
    with sitzung(db)() as s:
        try:
            a = lade_anlage(s, nr)
        except ValueError as fehler:
            ende(str(fehler))
    try:
        p = plane(a, rs)
    except AfaRegelError as fehler:
        ende(str(fehler))
    t = Table(title=f"AfA-Plan Nr. {a.nr} {escape(a.bezeichnung)}")
    for spalte in ("Jahr", "Monate", "AfA", "kumuliert", "Restbuchwert", "Rechenweg"):
        t.add_column(spalte, overflow="fold")
    for j in p.jahre:
        t.add_row(
            str(j.jahr),
            str(j.monate),
            betrag_de(j.betrag),
            betrag_de(j.kumuliert),
            betrag_de(j.restbuchwert),
            escape(j.rechenweg),
        )
    console.print(t)


@befehl.command("afa")
def afa(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    bis_monat: int = typer.Option(12, help="AfA bis einschließlich dieses Monats"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """AfA-Lauf: bucht die noch fehlende AfA als Vorschlag zur Prüfung."""
    from accounti.anlagen.afa import AfaRegelError
    from accounti.anlagen.lauf import afa_lauf
    from accounti.anzeige import betrag_de

    if not 1 <= bis_monat <= 12:
        ende(f"--bis-monat {bis_monat}: erlaubt sind 1 bis 12")
    einst = _einstellungen(config)
    with sitzung(db)() as s:
        try:
            e = afa_lauf(s, jahr, einst, bis_monat)
        except (AfaRegelError, ValueError) as fehler:
            ende(str(fehler))
        s.commit()
    if not e.buchungen:
        console.print(
            f"[green]AfA {jahr} bis {bis_monat:02d}: nichts zu buchen.[/green]"
        )
        return
    for p in e.positionen:
        console.print(
            f"  {escape(p.bezeichnung)}: {betrag_de(p.differenz)} "
            f"[dim]({escape(p.rechenweg)})[/dim]"
        )
    for b in e.buchungen:
        console.print(
            f"[yellow]{str(b.id)[:8]}[/yellow] {b.soll_konto} an {b.haben_konto} "
            f"{betrag_de(b.betrag_netto)} — {escape(b.buchungstext)}"
        )
    console.print(
        f"{len(e.buchungen)} Buchung(en) über {betrag_de(e.summe)} zur Prüfung — "
        f"freigeben: accounti anlagen freigeben --jahr {jahr}"
    )


@befehl.command("freigeben")
def freigeben_befehl(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    von: str = typer.Option("supervisor", help="Wer hat geprüft"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,  # noqa: ARG001
) -> None:
    """AfA-Vorschläge eines Jahres freigeben."""
    from accounti.anlagen.lauf import freigeben

    with sitzung(db)() as s:
        anzahl = freigeben(s, jahr, von)
        s.commit()
    console.print(f"[green]{anzahl} AfA-Buchung freigegeben[/green] ({jahr})")


@befehl.command("abgang")
def abgang(
    nr: str = typer.Argument(help="Inventarnummer"),
    datum_text: str = typer.Option(..., "--datum", help="Abgangsdatum"),
    art: str = typer.Option("verkauf", help="verkauf, entnahme, verschrottung"),
    erloes: str | None = typer.Option(None, help="Erlös netto"),
    gegenkonto: str | None = typer.Option(None, help="z.B. 1200 oder Debitor"),
    ohne_ust: bool = typer.Option(False, "--ohne-ust", help="Erlös ohne USt"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Abgang buchen: AfA bis zum Abgangsmonat, Restbuchwert, Erlös (Vorschläge)."""
    from accounti.anlagen.abgang import AbgangError, buche_abgang
    from accounti.anlagen.afa import AfaRegelError
    from accounti.anzeige import betrag_de
    from accounti.models.anlagen import AbgangArt

    try:
        abgang_art = AbgangArt(art)
    except ValueError:
        ende(f"Unbekannte Abgangsart '{art}'")
    einst = _einstellungen(config)
    with sitzung(db)() as s:
        try:
            e = buche_abgang(
                s,
                nr,
                datum(datum_text, "--datum"),
                einst,
                abgang_art,
                betrag(erloes, "--erloes") if erloes else None,
                gegenkonto,
                not ohne_ust,
            )
        except (AbgangError, AfaRegelError, ValueError) as fehler:
            ende(str(fehler))
        s.commit()
    for b in [*e.afa.buchungen, *e.buchungen]:
        console.print(
            f"[yellow]{str(b.id)[:8]}[/yellow] {b.soll_konto} an {b.haben_konto} "
            f"{betrag_de(b.betrag_netto)} — {escape(b.buchungstext)}"
        )
    for hinweis in e.hinweise:
        console.print(escape(hinweis))


@befehl.command("spiegel")
def spiegel(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    csv: Annotated[
        Path | None, typer.Option("--csv", help="zusätzlich als CSV")
    ] = None,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Anlagenspiegel: Zugänge, Abgänge, Abschreibungen, Restbuchwerte."""
    from accounti.anlagen.afa import AfaRegelError
    from accounti.anlagen.spiegel import SPALTEN, als_csv, anlagenspiegel, werte
    from accounti.anzeige import betrag_de
    from accounti.db.repo_anlagen import lade_anlagen

    rs = _einstellungen(config).rechtsstand()
    with sitzung(db)() as s:
        anlagen = lade_anlagen(s)
    try:
        sp = anlagenspiegel(anlagen, jahr, rs)
    except AfaRegelError as fehler:
        ende(str(fehler))
    # drei Blöcke statt einer breiten Tabelle: Anschaffungskosten, AfA, Restbuchwerte
    for titel, von, bis in (
        ("Anschaffungskosten", 0, 4),
        ("Abschreibungen", 4, 8),
        ("Restbuchwerte", 8, 10),
    ):
        t = Table(title=f"Anlagenspiegel {jahr} — {titel}")
        t.add_column("Gruppe", overflow="fold")
        for spalte in SPALTEN[von:bis]:
            t.add_column(spalte, justify="right", no_wrap=True)
        for z in [*sp.gruppen, sp.summe]:
            t.add_row(escape(z.bezeichnung), *(betrag_de(w) for w in werte(z)[von:bis]))
        console.print(t)
    if csv is not None:
        csv.write_text(als_csv(sp), encoding="utf-8")
        console.print(f"[green]CSV:[/green] {csv}")


@befehl.command("vorschlaege")
def vorschlaege_befehl(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Buchungen auf Anlagekonten, zu denen es noch kein Anlagegut gibt."""
    from accounti.anlagen.dienst import vorschlaege
    from accounti.anzeige import betrag_de

    einst = _einstellungen(config)
    with sitzung(db)() as s:
        treffer = vorschlaege(s, einst, jahr)
    if not treffer:
        console.print(f"[green]Keine Zugänge ohne Anlagegut ({jahr}).[/green]")
        return
    for b in treffer:
        console.print(
            f"{b.datum:%d.%m.%Y} {b.soll_konto} {betrag_de(b.betrag_netto)} "
            f"{escape(b.buchungstext)} [dim](Beleg {b.beleg_nummer or '—'})[/dim]"
        )
    console.print("[dim]Anlegen: accounti anlagen anlegen --beleg … --typ …[/dim]")
