"""Befehlsgruppe ``accounti zahlung``: Zahlungsvorschlag, Lauf, Freigabe, SEPA."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from accounti.models.zahlung import Zahlungslauf
    from accounti.zahlung.konfiguration import ZahlungEinstellungen
    from accounti.zahlung.vorschlag import Zahlungsvorschlag

NAME = "zahlung"
befehl = typer.Typer(
    help="Zahlungsverkehr: Vorschlag, Zahlungslauf, Freigabe, SEPA-Datei.",
    no_args_is_help=True,
)

VON_OPTION = typer.Option(
    None,
    "--von",
    help="Wer handelt (sonst ACCOUNTI_BENUTZER bzw. Anmeldename); beim Freigeben "
    "mit zahlung.vier_augen nicht erlaubt",
)
STICHTAG_OPTION = typer.Option(None, help="Ausführungstag JJJJ-MM-TT (heute)")
VORLAUF_OPTION = typer.Option(None, help="Planungshorizont in Tagen")
OHNE_SKONTO_OPTION = typer.Option(False, "--ohne-skonto", help="kein Skonto ziehen")
MIN_OPTION = typer.Option(None, "--min", help="Mindestbetrag je Posten")
MAX_OPTION = typer.Option(None, "--max", help="Höchstbetrag je Posten")
KONTAKT_OPTION = typer.Option(None, "--kontakt", help="nur diese Kreditoren (Konto)")
DATEI_OPTION = typer.Option(..., "--datei", help="Zieldatei, z.B. ueberweisung.xml")


def _fehler(text: str) -> typer.Exit:
    console.print(f"[red]{escape(text)}[/red]", soft_wrap=True)
    return typer.Exit(1)


def _zeile(text: str) -> None:
    console.print(text, soft_wrap=True)


def _datum(wert: str | None, name: str) -> date | None:
    if wert is None:
        return None
    try:
        return date.fromisoformat(wert)
    except ValueError as fehler:
        raise _fehler(f"{name}: Datum im Format JJJJ-MM-TT erwartet") from fehler


def _person(von: str | None) -> str:
    from accounti.zahlung.freigabe import person_standard

    return von or person_standard()


def _benutzer_oder_person(
    db: str, config: str, recht_name: str, von: str | None
) -> str:
    """Mit eingerichteten Benutzern: Recht und Einmalcode der handelnden Person —
    ins Protokoll kommt der Benutzer; ohne Benutzer wie bisher ``--von`` bzw.
    ``ACCOUNTI_BENUTZER``/Anmeldename."""
    from accounti.auth.cli import befehlsrecht_oder_ende
    from accounti.models.auth import Recht

    person = _person(von)
    benutzer = befehlsrecht_oder_ende(db, config, Recht(recht_name), person)
    return benutzer.name if benutzer is not None else person


def _einstellungen(config: str) -> ZahlungEinstellungen:
    from accounti.konfiguration import KonfigurationError
    from accounti.zahlung.konfiguration import lade_zahlung

    try:
        return lade_zahlung(config)
    except KonfigurationError as fehler:
        raise _fehler(str(fehler)) from fehler


@contextmanager
def _sitzung(db: str) -> Iterator[Session]:
    from accounti.db import init_db, session_factory

    engine, fabrik = session_factory(db)
    init_db(engine)
    with fabrik() as s:
        yield s
    engine.dispose()


def _vorschlag(
    s: Session,
    e: ZahlungEinstellungen,
    stichtag: date,
    kontakte: list[str] | None,
) -> Zahlungsvorschlag:
    from accounti.db.repository import lade_kontakt
    from accounti.zahlung.vorschlag import lade_vorschlag

    ids = None
    if kontakte:
        try:
            ids = {lade_kontakt(s, k).id for k in kontakte}
        except ValueError as fehler:
            raise _fehler(str(fehler)) from fehler
    return lade_vorschlag(s, stichtag, e, ids)


def _mit_filtern(
    e: ZahlungEinstellungen,
    vorlauf: int | None,
    ohne_skonto: bool,
    minimum: float | None,
    maximum: float | None,
) -> ZahlungEinstellungen:
    aenderung: dict[str, object] = {}
    if vorlauf is not None:
        aenderung["vorlauf_tage"] = vorlauf
    if ohne_skonto:
        aenderung["skonto_ziehen"] = False
    if minimum is not None:
        aenderung["mindestbetrag"] = Decimal(str(minimum))
    if maximum is not None:
        aenderung["hoechstbetrag"] = Decimal(str(maximum))
    return e.model_copy(update=aenderung)


def _zeige_vorschlag(v: Zahlungsvorschlag, vorlauf: int) -> None:
    from accounti.anzeige import betrag_de, datum_de

    _zeile(
        f"[bold]Zahlungsvorschlag zum {datum_de(v.stichtag)}[/bold] "
        f"(Horizont {vorlauf} Tage)"
    )
    if not v.positionen:
        _zeile("[dim]Nichts zu zahlen.[/dim]")
    for i, pos in enumerate(v.positionen, start=1):
        k, p = pos.kontakt, pos.posten
        skonto = f" (Skonto {betrag_de(pos.skonto)} €)" if pos.skonto else ""
        _zeile(
            f"{i:>3}. {escape(p.belegnummer or '—')} · {escape(k.name)} "
            f"({k.kreditor_konto or '—'}) · [bold]{betrag_de(pos.betrag)} €[/bold]"
            f"{skonto}"
        )
        _zeile(f"     [dim]{escape(pos.grund)}[/dim]")
    if v.positionen:
        _zeile(
            f"Summe {betrag_de(v.summe)} € · Skonto {betrag_de(v.skonto_summe)} € · "
            f"{len(v.positionen)} Posten"
        )
    if v.ausgeschlossen:
        _zeile("[yellow]Ausgeschlossen:[/yellow]")
        for a in v.ausgeschlossen:
            name = a.kontakt.name if a.kontakt else "?"
            _zeile(
                f"  {escape(a.posten.belegnummer or '—')} · {escape(name)} · "
                f"{betrag_de(a.posten.restbetrag)} € — {escape(a.grund)}"
            )


@befehl.command("vorschlag")
def vorschlag(
    stichtag: str | None = STICHTAG_OPTION,
    vorlauf: int | None = VORLAUF_OPTION,
    ohne_skonto: bool = OHNE_SKONTO_OPTION,
    minimum: float | None = MIN_OPTION,
    maximum: float | None = MAX_OPTION,
    kontakt: list[str] | None = KONTAKT_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Was ist zum Stichtag zu zahlen? Skontofristen zuerst, Grund je Position."""
    e = _mit_filtern(_einstellungen(config), vorlauf, ohne_skonto, minimum, maximum)
    tag = _datum(stichtag, "--stichtag") or date.today()
    with _sitzung(db) as s:
        v = _vorschlag(s, e, tag, kontakt)
    _zeige_vorschlag(v, e.vorlauf_tage)


@befehl.command("anlegen")
def anlegen(
    stichtag: str | None = STICHTAG_OPTION,
    ausfuehrung: str | None = typer.Option(
        None, help="abweichender Ausführungstag JJJJ-MM-TT"
    ),
    vorlauf: int | None = VORLAUF_OPTION,
    ohne_skonto: bool = OHNE_SKONTO_OPTION,
    minimum: float | None = MIN_OPTION,
    maximum: float | None = MAX_OPTION,
    kontakt: list[str] | None = KONTAKT_OPTION,
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Zahlungslauf (Entwurf) aus dem Vorschlag anlegen."""
    from accounti.anzeige import betrag_de, datum_de
    from accounti.auth.cli import befehlsrecht_oder_ende
    from accounti.models.auth import Recht
    from accounti.zahlung.freigabe import LaufError, lege_an

    e = _mit_filtern(_einstellungen(config), vorlauf, ohne_skonto, minimum, maximum)
    tag = _datum(stichtag, "--stichtag") or date.today()
    termin = _datum(ausfuehrung, "--ausfuehrung")
    person = _person(von)
    # mit eingerichteten Benutzern: Recht buchen und Einmalcode — der Ersteller ist
    # dann der Benutzer, nicht ein Freitext (Vier-Augen: er gibt nicht selbst frei)
    benutzer = befehlsrecht_oder_ende(db, config, Recht.BUCHEN, person)
    ersteller = benutzer.name if benutzer is not None else person
    with _sitzung(db) as s:
        v = _vorschlag(s, e, tag, kontakt)
        try:
            lauf = lege_an(s, v, e, ersteller, ausfuehrung=termin)
        except LaufError as fehler:
            raise _fehler(str(fehler)) from fehler
        s.commit()
    _zeile(
        f"[green]Zahlungslauf {lauf.nr} angelegt[/green] (Entwurf): "
        f"{len(lauf.zahlungen)} Zahlungen über {betrag_de(lauf.summe)} € zum "
        f"{datum_de(lauf.ausfuehrung)}"
    )
    _zeile(
        f"[dim]Weiter: accounti zahlung pruefen {lauf.nr} → freigeben {lauf.nr} → "
        f"sepa {lauf.nr} --datei ueberweisung.xml[/dim]"
    )


def _lauf_oder_ende(s: Session, nr: int) -> Zahlungslauf:
    from accounti.db.repo_zahlung import lade_lauf

    try:
        return lade_lauf(s, nr)
    except ValueError as fehler:
        raise _fehler(str(fehler)) from fehler


@befehl.command("liste")
def liste(
    status: str | None = typer.Option(None, help="entwurf, freigegeben, …"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Zahlungsläufe mit Status, Termin und Summe."""
    from rich.table import Table

    from accounti.anzeige import betrag_de, datum_de
    from accounti.db.repo_zahlung import lade_laeufe
    from accounti.models.zahlung import LaufStatus

    try:
        filter_status = {LaufStatus(status)} if status else None
    except ValueError as fehler:
        raise _fehler(f"--status: {', '.join(s.value for s in LaufStatus)}") from fehler
    with _sitzung(db) as s:
        laeufe = lade_laeufe(s, filter_status)
    if not laeufe:
        _zeile("[dim]Keine Zahlungsläufe.[/dim]")
        return
    tabelle = Table(title="Zahlungsläufe")
    for spalte in ("Nr.", "Status", "Ausführung", "Zahlungen", "Summe", "Angelegt von"):
        tabelle.add_column(spalte, no_wrap=True)
    for lauf in laeufe:
        tabelle.add_row(
            str(lauf.nr),
            lauf.status.value,
            datum_de(lauf.ausfuehrung),
            str(len(lauf.zahlungen)),
            betrag_de(lauf.summe),
            escape(lauf.erstellt_von),
        )
    console.print(tabelle)


@befehl.command("zeigen")
def zeigen(
    nr: int = typer.Argument(help="Nummer des Zahlungslaufs"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Zahlungen und Protokoll eines Laufs."""
    from accounti.anzeige import betrag_de, datum_de
    from accounti.db.repo_zahlung import lade_protokoll
    from accounti.zahlung.freigabe import angekommen
    from accounti.zahlung.iban import lesbar

    with _sitzung(db) as s:
        lauf = _lauf_oder_ende(s, nr)
        protokoll = lade_protokoll(s, lauf.id)
        da = {z.nr: angekommen(s, z) for z in lauf.zahlungen}
    _zeile(
        f"[bold]Zahlungslauf {lauf.nr}[/bold] · {lauf.status.value} · Ausführung "
        f"{datum_de(lauf.ausfuehrung)} · von {escape(lauf.auftraggeber_name)} "
        f"({lesbar(lauf.auftraggeber_iban)})"
    )
    for z in lauf.zahlungen:
        haken = " [green]✓ angekommen[/green]" if da[z.nr] else ""
        skonto = f" (Skonto {betrag_de(z.skonto)} €)" if z.skonto else ""
        _zeile(
            f"{z.nr:>3}. {escape(z.empfaenger)} · {lesbar(z.iban)} · "
            f"[bold]{betrag_de(z.betrag)} €[/bold]{skonto}{haken}"
        )
        _zeile(f"     {escape(z.verwendungszweck)}")
    _zeile(f"Summe {betrag_de(lauf.summe)} € · {len(lauf.zahlungen)} Zahlungen")
    if lauf.msg_id:
        _zeile(f"SEPA-Datei {lauf.msg_id} · SHA-256 {lauf.datei_hash}")
    _zeile("[bold]Protokoll[/bold]")
    for e in protokoll:
        _zeile(
            f"  {e.nr:>2}. {e.zeitpunkt:%d.%m.%Y %H:%M} {escape(e.person)} · "
            f"{e.aktion} · {escape(e.text)}"
        )


@befehl.command("entfernen")
def entfernen(
    nr: int = typer.Argument(help="Nummer des Zahlungslaufs"),
    position: int = typer.Argument(help="Nummer der Zahlung im Lauf"),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Zahlung aus dem Entwurf nehmen — der Posten ist danach wieder frei."""
    from accounti.anzeige import betrag_de
    from accounti.zahlung.freigabe import LaufError, entferne

    person = _benutzer_oder_person(db, config, "buchen", von)
    with _sitzung(db) as s:
        _lauf_oder_ende(s, nr)
        try:
            z = entferne(s, nr, position, person)
        except LaufError as fehler:
            raise _fehler(str(fehler)) from fehler
        s.commit()
    _zeile(
        f"Zahlung {z.nr} entfernt: {escape(z.belegnummer or '—')} an "
        f"{escape(z.empfaenger)} über {betrag_de(z.betrag)} €"
    )


def _befunde(ergebnis_zeilen: list[str], nr: int) -> typer.Exit:
    _zeile(f"[red]Lauf {nr} ist gesperrt:[/red]")
    for zeile in ergebnis_zeilen:
        _zeile(f"  [red]•[/red] {escape(zeile)}")
    return typer.Exit(1)


@befehl.command("pruefen")
def pruefen(
    nr: int = typer.Argument(help="Nummer des Zahlungslaufs"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Lauf blockierend prüfen: IBAN, Betrag, Sperren, Doppelzahlungen."""
    from accounti.zahlung.pruefung import pruefe_lauf

    e = _einstellungen(config)
    with _sitzung(db) as s:
        ergebnis = pruefe_lauf(s, _lauf_oder_ende(s, nr), e, date.today())
    if not ergebnis.ok:
        raise _befunde(ergebnis.zeilen(), nr)
    _zeile(f"[green]Lauf {nr}: keine Befunde[/green] — bereit zur Freigabe.")


@befehl.command("freigeben")
def freigeben(
    nr: int = typer.Argument(help="Nummer des Zahlungslaufs"),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Lauf prüfen und freigeben (mit zahlung.vier_augen: zwei Personen)."""
    from accounti.anzeige import betrag_de
    from accounti.auth.cli import befehlsrecht_oder_ende
    from accounti.models.auth import Recht
    from accounti.models.zahlung import LaufStatus
    from accounti.zahlung import freigabe

    e = _einstellungen(config)
    try:
        person = freigabe.person_fuer_freigabe(von, e)
    except freigabe.LaufError as fehler:
        raise _fehler(str(fehler)) from fehler
    # mit eingerichteten Benutzern: Rolle freigeber und Einmalcode (Baustein 10);
    # wer den Lauf angelegt hat, gibt ihn dann nicht frei — in der CLI immer:
    # zahlung.ersteller_darf_freigeben käme hier aus einer frei wählbaren Datei
    # (--config, ACCOUNTI_KONFIG, eigene Registry) und gilt nur im Browser
    benutzer = befehlsrecht_oder_ende(db, config, Recht.ZAHLUNG_FREIGEBEN, person)
    with _sitzung(db) as s:
        _lauf_oder_ende(s, nr)
        try:
            lauf = freigabe.freigeben(
                s,
                nr,
                person,
                e,
                date.today(),
                ersteller_ausgeschlossen=benutzer is not None,
            )
        except freigabe.LaufGesperrtError as fehler:
            raise _befunde(fehler.ergebnis.zeilen(), nr) from fehler
        except freigabe.LaufError as fehler:
            raise _fehler(str(fehler)) from fehler
        s.commit()
    if lauf.status is LaufStatus.FREIGEGEBEN:
        _zeile(
            f"[green]Lauf {nr} freigegeben[/green] von {escape(person)}: "
            f"{len(lauf.zahlungen)} Zahlungen über {betrag_de(lauf.summe)} €. "
            f"Weiter: accounti zahlung sepa {nr} --datei ueberweisung.xml"
        )
    else:
        _zeile(
            f"[yellow]Erste Freigabe von {escape(person)}[/yellow] — das "
            "Vier-Augen-Prinzip verlangt eine zweite Person."
        )


@befehl.command("sepa")
def sepa(
    nr: int = typer.Argument(help="Nummer des Zahlungslaufs"),
    datei: Path = DATEI_OPTION,
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """SEPA-Sammelüberweisung (pain.001.001.09) zum Hochladen ins Onlinebanking."""
    from accounti.anzeige import betrag_de, datum_de
    from accounti.zahlung.freigabe import LaufError, LaufGesperrtError
    from accounti.zahlung.sepa import erzeuge_datei

    e = _einstellungen(config)
    with _sitzung(db) as s:
        _lauf_oder_ende(s, nr)
        try:
            lauf, xml, neu = erzeuge_datei(s, nr, e, _person(von), date.today())
        except LaufGesperrtError as fehler:
            raise _befunde(fehler.ergebnis.zeilen(), nr) from fehler
        except LaufError as fehler:
            raise _fehler(str(fehler)) from fehler
        # Erst festschreiben, dann die Datei: Ohne Commit darf es keine Datei geben,
        # sonst entstünde beim nächsten Aufruf eine zweite mit neuer MsgId.
        s.commit()
    try:
        datei.write_bytes(xml)
    except OSError as fehler:
        raise _fehler(
            f"SEPA-Datei konnte nicht geschrieben werden ({fehler}). Lauf {nr} ist "
            f"{lauf.status.value}; dieselbe Datei mit 'accounti zahlung sepa {nr} "
            "--datei …' erneut ausgeben."
        ) from fehler
    if neu:
        _zeile(
            f"[green]SEPA-Datei geschrieben:[/green] {escape(str(datei))} "
            f"(pain.001.001.09, {lauf.msg_id}) — {len(lauf.zahlungen)} Überweisungen "
            f"über {betrag_de(lauf.summe)} € zum {datum_de(lauf.ausfuehrung)}."
        )
        _zeile(
            "Lauf ist jetzt eingereicht. Datei im Onlinebanking hochladen; danach "
            "Kontoumsätze importieren, 'accounti opos zuordnen' und "
            "'accounti zahlung abgleichen'."
        )
    else:
        _zeile(
            f"[yellow]Datei unverändert erneut ausgegeben[/yellow] ({lauf.msg_id}, "
            f"{lauf.status.value}): {escape(str(datei))} — nicht noch einmal "
            "hochladen, wenn die Bank sie schon hat."
        )


@befehl.command("stornieren")
def stornieren(
    nr: int = typer.Argument(help="Nummer des Zahlungslaufs"),
    grund: str = typer.Option(..., "--grund", help="Warum storniert wird"),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Lauf stornieren (mit Grund und Protokoll); die Posten werden wieder frei."""
    from accounti.models.zahlung import LaufStatus
    from accounti.zahlung.freigabe import LaufError, storniere

    # hebt eine Freigabe auf — mit Benutzern nur, wer Zahlungsläufe freigeben darf
    person = _benutzer_oder_person(db, config, "zahlung_freigeben", von)
    with _sitzung(db) as s:
        vorher = _lauf_oder_ende(s, nr).status
        try:
            storniere(s, nr, person, grund)
        except LaufError as fehler:
            raise _fehler(str(fehler)) from fehler
        s.commit()
    _zeile(f"Lauf {nr} storniert ({vorher.value} → storniert): {escape(grund)}")
    if vorher is LaufStatus.EINGEREICHT:
        _zeile(
            "[yellow]Die SEPA-Datei war schon erzeugt — wurde sie hochgeladen, den "
            "Auftrag bei der Bank zurückrufen.[/yellow]"
        )


@befehl.command("abgleichen")
def abgleichen(
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Eingereichte Läufe auf „ausgeführt“ setzen, sobald alle Posten ausgeglichen."""
    from accounti.zahlung.freigabe import pruefe_ausfuehrung

    with _sitzung(db) as s:
        fertig = pruefe_ausfuehrung(s, _person(von))
        s.commit()
    if not fertig:
        _zeile(
            "[dim]Eingereichte Läufe: noch keiner ausgeführt (erst Kontoumsätze "
            "importieren und 'accounti opos zuordnen').[/dim]"
        )
    for lauf in fertig:
        _zeile(f"[green]Lauf {lauf.nr} ausgeführt[/green] — alle Posten ausgeglichen.")


@befehl.command("sperre")
def sperre(
    kontakt: str = typer.Argument(help="Kreditorenkonto oder Anfang der ID"),
    grund: str | None = typer.Option(None, "--grund", help="Grund der Sperre"),
    aufheben: bool = typer.Option(False, "--aufheben", help="Sperre aufheben"),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Zahlungssperre an einem Kontakt setzen oder aufheben."""
    from accounti.zahlung.freigabe import LaufError, hebe_sperre_auf, setze_sperre

    person = _benutzer_oder_person(db, config, "buchen", von)
    with _sitzung(db) as s:
        try:
            if aufheben:
                k, war = hebe_sperre_auf(s, kontakt)
            else:
                k, war = setze_sperre(s, kontakt, grund or "", person), True
        except (LaufError, ValueError) as fehler:
            raise _fehler(str(fehler)) from fehler
        s.commit()
    if aufheben:
        _zeile(
            f"Zahlungssperre für {escape(k.name)} aufgehoben."
            if war
            else f"{escape(k.name)} war nicht gesperrt."
        )
    else:
        _zeile(
            f"[yellow]Zahlungssperre[/yellow] für {escape(k.name)}: "
            f"{escape(grund or '')}"
        )


@befehl.command("iban-klaeren")
def iban_klaeren(
    nr: int = typer.Argument(help="Nummer des Zahlungslaufs"),
    position: int = typer.Argument(help="Nummer der Zahlung im Lauf"),
    grund: str = typer.Option(
        ..., "--grund", help="Wie geklärt (wer, wann, über welchen Weg)"
    ),
    von: str | None = VON_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """IBAN-Abweichung Rechnung/Stammsatz geklärt: an den Stammsatz zahlen."""
    from accounti.zahlung.freigabe import LaufError
    from accounti.zahlung.freigabe import iban_klaeren as klaeren
    from accounti.zahlung.iban import lesbar

    # die Klärung ist die Betrugskontrolle: mit Benutzern buchen und Einmalcode
    person = _benutzer_oder_person(db, config, "buchen", von)
    with _sitzung(db) as s:
        _lauf_oder_ende(s, nr)
        try:
            k = klaeren(s, nr, position, person, grund)
        except LaufError as fehler:
            raise _fehler(str(fehler)) from fehler
        s.commit()
    _zeile(
        f"Geklärt: Zahlung {position} geht an den Stammsatz "
        f"{lesbar(k.stammsatz_iban)}, "
        f"nicht an {lesbar(k.rechnungs_iban)} von der Rechnung."
    )
