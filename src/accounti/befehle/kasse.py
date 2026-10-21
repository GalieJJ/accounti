"""``accounti kasse …`` — Kassenbuch (Baustein 12)."""

from __future__ import annotations

from datetime import date

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console, handelnde_person
from accounti.befehle._anlagen_abschluss import betrag, datum, ende, lade, sitzung
from accounti.db.tabellen_abschluss import JahrGesperrtError

NAME = "kasse"
befehl = typer.Typer(help="Kassenbuch: laufende Nummer, Bestand nie negativ, Storno.")


def _kasse(config: str):  # type: ignore[no-untyped-def]
    from accounti.abschluss.konfiguration import lade_kasse

    return lade(lade_kasse, config)


@befehl.command("anfangsbestand")
def anfangsbestand_befehl(
    betrag_text: str = typer.Option(..., "--betrag", help="Bestand in Euro"),
    datum_text: str | None = typer.Option(None, "--datum", help="Datum"),
    von: str | None = typer.Option(
        None,
        help="Wer erfasst (mit eingerichteten Benutzern: der Benutzer, mit Rolle "
        "und Einmalcode)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Ersten Bestand eines leeren Kassenbuchs erfassen (ohne Buchung)."""
    from accounti.abschluss.kassenbuch import KassenbuchError, anfangsbestand
    from accounti.anzeige import betrag_de
    from accounti.models.auth import Recht

    kasse = _kasse(config)
    wert, tag = betrag(betrag_text), datum(datum_text, "--datum")
    # mit Benutzern: buchen (buchhalter) und Einmalcode — das Kassenbuch ist eine
    # Grundaufzeichnung, erfasst hat der Benutzer, nicht ein Freitext
    with (
        handelnde_person(db, config, Recht.BUCHEN, von) as person,
        sitzung(db)() as s,
    ):
        try:
            v = anfangsbestand(s, wert, tag, kasse, person)
        except (KassenbuchError, JahrGesperrtError) as fehler:
            ende(str(fehler))
        s.commit()
    console.print(
        f"[green]Nr. {v.nr}[/green] Anfangsbestand {betrag_de(v.betrag)} € am "
        f"{v.datum:%d.%m.%Y}"
    )
    console.print(
        f"[dim]Den EB-Wert des Kassenkontos {kasse.konto} erfasst "
        "accounti abschluss eroeffnung (oder der Saldovortrag).[/dim]"
    )


@befehl.command("buchen")
def buchen(
    betrag_text: str = typer.Option(
        ..., "--betrag", help="Einnahme positiv, Ausgabe negativ, z.B. -24.90"
    ),
    text: str = typer.Option(..., "--text", help="Buchungstext"),
    datum_text: str | None = typer.Option(None, "--datum", help="Datum (heute)"),
    beleg: str | None = typer.Option(None, "--beleg", help="Belegnummer"),
    konto: str | None = typer.Option(
        None, "--konto", help="Gegenkonto — dann sofort gebucht, sonst über classify"
    ),
    steuer: str | None = typer.Option(None, "--steuer", help="Steuersatz, z.B. 19"),
    von: str | None = typer.Option(
        None,
        help="Wer erfasst (mit eingerichteten Benutzern: der Benutzer, mit Rolle "
        "und Einmalcode)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Bargeschäft erfassen — abgelehnt, wenn die Kasse ins Minus fiele."""
    from accounti.abschluss.kassenbuch import KassenbuchError, bestand, buche_kasse
    from accounti.anzeige import betrag_de
    from accounti.db.repo_kasse import lade_kassenbuch
    from accounti.models.auth import Recht

    kasse = _kasse(config)
    satz = betrag(steuer, "--steuer") if steuer else None
    wert, tag = betrag(betrag_text), datum(datum_text, "--datum")
    # mit Benutzern: buchen (buchhalter) und Einmalcode. Mit --konto entsteht sofort
    # eine freigegebene Buchung (geprueft_von = Benutzer) — buchen schließt laut
    # Rollenmatrix das Freigeben ein
    with (
        handelnde_person(db, config, Recht.BUCHEN, von) as person,
        sitzung(db)() as s,
    ):
        try:
            v = buche_kasse(s, wert, text, kasse, tag, beleg, konto, satz, person)
        except (KassenbuchError, JahrGesperrtError) as fehler:
            ende(str(fehler))
        stand = bestand(lade_kassenbuch(s))
        s.commit()
    console.print(
        f"[green]Nr. {v.nr}[/green] {v.datum:%d.%m.%Y} {escape(v.text)} "
        f"{betrag_de(v.betrag)} € — Bestand {betrag_de(stand)} €"
        + ("" if v.buchung_id else " [dim](Kontierung: accounti classify)[/dim]")
    )


@befehl.command("storno")
def storno(
    nr: int = typer.Argument(help="Nummer des Kassenvorgangs"),
    grund: str = typer.Option(..., "--grund", help="Warum storniert wird"),
    datum_text: str | None = typer.Option(None, "--datum", help="Datum (heute)"),
    von: str | None = typer.Option(
        None,
        help="Wer erfasst (mit eingerichteten Benutzern: der Benutzer, mit Rolle "
        "und Einmalcode)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Kassenvorgang stornieren (Gegeneintrag; das Original bleibt stehen)."""
    from accounti.abschluss.kassenbuch import KassenbuchError, storniere
    from accounti.anzeige import betrag_de
    from accounti.models.auth import Recht

    kasse = _kasse(config)
    tag = datum(datum_text, "--datum")
    # mit Benutzern: buchen (buchhalter) und Einmalcode; die Umkehrbuchung einer
    # freigegebenen Buchung ist ein Storno (Baustein 7)
    with (
        handelnde_person(db, config, Recht.BUCHEN, von) as person,
        sitzung(db)() as s,
    ):
        try:
            v = storniere(s, nr, grund, kasse, tag, person)
        except (KassenbuchError, JahrGesperrtError) as fehler:
            ende(str(fehler))
        s.commit()
    console.print(f"[green]Nr. {v.nr}[/green] {escape(v.text)} {betrag_de(v.betrag)} €")


@befehl.command("liste")
def liste(
    jahr: int = typer.Option(date.today().year, help="Jahr"),
    monat: int | None = typer.Option(None, help="nur dieser Monat"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,  # noqa: ARG001
) -> None:
    """Kassenbuch mit laufendem Bestand."""
    from accounti.abschluss.kassenbuch import verlauf
    from accounti.anzeige import betrag_de
    from accounti.db.repo_kasse import lade_kassenbuch

    with sitzung(db)() as s:
        buch = lade_kassenbuch(s)
    t = Table(title=f"Kassenbuch {jahr}" + (f"/{monat:02d}" if monat else ""))
    t.add_column("Nr")
    t.add_column("Datum", no_wrap=True)
    t.add_column("Text", overflow="fold")
    t.add_column("Einnahme", justify="right", no_wrap=True)
    t.add_column("Ausgabe", justify="right", no_wrap=True)
    t.add_column("Bestand", justify="right", no_wrap=True)
    for v, stand in verlauf(buch):
        if v.datum.year != jahr or (monat and v.datum.month != monat):
            continue
        t.add_row(
            str(v.nr),
            f"{v.datum:%d.%m.%Y}",
            escape(v.text),
            betrag_de(v.betrag) if v.betrag > 0 else "",
            betrag_de(-v.betrag) if v.betrag < 0 else "",
            betrag_de(stand),
        )
    console.print(t)


@befehl.command("bestand")
def bestand_befehl(
    datum_text: str | None = typer.Option(None, "--datum", help="Stichtag (heute)"),
    gezaehlt: str | None = typer.Option(None, help="Kassensturz: gezählter Bestand"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,  # noqa: ARG001
) -> None:
    """Soll-Bestand zum Stichtag, mit --gezaehlt als Kassensturz."""
    from accounti.abschluss.kassenbuch import bestand
    from accounti.anzeige import betrag_de
    from accounti.db.repo_kasse import lade_kassenbuch

    stichtag = datum(datum_text, "--datum")
    with sitzung(db)() as s:
        soll = bestand(lade_kassenbuch(s), stichtag)
    console.print(
        f"Kassenbestand laut Kassenbuch {stichtag:%d.%m.%Y}: {betrag_de(soll)} €"
    )
    if gezaehlt is not None:
        ist = betrag(gezaehlt, "--gezaehlt")
        differenz = ist - soll
        farbe = "green" if differenz == 0 else "red"
        console.print(
            f"Gezählt {betrag_de(ist)} € — [{farbe}]Differenz {betrag_de(differenz)} €"
            f"[/{farbe}]"
            + ("" if differenz == 0 else " (Kassendifferenz begründen und buchen)")
        )
