"""CLI ``accounti aufgaben`` — Aufgaben & Rückfragen (Baustein 8)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import TYPE_CHECKING, TypeVar

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from accounti.aufgaben.einstellungen import AufgabenEinstellungen
    from accounti.aufgaben.prueflaeufe import Laufergebnis
    from accounti.models.aufgaben import Aufgabe, Kommentar

NAME = "aufgaben"
befehl = typer.Typer(
    help="Aufgaben & Rückfragen: Liste, Zuweisung, Rückfragen, Prüfläufe, Erinnerung.",
    no_args_is_help=True,
)

T = TypeVar("T")

STICHTAG_OPTION = typer.Option(
    None, "--stichtag", help="Stichtag JJJJ-MM-TT (Standard: heute)"
)
VON_OPTION = typer.Option(None, "--von", help="Wer (Standard: aufgaben.ich / Login)")
LAUF_OPTION = typer.Option(
    None, "--lauf", help="nur diese Prüfläufe (mehrfach möglich)"
)


def _fehler(text: str) -> typer.Exit:
    console.print(f"[red]{escape(text)}[/red]")
    return typer.Exit(1)


def _einstellungen(config: str) -> AufgabenEinstellungen:
    from accounti.aufgaben.einstellungen import lade_aufgaben_einstellungen
    from accounti.konfiguration import KonfigurationError

    try:
        return lade_aufgaben_einstellungen(config)
    except KonfigurationError as fehler:
        raise _fehler(str(fehler)) from fehler


@contextmanager
def _sitzung(db: str) -> Iterator[Session]:
    from accounti.db import init_db, session_factory

    engine, make_session = session_factory(db)
    init_db(engine)
    try:
        with make_session() as s:
            yield s
    finally:
        engine.dispose()


def _ausfuehren(db: str, schritt: Callable[[Session], T]) -> T:
    """Führt einen Schritt in einer Sitzung aus und committet; Fehler → Exit 1."""
    from accounti.aufgaben.fehler import AufgabenError

    with _sitzung(db) as s:
        try:
            ergebnis = schritt(s)
        except AufgabenError as fehler:
            raise _fehler(str(fehler)) from fehler
        s.commit()
        return ergebnis


def _stichtag(text: str | None) -> date:
    if text is None:
        return date.today()
    try:
        return date.fromisoformat(text)
    except ValueError as fehler:
        raise _fehler(f"Stichtag {text!r} bitte als JJJJ-MM-TT angeben") from fehler


def _von(von: str | None, einstellungen: AufgabenEinstellungen) -> str:
    from accounti.aufgaben.zustaendigkeit import wer_bin_ich

    return von or wer_bin_ich(einstellungen)


def _faellig_text(a: Aufgabe, heute: date) -> str:
    from accounti.anzeige import datum_de

    if a.faellig_am is None:
        return "—"
    text = datum_de(a.faellig_am)
    if a.aktiv and a.faellig_am < heute:
        return f"[red]{text}[/red]"
    return text


# ---------------------------------------------------------------------------
# Liste und Einzelansicht
# ---------------------------------------------------------------------------


@befehl.command("liste")
def liste(
    alle: bool = typer.Option(
        False, "--alle/--offen", help="auch erledigte und hinfällige (Standard: offen)"
    ),
    zustaendig: str | None = typer.Option(
        None, "--zustaendig", help="Benutzer oder 'ich' (inkl. eigener Rollen)"
    ),
    unzugewiesen: bool = typer.Option(
        False, "--unzugewiesen", help="nur die gemeinsame Liste"
    ),
    art: str | None = typer.Option(None, "--art", help="z.B. beleg_fehlt"),
    faellig: bool = typer.Option(
        False, "--faellig", help="nur heute oder früher fällig"
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Aufgaben anzeigen — unzugewiesene stehen in der gemeinsamen Liste."""
    from accounti.aufgaben.zustaendigkeit import gemeinsame_liste, ist_zustaendig
    from accounti.db.repo_aufgaben import lade_aufgaben
    from accounti.models.aufgaben import AKTIVE_STATUS

    einstellungen = _einstellungen(config)
    heute = date.today()
    with _sitzung(db) as s:
        aufgaben = lade_aufgaben(s, status=None if alle else AKTIVE_STATUS, art=art)
    gemeinsam = gemeinsame_liste(aufgaben)
    wer = None
    if zustaendig is not None:
        wer = _von(None, einstellungen) if zustaendig == "ich" else zustaendig
        aufgaben = [a for a in aufgaben if ist_zustaendig(a, wer, einstellungen)]
    if unzugewiesen:
        aufgaben = [a for a in aufgaben if a.unzugewiesen]
    if faellig:
        aufgaben = [a for a in aufgaben if a.faellig_am and a.faellig_am <= heute]
    aufgaben.sort(key=lambda a: (a.faellig_am or date.max, -a.prioritaet.rang, a.nr))

    if not aufgaben:
        console.print(
            f"[dim]Keine Aufgaben{f' für {escape(wer)}' if wer else ''}.[/dim]"
        )
    else:
        tabelle = Table(title="Aufgaben")
        tabelle.add_column("Nr", justify="right", no_wrap=True)
        tabelle.add_column("Art", no_wrap=True)
        tabelle.add_column("Titel", overflow="fold")
        tabelle.add_column("Zuständig", no_wrap=True)
        tabelle.add_column("Fällig", no_wrap=True)
        tabelle.add_column("Status", no_wrap=True)
        for a in aufgaben:
            prio = " [red]![/red]" if a.prioritaet.value == "hoch" else ""
            tabelle.add_row(
                str(a.nr),
                a.art,
                escape(a.titel) + prio,
                escape(a.zustaendigkeit),
                _faellig_text(a, heute),
                a.status.value,
            )
        console.print(tabelle)
    if wer is not None and gemeinsam and not unzugewiesen:
        n = len(gemeinsam)
        console.print(
            f"{n} {'Aufgabe' if n == 1 else 'Aufgaben'} in der gemeinsamen Liste — "
            "accounti aufgaben liste --unzugewiesen"
        )


def _kommentarzeile(k: Kommentar) -> str:
    kopf = f"  {k.erstellt_am:%d.%m.%Y %H:%M}  {escape(k.autor)}"
    if k.art.value == "ereignis":
        return f"{kopf}  [dim]{escape(k.text)}[/dim]"
    art = "Rückfrage" if k.art.value == "rueckfrage" else "Kommentar"
    return f"{kopf}  {art}: {escape(k.text)}"


@befehl.command("zeige")
def zeige(
    nr: str = typer.Argument(help="Nummer der Aufgabe (oder Anfang der ID)"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Eine Aufgabe mit Bezugsobjekt und Verlauf."""
    from accounti.anzeige import datum_de
    from accounti.aufgaben.erzeugung import finde_aufgabe
    from accounti.aufgaben.objekte import beschreibe
    from accounti.db.repo_aufgaben import lade_kommentare

    _einstellungen(config)

    def lesen(s: Session) -> tuple[Aufgabe, str, list[Kommentar], list[Kommentar]]:
        a = finde_aufgabe(s, nr)
        verlauf = lade_kommentare(s, aufgabe_id=a.id)
        am_objekt = [
            k
            for k in lade_kommentare(s, objekt=a.objekt)
            if k.aufgabe_id != a.id and k.art.value != "ereignis"
        ]
        return a, beschreibe(s, a.objekt), verlauf, am_objekt

    a, bezug, verlauf, am_objekt = _ausfuehren(db, lesen)
    console.print(
        f"[bold]Aufgabe #{a.nr}[/bold] · {a.art} · {a.status.value} · "
        f"Priorität {a.prioritaet.value}"
    )
    console.print(f"  {escape(a.titel)}")
    if a.beschreibung:
        console.print(f"  [dim]{escape(a.beschreibung)}[/dim]")
    console.print(f"  Bezug:      {escape(bezug)}")
    console.print(f"  Zuständig:  {escape(a.zustaendigkeit)}")
    console.print(f"  Fällig:     {datum_de(a.faellig_am)}")
    console.print(f"  Erzeugt:    {escape(a.erzeugt_von)}, {a.erstellt_am:%d.%m.%Y}")
    if a.quittiert_von:
        console.print(f"  Erledigt:   von {escape(a.quittiert_von)}")
    if a.abschluss_grund:
        console.print(f"  Grund:      {escape(a.abschluss_grund)}")
    console.print("[bold]Verlauf[/bold]")
    for k in verlauf:
        console.print(_kommentarzeile(k))
    if am_objekt:
        console.print("[bold]Am Bezugsobjekt[/bold]")
        for k in am_objekt:
            console.print(_kommentarzeile(k))


@befehl.command("objekt")
def objekt(
    typ: str = typer.Argument(help="beleg, buchung, transaktion, kontakt, …"),
    schluessel: str = typer.Argument(help="Anfang der ID, Personenkonto oder IBAN"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Alles zu einem Objekt: Rückfragen, Kommentare und Aufgaben."""
    from accounti.aufgaben.erzeugung import aufgaben_zu, kommentare_zu
    from accounti.aufgaben.objekte import beschreibe, loese_auf

    _einstellungen(config)

    def lesen(s: Session) -> tuple[str, list[Aufgabe], list[Kommentar]]:
        o = loese_auf(s, typ, schluessel)
        return beschreibe(s, o), aufgaben_zu(s, o), kommentare_zu(s, o)

    bezug, aufgaben, kommentare = _ausfuehren(db, lesen)
    console.print(f"[bold]{escape(bezug)}[/bold]")
    if aufgaben:
        console.print("[bold]Aufgaben[/bold]")
        for a in aufgaben:
            console.print(
                f"  #{a.nr}  {a.art} · {a.status.value} · {escape(a.zustaendigkeit)}"
                f" · {escape(a.titel)}"
            )
    console.print(f"[bold]Rückfragen und Kommentare[/bold] ({len(kommentare)})")
    for k in kommentare:
        console.print(_kommentarzeile(k))


# ---------------------------------------------------------------------------
# Bearbeiten
# ---------------------------------------------------------------------------


@befehl.command("zuweisen")
def zuweisen(
    nr: str = typer.Argument(help="Nummer der Aufgabe"),
    an: str | None = typer.Option(None, "--an", help="Benutzer"),
    rolle: str | None = typer.Option(None, "--rolle", help="Rolle"),
    frei: bool = typer.Option(False, "--frei", help="zurück in die gemeinsame Liste"),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """An einen Benutzer, eine Rolle oder zurück in die gemeinsame Liste."""
    from accounti.aufgaben.erzeugung import weise_zu

    if frei == (an is not None or rolle is not None):
        raise _fehler("Genau eins angeben: --an NAME, --rolle ROLLE oder --frei")
    wer = _von(von, _einstellungen(config))
    a = _ausfuehren(db, lambda s: weise_zu(s, nr, an=an, rolle=rolle, von=wer))
    if a.unzugewiesen:
        console.print(f"#{a.nr} zurück in die gemeinsame Liste")
    else:
        console.print(f"#{a.nr} zugewiesen an {escape(a.zustaendigkeit)}")


@befehl.command("status")
def status(
    nr: str = typer.Argument(help="Nummer der Aufgabe"),
    neuer_status: str = typer.Argument(help="offen, in_arbeit oder wartet"),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Status setzen: offen, in_arbeit oder wartet (erledigen: 'erledigen')."""
    from accounti.aufgaben.erzeugung import setze_status
    from accounti.models.aufgaben import AufgabenStatus

    erlaubt = ("offen", "in_arbeit", "wartet")
    if neuer_status not in erlaubt:
        raise _fehler(
            f"Status '{neuer_status}' unbekannt — erlaubt: {', '.join(erlaubt)}"
        )
    wer = _von(von, _einstellungen(config))
    a = _ausfuehren(
        db, lambda s: setze_status(s, nr, AufgabenStatus(neuer_status), von=wer)
    )
    console.print(f"#{a.nr} {a.status.value}")


@befehl.command("erledigen")
def erledigen(
    nr: str = typer.Argument(help="Nummer der Aufgabe"),
    text: str | None = typer.Option(None, "--text", help="Begründung / Ergebnis"),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Als erledigt abschließen — ein späterer Prüflauf öffnet sie nicht wieder.

    „Beleg fehlt“ nur mit Begründung (--text), z.B. warum kein Beleg nötig ist."""
    from accounti.aufgaben.erzeugung import erledige

    wer = _von(von, _einstellungen(config))
    a = _ausfuehren(db, lambda s: erledige(s, nr, von=wer, text=text))
    console.print(f"[green]#{a.nr} erledigt[/green] ({escape(wer)})")


@befehl.command("kommentieren")
def kommentieren(
    nr: str | None = typer.Argument(None, help="Nummer der Aufgabe"),
    text: str = typer.Option(..., "--text", help="Kommentar"),
    beleg: str | None = typer.Option(
        None, "--beleg", help="statt einer Aufgabe direkt am Beleg (Anfang der ID)"
    ),
    objekt: str | None = typer.Option(
        None, "--objekt", help="statt einer Aufgabe an einem Objekt: typ:schlüssel"
    ),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Kommentar an einer Aufgabe oder direkt an einem Objekt (z.B. Beleg)."""
    from accounti.aufgaben.erzeugung import kommentiere
    from accounti.aufgaben.fehler import AufgabenError
    from accounti.aufgaben.objekte import loese_auf
    from accounti.models.aufgaben import Objekt

    wer = _von(von, _einstellungen(config))

    def schreiben(s: Session) -> Kommentar:
        ziel: Objekt | None = None
        if beleg is not None:
            ziel = loese_auf(s, "beleg", beleg)
        elif objekt is not None:
            try:
                roh = Objekt.aus_text(objekt)
            except ValueError as fehler:
                raise AufgabenError(str(fehler)) from fehler
            ziel = loese_auf(s, roh.typ, roh.id)
        return kommentiere(s, text, wer, aufgabe=nr, objekt=ziel)

    k = _ausfuehren(db, schreiben)
    console.print(f"Kommentar an {escape(str(k.objekt))} gespeichert.")


@befehl.command("rueckfrage")
def rueckfrage(
    schluessel: str = typer.Argument(help="Beleg (Anfang der ID)"),
    text: str = typer.Option(..., "--text", help="die Frage"),
    an: str | None = typer.Option(None, "--an", help="als Aufgabe für Benutzer"),
    rolle: str | None = typer.Option(None, "--rolle", help="als Aufgabe für Rolle"),
    als_aufgabe: bool = typer.Option(
        False, "--aufgabe", help="als Aufgabe in die gemeinsame Liste"
    ),
    typ: str = typer.Option("beleg", "--typ", help="Objekttyp, Standard beleg"),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Rückfrage am Beleg festhalten — dort später wiederzufinden."""
    from accounti.aufgaben.erzeugung import Rueckfrage, halte_rueckfrage_fest
    from accounti.aufgaben.objekte import beschreibe, loese_auf

    einstellungen = _einstellungen(config)
    wer = _von(von, einstellungen)

    def schreiben(s: Session) -> tuple[Rueckfrage, str]:
        ziel = loese_auf(s, typ, schluessel)
        r = halte_rueckfrage_fest(
            s,
            ziel,
            text,
            wer,
            an=an,
            rolle=rolle,
            als_aufgabe=als_aufgabe,
            einstellungen=einstellungen,
        )
        return r, beschreibe(s, ziel)

    r, bezug = _ausfuehren(db, schreiben)
    console.print(f"Rückfrage am {escape(bezug)} festgehalten.")
    if r.aufgabe is not None:
        console.print(
            f"Als Aufgabe #{r.aufgabe.nr} für {escape(r.aufgabe.zustaendigkeit)}."
        )


# ---------------------------------------------------------------------------
# Prüfläufe und Erinnerungen
# ---------------------------------------------------------------------------


def _pruefausgabe(ergebnisse: list[Laufergebnis]) -> None:
    for e in ergebnisse:
        g = e.abgleich
        console.print(
            f"{e.name}: {len(g.neu)} neu, {len(g.unveraendert)} unverändert, "
            f"{len(g.aktualisiert)} aktualisiert, {len(g.wieder_offen)} wieder offen, "
            f"{len(g.hinfaellig)} hinfällig"
            + (f", {len(g.abgeschlossen)} bleiben erledigt" if g.abgeschlossen else "")
            + (
                f", {len(g.uebersprungen)} gleichzeitig geändert (nächster Lauf)"
                if g.uebersprungen
                else ""
            )
        )
        for a in g.neu + g.wieder_offen:
            console.print(f"  [yellow]+[/yellow] #{a.nr} {escape(a.titel)}")
        for a in g.hinfaellig:
            console.print(
                f"  [green]✓[/green] #{a.nr} hinfällig: "
                f"{escape(a.abschluss_grund or '')}"
            )


def _pruefen(
    db: str,
    einstellungen: AufgabenEinstellungen,
    stichtag: date,
    laeufe: list[str] | None,
    zeitraum: str | None,
) -> list[Laufergebnis]:
    from accounti.aufgaben.prueflaeufe import fuehre_prueflaeufe_aus

    jetzt = datetime.combine(stichtag, datetime.now().time())
    return _ausfuehren(
        db,
        lambda s: fuehre_prueflaeufe_aus(
            s,
            einstellungen,
            stichtag=stichtag,
            namen=laeufe or None,
            zeitraum=zeitraum,
            jetzt=jetzt,
        ),
    )


@befehl.command("pruefen")
def pruefen(
    lauf: list[str] | None = LAUF_OPTION,
    zeitraum: str | None = typer.Option(None, "--zeitraum", help="JJJJ-MM"),
    stichtag: str | None = STICHTAG_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Prüfläufe: aus vorhandenen Daten Aufgaben erzeugen, Entfallenes schließen."""
    einstellungen = _einstellungen(config)
    _pruefausgabe(_pruefen(db, einstellungen, _stichtag(stichtag), lauf, zeitraum))


def _erinnern(
    db: str, config: str, einstellungen: AufgabenEinstellungen, stichtag: date
) -> bool:
    """Versendet die Tagesübersichten; True, wenn alles zugestellt wurde."""
    from accounti.aufgaben.benachrichtigung import (
        baue_kanaele,
        versende_tagesuebersichten,
    )

    kanaele, kanalfehler = baue_kanaele(einstellungen, config)
    for name, text in kanalfehler.items():
        console.print(f"[red]Kanal {name}: {escape(text)}[/red]")
    jetzt = datetime.combine(stichtag, datetime.now().time())
    lauf = _ausfuehren(
        db,
        lambda s: versende_tagesuebersichten(
            s,
            einstellungen,
            kanaele,
            stichtag=stichtag,
            jetzt=jetzt,
            kanalfehler=kanalfehler,
            sichern=s.commit,  # Gesendetes bleibt protokolliert, auch bei Abbruch
        ),
    )
    if not lauf.uebersichten:
        console.print(
            "[dim]Nichts zu melden — keine fälligen oder neuen Aufgaben.[/dim]"
        )
    for z in lauf.zustellungen:
        n = len(z.nummern)
        anzahl = f"{n} {'Aufgabe' if n == 1 else 'Aufgaben'}"
        if z.uebersprungen:
            console.print(
                f"[dim]{escape(z.empfaenger)}: {z.kanal} heute schon zugestellt[/dim]"
            )
        elif z.erfolgreich:
            console.print(
                f"[green]{escape(z.empfaenger)}: {z.kanal} an "
                f"{escape(z.adresse or '—')} — {anzahl}[/green]"
            )
        else:
            console.print(
                f"[red]{escape(z.empfaenger)}: {z.kanal} fehlgeschlagen — "
                f"{escape(z.fehler or '')}[/red]"
            )
    return not kanalfehler and all(z.erfolgreich for z in lauf.zustellungen)


@befehl.command("erinnern")
def erinnern(
    vorschau: bool = typer.Option(
        False, "--vorschau", help="Tagesübersichten nur anzeigen, nichts senden"
    ),
    stichtag: str | None = STICHTAG_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Fällige Erinnerungen als gebündelte Tagesübersicht je Empfänger versenden."""
    from accounti.aufgaben.benachrichtigung import stelle_zusammen

    einstellungen = _einstellungen(config)
    tag = _stichtag(stichtag)
    if vorschau:
        with _sitzung(db) as s:
            uebersichten = stelle_zusammen(s, einstellungen, tag)
        if not uebersichten:
            console.print("[dim]Nichts zu melden.[/dim]")
        for u in uebersichten:
            console.print(f"[bold]{escape(u.betreff())}[/bold]")
            console.print(escape(u.text()), highlight=False)
        return
    if not _erinnern(db, config, einstellungen, tag):
        raise typer.Exit(1)


@befehl.command("lauf")
def lauf(
    stichtag: str | None = STICHTAG_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Geplanter Lauf (Cron, nach 'accounti bank lauf'): prüfen, dann erinnern."""
    from accounti.betrieb.laufsperre import LaufLaeuftError, laufsperre

    einstellungen = _einstellungen(config)
    tag = _stichtag(stichtag)
    try:
        # je Datenbank höchstens ein aufgaben lauf — auch gegen Dienst lauf und REST
        with laufsperre(db, "aufgaben"):
            _pruefausgabe(_pruefen(db, einstellungen, tag, None, None))
            erinnert = _erinnern(db, config, einstellungen, tag)
    except LaufLaeuftError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(1) from fehler
    if not erinnert:
        raise typer.Exit(1)
