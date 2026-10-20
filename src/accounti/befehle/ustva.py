"""``accounti ustva`` — Umsatzsteuer-Voranmeldung (Baustein 9)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy.orm import Session

    from accounti.elster.konfiguration import ElsterEinstellungen
    from accounti.elster.uebermittlung import Uebermittler
    from accounti.elster.ustva import Vorbereitung
    from accounti.elster.zahllast import Zahllastbuchung
    from accounti.konfiguration import Buchhaltung
    from accounti.models.elster import Meldeart, Modus, Uebermittlung
    from accounti.steuer.plausibilitaet import Befund
    from accounti.steuer.zeitraum import Zeitraum

ARCHIV_STANDARD = "archiv/belege"  # wie die Belege: ein Archiv für alles
ARCHIV_OPTION = typer.Option(ARCHIV_STANDARD, "--archiv", help="Archivverzeichnis")

NAME = "ustva"
befehl = typer.Typer(
    help="Umsatzsteuer-Voranmeldung: Kennziffern, Prüfung, Freigabe, Übermittlung."
)

PERIOD_OPTION = typer.Option(
    None, "--period", help="Zeitraum, z.B. 2026-08 oder 2026-Q3"
)
_ZEICHEN = {"fehler": "[red]✗ Fehler[/red]", "warnung": "[yellow]! Warnung[/yellow]"}


def euro(wert: object) -> str:
    """Bemessungsgrundlage in vollen Euro mit Tausenderpunkt."""
    from decimal import Decimal

    from accounti.anzeige import betrag_de

    if isinstance(wert, Decimal) and wert == wert.to_integral_value():
        return f"{int(wert):,}".replace(",", ".")
    return betrag_de(wert if isinstance(wert, Decimal) else None)


@dataclass
class Lauf:
    """Konfiguration eines Aufrufs — einmal geladen, Fehler klar gemeldet."""

    zeitraum: Zeitraum
    config: str
    buchhaltung: Buchhaltung
    einstellungen: ElsterEinstellungen
    ustid_max_alter_tage: int
    oss: bool

    def vorbereiten(self, s: Session) -> Vorbereitung:
        from accounti.elster.ustva import bereite_vor

        return bereite_vor(
            s,
            self.zeitraum,
            buchhaltung=self.buchhaltung,
            einstellungen=self.einstellungen,
            ustid_max_alter_tage=self.ustid_max_alter_tage,
            oss_aktiv=self.oss,
        )


def ende(fehler: object, kode: int = 2) -> NoReturn:
    console.print(f"[red]{escape(str(fehler))}[/red]")
    raise typer.Exit(kode)


@contextmanager
def sitzung(period: str | None, db: str, config: str) -> Iterator[tuple[Session, Lauf]]:
    """Konfiguration laden und eine Datenbanksitzung öffnen — oder klar beenden."""
    from accounti.db import init_db, session_factory
    from accounti.elster.konfiguration import lade_elster, lade_oss
    from accounti.konfiguration import (
        KonfigurationError,
        lade_buchhaltung,
        lade_ustid_pruefung,
    )
    from accounti.steuer.zeitraum import Zeitraum, ZeitraumError

    if period is None:
        ende("Zeitraum fehlt — z.B. --period 2026-08")
    try:
        lauf = Lauf(
            zeitraum=Zeitraum.lies(period),
            config=config,
            buchhaltung=lade_buchhaltung(config),
            einstellungen=lade_elster(config),
            ustid_max_alter_tage=lade_ustid_pruefung(config).max_alter_tage,
            oss=lade_oss(config),
        )
    except (ZeitraumError, KonfigurationError) as fehler:
        ende(fehler)
    engine, make_session = session_factory(db)
    init_db(engine)
    try:
        with make_session() as s:
            yield s, lauf
    finally:
        engine.dispose()


def vorbereitung(period: str | None, db: str, config: str) -> Vorbereitung:
    with sitzung(period, db, config) as (s, lauf):
        return lauf.vorbereiten(s)


def zeige_befunde(
    befunde: list[Befund],
    gesperrt: str = "Freigabe gesperrt",
    moeglich: str = "Freigabe möglich[/green] (accounti ustva freigeben)",
) -> None:
    from accounti.steuer.plausibilitaet import freigabe_gesperrt

    for b in befunde:
        zeichen = _ZEICHEN.get(b.schweregrad.value, "[dim]i Hinweis[/dim]")
        console.print(f"  {zeichen}  {escape(b.text)}")
    fehler = sum(1 for b in befunde if b.schweregrad.value == "fehler")
    if freigabe_gesperrt(befunde):
        console.print(
            f"[red bold]{gesperrt}:[/red bold] {fehler} Fehler — erst beheben"
        )
    else:
        console.print(f"[green]{moeglich}")


def zeige_kennziffern(v: Vorbereitung) -> None:
    from rich.table import Table

    from accounti.anzeige import betrag_de
    from accounti.steuer.voranmeldung import KENNZIFFERN_2026, Art

    va = v.voranmeldung
    tabelle = Table(title=f"Umsatzsteuer-Voranmeldung {v.zeitraum.text}")
    for spalte, ausrichtung in (
        ("Zeile", "right"),
        ("Kz", "right"),
        ("Bezeichnung", "left"),
        ("Bemessungsgrundlage", "right"),
        ("Steuer", "right"),
    ):
        tabelle.add_column(
            spalte,
            justify=ausrichtung,  # type: ignore[arg-type]
            overflow="fold",
        )
    werte = va.formularwerte()
    summen = [
        (37, "37", "Umsatzsteuer", va.umsatzsteuer),
        (45, "38–44", "Vorsteuer", va.vorsteuer),
    ]
    for kz in sorted(werte, key=lambda k: KENNZIFFERN_2026[k].zeile):
        k = KENNZIFFERN_2026[kz]
        while summen and summen[0][0] <= k.zeile:
            _, zeile, name, betrag = summen.pop(0)
            tabelle.add_row(zeile, "", name, "", betrag_de(betrag), style="bold")
        if kz == 83:
            continue
        if k.art is Art.BMG:
            steuer = betrag_de(va.steuer(kz)) if k.satz is not None else ""
            tabelle.add_row(
                str(k.zeile), str(kz), k.bezeichnung, euro(werte[kz]), steuer
            )
        else:
            tabelle.add_row(
                str(k.zeile), str(kz), k.bezeichnung, "", betrag_de(werte[kz])
            )
    art = "Überschuss (Erstattung)" if va.ist_erstattung else "Vorauszahlung"
    tabelle.add_row("50", "83", art, "", betrag_de(va.kz83), style="bold")
    console.print(tabelle)


def als_json(v: Vorbereitung) -> str:
    va = v.voranmeldung
    return json.dumps(
        {
            "zeitraum": str(v.zeitraum),
            "kennziffern": {str(kz): str(w) for kz, w in va.formularwerte().items()},
            "umsatzsteuer": str(va.umsatzsteuer),
            "vorsteuer": str(va.vorsteuer),
            "befunde": [
                {"regel": b.regel, "schweregrad": b.schweregrad.value, "text": b.text}
                for b in v.befunde
            ],
            "freigabe_gesperrt": v.gesperrt,
        },
        ensure_ascii=False,
        indent=2,
    )


@befehl.callback(invoke_without_command=True)
def ustva(
    ctx: typer.Context,
    period: str | None = PERIOD_OPTION,
    json_ausgabe: bool = typer.Option(False, "--json", help="Maschinenlesbar"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Kennziffern (Vordruck 2026) und Plausibilisierung eines Zeitraums."""
    if ctx.invoked_subcommand is not None:
        return
    v = vorbereitung(period, db, config)
    if json_ausgabe:
        typer.echo(als_json(v))
        return
    zeige_kennziffern(v)
    zeige_befunde(v.befunde)


@befehl.command("pruefen")
def pruefen(
    period: str | None = PERIOD_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Nur die Plausibilisierung — Exit 1, wenn die Freigabe gesperrt ist."""
    v = vorbereitung(period, db, config)
    console.print(f"[bold]Prüfung {v.zeitraum.text}[/bold]")
    zeige_befunde(v.befunde)
    if v.gesperrt:
        raise typer.Exit(1)


@befehl.command("freigeben")
def freigeben(
    period: str | None = PERIOD_OPTION,
    von: str = typer.Option(..., "--von", help="Wer gibt frei (Name)"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Werte des Zeitraums zur Abgabe freigeben — immer durch einen Menschen."""
    from accounti.anzeige import betrag_de
    from accounti.auth.cli import befehlsrecht_oder_ende
    from accounti.elster.freigabe import FreigabeError, gib_frei
    from accounti.models.auth import Recht

    # mit eingerichteten Benutzern: Rolle freigeber und Einmalcode (Baustein 10)
    befehlsrecht_oder_ende(db, config, Recht.STEUER_FREIGEBEN, von)
    with sitzung(period, db, config) as (s, lauf):
        v = lauf.vorbereiten(s)
        zeige_kennziffern(v)
        zeige_befunde(v.befunde)
        try:
            f = gib_frei(s, v, von)
        except FreigabeError as fehler:
            ende(fehler, 1)
        s.commit()
    console.print(
        f"[green]Freigegeben von {escape(f.freigegeben_von)}[/green] am "
        f"{f.zeitpunkt:%d.%m.%Y %H:%M} — Kz 83 {betrag_de(v.voranmeldung.kz83)} € "
        f"[dim](Werte-Hash {f.inhalt_hash[:12]}…)[/dim]"
    )
    console.print(f"Abgeben: accounti ustva uebermitteln --period {v.zeitraum}")


def zeige_uebermittlung(u: Uebermittlung, weg_grund: str) -> None:
    from accounti.anzeige import betrag_de

    farbe = "green" if u.erfolgreich else "red"
    console.print(f"[{farbe}]{escape(u.ergebnis)}[/{farbe}]")
    bericht = json.loads(u.pruefbericht)
    for zeile in [*bericht.get("intern", []), *bericht.get("hinweise", [])]:
        console.print(f"  [yellow]{escape(str(zeile))}[/yellow]")
    zeilen = [
        f"Modus {u.modus.value} · Weg {u.weg} ({escape(weg_grund)})",
        f"Kz {83 if u.art.value == 'UStVA' else 38} {betrag_de(u.betrag)} €"
        + (" · berichtigt (Kz 10)" if u.berichtigt else ""),
    ]
    if u.ticket:
        zeilen.append(f"Ticket {u.ticket}")
    if u.freigegeben_von:
        zeilen.append(f"freigegeben von {escape(u.freigegeben_von)}")
    zeilen.append(f"Protokoll Nr. {u.nr} · Datensatz {u.datensatz_hash[:12]}…")
    for zeile in zeilen:
        console.print(f"  {zeile}")
    if u.weg == "attrappe":
        console.print(
            "[yellow]Attrappe (elster.uebermittler) — es wurde nichts an ELSTER "
            "gesendet[/yellow]"
        )


def modus_fuer(
    s: Session, art: Meldeart, modus: Modus, uebermittler: Uebermittler | None
) -> Modus:
    """Spec 5: Testmodus ist der Default beim ersten Lauf — ohne erfolgreichen
    Prüf- oder Testfall-Lauf über diesen Weg wird nur geprüft."""
    from accounti.elster.ustva import ATTRAPPE, hat_testlauf
    from accounti.models.elster import Modus

    if (
        modus is not Modus.ECHT
        or uebermittler is None
        or uebermittler.weg == ATTRAPPE
        or hat_testlauf(s, art, uebermittler.weg)
    ):
        return modus
    console.print(
        f"[yellow]Erster Lauf über {escape(uebermittler.weg)}: Testmodus (Default beim "
        "ersten Lauf) — der Datensatz wird geprüft, nichts wird abgegeben. Zum "
        "Abgeben danach erneut aufrufen.[/yellow]"
    )
    return Modus.PRUEFUNG


def buche_zahllast_sicher(
    s: Session,
    u: Uebermittlung,
    buchhaltung: Buchhaltung,
    einstellungen: ElsterEinstellungen,
    steuernummer: str,
) -> tuple[Zahllastbuchung | None, str | None]:
    """Zahllast nach dem festgeschriebenen Protokoll — scheitert sie, bleibt der
    Nachweis, und ``accounti elster zahllast`` holt die Buchung nach."""
    from accounti.elster.zahllast import buche_zahllast

    try:
        z = buche_zahllast(
            s,
            u,
            buchhaltung=buchhaltung,
            einstellungen=einstellungen,
            steuernummer=steuernummer,
        )
        s.commit()
    except Exception as fehler:  # die Abgabe steht, nur die Buchung fehlt
        s.rollback()
        return None, f"{type(fehler).__name__}: {fehler}"
    return z, None


def melde_zahllast_fehler(fehler: str | None) -> None:
    if fehler is None:
        return
    console.print(
        f"[red]Zahllast nicht gebucht: {escape(fehler)}[/red] — die Abgabe steht im "
        "Protokoll; nachholen mit: accounti elster zahllast"
    )
    raise typer.Exit(1)


@befehl.command("uebermitteln")
def uebermitteln(
    period: str | None = PERIOD_OPTION,
    test: bool = typer.Option(
        False, "--test", help="Testmodus: Datensatz erzeugen und prüfen, nichts abgeben"
    ),
    testfall: bool = typer.Option(
        False, "--testfall", help="Mit Testmerker an ELSTER senden (wird gelöscht)"
    ),
    ausgabe: str | None = typer.Option(
        None, "--ausgabe", help="Datensatz zusätzlich in diese Datei schreiben"
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
    archiv: str = ARCHIV_OPTION,
) -> None:
    """Voranmeldung übermitteln — nur mit Freigabe; ``--test`` gibt nichts ab."""
    from pathlib import Path

    # Hinweis: ``elster.uebermittlung`` wird als Modul geladen, damit Tests die
    # Auswahl des Übermittlers ersetzen können.
    from accounti.belege.archiv import BelegArchiv
    from accounti.elster import uebermittlung
    from accounti.elster.konfiguration import KonfigurationError
    from accounti.elster.ustva import kontext_aus, uebermittle
    from accounti.models.elster import Meldeart, Modus
    from accounti.steuer.zeitraum import ZeitraumError

    if test and testfall:
        ende("--test und --testfall schließen sich aus")
    modus = Modus.PRUEFUNG if test else Modus.TESTFALL if testfall else Modus.ECHT
    with sitzung(period, db, config) as (s, lauf):
        try:
            kontext = kontext_aus(config, lauf.einstellungen)
        except KonfigurationError as fehler:
            ende(fehler)
        uebermittler, grund = uebermittlung.waehle_uebermittler(lauf.einstellungen)
        if uebermittler is None:
            console.print(f"[dim]{escape(grund)}[/dim]")
        modus = modus_fuer(s, Meldeart.USTVA, modus, uebermittler)
        v = lauf.vorbereiten(s)
        zeige_befunde(v.befunde)
        try:
            u = uebermittle(
                s,
                v,
                modus=modus,
                kontext=kontext,
                uebermittler=uebermittler,
                archiv=BelegArchiv(archiv),
            )
        except (uebermittlung.UebermittlungError, ZeitraumError) as fehler:
            ende(fehler, 1)
        s.commit()  # der Nachweis bleibt, was auch immer danach geschieht
        z, zahllast_fehler = buche_zahllast_sicher(
            s, u, lauf.buchhaltung, lauf.einstellungen, kontext.steuernummer
        )
    if ausgabe:
        Path(ausgabe).write_text(u.datensatz, encoding="utf-8")
        console.print(f"[dim]Datensatz → {escape(ausgabe)}[/dim]")
    zeige_uebermittlung(u, grund)
    if z is not None:
        zeige_zahllast(z)
    melde_zahllast_fehler(zahllast_fehler)
    if not u.erfolgreich:
        raise typer.Exit(1)


def zeige_zahllast(z: Zahllastbuchung) -> None:
    from accounti.anzeige import betrag_de, datum_de
    from accounti.models import PostenRichtung
    from accounti.models.elster import Meldeart

    art = "Erstattung" if z.betrag < 0 else "Zahllast"
    if z.art is Meldeart.DAUERFRIST:
        art = "Sondervorauszahlung"
    text = f"{art} {betrag_de(z.betrag)} €"
    if z.verrechnet:
        text += (
            f", davon {betrag_de(z.verrechnet)} € mit dem offenen Posten des Zeitraums "
            "verrechnet"
        )
    if z.posten is not None:
        richtung = (
            "offener Posten"
            if z.posten.richtung is PostenRichtung.VERBINDLICHKEIT
            else "Forderung (offener Posten)"
        )
        if z.verrechnet:
            text += f", Rest {betrag_de(z.posten.betrag)} €"
        text += (
            f" als {richtung} bei {escape(z.kontakt.name)} (Kreditor "
            f"{z.kontakt.kreditor_konto}), fällig {datum_de(z.posten.faellig_am)}"
        )
    console.print(f"{text} — gebucht {z.buchung.soll_konto} an {z.buchung.haben_konto}")


def _betrag(text: str | None, name: str) -> Decimal | None:
    """``39000``, ``39000.00`` oder ``39.000,00`` → Decimal."""
    from decimal import Decimal, InvalidOperation

    if text is None:
        return None
    roh = text.strip()
    if "," in roh:
        roh = roh.replace(".", "").replace(",", ".")
    try:
        return Decimal(roh)
    except InvalidOperation:
        ende(f"{name}: {text!r} ist kein Betrag")


@befehl.command("dauerfrist")
def dauerfrist(
    jahr: int = typer.Option(..., "--jahr", help="Jahr der Dauerfristverlängerung"),
    summe_vorjahr: str | None = typer.Option(
        None, "--summe-vorjahr", help="Summe der Vorauszahlungen (Kz 83) im Vorjahr"
    ),
    svz_vorjahr: str | None = typer.Option(
        None, "--svz-vorjahr", help="Im Vorjahr abgezogene Sondervorauszahlung"
    ),
    freigeben: bool = typer.Option(False, "--freigeben", help="Freigabe erteilen"),
    von: str | None = typer.Option(None, "--von", help="Wer gibt frei (Name)"),
    uebermitteln: bool = typer.Option(False, "--uebermitteln", help="Abgeben"),
    test: bool = typer.Option(False, "--test", help="Nur erzeugen und prüfen"),
    testfall: bool = typer.Option(False, "--testfall", help="Mit Testmerker senden"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
    archiv: str = ARCHIV_OPTION,
) -> None:
    """Dauerfristverlängerung mit Sondervorauszahlung (1/11) berechnen und anmelden."""
    from accounti.anzeige import betrag_de, datum_de
    from accounti.belege.archiv import BelegArchiv
    from accounti.db import init_db, session_factory
    from accounti.elster import uebermittlung
    from accounti.elster.dauerfrist import (
        DauerfristError,
        berechne_svz,
        gib_dauerfrist_frei,
        uebermittle_dauerfrist,
    )
    from accounti.elster.freigabe import FreigabeError
    from accounti.elster.konfiguration import KonfigurationError, lade_elster
    from accounti.elster.ustva import kontext_aus
    from accounti.konfiguration import lade_buchhaltung
    from accounti.models.elster import Meldeart, Modus
    from accounti.steuer.fristen import sondervorauszahlung_frist

    if test and testfall:
        ende("--test und --testfall schließen sich aus")
    if freigeben and von:
        from accounti.auth.cli import befehlsrecht_oder_ende
        from accounti.models.auth import Recht

        befehlsrecht_oder_ende(db, config, Recht.STEUER_FREIGEBEN, von)
    try:
        einstellungen = lade_elster(config)
        buchhaltung = lade_buchhaltung(config)
    except KonfigurationError as fehler:
        ende(fehler)
    summe = _betrag(summe_vorjahr, "--summe-vorjahr")
    vorjahr = _betrag(svz_vorjahr, "--svz-vorjahr")
    engine, make_session = session_factory(db)
    init_db(engine)
    try:
        with make_session() as s:
            try:
                svz = berechne_svz(s, jahr, einstellungen, summe, vorjahr)
            except DauerfristError as fehler:
                ende(fehler)
            console.print(f"[bold]Dauerfristverlängerung {jahr}[/bold]")
            if svz.betrag is None:
                console.print("  Quartalszahler: Antrag ohne Sondervorauszahlung")
            else:
                frist = sondervorauszahlung_frist(jahr, einstellungen.bundesland)
                console.print(
                    f"  Vorauszahlungen {jahr - 1}: {betrag_de(svz.summe_vorjahr)} € · "
                    f"Sondervorauszahlung {jahr - 1}: {betrag_de(svz.svz_vorjahr)} €"
                )
                console.print(
                    f"  Sondervorauszahlung {jahr} (Kz 38, 1/11): "
                    f"[bold]{betrag_de(svz.betrag)} €[/bold] — anzumelden bis "
                    f"{datum_de(frist.faellig_am)}"
                )
            if freigeben:
                try:
                    f = gib_dauerfrist_frei(s, svz, von or "")
                except FreigabeError as fehler:
                    ende(fehler, 1)
                s.commit()
                console.print(
                    f"[green]Freigegeben von {escape(f.freigegeben_von)}[/green]"
                )
            if not (uebermitteln or test or testfall):
                return
            try:
                kontext = kontext_aus(config, einstellungen)
            except KonfigurationError as fehler:
                ende(fehler)
            uebermittler, grund = uebermittlung.waehle_uebermittler(einstellungen)
            modus = (
                Modus.PRUEFUNG if test else Modus.TESTFALL if testfall else Modus.ECHT
            )
            modus = modus_fuer(s, Meldeart.DAUERFRIST, modus, uebermittler)
            try:
                u = uebermittle_dauerfrist(
                    s,
                    svz,
                    modus=modus,
                    kontext=kontext,
                    uebermittler=uebermittler,
                    archiv=BelegArchiv(archiv),
                )
            except uebermittlung.UebermittlungError as fehler:
                ende(fehler, 1)
            s.commit()
            z, zahllast_fehler = buche_zahllast_sicher(
                s, u, buchhaltung, einstellungen, kontext.steuernummer
            )
    finally:
        engine.dispose()
    zeige_uebermittlung(u, grund)
    if z is not None:
        zeige_zahllast(z)
    melde_zahllast_fehler(zahllast_fehler)
    if not u.erfolgreich:
        raise typer.Exit(1)
