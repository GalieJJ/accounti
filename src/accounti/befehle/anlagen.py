"""``accounti anlagen …`` — Anlagenbuchhaltung (Baustein 12)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console, handelnde_person
from accounti.befehle._anlagen_abschluss import betrag, datum, ende, lade, sitzung
from accounti.db.tabellen_abschluss import JahrGesperrtError

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
    buchung: str | None = typer.Option(
        None,
        help="Zugangsbuchung (Anfang der ID), z.B. ein Bankumsatz ohne Beleg — "
        "liefert fehlende Angaben, anlagen vorschlaege nennt sie dann nicht mehr",
    ),
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
                buchung=buchung,
            )
        except (AnlageError, AfaRegelError, JahrGesperrtError) as fehler:
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


@befehl.command("aendern")
def aendern(
    nr: str = typer.Argument(help="Inventarnummer"),
    grund: str | None = typer.Option(
        None, help="Begründung (Pflicht, sobald sich der AfA-Plan ändert; Journal)"
    ),
    bezeichnung: str | None = typer.Option(None),
    datum_text: str | None = typer.Option(None, "--datum", help="Anschaffungsdatum"),
    kosten: str | None = typer.Option(None, help="Anschaffungskosten netto"),
    nutzungsdauer: int | None = typer.Option(None, help="Jahre"),
    art: str | None = typer.Option(
        None, help="linear, degressiv, gwg, sammelposten, digital, e_fahrzeug, keine"
    ),
    konto: str | None = typer.Option(None, help="Anlagekonto"),
    afa_konto: str | None = typer.Option(None, help="abweichendes AfA-Konto"),
    buchung: str | None = typer.Option(
        None, help="Zugangsbuchung verknüpfen (Anfang der ID)"
    ),
    von: str | None = typer.Option(
        None,
        help="Wer ändert (sonst ACCOUNTI_BENUTZER bzw. Anmeldename; mit "
        "eingerichteten Benutzern: Rolle und Einmalcode)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Anlagegut ändern — gebuchte AfA wird per Korrektur (Vorschlag) neu gerechnet."""
    from accounti.anlagen.abgang import AbgangError
    from accounti.anlagen.aenderung import aendere_anlage
    from accounti.anlagen.afa import AfaRegelError
    from accounti.anlagen.dienst import AnlageError
    from accounti.anzeige import betrag_de
    from accounti.db.tabellen import UnveraenderbarError
    from accounti.models.anlagen import AfaArt
    from accounti.models.auth import Recht

    einst = _einstellungen(config)
    try:
        afa_art = AfaArt(art) if art else None
    except ValueError:
        ende(f"Unbekannte AfA-Art '{art}'")
    # mit Benutzern: buchen (buchhalter) und Einmalcode — die Änderung erzeugt
    # AfA-Vorschläge und steht mit der Person im Journal
    with (
        handelnde_person(db, config, Recht.BUCHEN, von),
        sitzung(db)() as s,
    ):
        try:
            e = aendere_anlage(
                s,
                nr,
                einst,
                grund=grund,
                bezeichnung=bezeichnung,
                datum=datum(datum_text, "--datum") if datum_text else None,
                kosten=betrag(kosten, "--kosten") if kosten else None,
                nutzungsdauer=nutzungsdauer,
                art=afa_art,
                konto=konto,
                afa_konto=afa_konto,
                buchung=buchung,
            )
        except (
            AnlageError,
            AbgangError,
            AfaRegelError,
            JahrGesperrtError,
            UnveraenderbarError,
            ValueError,
        ) as fehler:
            ende(str(fehler))
        s.commit()
    console.print(f"[green]Anlagegut Nr. {e.anlage.nr} geändert[/green]")
    for feld, (alt, neu) in e.geaendert.items():
        console.print(f"  {feld}: {escape(str(alt))} → {escape(str(neu))}")
    _neuberechnung_zeigen(e.neuberechnung, betrag_de)


def _neuberechnung_zeigen(nb, betrag_de) -> None:  # type: ignore[no-untyped-def]
    for b in nb.verworfen:
        console.print(
            f"[dim]verworfen: {str(b.id)[:8]} {b.soll_konto} an {b.haben_konto} "
            f"{betrag_de(b.betrag_netto)} — {escape(b.buchungstext)}[/dim]"
        )
    for b in nb.buchungen:
        console.print(
            f"[yellow]{str(b.id)[:8]}[/yellow] {b.datum:%d.%m.%Y} {b.soll_konto} an "
            f"{b.haben_konto} {betrag_de(b.betrag_netto)} — {escape(b.buchungstext)}"
        )
    for jahr in sorted({lauf.jahr for lauf in nb.afa}):
        console.print(f"freigeben: accounti anlagen freigeben --jahr {jahr}")
    for hinweis in nb.hinweise:
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
        except (AfaRegelError, ValueError, JahrGesperrtError) as fehler:
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
    von: str | None = typer.Option(
        None,
        help="Wer hat geprüft (ohne Benutzer; sonst ACCOUNTI_BENUTZER bzw. "
        "Anmeldename — mit Einmalcode)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """AfA-Vorschläge eines Jahres freigeben (Buchungsfreigabe)."""
    from accounti.anlagen.lauf import freigeben
    from accounti.auth.cli import befehlsrecht_oder_ende
    from accounti.models.auth import Recht
    from accounti.pruefung.person import aktuelle_person, geprueft_als

    # mit eingerichteten Benutzern: Buchungen freigeben (buchhalter/freigeber) und
    # Einmalcode; geprüft hat dann der Benutzer (Spec 4.1: ein echter Benutzer) —
    # ohne Benutzer --von bzw. ACCOUNTI_BENUTZER oder der Anmeldename
    benutzer = befehlsrecht_oder_ende(
        db, config, Recht.BUCHUNG_FREIGEBEN, aktuelle_person(von)
    )
    pruefer = benutzer.name if benutzer is not None else aktuelle_person(von)
    with geprueft_als(benutzer.name if benutzer else None), sitzung(db)() as s:
        try:
            anzahl = freigeben(s, jahr, pruefer)
        except JahrGesperrtError as fehler:
            ende(str(fehler))
        s.commit()
    console.print(f"[green]{anzahl} AfA-Buchung freigegeben[/green] ({jahr})")


@befehl.command("abgang")
def abgang(
    nr: str = typer.Argument(help="Inventarnummer"),
    datum_text: str | None = typer.Option(None, "--datum", help="Abgangsdatum"),
    art: str = typer.Option("verkauf", help="verkauf, entnahme, verschrottung"),
    erloes: str | None = typer.Option(None, help="Erlös netto"),
    gegenkonto: str | None = typer.Option(None, help="z.B. 1200 oder Debitor"),
    ohne_ust: bool = typer.Option(False, "--ohne-ust", help="Erlös ohne USt"),
    zuruecknehmen: bool = typer.Option(
        False,
        "--zuruecknehmen",
        help="Abgang zurücknehmen, solange seine Buchungen Vorschläge sind (mit "
        "--grund)",
    ),
    grund: str | None = typer.Option(None, help="Grund der Rücknahme (Journal)"),
    von: str | None = typer.Option(
        None,
        help="Wer handelt (sonst ACCOUNTI_BENUTZER bzw. Anmeldename; mit "
        "eingerichteten Benutzern: Rolle und Einmalcode)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Abgang buchen: AfA bis zum Abgangsmonat, Restbuchwert, Erlös (Vorschläge)."""
    from accounti.anlagen.abgang import AbgangError, buche_abgang
    from accounti.anlagen.afa import AfaRegelError
    from accounti.anzeige import betrag_de
    from accounti.models.anlagen import AbgangArt

    if zuruecknehmen:
        _abgang_zuruecknehmen(nr, grund, von, db, config)
        return
    if datum_text is None:
        ende("--datum fehlt (Abgangsdatum)")
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
        except (AbgangError, AfaRegelError, ValueError, JahrGesperrtError) as fehler:
            ende(str(fehler))
        s.commit()
    for b in [*e.afa.buchungen, *e.buchungen]:
        console.print(
            f"[yellow]{str(b.id)[:8]}[/yellow] {b.soll_konto} an {b.haben_konto} "
            f"{betrag_de(b.betrag_netto)} — {escape(b.buchungstext)}"
        )
    for hinweis in e.hinweise:
        console.print(escape(hinweis))


def _abgang_zuruecknehmen(
    nr: str, grund: str | None, von: str | None, db: str, config: str
) -> None:
    from accounti.anlagen.abgang import AbgangError
    from accounti.anlagen.aenderung import nimm_abgang_zurueck
    from accounti.anlagen.afa import AfaRegelError
    from accounti.anzeige import betrag_de
    from accounti.db.tabellen import UnveraenderbarError
    from accounti.models.auth import Recht

    einst = _einstellungen(config)
    # mit Benutzern: buchen (buchhalter) und Einmalcode — verwirft Vorschläge
    with (
        handelnde_person(db, config, Recht.BUCHEN, von),
        sitzung(db)() as s,
    ):
        try:
            r = nimm_abgang_zurueck(s, nr, einst, grund or "")
        except (
            AbgangError,
            AfaRegelError,
            JahrGesperrtError,
            UnveraenderbarError,
            ValueError,
        ) as fehler:
            ende(str(fehler))
        s.commit()
    console.print(
        f"[green]Abgang von Anlagegut Nr. {r.anlage.nr} zurückgenommen[/green] "
        f"(war {r.vorher.abgang_datum:%d.%m.%Y})"
    )
    _neuberechnung_zeigen(r.neuberechnung, betrag_de)


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
    from accounti.anlagen.dienst import vermutlich_erfasst, vorschlaege
    from accounti.anzeige import betrag_de

    einst = _einstellungen(config)
    with sitzung(db)() as s:
        treffer = vorschlaege(s, einst, jahr)
        vermutlich = vermutlich_erfasst(s, einst, jahr)
    for b, a in vermutlich:
        console.print(
            f"[dim]{b.datum:%d.%m.%Y} {b.soll_konto} {betrag_de(b.betrag_netto)} "
            f"{escape(b.buchungstext)} — vermutlich erfasst als Nr. {a.nr} "
            f"{escape(a.bezeichnung)} (verknüpfen: accounti anlagen aendern {a.nr} "
            f"--buchung {str(b.id)[:8]})[/dim]"
        )
    if not treffer:
        console.print(f"[green]Keine Zugänge ohne Anlagegut ({jahr}).[/green]")
        return
    for b in treffer:
        console.print(
            f"{b.datum:%d.%m.%Y} {b.soll_konto} {betrag_de(b.betrag_netto)} "
            f"{escape(b.buchungstext)} [dim](Beleg {b.beleg_nummer or '—'}, "
            f"Buchung {str(b.id)[:8]})[/dim]"
        )
    console.print(
        "[dim]Anlegen: accounti anlagen anlegen --beleg … bzw. --buchung … "
        "--typ …[/dim]"
    )
