"""Befehlsgruppe ``accounti mahnwesen``: Mahnlauf, Mahnschreiben, Sperren, Zinsen."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from accounti.konfiguration import Firma
    from accounti.mahnwesen.konfiguration import MahnEinstellungen
    from accounti.models import Kontakt
    from accounti.models.mahnwesen import Mahnung

NAME = "mahnwesen"
befehl = typer.Typer(
    help="Mahnwesen: Mahnlauf, Mahnschreiben, Mahnsperre, Verzugszinsen.",
    no_args_is_help=True,
)

ARCHIV_OPTION = typer.Option("archiv/belege", help="Belegarchiv für die Mahn-PDFs")
PDF_OPTION = typer.Option(None, "--pdf", help="Mahnschreiben als PDF hierhin")
TEXT_OPTION = typer.Option(None, "--text", help="Mahnschreiben als Text hierhin")


def _zeile(text: str) -> None:
    console.print(text, soft_wrap=True)


def _fehler(text: str) -> typer.Exit:
    console.print(f"[red]{escape(text)}[/red]", soft_wrap=True)
    return typer.Exit(1)


def _einstellungen(config: str) -> MahnEinstellungen:
    from accounti.konfiguration import KonfigurationError
    from accounti.mahnwesen.konfiguration import lade_mahnwesen

    try:
        return lade_mahnwesen(config)
    except KonfigurationError as fehler:
        raise _fehler(str(fehler)) from fehler


def _firma(config: str) -> Firma:
    from accounti.konfiguration import KonfigurationError, lade_firma

    try:
        return lade_firma(config)
    except KonfigurationError as fehler:
        raise _fehler(f"Absender des Mahnschreibens: {fehler}") from fehler


@contextmanager
def _sitzung(db: str) -> Iterator[Session]:
    from accounti.db import init_db, session_factory

    engine, fabrik = session_factory(db)
    init_db(engine)
    with fabrik() as s:
        yield s
    engine.dispose()


def _kontakt(s: Session, schluessel: str) -> Kontakt:
    from accounti.db.repository import lade_kontakt

    try:
        return lade_kontakt(s, schluessel)
    except ValueError as fehler:
        raise _fehler(str(fehler)) from fehler


def _mahnung(s: Session, nr: int) -> Mahnung:
    from accounti.db.repo_mahnwesen import lade_mahnung

    try:
        return lade_mahnung(s, nr)
    except ValueError as fehler:
        raise _fehler(str(fehler)) from fehler


def _kurz(m: Mahnung, kunde: str) -> str:
    from accounti.anzeige import betrag_de

    teile = [f"{betrag_de(m.restbetrag)} € offen"]
    if m.zinsen:
        teile.append(f"Zinsen {betrag_de(m.zinsen)} €")
    if m.pauschale:
        teile.append(f"Pauschale {betrag_de(m.pauschale)} €")
    if m.gebuehren:
        teile.append(f"Gebühren {betrag_de(m.gebuehren)} €")
    return (
        f"Mahnung {m.nr} · {escape(m.stufe_name)} · {escape(m.belegnummer or '—')} · "
        f"{escape(kunde)} · {', '.join(teile)} · [bold]{betrag_de(m.summe)} €[/bold]"
    )


@befehl.command("lauf")
def lauf(
    stichtag: str | None = typer.Option(None, help="Mahndatum JJJJ-MM-TT (heute)"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Überfällige Forderungen prüfen und Mahnungen als Entwurf anlegen."""
    from accounti.anzeige import datum_de
    from accounti.db.repository import lade_kontakte
    from accounti.mahnwesen.lauf import mahnlauf

    e = _einstellungen(config)
    try:
        tag = date.fromisoformat(stichtag) if stichtag else date.today()
    except ValueError as fehler:
        raise _fehler("--stichtag: Datum im Format JJJJ-MM-TT erwartet") from fehler
    with _sitzung(db) as s:
        ergebnis = mahnlauf(s, tag, e)
        namen = {k.id: k.name for k in lade_kontakte(s)}
        s.commit()
    _zeile(f"[bold]Mahnlauf zum {datum_de(tag)}[/bold]")
    if not ergebnis.mahnungen:
        _zeile("[dim]Keine neuen Mahnungen.[/dim]")
    for m in ergebnis.mahnungen:
        _zeile(_kurz(m, namen.get(m.kontakt_id, "?")))
        art = "Unternehmer" if m.unternehmer else "Verbraucher"
        _zeile(f"     [dim]{art}: {escape(m.einstufung)}[/dim]")
        if m.verzug_grund:
            ab = f" ab {datum_de(m.verzug_ab)}" if m.verzug_ab else ""
            _zeile(f"     [dim]Verzug{ab}: {escape(m.verzug_grund)}[/dim]")
    if ergebnis.ausnahmen:
        _zeile("[yellow]Nicht gemahnt:[/yellow]")
        for a in ergebnis.ausnahmen:
            name = a.kontakt.name if a.kontakt else "?"
            _zeile(
                f"  {escape(a.posten.belegnummer or '—')} · {escape(name)} — "
                f"{escape(a.grund)}"
            )
    if ergebnis.mahnungen:
        _zeile(
            "[dim]Weiter: accounti mahnwesen zeigen <Nr> → versenden <Nr> --pdf "
            "mahnung.pdf (oder --text, --email)[/dim]"
        )


@befehl.command("liste")
def liste(
    status: str | None = typer.Option(None, help="entwurf, versendet, verworfen"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Mahnungen mit Stufe, Status und Gesamtbetrag."""
    from rich.table import Table

    from accounti.anzeige import betrag_de, datum_de
    from accounti.db.repo_mahnwesen import lade_mahnungen
    from accounti.db.repository import lade_kontakte
    from accounti.models.mahnwesen import MahnungStatus

    try:
        filter_status = {MahnungStatus(status)} if status else None
    except ValueError as fehler:
        raise _fehler("--status: entwurf, versendet oder verworfen") from fehler
    with _sitzung(db) as s:
        mahnungen = lade_mahnungen(s, filter_status)
        namen = {k.id: k.name for k in lade_kontakte(s)}
    if not mahnungen:
        _zeile("[dim]Keine Mahnungen.[/dim]")
        return
    tabelle = Table(title="Mahnungen")
    for spalte in ("Nr.", "Datum", "Stufe", "Rechnung", "Kunde", "Gesamt", "Status"):
        tabelle.add_column(spalte, no_wrap=spalte != "Kunde")
    for m in mahnungen:
        tabelle.add_row(
            str(m.nr),
            datum_de(m.datum),
            escape(m.stufe_name),
            escape(m.belegnummer or "—"),
            escape(namen.get(m.kontakt_id, "?")),
            betrag_de(m.summe),
            m.status.value,
        )
    console.print(tabelle)


@befehl.command("zeigen")
def zeigen(
    nr: int = typer.Argument(help="Nummer der Mahnung"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Das Mahnschreiben als Text."""
    from accounti.mahnwesen.schreiben import mahntext

    e = _einstellungen(config)
    with _sitzung(db) as s:
        m = _mahnung(s, nr)
        k = _kontakt(s, str(m.kontakt_id))
    firma = _firma(config)
    _zeile(f"[dim]Mahnung {m.nr} · {m.status.value}[/dim]")
    console.print(escape(mahntext(m, k, firma, e)), soft_wrap=True, highlight=False)


@befehl.command("versenden")
def versenden(
    nr: int = typer.Argument(help="Nummer der Mahnung"),
    pdf: Path | None = PDF_OPTION,
    text: Path | None = TEXT_OPTION,
    email: bool = typer.Option(False, "--email", help="per E-Mail (Abschnitt versand)"),
    an: str | None = typer.Option(
        None, "--an", help="E-Mail-Empfänger (sonst Kontakt)"
    ),
    am: str | None = typer.Option(
        None,
        "--am",
        help="Versandtag JJJJ-MM-TT (heute), z.B. wenn der Brief gestern zur Post ging",
    ),
    archiv: str = ARCHIV_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Mahnung versenden — erst dann zählt die Mahnstufe am Posten hoch."""
    from datetime import datetime

    from accounti.belege.archiv import BelegArchiv
    from accounti.erechnung.versand import SmtpVersand, lade_versand
    from accounti.konfiguration import KonfigurationError
    from accounti.mahnwesen.lauf import MahnError
    from accounti.mahnwesen.versand import Versandauftrag, versende_mahnung

    e = _einstellungen(config)
    jetzt = datetime.now().replace(microsecond=0)
    if am is not None:
        try:
            tag = date.fromisoformat(am)
        except ValueError as fehler:
            raise _fehler("--am: Datum im Format JJJJ-MM-TT erwartet") from fehler
        if tag > jetzt.date():
            raise _fehler(f"--am: {am} liegt in der Zukunft")
        if email and tag != jetzt.date():
            raise _fehler("--am: E-Mails gehen heute hinaus — --am nur für Briefe")
        jetzt = datetime.combine(tag, jetzt.time())
    auftrag = Versandauftrag(pdf=pdf, text=text, an=an)
    if email:
        try:
            versand = lade_versand(config)
        except KonfigurationError as fehler:
            raise _fehler(str(fehler)) from fehler
        auftrag.weg = SmtpVersand(versand)
        auftrag.absender = versand.absender
        auftrag.bcc = versand.bcc
    if pdf is None and text is None and not email:
        raise _fehler("Wohin? Mindestens --pdf, --text oder --email angeben.")
    firma = _firma(config)
    with _sitzung(db) as s:
        _mahnung(s, nr)
        try:
            m = versende_mahnung(
                s, nr, firma, e, auftrag, BelegArchiv(archiv), jetzt=jetzt
            )
        except MahnError as fehler:
            raise _fehler(str(fehler)) from fehler
        s.commit()
    ziele = [str(x) for x in (pdf, text) if x is not None]
    if email:
        ziele.append(f"E-Mail an {an or 'Kontaktadresse'}")
    _zeile(
        f"[green]Mahnung {m.nr} versendet[/green] ({escape(', '.join(ziele))}) — "
        f"Posten {escape(m.belegnummer or '—')} hat jetzt Mahnstufe {m.stufe}."
    )


@befehl.command("verwerfen")
def verwerfen(
    nr: int = typer.Argument(help="Nummer der Mahnung"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Mahnentwurf verwerfen (z.B. weil inzwischen gezahlt wurde)."""
    from accounti.mahnwesen.lauf import MahnError, verwerfe

    with _sitzung(db) as s:
        _mahnung(s, nr)
        try:
            verwerfe(s, nr)
        except MahnError as fehler:
            raise _fehler(str(fehler)) from fehler
        s.commit()
    _zeile(f"Mahnung {nr} verworfen.")


@befehl.command("sperre")
def sperre(
    kontakt: str = typer.Argument(help="Debitorenkonto oder Anfang der ID"),
    grund: str | None = typer.Option(None, "--grund", help="Grund der Mahnsperre"),
    aufheben: bool = typer.Option(False, "--aufheben", help="Sperre aufheben"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Kunden vom Mahnlauf ausnehmen (Mahnsperre) oder die Sperre aufheben."""
    from accounti.db.repo_mahnwesen import lade_mahnkontakte, speichere_mahnkontakt
    from accounti.models.mahnwesen import MahnKontakt

    if not aufheben and not (grund or "").strip():
        raise _fehler("Eine Mahnsperre braucht einen Grund (--grund).")
    with _sitzung(db) as s:
        k = _kontakt(s, kontakt)
        vorher = lade_mahnkontakte(s).get(k.id) or MahnKontakt(kontakt_id=k.id)
        speichere_mahnkontakt(
            s,
            vorher.model_copy(
                update={
                    "mahnsperre": not aufheben,
                    "sperrgrund": None if aufheben else (grund or "").strip(),
                }
            ),
        )
        s.commit()
    if aufheben:
        _zeile(f"Mahnsperre für {escape(k.name)} aufgehoben.")
    else:
        _zeile(
            f"[yellow]Mahnsperre[/yellow] für {escape(k.name)}: {escape(grund or '')}"
        )


@befehl.command("kunde")
def kunde(
    kontakt: str = typer.Argument(help="Debitorenkonto oder Anfang der ID"),
    unternehmer: bool = typer.Option(False, "--unternehmer", help="B2B: + 9 Punkte"),
    verbraucher: bool = typer.Option(False, "--verbraucher", help="B2C: + 5 Punkte"),
    offen: bool = typer.Option(False, "--offen", help="Einstufung entfernen"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Kunden als Unternehmer oder Verbraucher einstufen (Verzugszins, Pauschale)."""
    from accounti.db.repo_mahnwesen import lade_mahnkontakte, speichere_mahnkontakt
    from accounti.models.mahnwesen import MahnKontakt

    if sum((unternehmer, verbraucher, offen)) != 1:
        raise _fehler("Genau eine Angabe: --unternehmer, --verbraucher oder --offen")
    wert = None if offen else unternehmer
    with _sitzung(db) as s:
        k = _kontakt(s, kontakt)
        vorher = lade_mahnkontakte(s).get(k.id) or MahnKontakt(kontakt_id=k.id)
        speichere_mahnkontakt(s, vorher.model_copy(update={"unternehmer": wert}))
        s.commit()
    art = {None: "nicht eingestuft", True: "Unternehmer", False: "Verbraucher"}[wert]
    _zeile(f"{escape(k.name)}: {art}")


@befehl.command("basiszins")
def basiszins(
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Basiszinssätze nach § 247 BGB mit Gültigkeitszeitraum."""
    from rich.table import Table

    from accounti.anzeige import datum_de
    from accounti.mahnwesen.basiszins import QUELLE, STAND

    e = _einstellungen(config)
    tabelle = Table(title="Basiszinssatz nach § 247 BGB")
    for spalte in ("gültig ab", "bis", "Basiszins", "B2C (+5)", "B2B (+9)"):
        tabelle.add_column(spalte, no_wrap=True, justify="right")

    def prozent(wert: object) -> str:
        return f"{wert:.2f} %".replace(".", ",")

    for s in reversed(e.basiszinstabelle()):
        tabelle.add_row(
            datum_de(s.ab),
            datum_de(s.bis),
            prozent(s.satz),
            prozent(s.satz + 5),
            prozent(s.satz + 9),
        )
    console.print(tabelle)
    _zeile(
        f"Quelle: {QUELLE} (Stand {datum_de(STAND)}); neue Sätze in "
        "mahnwesen.basiszinssaetze"
    )


@befehl.command("historie")
def historie(
    kontakt: str = typer.Argument(help="Debitorenkonto oder Anfang der ID"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Mahnungen eines Kunden mit Stufe, Datum und Versandweg."""
    from accounti.anzeige import betrag_de, datum_de
    from accounti.db.repo_mahnwesen import lade_mahnungen

    with _sitzung(db) as s:
        k = _kontakt(s, kontakt)
        mahnungen = lade_mahnungen(s, kontakt_id=k.id)
    _zeile(f"[bold]Mahnhistorie {escape(k.name)}[/bold] ({k.debitor_konto or '—'})")
    if not mahnungen:
        _zeile("[dim]Keine Mahnungen.[/dim]")
    for m in mahnungen:
        weg = f" per {m.versand_weg}" if m.versand_weg else ""
        _zeile(
            f"  {datum_de(m.datum)} · Mahnung {m.nr} · {escape(m.stufe_name)} · "
            f"{escape(m.belegnummer or '—')} · {betrag_de(m.summe)} € · "
            f"{m.status.value}{weg}"
        )
