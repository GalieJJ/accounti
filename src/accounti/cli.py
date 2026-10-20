"""accounti CLI — Kommandozeilenschnittstelle."""

from decimal import Decimal
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console

if TYPE_CHECKING:
    from datetime import date
    from types import ModuleType

    from sqlalchemy.orm import Session, sessionmaker

    from accounti.bank.lauf import KontoAbruf
    from accounti.belege.kanaele import BelegKanal
    from accounti.belege.pipeline import Erkenner
    from accounti.erechnung.kosit import KositErgebnis
    from accounti.erechnung.mustang import MustangErgebnis
    from accounti.erechnung.validierung import Befund
    from accounti.konfiguration import Firma, UstIdEinstellungen
    from accounti.kontakte.ustid import Bewertung
    from accounti.models import (
        Beleg,
        Buchungssatz,
        Kontakt,
        PostenRichtung,
        Transaktion,
        UstIdPruefung,
    )
    from accounti.opos.zuordnung import Zuordnungsvorschlag

app = typer.Typer(
    name="accounti",
    help="KI-gestützte Buchhaltungsautomatisierung für deutsche Unternehmen.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Zeigt die aktuelle Version an."""
    from accounti import __version__

    console.print(f"accounti {__version__}")


# ---------------------------------------------------------------------------
# Import-Befehle
# ---------------------------------------------------------------------------
import_app = typer.Typer(help="Transaktionen importieren.")
app.add_typer(import_app, name="import")


@import_app.command("bank")
def import_bank(
    datei: str = typer.Argument(help="Pfad zur Bank-CSV-Datei"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    format: str = typer.Option("auto", help="Bankformat (auto = erkennen)"),
    konto: str | None = typer.Option(
        None, help="Eingerichtetes Bankkonto (IBAN) — Sachkonto und Dublettenschutz"
    ),
) -> None:
    """Banktransaktionen importieren — was schon da ist, wird übersprungen."""
    from rich.markup import escape

    from accounti.bank.lauf import speichere_neue
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_bankkonto
    from accounti.importers.kontoauszug import importiere_fuer_konto
    from accounti.importers.profil import waehle_importer

    try:
        importer = waehle_importer(datei, format)
    except ValueError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        bankkonto = None
        try:
            if konto is not None:
                bankkonto = lade_bankkonto(s, konto)
            # MT940/CAMT: nur Auszüge dieses Kontos; Saldo, der nicht aufgeht → Fehler
            transaktionen = importiere_fuer_konto(
                importer, datei, bankkonto.iban if bankkonto else None
            )
        except ValueError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
        neu, doppelt = speichere_neue(
            s, transaktionen, f"datei:{importer.name}", bankkonto
        )
        s.commit()
    console.print(
        f"[green]{neu}[/green] Transaktionen importiert"
        + (f", {doppelt} Dubletten übersprungen." if doppelt else ".")
    )


@import_app.command("banken")
def import_banken() -> None:
    """Verfügbare Bankformate auflisten."""
    from accounti.importers import BANK_IMPORTERS
    from accounti.importers.profil import lade_banken_profile, registriere_profile

    registriere_profile(lade_banken_profile("config/banken.yaml"))
    console.print("[bold]Verfügbare Bankformate:[/bold]")
    for name in sorted(BANK_IMPORTERS):
        console.print(f"  • {name}")
    console.print("  • [dim]auto (automatische Erkennung)[/dim]")


# ---------------------------------------------------------------------------
# Belege
# ---------------------------------------------------------------------------
belege_app = typer.Typer(help="Belege erfassen und verwalten.")
app.add_typer(belege_app, name="belege")

ARCHIV_STANDARD = "archiv/belege"


def _beleg_zeile(b: "Beleg") -> str:
    """Kurzbeschreibung eines erkannten Belegs für die Konsole."""
    from rich.markup import escape

    teile = [b.belegart.value]
    if b.brutto is not None:
        teile.append(f"{b.brutto:.2f} {b.waehrung}")
    if b.status.value == "pruefung":
        teile.append(f"[yellow]zur Prüfung: {escape(b.pruef_grund or '')}[/yellow]")
    else:
        teile.append(b.status.value)
    return " · ".join(teile)


def _beleg_erkenner(
    llm: bool, eigene_ust_id: list[str], eigene_firma: str | None, sprache: str
) -> "Erkenner":
    from accounti.belege.erkennung import BelegErkenner
    from accounti.belege.llm import LLMBelegEngine
    from accounti.belege.ocr.tesseract import TesseractEngine

    return BelegErkenner(
        ocr=TesseractEngine(sprache=sprache),
        llm=LLMBelegEngine() if llm else None,
        eigene_ust_ids=set(eigene_ust_id),
        eigene_firma=eigene_firma,
    )


def _belege_aufnehmen(
    kanal: "BelegKanal", db: str, archiv: str, erkenner: "Erkenner | None"
) -> None:
    """Holt alle Rohbelege eines Kanals ab und nimmt sie einzeln auf."""
    from rich.markup import escape

    from accounti.belege.archiv import BelegArchiv
    from accounti.belege.pipeline import nimm_auf
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_beleg
    from accounti.models import Eingangsergebnis

    engine, make_session = session_factory(db)
    init_db(engine)
    belegarchiv = BelegArchiv(archiv)
    zaehler = dict.fromkeys(Eingangsergebnis, 0)
    with make_session() as s:
        for roh in kanal.abholen():
            eingang = nimm_auf(s, belegarchiv, roh, erkenner=erkenner)
            s.commit()
            kanal.bestaetige(roh)
            zaehler[eingang.ergebnis] += 1
            if eingang.ergebnis is Eingangsergebnis.DUBLETTE:
                console.print(
                    f"[dim]Dublette[/dim]  {escape(roh.dateiname)} — "
                    f"{escape(eingang.hinweis or '')}"
                )
                continue
            beleg = lade_beleg(s, eingang.beleg_id) if eingang.beleg_id else None
            info = f" — {_beleg_zeile(beleg)}" if beleg else ""
            if eingang.ergebnis is Eingangsergebnis.NEU:
                console.print(f"[green]neu[/green]       {escape(roh.dateiname)}{info}")
            else:
                console.print(
                    f"[yellow]Verdacht[/yellow]  {escape(roh.dateiname)}{info}"
                )
    console.print(
        f"[green]{zaehler[Eingangsergebnis.NEU]} neu[/green], "
        f"{zaehler[Eingangsergebnis.DUBLETTE]} Dubletten, "
        f"[yellow]{zaehler[Eingangsergebnis.VERDACHT]} Verdacht[/yellow]."
    )


# Gemeinsame Optionen der Befehle, die Belege lesen
ERKENNEN_OPTION = typer.Option(
    True, "--erkennen/--ohne-erkennung", help="Belege direkt lesen"
)
LLM_OPTION = typer.Option(
    False, "--llm/--no-llm", help="LLM-Stufe für Lücken (maskiert, Standard: aus)"
)
EIGENE_UST_ID_OPTION = typer.Option(
    [], "--eigene-ust-id", help="Eigene USt-IdNr. (erkennt Ausgangsrechnungen)"
)
EIGENE_FIRMA_OPTION = typer.Option(None, help="Eigener Firmenname")
OCR_SPRACHE_OPTION = typer.Option("deu", help="Tesseract-Sprache(n), z.B. deu+eng")


@belege_app.command("kanaele")
def belege_kanaele() -> None:
    """Verfügbare Beleg-Kanäle auflisten."""
    from accounti.belege.kanaele import BELEG_KANAELE

    console.print("[bold]Verfügbare Beleg-Kanäle:[/bold]")
    for name, kanal in sorted(BELEG_KANAELE.items()):
        console.print(f"  • {name:8} [dim]{kanal.beschreibung}[/dim]")


@belege_app.command("import")
def belege_import(
    dateien: Annotated[list[str], typer.Argument(help="Belegdatei(en)")],
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    erkennen: bool = ERKENNEN_OPTION,
    llm: bool = LLM_OPTION,
    eigene_ust_id: list[str] = EIGENE_UST_ID_OPTION,
    eigene_firma: str | None = EIGENE_FIRMA_OPTION,
    ocr_sprache: str = OCR_SPRACHE_OPTION,
) -> None:
    """Einzelne Belege importieren."""
    from pathlib import Path

    from accounti.belege.kanaele.upload import UploadKanal

    fehlend = [d for d in dateien if not Path(d).is_file()]
    if fehlend:
        console.print(f"[red]Datei nicht gefunden: {', '.join(fehlend)}[/red]")
        raise typer.Exit(1)
    erkenner = (
        _beleg_erkenner(llm, eigene_ust_id, eigene_firma, ocr_sprache)
        if erkennen
        else None
    )
    _belege_aufnehmen(UploadKanal(dateien), db, archiv, erkenner)


@belege_app.command("abholen")
def belege_abholen(
    kanal: str = typer.Option(..., help="Kanal: ordner, email oder connector"),
    ordner: str = typer.Option("eingang/belege", help="Ordner für den Kanal 'ordner'"),
    quelle: str | None = typer.Option(
        None, help="Nur dieses Postfach bzw. diesen Connector (Name)"
    ),
    config: str = typer.Option(
        "config/accounti.yaml", "--config", help="Konfiguration (belegkanaele)"
    ),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    erkennen: bool = ERKENNEN_OPTION,
    llm: bool = LLM_OPTION,
    eigene_ust_id: list[str] = EIGENE_UST_ID_OPTION,
    eigene_firma: str | None = EIGENE_FIRMA_OPTION,
    ocr_sprache: str = OCR_SPRACHE_OPTION,
) -> None:
    """Einen Kanal einmal leeren."""
    from pathlib import Path

    from accounti.belege.kanaele.ordner import OrdnerKanal

    if kanal != OrdnerKanal.name:
        from accounti.befehle.kanaele import eigene_firma_vorgabe, hole_ab

        eigene_ust_id, eigene_firma = eigene_firma_vorgabe(
            config, eigene_ust_id, eigene_firma
        )
        erkenner = (
            _beleg_erkenner(llm, eigene_ust_id, eigene_firma, ocr_sprache)
            if erkennen
            else None
        )
        hole_ab(
            kanal,
            quelle,
            config,
            db,
            lambda k: _belege_aufnehmen(k, db, archiv, erkenner),
        )
        return
    if not Path(ordner).is_dir():
        console.print(f"[red]Ordner nicht gefunden: {ordner}[/red]")
        raise typer.Exit(1)
    erkenner = (
        _beleg_erkenner(llm, eigene_ust_id, eigene_firma, ocr_sprache)
        if erkennen
        else None
    )
    _belege_aufnehmen(OrdnerKanal(ordner), db, archiv, erkenner)


@belege_app.command("erkennen")
def belege_erkennen(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    llm: bool = LLM_OPTION,
    eigene_ust_id: list[str] = EIGENE_UST_ID_OPTION,
    eigene_firma: str | None = EIGENE_FIRMA_OPTION,
    ocr_sprache: str = OCR_SPRACHE_OPTION,
) -> None:
    """Ungelesene und zur Prüfung liegende Belege erneut aus dem Archiv lesen."""
    from accounti.belege.archiv import BelegArchiv
    from accounti.belege.pipeline import erkenne_erneut
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_belege
    from accounti.models import BelegStatus

    erkenner = _beleg_erkenner(llm, eigene_ust_id, eigene_firma, ocr_sprache)
    engine, make_session = session_factory(db)
    init_db(engine)
    belegarchiv = BelegArchiv(archiv)
    erfasst = 0
    with make_session() as s:
        offen = lade_belege(
            s, status={BelegStatus.EINGEGANGEN, BelegStatus.ZUR_PRUEFUNG}
        )
        for alt in offen:
            neu = erkenne_erneut(s, belegarchiv, alt, erkenner)
            s.commit()
            erfasst += neu.status is BelegStatus.ERFASST
            console.print(f"{str(neu.id)[:8]}  {neu.dateiname} — {_beleg_zeile(neu)}")
    console.print(
        f"{len(offen)} Belege gelesen, [green]{erfasst} erfasst[/green], "
        f"[yellow]{len(offen) - erfasst} zur Prüfung[/yellow]."
    )


@belege_app.command("liste")
def belege_liste(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    status: str | None = typer.Option(None, help="eingegangen, pruefung oder erfasst"),
) -> None:
    """Belege anzeigen."""
    from rich.markup import escape
    from rich.table import Table

    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_belege
    from accounti.models import BelegStatus

    try:
        filter_ = {BelegStatus(status)} if status else None
    except ValueError as fehler:
        erlaubt = ", ".join(s.value for s in BelegStatus)
        console.print(f"[red]Unbekannter Status '{status}'. Erlaubt: {erlaubt}[/red]")
        raise typer.Exit(1) from fehler

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        belege = lade_belege(s, status=filter_)
    if not belege:
        console.print("[dim]Keine Belege.[/dim]")
        return

    tabelle = Table(title="Belege")
    tabelle.add_column("ID", no_wrap=True)
    tabelle.add_column("Datei", overflow="fold")
    tabelle.add_column("Art", no_wrap=True)
    tabelle.add_column("Brutto", justify="right", no_wrap=True)
    tabelle.add_column("Status", no_wrap=True)
    for b in belege:
        tabelle.add_row(
            str(b.id)[:8],
            b.dateiname,
            b.belegart.value,
            f"{b.brutto:.2f}" if b.brutto is not None else "—",
            b.status.value,
        )
    console.print(tabelle)
    hinweise = [b for b in belege if b.pruef_grund]
    if hinweise:
        console.print("[bold]Prüfhinweise:[/bold]")
        for b in hinweise:
            console.print(f"  {str(b.id)[:8]}  {escape(b.pruef_grund or '')}")


# ---------------------------------------------------------------------------
# E-Rechnung
# ---------------------------------------------------------------------------
rechnung_app = typer.Typer(help="E-Rechnungen schreiben, ausstellen und prüfen.")
app.add_typer(rechnung_app, name="rechnung")

KONFIG_OPTION = typer.Option("config/accounti.yaml", "--config", help="Firmendaten")


def _datum_option(wert: str | None, name: str) -> "date | None":
    from datetime import date

    if wert is None:
        return None
    try:
        return date.fromisoformat(wert)
    except ValueError as fehler:
        console.print(f"[red]{name}: Datum im Format JJJJ-MM-TT erwartet[/red]")
        raise typer.Exit(1) from fehler


def _lade_firma_oder_ende(pfad: str) -> "Firma":
    from rich.markup import escape

    from accounti.konfiguration import KonfigurationError, lade_firma

    try:
        return lade_firma(pfad)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler


def _befunde_tabelle(befunde: "list[Befund]") -> None:
    from rich.markup import escape
    from rich.table import Table

    from accounti.erechnung.validierung import Schwere

    tabelle = Table(title="Befunde")
    tabelle.add_column("Schwere", no_wrap=True)
    tabelle.add_column("Regel", no_wrap=True)
    tabelle.add_column("Befund", overflow="fold")
    for b in befunde:
        farbe = "red" if b.schwere is Schwere.FEHLER else "yellow"
        tabelle.add_row(
            f"[{farbe}]{b.schwere.value}[/{farbe}]", b.regel, escape(b.text)
        )
    console.print(tabelle)


def _kosit_ausgabe(ergebnis: "KositErgebnis") -> None:
    from rich.markup import escape

    if ergebnis.akzeptiert:
        console.print("[green]KoSIT-Prüftool: ACCEPT[/green]")
    else:
        console.print("[red]KoSIT-Prüftool: REJECT[/red]")
    for m in ergebnis.meldungen:
        farbe = "red" if m.stufe in ("error", "fatal") else "yellow"
        console.print(f"  [{farbe}]{m.stufe}[/{farbe}] {escape(str(m))}")


@rechnung_app.command("neu")
def rechnung_neu(
    name: str = typer.Option(..., help="Name des Kunden"),
    strasse: str | None = typer.Option(None, help="Straße und Hausnummer"),
    plz: str | None = typer.Option(None, help="Postleitzahl"),
    ort: str | None = typer.Option(None, help="Ort"),
    land: str = typer.Option("DE", help="Ländercode (ISO 3166-1)"),
    ust_id: str | None = typer.Option(None, help="USt-IdNr. des Kunden"),
    email: str | None = typer.Option(None, help="E-Mail für die E-Rechnung (BT-49)"),
    leitweg_id: str | None = typer.Option(None, help="Leitweg-ID/Käuferreferenz"),
    privat: bool = typer.Option(False, "--privat", help="Kunde ist Verbraucher"),
    leistungsdatum: str | None = typer.Option(None, help="JJJJ-MM-TT"),
    bestellnummer: str | None = typer.Option(None, help="Bestellnummer des Kunden"),
    notiz: str | None = typer.Option(None, help="Freitext auf der Rechnung"),
    skonto_prozent: float | None = typer.Option(None, help="Skonto in Prozent"),
    skonto_tage: int | None = typer.Option(None, help="Skontofrist in Tagen"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Rechnungsentwurf anlegen."""
    from decimal import Decimal

    from accounti.db import init_db, session_factory
    from accounti.db.repository import speichere_ausgangsrechnung
    from accounti.models import Ausgangsrechnung, Rechnungsempfaenger

    entwurf = Ausgangsrechnung(
        kunde=Rechnungsempfaenger(
            name=name,
            strasse=strasse,
            plz=plz,
            ort=ort,
            land=land.upper(),
            ust_id=ust_id,
            email=email,
            leitweg_id=leitweg_id,
            privat=privat,
        ),
        leistungsdatum=_datum_option(leistungsdatum, "--leistungsdatum"),
        bestellnummer=bestellnummer,
        notiz=notiz,
        skonto_prozent=Decimal(str(skonto_prozent)) if skonto_prozent else None,
        skonto_tage=skonto_tage,
    )
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        speichere_ausgangsrechnung(s, entwurf)
        s.commit()
    console.print(f"[green]Entwurf {str(entwurf.id)[:8]} angelegt[/green] für {name}")
    console.print(
        f"[dim]Positionen: accounti rechnung position {str(entwurf.id)[:8]} "
        "--text .. --preis ..[/dim]"
    )


@rechnung_app.command("position")
def rechnung_position(
    schluessel: str = typer.Argument(help="Entwurfs-ID (Anfang genügt)"),
    text: str = typer.Option(..., help="Bezeichnung"),
    preis: float = typer.Option(..., help="Einzelpreis netto"),
    menge: float = typer.Option(1.0, help="Menge"),
    einheit: str = typer.Option("C62", help="Einheit (C62 Stück, HUR Stunde, …)"),
    ermaessigt: bool = typer.Option(False, "--ermaessigt", help="Ermäßigter Satz"),
    leistung: bool = typer.Option(
        False, "--leistung", help="Dienstleistung (Reverse Charge bei EU-Unternehmen)"
    ),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Position zu einem Entwurf hinzufügen. Der Steuersatz kommt aus steuer/."""
    from decimal import Decimal

    from rich.markup import escape

    from accounti.db import session_factory
    from accounti.db.repository import fuege_position_hinzu
    from accounti.models import AusgangsPosition

    position = AusgangsPosition(
        bezeichnung=text,
        einzelpreis=Decimal(str(preis)),
        menge=Decimal(str(menge)),
        einheit=einheit,
        ermaessigt=ermaessigt,
        sonstige_leistung=leistung,
    )
    _, make_session = session_factory(db)
    with make_session() as s:
        try:
            r = fuege_position_hinzu(s, schluessel, position)
        except ValueError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
        s.commit()
    console.print(
        f"Position {len(r.positionen)}: {escape(text)} — {position.netto:.2f} EUR netto"
    )


@rechnung_app.command("zeigen")
def rechnung_zeigen(
    schluessel: str = typer.Argument(help="Entwurfs-ID oder Rechnungsnummer"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    config: str = KONFIG_OPTION,
) -> None:
    """Vorschau mit Steuer und Summen (für Entwürfe) bzw. Daten der Rechnung."""
    from datetime import date

    from rich.markup import escape
    from rich.table import Table

    from accounti.db import session_factory
    from accounti.db.repository import lade_ausgangsrechnung
    from accounti.erechnung.erzeuger.aufbau import baue_rechnung
    from accounti.erechnung.validierung import pruefe

    firma = _lade_firma_oder_ende(config)
    _, make_session = session_factory(db)
    with make_session() as s:
        try:
            entwurf = lade_ausgangsrechnung(s, schluessel)
        except ValueError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
    try:
        r = baue_rechnung(
            entwurf,
            firma,
            entwurf.nummer or "ENTWURF",
            entwurf.rechnungsdatum or date.today(),
        )
    except ValueError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler

    console.print(
        f"[bold]{escape(r.nummer or '')}[/bold] an {escape(r.kaeufer.name or '')} "
        f"({entwurf.status.value})"
    )
    tabelle = Table()
    tabelle.add_column("Pos")
    tabelle.add_column("Bezeichnung", overflow="fold")
    tabelle.add_column("Menge", justify="right")
    tabelle.add_column("Netto", justify="right")
    tabelle.add_column("Steuer")
    for z in r.zeilen:
        tabelle.add_row(
            z.id or "",
            escape(z.bezeichnung or ""),
            f"{z.menge} {z.einheit}",
            f"{z.netto:.2f}",
            f"{z.steuerkategorie} {z.steuersatz} %",
        )
    console.print(tabelle)
    for st in r.steuern:
        console.print(
            f"  {st.kategorie} {st.satz} %: "
            f"Basis {st.basis:.2f}, Steuer {st.betrag:.2f}"
        )
    for notiz in r.notizen:
        console.print(f"  [dim]{escape(notiz)}[/dim]")
    s_ = r.summen
    console.print(
        f"  Netto {s_.netto:.2f} · Steuer {s_.steuer:.2f} · "
        f"[bold]Brutto {s_.brutto:.2f} EUR[/bold]"
    )
    befunde = pruefe(r)
    if befunde:
        _befunde_tabelle(befunde)
    if entwurf.status.value == "ausgestellt":
        from accounti.db.repository import lade_versandprotokolle

        with make_session() as s:
            protokolle = lade_versandprotokolle(s, str(entwurf.id))
        if not protokolle:
            console.print("[dim]Versand: noch nicht versendet[/dim]")
        for p in protokolle:
            ergebnis = (
                "[green]versendet[/green]"
                if p.erfolgreich
                else f"[red]fehlgeschlagen: {escape(p.fehler or '')}[/red]"
            )
            console.print(
                f"  Versand {p.zeitpunkt:%d.%m.%Y %H:%M} · {p.weg} · "
                f"{escape(p.empfaenger)} · {p.format} · {ergebnis}"
            )


@rechnung_app.command("liste")
def rechnung_liste(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Entwürfe und ausgestellte Rechnungen anzeigen."""
    from decimal import Decimal

    from rich.markup import escape
    from rich.table import Table

    from accounti.db import init_db, session_factory
    from accounti.db.repository import (
        lade_ausgangsrechnungen,
        lade_versandprotokolle,
    )

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        rechnungen = lade_ausgangsrechnungen(s)
        versendet = {
            r.id: any(p.erfolgreich for p in lade_versandprotokolle(s, str(r.id)))
            for r in rechnungen
            if r.nummer
        }
    if not rechnungen:
        console.print("[dim]Keine Rechnungen.[/dim]")
        return
    tabelle = Table(title="Ausgangsrechnungen")
    tabelle.add_column("ID", no_wrap=True)
    tabelle.add_column("Nummer", no_wrap=True)
    tabelle.add_column("Kunde", overflow="fold")
    tabelle.add_column("Netto", justify="right", no_wrap=True)
    tabelle.add_column("Status", no_wrap=True)
    for r in rechnungen:
        netto = sum((p.netto for p in r.positionen), start=Decimal(0))
        tabelle.add_row(
            str(r.id)[:8],
            r.nummer or "—",
            escape(r.kunde.name),
            f"{netto:.2f}",
            "versendet" if versendet.get(r.id) else r.status.value,
        )
    console.print(tabelle)


def _mustang_ausgabe(ergebnis: "MustangErgebnis") -> None:
    from rich.markup import escape

    if ergebnis.gueltig:
        console.print("[green]Mustang/veraPDF: ZUGFeRD-PDF gültig (PDF/A-3b)[/green]")
    else:
        console.print("[red]Mustang/veraPDF: ZUGFeRD-PDF ungültig[/red]")
    for m in ergebnis.meldungen:
        console.print(f"  [red]{escape(m)}[/red]")


def _ustid_vor_ausstellung(
    make_session: "sessionmaker[Session]",
    schluessel: str,
    firma: "Firma",
    rechnungsdatum: "date",
    einstellungen: "UstIdEinstellungen",
) -> None:
    """Steuerfreie EU-Rechnung ohne aktuelle Bestätigung: jetzt beim BZSt anfragen.

    Eigene Transaktion: Das Ergebnis bleibt im Protokoll, auch wenn die
    Ausstellung danach scheitert. Ob es reicht, entscheidet ``stelle_aus``.
    """
    from rich.markup import escape

    from accounti.db.repository import lade_ausgangsrechnung
    from accounti.erechnung.erzeuger.aufbau import ustid_pflichtig
    from accounti.kontakte.ustid import (
        EvatrClient,
        UstIdError,
        aktuelle_bestaetigung,
        baue_anfrage,
        pruefe_ustid,
    )
    from accounti.models import AusgangsrechnungStatus

    with make_session() as s:
        try:
            entwurf = lade_ausgangsrechnung(s, schluessel)
        except ValueError:
            return  # meldet stelle_aus
        if entwurf.status is not AusgangsrechnungStatus.ENTWURF or not (
            ustid_pflichtig(entwurf, firma)
        ):
            return
        k = entwurf.kunde
        lage = aktuelle_bestaetigung(
            s, k.ust_id, rechnungsdatum, einstellungen.max_alter_tage
        )
        if lage.bestaetigt:
            return
        try:
            anfrage = baue_anfrage(
                firma.ust_id, k.ust_id, k.name, k.strasse, k.plz, k.ort
            )
            weg = EvatrClient(einstellungen.url, einstellungen.timeout_sekunden)
        except UstIdError as fehler:
            console.print(f"[red]Nicht ausgestellt: {escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
        console.print(f"[dim]USt-IdNr. {anfrage.ust_id}: Bestätigung beim BZSt …[/dim]")
        p = pruefe_ustid(s, weg, anfrage)
        s.commit()
    _ustid_ausgabe(p)


@rechnung_app.command("ausstellen")
def rechnung_ausstellen(
    schluessel: str = typer.Argument(help="Entwurfs-ID (Anfang genügt)"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    config: str = KONFIG_OPTION,
    ausgabe: str = typer.Option("rechnungen", help="Verzeichnis für XML und PDF"),
    datum: str | None = typer.Option(None, help="Rechnungsdatum JJJJ-MM-TT (heute)"),
    ohne_pruefung: bool = typer.Option(
        False,
        "--ohne-formale-pruefung",
        "--ohne-kosit",
        help="Ohne KoSIT- und Mustang-Prüfung ausstellen (nicht empfohlen)",
    ),
) -> None:
    """Nummer vergeben, XRechnung + ZUGFeRD-PDF erzeugen, prüfen, archivieren."""
    from datetime import date
    from pathlib import Path

    from rich.markup import escape

    from accounti.belege.archiv import BelegArchiv
    from accounti.db import init_db, session_factory
    from accounti.erechnung.ausstellung import AusstellungError, stelle_aus
    from accounti.erechnung.kosit import KositPruefer
    from accounti.erechnung.mustang import MustangPruefer
    from accounti.konfiguration import KonfigurationError, lade_ustid_pruefung

    firma = _lade_firma_oder_ende(config)
    try:
        ustid_einstellungen = lade_ustid_pruefung(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    rechnungsdatum = _datum_option(datum, "--datum") or date.today()
    kosit = pdf_pruefer = None
    if not ohne_pruefung:
        kosit, pdf_pruefer = KositPruefer(), MustangPruefer()
        fehlt = [
            name
            for name, w in (("KoSIT-Prüftool", kosit), ("Mustang", pdf_pruefer))
            if not w.verfuegbar()
        ]
        if fehlt:
            console.print(
                f"[red]{' und '.join(fehlt)} nicht installiert — die E-Rechnung kann "
                "nicht formal geprüft werden.[/red]\n"
                "Installation: scripts/pruefwerkzeuge_installieren.sh · "
                "ausdrücklich ohne Prüfung: --ohne-formale-pruefung"
            )
            raise typer.Exit(1)

    engine, make_session = session_factory(db)
    init_db(engine)
    _ustid_vor_ausstellung(
        make_session, schluessel, firma, rechnungsdatum, ustid_einstellungen
    )
    with make_session() as s:
        try:
            ergebnis = stelle_aus(
                s,
                BelegArchiv(archiv),
                schluessel,
                firma,
                rechnungsdatum,
                kosit=kosit,
                pdf_pruefer=pdf_pruefer,
                ustid_max_alter_tage=ustid_einstellungen.max_alter_tage,
            )
        except (AusstellungError, ValueError) as fehler:
            s.rollback()  # Nummer bleibt frei, der Kreis lückenlos
            console.print(f"[red]Nicht ausgestellt: {escape(str(fehler))}[/red]")
            if isinstance(fehler, AusstellungError):
                if fehler.kosit is not None:
                    _kosit_ausgabe(fehler.kosit)
                if fehler.mustang is not None:
                    _mustang_ausgabe(fehler.mustang)
            raise typer.Exit(1) from fehler
        s.commit()

    ziel = Path(ausgabe)
    ziel.mkdir(parents=True, exist_ok=True)
    nummer = ergebnis.rechnung.nummer or ""
    (ziel / f"{nummer}.xml").write_bytes(ergebnis.xml)
    (ziel / f"{nummer}.pdf").write_bytes(ergebnis.pdf)
    console.print(
        f"[green]Rechnung {nummer} ausgestellt[/green] — "
        f"{ergebnis.beleg.brutto:.2f} EUR brutto → {ziel / nummer}.pdf (ZUGFeRD), "
        f".xml (XRechnung)"
    )
    if ergebnis.kosit is not None:
        _kosit_ausgabe(ergebnis.kosit)
    if ergebnis.mustang is not None:
        _mustang_ausgabe(ergebnis.mustang)
    if ohne_pruefung:
        console.print("[yellow]Ohne formale Prüfung ausgestellt.[/yellow]")
    for b in ergebnis.befunde:
        console.print(f"  [yellow]Hinweis {escape(str(b))}[/yellow]")
    if ergebnis.ustid is not None and ergebnis.ustid.pruefung is not None:
        p = ergebnis.ustid.pruefung
        console.print(
            f"  USt-IdNr. {p.ust_id}: {escape(ergebnis.ustid.grund)} "
            f"(BZSt, Protokoll Nr. {p.nr})"
        )
        for hinweis in ergebnis.ustid.hinweise:
            console.print(f"  [yellow]Hinweis: {escape(hinweis)}[/yellow]")


@rechnung_app.command("senden")
def rechnung_senden(
    schluessel: str = typer.Argument(help="Rechnungsnummer (oder Anfang der ID)"),
    format: str = typer.Option(
        "zugferd", help="zugferd (PDF mit XRechnung) oder xrechnung (nur XML)"
    ),
    an: str | None = typer.Option(None, help="Empfänger statt der E-Mail des Kunden"),
    eml: str | None = typer.Option(
        None, help="Nachricht nur in diese Datei schreiben, nicht senden"
    ),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    config: str = KONFIG_OPTION,
) -> None:
    """Ausgestellte Rechnung per E-Mail versenden (archivierte Datei, mit Protokoll)."""
    from pathlib import Path

    from rich.markup import escape

    from accounti.belege.archiv import BelegArchiv
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_ausgangsrechnung
    from accounti.erechnung.versand import (
        SmtpVersand,
        VersandError,
        baue_nachricht,
        lade_versand,
        versende,
    )
    from accounti.konfiguration import KonfigurationError

    firma = _lade_firma_oder_ende(config)
    try:
        konfiguration = lade_versand(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    belegarchiv = BelegArchiv(archiv)
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        try:
            if eml:
                rechnung = lade_ausgangsrechnung(s, schluessel)
                empfaenger = an or rechnung.kunde.email or "unbekannt@example.invalid"
                nachricht = baue_nachricht(
                    rechnung, firma, konfiguration, belegarchiv, format, empfaenger
                )
                Path(eml).write_bytes(nachricht.as_bytes())
                console.print(f"Nachricht geschrieben (nicht gesendet): {escape(eml)}")
                return
            protokoll = versende(
                s,
                belegarchiv,
                schluessel,
                firma,
                konfiguration,
                SmtpVersand(konfiguration),
                format=format,
                an=an,
            )
        except (VersandError, ValueError) as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
        s.commit()  # das Protokoll bleibt auch bei einem Fehlschlag erhalten
    if protokoll.erfolgreich:
        console.print(
            f"[green]{escape(protokoll.dateiname)} an {escape(protokoll.empfaenger)} "
            "versendet[/green]"
        )
    else:
        console.print(
            f"[red]Versand an {escape(protokoll.empfaenger)} fehlgeschlagen: "
            f"{escape(protokoll.fehler or '')}[/red]"
        )
        raise typer.Exit(1)


@rechnung_app.command("pruefen")
def rechnung_pruefen(
    datei: str = typer.Argument(help="XRechnung (XML) oder ZUGFeRD/Factur-X (PDF)"),
    kosit: bool = typer.Option(
        False, "--kosit", help="Zusätzlich formal mit dem KoSIT-Prüftool prüfen"
    ),
) -> None:
    """E-Rechnung lesen und validieren, ohne sie zu importieren."""
    from pathlib import Path

    from rich.markup import escape

    from accounti.belege.erkennung import erkenne_format
    from accounti.belege.kanaele import RohBeleg
    from accounti.erechnung import ERechnungError, lies
    from accounti.erechnung.kosit import KositNichtVerfuegbarError, KositPruefer
    from accounti.erechnung.validierung import Schwere, pruefe

    pfad = Path(datei)
    if not pfad.is_file():
        console.print(f"[red]Datei nicht gefunden: {escape(datei)}[/red]")
        raise typer.Exit(1)
    roh = RohBeleg(
        dateiname=pfad.name, inhalt=pfad.read_bytes(), kanal="cli", herkunft=datei
    )
    xml = erkenne_format(roh).xml
    if xml is None:
        console.print("[red]keine E-Rechnung (weder XRechnung noch ZUGFeRD)[/red]")
        raise typer.Exit(1)
    try:
        r = lies(xml)
    except ERechnungError as fehler:
        console.print(f"[red]E-Rechnung nicht lesbar: {escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler

    def zeile(label: str, wert: object) -> None:
        console.print(f"  {label:14} {escape(str(wert)) if wert is not None else '—'}")

    console.print(f"[bold]E-Rechnung[/bold] ({r.syntax}, Profil {r.profil.value})")
    zeile("Nummer", r.nummer)
    zeile("Datum", r.datum)
    zeile("Verkäufer", f"{r.verkaeufer.name} ({r.verkaeufer.ust_id or '—'})")
    zeile("Käufer", r.kaeufer.name)
    zeile("Positionen", len(r.zeilen))
    zeile("Netto", r.summen.netto)
    zeile("Steuer", r.summen.steuer)
    zeile("Brutto", r.summen.brutto)
    zeile("Zahlbetrag", r.summen.zahlbetrag)

    befunde = pruefe(r)
    if befunde:
        _befunde_tabelle(befunde)
    else:
        console.print("[green]Keine Befunde.[/green]")
    abgelehnt = False
    if kosit:
        try:
            ergebnis = KositPruefer().pruefe(xml, pfad.with_suffix(".xml").name)
        except KositNichtVerfuegbarError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
        _kosit_ausgabe(ergebnis)
        abgelehnt = not ergebnis.akzeptiert
    if abgelehnt or any(b.schwere is Schwere.FEHLER for b in befunde):
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Kontakte (Debitoren und Kreditoren)
# ---------------------------------------------------------------------------
kontakte_app = typer.Typer(help="Debitoren und Kreditoren verwalten.")
app.add_typer(kontakte_app, name="kontakte")


def _kontakt_oder_ende(session: "Session", schluessel: str) -> "Kontakt":
    from rich.markup import escape

    from accounti.db.repository import lade_kontakt

    try:
        return lade_kontakt(session, schluessel)
    except ValueError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler


def _konten(k: "Kontakt") -> str:
    return " / ".join(filter(None, [k.kreditor_konto, k.debitor_konto]))


@kontakte_app.command("liste")
def kontakte_liste(
    typ: str | None = typer.Option(None, help="kreditor oder debitor"),
    status: str | None = typer.Option(None, help="geprueft oder pruefung"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Kontakte mit Personenkonten anzeigen."""
    from rich.markup import escape
    from rich.table import Table

    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_kontakte

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        kontakte = lade_kontakte(s)
    if typ == "kreditor":
        kontakte = [k for k in kontakte if k.ist_kreditor]
    elif typ == "debitor":
        kontakte = [k for k in kontakte if k.ist_debitor]
    elif typ is not None:
        console.print("[red]--typ: kreditor oder debitor[/red]")
        raise typer.Exit(1)
    if status is not None:
        kontakte = [k for k in kontakte if k.status.value == status]
    if not kontakte:
        console.print("[dim]Keine Kontakte.[/dim]")
        return
    tabelle = Table(title="Kontakte")
    for spalte in ("Konto", "Name", "Ort", "USt-IdNr.", "Sachkonto", "Status"):
        tabelle.add_column(spalte, overflow="fold")
    for k in kontakte:
        tabelle.add_row(
            _konten(k),
            escape(k.name),
            escape(" ".join(filter(None, [k.plz, k.ort]))),
            k.ust_id or "—",
            k.sachkonto or "—",
            k.status.value,
        )
    console.print(tabelle)


@kontakte_app.command("zeigen")
def kontakte_zeigen(
    schluessel: str = typer.Argument(help="Personenkonto oder Anfang der ID"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Stammdaten und offene Posten eines Kontakts."""
    from rich.markup import escape

    from accounti.anzeige import betrag_de, datum_de
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_posten, lade_ustid_pruefungen
    from accounti.kontakte.ustid import bewerte, normalisiere
    from accounti.opos.auswertung import offene_posten

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        k = _kontakt_oder_ende(s, schluessel)
        posten = [p for p in offene_posten(lade_posten(s)) if p.kontakt_id == k.id]
        pruefungen = (
            lade_ustid_pruefungen(s, normalisiere(k.ust_id)) if k.ust_id else []
        )

    def zeile(label: str, wert: object) -> None:
        text = "—" if wert in (None, "") else escape(str(wert))
        console.print(f"  {label:18} {text}")

    console.print(f"[bold]{escape(k.name)}[/bold] ({_konten(k)})")
    zeile("Status", k.status.value + (f" — {k.pruef_grund}" if k.pruef_grund else ""))
    zeile(
        "Anschrift",
        ", ".join(
            filter(None, [k.strasse, f"{k.plz or ''} {k.ort or ''}".strip(), k.land])
        ),
    )
    zeile("USt-IdNr.", k.ust_id)
    if pruefungen:
        letzte = pruefungen[-1]
        zeile(
            "USt-IdNr.-Prüfung",
            f"{datum_de(letzte.zeitpunkt.date())}: {bewerte(letzte).grund}",
        )
    zeile("Steuernummer", k.steuernummer)
    zeile("IBAN", k.iban)
    zeile("E-Mail", k.email)
    zeile("Sachkonto", k.sachkonto)
    zeile(
        "Zahlungsziel", f"{k.zahlungsziel_tage} Tage" if k.zahlungsziel_tage else None
    )
    if k.skonto_prozent is not None:
        zeile("Skonto", f"{k.skonto_prozent.normalize()} % in {k.skonto_tage} Tagen")
    summe = sum((p.restbetrag for p in posten), start=Decimal(0))
    zeile("Offene Posten", f"{len(posten)} · {betrag_de(summe)} €")


@kontakte_app.command("bestaetigen")
def kontakte_bestaetigen(
    schluessel: str = typer.Argument(help="Personenkonto oder Anfang der ID"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Automatisch angelegten Kontakt nach Prüfung freigeben."""
    from rich.markup import escape

    from accounti.db import init_db, session_factory
    from accounti.db.repository import aktualisiere_kontakt
    from accounti.models import KontaktStatus

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        k = _kontakt_oder_ende(s, schluessel)
        aktualisiere_kontakt(
            s,
            k.model_copy(
                update={"status": KontaktStatus.GEPRUEFT, "pruef_grund": None}
            ),
        )
        s.commit()
    console.print(f"[green]Bestätigt:[/green] {escape(k.name)} ({_konten(k)})")


@kontakte_app.command("bearbeiten")
def kontakte_bearbeiten(
    schluessel: str = typer.Argument(help="Personenkonto oder Anfang der ID"),
    name: str | None = typer.Option(None),
    sachkonto: str | None = typer.Option(None, help="Vorschlag für Buchungen"),
    zahlungsziel: int | None = typer.Option(None, help="Zahlungsziel in Tagen"),
    skonto_prozent: float | None = typer.Option(None),
    skonto_tage: int | None = typer.Option(None),
    ust_id: str | None = typer.Option(None),
    steuernummer: str | None = typer.Option(None),
    iban: str | None = typer.Option(None),
    email: str | None = typer.Option(None),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Stammdaten eines Kontakts ändern."""
    from rich.markup import escape

    from accounti.db import init_db, session_factory
    from accounti.db.repository import aktualisiere_kontakt

    aenderungen: dict[str, object] = {
        feld: wert
        for feld, wert in (
            ("name", name),
            ("sachkonto", sachkonto),
            ("zahlungsziel_tage", zahlungsziel),
            ("skonto_tage", skonto_tage),
            ("ust_id", ust_id),
            ("steuernummer", steuernummer),
            ("iban", iban.replace(" ", "").upper() if iban else None),
            ("email", email),
        )
        if wert is not None
    }
    if skonto_prozent is not None:
        aenderungen["skonto_prozent"] = Decimal(str(skonto_prozent))
    if not aenderungen:
        console.print("[yellow]Nichts zu ändern.[/yellow]")
        return
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        k = _kontakt_oder_ende(s, schluessel)
        aktualisiere_kontakt(s, k.model_copy(update=aenderungen))
        s.commit()
    console.print(
        f"[green]Geändert:[/green] {escape(k.name)} — " + ", ".join(sorted(aenderungen))
    )


# ---------------------------------------------------------------------------
# Offene Posten
# ---------------------------------------------------------------------------
_VERGLEICH = {
    "A": "stimmt",
    "B": "stimmt nicht",
    "C": "nicht angefragt",
    "D": "nicht mitgeteilt",
}


def _ustid_ausgabe(p: "UstIdPruefung") -> "Bewertung":
    """Ergebnis einer Bestätigungsabfrage — grün bestätigt, gelb gültig, rot sonst."""
    from rich.markup import escape

    from accounti.kontakte.ustid import bewerte

    b = bewerte(p)
    farbe = "green" if b.bestaetigt else "yellow" if b.gueltig else "red"
    wer = f" ({escape(p.firmenname)}, {p.art.value})" if p.firmenname else ""
    console.print(f"[{farbe}]USt-IdNr. {p.ust_id}[/{farbe}]{wer} — {escape(b.grund)}")
    vergleich = [
        f"{name} {_VERGLEICH.get(wert, wert)}"
        for name, wert in (
            ("Name", p.erg_firmenname),
            ("Straße", p.erg_strasse),
            ("PLZ", p.erg_plz),
            ("Ort", p.erg_ort),
        )
        if wert
    ]
    if vergleich:
        console.print("  " + " · ".join(vergleich))
    for hinweis in b.hinweise:
        console.print(f"  [yellow]Hinweis: {escape(hinweis)}[/yellow]")
    console.print(
        f"  [dim]BZSt {p.bzst_zeitpunkt or '—'} · ID {p.bzst_id or '—'} · "
        f"Protokoll Nr. {p.nr}[/dim]"
    )
    return b


@kontakte_app.command("pruefe-ustid")
def kontakte_pruefe_ustid(
    schluessel: str = typer.Argument(help="Personenkonto oder Anfang der ID"),
    einfach: bool = typer.Option(
        False, "--einfach", help="Nur Gültigkeit, ohne Name und Anschrift"
    ),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    config: str = KONFIG_OPTION,
) -> None:
    """USt-IdNr. beim BZSt bestätigen lassen (qualifiziert) und protokollieren."""
    from rich.markup import escape

    from accounti.db import init_db, session_factory
    from accounti.konfiguration import (
        KonfigurationError,
        lade_eigene_firma,
        lade_ustid_pruefung,
    )
    from accounti.kontakte.ustid import (
        EvatrClient,
        UstIdError,
        baue_anfrage,
        pruefe_ustid,
    )

    try:
        einstellungen = lade_ustid_pruefung(config)
        eigene = lade_eigene_firma(config)
        weg = EvatrClient(einstellungen.url, einstellungen.timeout_sekunden)
    except (KonfigurationError, UstIdError) as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        k = _kontakt_oder_ende(s, schluessel)
        try:
            anfrage = baue_anfrage(
                eigene.ust_id if eigene else None,
                k.ust_id,
                k.name,
                k.strasse,
                k.plz,
                k.ort,
                einfach=einfach,
            )
        except UstIdError as fehler:
            console.print(f"[red]{escape(k.name)}: {escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
        p = pruefe_ustid(s, weg, anfrage, kontakt_id=k.id)
        s.commit()  # der Nachweis bleibt, was auch immer danach geschieht
    if not _ustid_ausgabe(p).gueltig:
        raise typer.Exit(1)


@kontakte_app.command("ustid-protokoll")
def kontakte_ustid_protokoll(
    ust_id: str | None = typer.Argument(None, help="Nur diese USt-IdNr."),
    csv_datei: str | None = typer.Option(
        None, "--csv", help="Protokoll als CSV (Semikolon) exportieren"
    ),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Protokoll der USt-IdNr.-Bestätigungen — mit Prüfung auf Unverändertheit."""
    import csv
    from pathlib import Path

    from rich.markup import escape
    from rich.table import Table

    from accounti.anzeige import datum_de
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_ustid_pruefungen
    from accounti.kontakte.ustid import bewerte, normalisiere, pruefe_protokoll
    from accounti.models import UstIdPruefung

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        alle = lade_ustid_pruefungen(s)
    befunde = pruefe_protokoll(alle)
    eintraege = (
        [p for p in alle if p.ust_id == normalisiere(ust_id)] if ust_id else alle
    )

    if eintraege:
        tabelle = Table(title="USt-IdNr.-Protokoll")
        for spalte in ("Nr", "Zeitpunkt", "USt-IdNr.", "Art", "Status", "Ergebnis"):
            tabelle.add_column(spalte, overflow="fold")
        for p in eintraege:
            tabelle.add_row(
                str(p.nr),
                f"{datum_de(p.zeitpunkt.date())} {p.zeitpunkt:%H:%M:%S}",
                p.ust_id,
                p.art.value,
                p.status or (f"HTTP {p.http_status}" if p.http_status else "—"),
                escape(bewerte(p).grund),
            )
        console.print(tabelle)
    else:
        console.print("[dim]Keine Einträge.[/dim]")
    if csv_datei:
        with Path(csv_datei).open("w", encoding="utf-8", newline="") as datei:
            schreiber = csv.DictWriter(
                datei, fieldnames=list(UstIdPruefung.model_fields), delimiter=";"
            )
            schreiber.writeheader()
            for p in eintraege:
                schreiber.writerow(p.model_dump(mode="json"))
        console.print(f"[dim]{len(eintraege)} Einträge → {escape(csv_datei)}[/dim]")

    if befunde:
        console.print("[red]Protokoll beschädigt:[/red]")
        for befund in befunde:
            console.print(f"  [red]{escape(befund)}[/red]")
        raise typer.Exit(1)
    console.print(
        "[green]Protokoll vollständig und unverändert[/green] — "
        f"{len(alle)} {'Eintrag' if len(alle) == 1 else 'Einträge'}, Hash-Kette geprüft"
    )


opos_app = typer.Typer(help="Offene Posten: verbuchen, Liste, Fälligkeitsstaffel.")
app.add_typer(opos_app, name="opos")

_RICHTUNGEN = {
    "eingang": "verbindlichkeit",
    "verbindlichkeit": "verbindlichkeit",
    "verbindlichkeiten": "verbindlichkeit",
    "ausgang": "forderung",
    "forderung": "forderung",
    "forderungen": "forderung",
}


def _richtung_option(wert: str | None) -> "PostenRichtung | None":
    from accounti.models import PostenRichtung

    if wert is None:
        return None
    if wert.lower() not in _RICHTUNGEN:
        console.print(
            "[red]--richtung: eingang (Verbindlichkeiten) "
            "oder ausgang (Forderungen)[/red]"
        )
        raise typer.Exit(1)
    return PostenRichtung(_RICHTUNGEN[wert.lower()])


@opos_app.command("verbuchen")
def opos_verbuchen(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    config: str = KONFIG_OPTION,
) -> None:
    """Erfasste Rechnungen auf Personenkonten buchen und offene Posten anlegen."""
    from rich.markup import escape

    from accounti.anzeige import betrag_de, datum_de
    from accounti.belege.archiv import BelegArchiv
    from accounti.db import init_db, session_factory
    from accounti.klassifikation.engine import STANDARD_REGELN, RegelwerkEngine
    from accounti.klassifikation.regeln_loader import lade_regeln
    from accounti.konfiguration import (
        KonfigurationError,
        lade_buchhaltung,
        lade_eigene_firma,
        lade_ustid_pruefung,
    )
    from accounti.models import BuchungStatus, PostenRichtung
    from accounti.opos.verbuchung import verbuche_belege

    try:
        einstellungen = lade_buchhaltung(config)
        ustid_einstellungen = lade_ustid_pruefung(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    regelwerk = RegelwerkEngine(lade_regeln("config/regeln.yaml") + STANDARD_REGELN)
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        lauf = verbuche_belege(
            s,
            einstellungen,
            BelegArchiv(archiv),
            regelwerk,
            eigene_firma=lade_eigene_firma(config),
            ustid_max_alter_tage=ustid_einstellungen.max_alter_tage,
        )
        s.commit()
    for v in lauf.verbucht:
        k = v.treffer.kontakt
        rolle = (
            f"Kreditor {k.kreditor_konto}"
            if v.posten.richtung is PostenRichtung.VERBINDLICHKEIT
            else f"Debitor {k.debitor_konto}"
        )
        herkunft = "neu" if v.kontakt_neu else f"erkannt über {v.merkmal}"
        if v.kontakt_neu and k.status.value == "pruefung":
            herkunft += ", zur Prüfung"
        pruefen = sum(b.status is BuchungStatus.ZUR_PRUEFUNG for b in v.buchungen)
        console.print(
            f"[green]{escape(v.beleg.belegnummer or v.beleg.dateiname)}[/green] → "
            f"{rolle} {escape(k.name)} ({herkunft}) · "
            f"{betrag_de(v.posten.betrag)} € fällig {datum_de(v.posten.faellig_am)} · "
            f"{len(v.buchungen)} Buchungen"
            + (f", [yellow]{pruefen} zur Prüfung[/yellow]" if pruefen else "")
        )
        for hinweis in v.hinweise:
            console.print(f"  [yellow]{escape(hinweis)}[/yellow]")
    for beleg, grund in lauf.fehler:
        console.print(
            "[red]Nicht verbucht:[/red] "
            f"{escape(beleg.belegnummer or beleg.dateiname)} — {escape(grund)}"
        )
    if not lauf.verbucht and not lauf.fehler:
        console.print("[dim]Nichts zu verbuchen.[/dim]")
    elif lauf.verbucht:
        console.print(
            "[dim]Nächster Schritt: Bankumsätze importieren und 'accounti opos "
            "zuordnen' vor 'accounti classify' ausführen.[/dim]"
        )


@opos_app.command("liste")
def opos_liste(
    richtung: str | None = typer.Option(None, help="eingang oder ausgang"),
    faellig: bool = typer.Option(False, "--faellig", help="nur fällige Posten"),
    stichtag: str | None = typer.Option(None, help="JJJJ-MM-TT (heute)"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Offene Posten anzeigen."""
    from datetime import date

    from rich.markup import escape
    from rich.table import Table

    from accounti.anzeige import betrag_de, datum_de
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_kontakte, lade_posten
    from accounti.opos.auswertung import offene_posten, ueberfaellig_tage

    filter_richtung = _richtung_option(richtung)
    tag = _datum_option(stichtag, "--stichtag") or date.today()
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        posten = offene_posten(
            lade_posten(s),
            faellig_bis=tag if faellig else None,
            richtung=filter_richtung,
        )
        kontakte = {k.id: k for k in lade_kontakte(s)}
    if not posten:
        console.print("[dim]Keine offenen Posten.[/dim]")
        return
    tabelle = Table(title=f"Offene Posten zum {datum_de(tag)}")
    tabelle.add_column("Fällig", no_wrap=True)
    tabelle.add_column("Tage", justify="right", no_wrap=True)
    tabelle.add_column("Konto", no_wrap=True)
    tabelle.add_column("Kontakt", overflow="fold")
    tabelle.add_column("Beleg", no_wrap=True)
    tabelle.add_column("Rest", justify="right", no_wrap=True)
    tabelle.add_column("Skonto bis", no_wrap=True)
    for p in posten:
        k = kontakte.get(p.kontakt_id)
        tage = ueberfaellig_tage(p, tag)
        konto = (
            (
                k.kreditor_konto
                if p.richtung.value == "verbindlichkeit"
                else k.debitor_konto
            )
            if k
            else None
        )
        tabelle.add_row(
            f"{p.faellig_am:%d.%m.%y}",
            f"[red]{tage}[/red]" if tage > 0 else str(tage),
            konto or "—",
            escape(k.name if k else "?"),
            escape(p.belegnummer or "—"),
            betrag_de(p.restbetrag),
            f"{p.skonto_bis:%d.%m.%y}" if p.skonto_bis else "—",
        )
    console.print(tabelle)
    summe = sum((p.restbetrag for p in posten), start=Decimal(0))
    console.print(f"  {len(posten)} Posten · Rest {betrag_de(summe)} €")


@opos_app.command("staffel")
def opos_staffel(
    stichtag: str | None = typer.Option(None, help="JJJJ-MM-TT (heute)"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Fälligkeitsstaffel für Verbindlichkeiten und Forderungen."""
    from datetime import date

    from rich.table import Table

    from accounti.anzeige import betrag_de, datum_de
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_posten
    from accounti.models import PostenRichtung
    from accounti.opos.auswertung import STAFFELN, faelligkeitsstaffel

    tag = _datum_option(stichtag, "--stichtag") or date.today()
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        posten = lade_posten(s)
    verbindlichkeiten = faelligkeitsstaffel(
        [p for p in posten if p.richtung is PostenRichtung.VERBINDLICHKEIT], tag
    )
    forderungen = faelligkeitsstaffel(
        [p for p in posten if p.richtung is PostenRichtung.FORDERUNG], tag
    )
    tabelle = Table(title=f"Fälligkeitsstaffel zum {datum_de(tag)}")
    tabelle.add_column("Überfällig")
    tabelle.add_column("Verbindlichkeiten", justify="right")
    tabelle.add_column("Forderungen", justify="right")
    for stufe in STAFFELN:
        tabelle.add_row(
            stufe, betrag_de(verbindlichkeiten[stufe]), betrag_de(forderungen[stufe])
        )
    tabelle.add_row(
        "[bold]Summe[/bold]",
        f"[bold]{betrag_de(sum(verbindlichkeiten.values(), start=Decimal(0)))}[/bold]",
        f"[bold]{betrag_de(sum(forderungen.values(), start=Decimal(0)))}[/bold]",
    )
    console.print(tabelle)


_STUFEN = {
    "referenz": "Referenz",
    "exakt": "exakt",
    "skonto": "Skonto",
    "teil": "Teilzahlung",
    "ueberzahlung": "Überzahlung",
    "sammel": "Sammelzahlung",
    "unscharf": "unscharf",
}


@opos_app.command("zuordnen")
def opos_zuordnen(
    period: str | None = typer.Option(None, "--period", help="nur Monat JJJJ-MM"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    config: str = KONFIG_OPTION,
) -> None:
    """Bankzahlungen offenen Posten zuordnen — Eindeutiges wird sofort ausgeglichen."""
    from rich.markup import escape

    from accounti.anzeige import betrag_de, datum_de
    from accounti.db import init_db, session_factory
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung
    from accounti.opos.zahlungslauf import zuordne_zahlungen

    try:
        einstellungen = lade_buchhaltung(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        lauf = zuordne_zahlungen(s, einstellungen, zeitraum=period)
        s.commit()

    def anteile_text(vorschlag: "Zuordnungsvorschlag") -> str:
        teile = []
        for a in vorschlag.anteile:
            text = f"{a.posten.belegnummer or '?'} {betrag_de(a.betrag)}"
            if a.skonto:
                text += f" (Skonto {betrag_de(a.skonto)})"
            teile.append(text)
        return ", ".join(teile)

    for tx, v in lauf.gebucht:
        console.print(
            f"[green]{datum_de(tx.datum)} {betrag_de(tx.betrag)} €[/green] → "
            f"{escape(anteile_text(v))} · {_STUFEN[v.stufe.value]}"
        )
    for tx, v in lauf.vorgeschlagen:
        console.print(
            f"[yellow]Vorschlag {str(tx.id)[:8]}[/yellow] {datum_de(tx.datum)} "
            f"{betrag_de(tx.betrag)} € → {escape(anteile_text(v))} · "
            f"{_STUFEN[v.stufe.value]} ({v.confidence:.2f})"
        )
    console.print(
        f"[green]{len(lauf.gebucht)} ausgeglichen[/green], "
        f"[yellow]{len(lauf.vorgeschlagen)} Vorschläge[/yellow], "
        f"{lauf.ohne_treffer} ohne passenden Posten (→ classify)."
    )
    if lauf.vorgeschlagen:
        console.print(
            "[dim]Prüfen: accounti opos vorschlaege · "
            "accounti opos bestaetigen <ID> · accounti opos ablehnen <ID>[/dim]"
        )


@opos_app.command("vorschlaege")
def opos_vorschlaege(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Offene Zuordnungsvorschläge anzeigen."""
    from collections import defaultdict
    from uuid import UUID

    from rich.markup import escape
    from rich.table import Table

    from accounti.anzeige import betrag_de, datum_de
    from accounti.db import init_db, session_factory
    from accounti.db.repository import (
        lade_einen_posten,
        lade_transaktion,
        lade_zuordnungen,
    )
    from accounti.models import ZuordnungStatus

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        zuordnungen = lade_zuordnungen(s, status={ZuordnungStatus.VORGESCHLAGEN})
        je_tx: dict[UUID, list[str]] = defaultdict(list)
        for z in zuordnungen:
            p = lade_einen_posten(s, z.posten_id)
            text = f"{p.belegnummer or '?'} {betrag_de(z.betrag)}"
            if z.skonto:
                text += f" (Skonto {betrag_de(z.skonto)})"
            je_tx[z.transaktion_id].append(text)
        transaktionen = {t: lade_transaktion(s, t) for t in je_tx}
    if not zuordnungen:
        console.print("[dim]Keine Vorschläge.[/dim]")
        return
    erste = {z.transaktion_id: z for z in reversed(zuordnungen)}
    tabelle = Table(title="Zuordnungsvorschläge")
    tabelle.add_column("ID", no_wrap=True)
    tabelle.add_column("Datum", no_wrap=True)
    tabelle.add_column("Betrag", justify="right", no_wrap=True)
    tabelle.add_column("Posten", overflow="fold")
    tabelle.add_column("Stufe", no_wrap=True)
    for tx_id, posten in je_tx.items():
        tx = transaktionen[tx_id]
        z = erste[tx_id]
        tabelle.add_row(
            str(tx_id)[:8],
            datum_de(tx.datum) if tx else "—",
            betrag_de(tx.betrag) if tx else "—",
            escape(", ".join(posten)),
            f"{z.stufe} {z.confidence:.2f}",
        )
    console.print(tabelle)
    for tx_id in je_tx:
        tx = transaktionen[tx_id]
        zweck = tx.verwendungszweck[:60] if tx else ""
        console.print(
            f"  {str(tx_id)[:8]}  {escape(erste[tx_id].begruendung)} "
            f"[dim]— {escape(zweck)}[/dim]"
        )


@opos_app.command("bestaetigen")
def opos_bestaetigen(
    transaktion: str = typer.Argument(help="ID des Vorschlags (Anfang genügt)"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    config: str = KONFIG_OPTION,
) -> None:
    """Zuordnungsvorschlag buchen."""
    from rich.markup import escape

    from accounti.db import init_db, session_factory
    from accounti.konfiguration import lade_buchhaltung
    from accounti.opos.zahlungslauf import ZahlungslaufError, bestaetige

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        try:
            buchungen = bestaetige(s, transaktion, lade_buchhaltung(config))
        except ZahlungslaufError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
        s.commit()
    console.print(
        f"[green]Vorschlag {escape(transaktion)} gebucht[/green] — "
        f"{len(buchungen)} Buchungen"
    )


@opos_app.command("ablehnen")
def opos_ablehnen(
    transaktion: str = typer.Argument(help="ID des Vorschlags (Anfang genügt)"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Zuordnungsvorschlag verwerfen — die Zahlung geht zurück in die Kontierung."""
    from rich.markup import escape

    from accounti.db import init_db, session_factory
    from accounti.opos.zahlungslauf import ZahlungslaufError, lehne_ab

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        try:
            lehne_ab(s, transaktion)
        except ZahlungslaufError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
        s.commit()
    console.print(
        f"Vorschlag {escape(transaktion)} abgelehnt — die Zahlung wird bei "
        "'accounti classify' wieder berücksichtigt."
    )


# ---------------------------------------------------------------------------
# Bank — Belegabgleich (Baustein 5)
# ---------------------------------------------------------------------------
bank_app = typer.Typer(help="Bankumsätze mit Belegen abgleichen.")
app.add_typer(bank_app, name="bank")


def _umsatz_text(tx: "Transaktion") -> str:
    from accounti.anzeige import betrag_de, datum_de

    wer = " · ".join(filter(None, [tx.gegenkonto_name, tx.verwendungszweck[:40]]))
    return f"{datum_de(tx.datum)} {betrag_de(tx.betrag)} € {wer}"


def _beleg_text(b: "Beleg") -> str:
    from accounti.anzeige import betrag_de, datum_de

    was = " ".join(filter(None, [b.lieferant_name, b.belegnummer])) or b.dateiname
    return f"{was} ({datum_de(b.belegdatum)}, {betrag_de(b.brutto)} €)"


@bank_app.command("abgleich")
def bank_abgleich(
    period: str | None = typer.Option(None, help="Nur Umsätze dieses Monats (JJJJ-MM)"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Umsätze mit Quittungen und sonstigen Belegen abgleichen — vor 'classify'."""
    from rich.markup import escape

    from accounti.bank.abgleichslauf import gleiche_belege_ab
    from accounti.db import init_db, session_factory

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        ergebnis = gleiche_belege_ab(s, zeitraum=period)
        s.commit()
    for k in ergebnis.automatisch:
        console.print(
            f"[green]✓[/green] {escape(_umsatz_text(k.transaktion))} ↔ "
            f"{escape(_beleg_text(k.beleg))} [dim]({k.stufe.value})[/dim]"
        )
    gesehen = set()
    for k in ergebnis.vorschlaege:
        if k.transaktion.id not in gesehen:
            gesehen.add(k.transaktion.id)
            console.print(f"[yellow]?[/yellow] {escape(_umsatz_text(k.transaktion))}")
        console.print(
            f"    ↔ {escape(_beleg_text(k.beleg))} [dim]{k.confidence:.0%} — "
            f"{escape(k.begruendung)}[/dim]"
        )
    for tx in ergebnis.ruecklastschriften:
        console.print(
            f"[yellow]Rücklastschrift, nicht abgeglichen:[/yellow] "
            f"{escape(_umsatz_text(tx))}"
        )
    anzahl = len(ergebnis.vorschlaege)
    console.print(
        f"[green]{len(ergebnis.automatisch)} abgeglichen[/green], "
        f"[yellow]{anzahl} {'Vorschlag' if anzahl == 1 else 'Vorschläge'}[/yellow], "
        f"{ergebnis.ohne_treffer} ohne passenden Beleg."
    )
    if ergebnis.vorschlaege:
        console.print("[dim]Vorschläge prüfen: accounti bank vorschlaege[/dim]")
    console.print(
        "[dim]Nächster Schritt: accounti classify (kontiert aus dem Beleg)[/dim]"
    )


@bank_app.command("vorschlaege")
def bank_vorschlaege(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Offene Abgleich-Vorschläge mit ID zum Bestätigen oder Ablehnen."""
    from rich.markup import escape
    from rich.table import Table

    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_abgleiche, lade_belege, lade_transaktionen
    from accounti.models import AbgleichStatus

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        vorschlaege = lade_abgleiche(s, status={AbgleichStatus.VORGESCHLAGEN})
        transaktionen = {t.id: t for t in lade_transaktionen(s)}
        belege = {b.id: b for b in lade_belege(s)}
    if not vorschlaege:
        console.print("[dim]Keine offenen Vorschläge.[/dim]")
        return
    tabelle = Table(title="Abgleich-Vorschläge")
    for spalte in ("ID", "Umsatz", "Beleg", "Sicherheit", "Begründung"):
        tabelle.add_column(spalte, overflow="fold")
    for a in vorschlaege:
        tabelle.add_row(
            str(a.id)[:8],
            escape(_umsatz_text(transaktionen[a.transaktion_id])),
            escape(_beleg_text(belege[a.beleg_id])),
            f"{a.confidence:.0%}",
            escape(a.begruendung),
        )
    console.print(tabelle)
    console.print(
        "[dim]accounti bank bestaetigen <ID> · accounti bank ablehnen <ID>[/dim]"
    )


def _abgleich_entscheiden(praefix: str, db: str, bestaetigen: bool) -> None:
    from rich.markup import escape

    from accounti.bank.abgleichslauf import (
        AbgleichError,
        bestaetige_abgleich,
        lehne_abgleich_ab,
    )
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_belege, lade_transaktion

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        try:
            a = (bestaetige_abgleich if bestaetigen else lehne_abgleich_ab)(s, praefix)
        except AbgleichError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
        s.commit()
        tx = lade_transaktion(s, a.transaktion_id)
        beleg = next(b for b in lade_belege(s) if b.id == a.beleg_id)
    paar = f"{_beleg_text(beleg)} ↔ {_umsatz_text(tx) if tx else a.transaktion_id}"
    if bestaetigen:
        console.print(f"[green]Bestätigt:[/green] {escape(paar)}")
        console.print(
            "[dim]Konkurrierende Vorschläge sind verworfen. "
            "Nächster Schritt: accounti classify[/dim]"
        )
    else:
        console.print(f"[yellow]Abgelehnt:[/yellow] {escape(paar)}")


@bank_app.command("bestaetigen")
def bank_bestaetigen(
    vorschlag: str = typer.Argument(help="ID des Vorschlags (Anfang genügt)"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Abgleich-Vorschlag bestätigen."""
    _abgleich_entscheiden(vorschlag, db, bestaetigen=True)


@bank_app.command("ablehnen")
def bank_ablehnen(
    vorschlag: str = typer.Argument(help="ID des Vorschlags (Anfang genügt)"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Abgleich-Vorschlag ablehnen — das Paar wird nicht wieder vorgeschlagen."""
    _abgleich_entscheiden(vorschlag, db, bestaetigen=False)


@bank_app.command("offen")
def bank_offen(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Umsätze ohne Beleg und Quittungen/sonstige Belege ohne Umsatz."""
    from rich.markup import escape

    from accounti.bank.abgleichslauf import offen_in_der_bank
    from accounti.db import init_db, session_factory
    from accounti.db.repository import gebuchte_transaktion_ids

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        bericht = offen_in_der_bank(s)
        kontiert = gebuchte_transaktion_ids(s)
    console.print(
        f"[bold]Umsätze ohne Beleg[/bold] ({len(bericht.umsaetze_ohne_beleg)})"
    )
    for tx in bericht.umsaetze_ohne_beleg:
        stand = "kontiert" if tx.id in kontiert else "offen"
        console.print(f"  {escape(_umsatz_text(tx))} [dim]{stand}[/dim]")
    console.print(
        f"[bold]Belege ohne Umsatz[/bold] ({len(bericht.belege_ohne_umsatz)})"
    )
    for b in bericht.belege_ohne_umsatz:
        console.print(f"  {escape(_beleg_text(b))}")
    console.print("[dim]Rechnungen ohne Zahlung stehen in 'accounti opos liste'.[/dim]")


@bank_app.command("schluessel")
def bank_schluessel() -> None:
    """Neuen Schlüssel für den Tresor der Bankzugänge erzeugen."""
    from accounti.bank.tresor import UMGEBUNG, neuer_schluessel

    console.print(
        "Diesen Schlüssel sicher aufbewahren (Passwortmanager) und in der Umgebung "
        "setzen — ohne ihn sind gespeicherte Bankzugänge nicht mehr lesbar:"
    )
    console.print(f"export {UMGEBUNG}={neuer_schluessel()}", soft_wrap=True)


@bank_app.command("verbinde")
def bank_verbinde(
    provider: str = typer.Option("datei", help="datei (später: fints, psd2)"),
    iban: str = typer.Option(..., help="IBAN des Kontos"),
    bezeichnung: str = typer.Option(..., help="z.B. 'Giro Sparkasse'"),
    sachkonto: str = typer.Option("1200", help="Finanzkonto im Kontenrahmen"),
    feld: Annotated[
        list[str] | None,
        typer.Option(help="Einstellung des Providers, z.B. ordner=./auszuege"),
    ] = None,
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Bankkonto einrichten; Zugangsdaten werden abgefragt und verschlüsselt."""
    import re

    from rich.markup import escape

    from accounti.bank.provider import BANK_PROVIDER
    from accounti.bank.tresor import TresorError, lade_schluessel, verschluessele
    from accounti.db import init_db, session_factory
    from accounti.db.repository import speichere_bankkonto
    from accounti.models import Bankkonto

    def ende(text: str) -> None:
        console.print(f"[red]{escape(text)}[/red]")
        raise typer.Exit(1)

    klasse = BANK_PROVIDER.get(provider)
    if klasse is None:
        ende(
            f"Unbekannter Provider '{provider}'. Verfügbar: {', '.join(BANK_PROVIDER)}"
        )
        return
    einstellungen: dict[str, str] = {}
    for eintrag in feld or []:
        name, _, wert = eintrag.partition("=")
        if name not in klasse.felder:
            erlaubt = ", ".join(klasse.felder) or "keine"
            ende(f"Einstellung '{name}' gibt es bei {provider} nicht ({erlaubt})")
        einstellungen[name] = wert
    konto = Bankkonto(
        iban=re.sub(r"\s", "", iban).upper(),
        bezeichnung=bezeichnung,
        sachkonto=sachkonto,
        provider=provider,
        einstellungen=einstellungen,
    )
    if klasse.geheime_felder:
        try:
            schluessel = lade_schluessel()
        except TresorError as fehler:
            ende(str(fehler))
            return
        geheim = {
            name: typer.prompt(name, hide_input=True) for name in klasse.geheime_felder
        }
        konto = konto.model_copy(
            update={"zugang": verschluessele(geheim, schluessel, str(konto.id))}
        )
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        try:
            speichere_bankkonto(s, konto)
        except ValueError as fehler:
            ende(str(fehler))
        s.commit()
    console.print(
        f"[green]Eingerichtet:[/green] {escape(konto.bezeichnung)} {konto.iban} "
        f"({provider}, Sachkonto {konto.sachkonto})"
        + (" — Zugang verschlüsselt gespeichert" if konto.zugang else "")
    )
    console.print("[dim]Nächster Schritt: accounti bank abrufen[/dim]")


@bank_app.command("konten")
def bank_konten(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Eingerichtete Bankkonten mit Abrufstand."""
    from rich.markup import escape
    from rich.table import Table

    from accounti.anzeige import datum_de
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_bankkonten

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        konten = lade_bankkonten(s)
    if not konten:
        console.print("[dim]Keine Bankkonten — accounti bank verbinde …[/dim]")
        return
    tabelle = Table(title="Bankkonten")
    for spalte in ("IBAN", "Bezeichnung", "Sachkonto", "Provider", "Stand", "Zustand"):
        tabelle.add_column(spalte, overflow="fold")
    for k in konten:
        zustand = k.zustand.value + (f": {k.meldung}" if k.meldung else "")
        tabelle.add_row(
            k.iban,
            escape(k.bezeichnung),
            k.sachkonto,
            k.provider,
            datum_de(k.abrufstand) if k.abrufstand else "—",
            escape(zustand),
        )
    console.print(tabelle)


def _abruf_ausgabe(abrufe: "list[KontoAbruf]") -> None:
    from rich.markup import escape

    for a in abrufe:
        farbe = {"bereit": "green", "freigabe_noetig": "yellow"}.get(
            a.zustand.value, "red"
        )
        text = f"{a.neu} neu, {a.doppelt} schon vorhanden"
        if a.meldung:
            text = f"{a.zustand.value}: {a.meldung}"
        console.print(
            f"[{farbe}]{escape(a.konto.bezeichnung)}[/{farbe}] {a.konto.iban} — "
            f"{escape(text)}"
        )
    if not abrufe:
        console.print("[dim]Keine Bankkonten — accounti bank verbinde …[/dim]")


@bank_app.command("abrufen")
def bank_abrufen(
    konto: str | None = typer.Option(None, help="Nur dieses Konto (IBAN)"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Neue Umsätze aller Konten holen — ohne Dubletten."""
    from rich.markup import escape

    from accounti.bank.lauf import rufe_ab
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_bankkonto

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        konten = None
        if konto is not None:
            try:
                konten = [lade_bankkonto(s, konto)]
            except ValueError as fehler:
                console.print(f"[red]{escape(str(fehler))}[/red]")
                raise typer.Exit(1) from fehler
        abrufe = rufe_ab(s, konten=konten)
        s.commit()
    _abruf_ausgabe(abrufe)


@bank_app.command("lauf")
def bank_lauf_befehl(
    llm: bool = typer.Option(False, "--llm/--no-llm", help="LLM-Stufe nutzen"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    config: str = KONFIG_OPTION,
) -> None:
    """Geplanter Lauf: abrufen → offene Posten zuordnen → abgleichen → kontieren."""
    from rich.markup import escape

    from accounti.bank.lauf import bank_lauf
    from accounti.befehle.kreditkarte import zeige_kartenabgleich
    from accounti.db import init_db, session_factory
    from accounti.klassifikation.engine import (
        STANDARD_REGELN,
        KlassifikationsEngine,
        RegelwerkEngine,
    )
    from accounti.klassifikation.llm import LLMEngine
    from accounti.klassifikation.regeln_loader import lade_regeln
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung

    try:
        einstellungen = lade_buchhaltung(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    engine = KlassifikationsEngine(
        regelwerk=RegelwerkEngine(lade_regeln("config/regeln.yaml") + STANDARD_REGELN),
        llm=LLMEngine() if llm else None,
    )
    db_engine, make_session = session_factory(db)
    init_db(db_engine)
    with make_session() as s:
        ergebnis = bank_lauf(s, engine, einstellungen)
        s.commit()
    _abruf_ausgabe(ergebnis.abrufe)
    zeige_kartenabgleich(ergebnis.kreditkarten, still=True)
    z, a, k = ergebnis.zuordnung, ergebnis.abgleich, ergebnis.kontierung
    console.print(
        f"Offene Posten: {len(z.gebucht)} ausgeglichen, {len(z.vorgeschlagen)} "
        f"vorgeschlagen · Belege: {len(a.automatisch)} abgeglichen, "
        f"{len(a.vorschlaege)} vorgeschlagen · Kontierung: {k.kontiert} kontiert "
        f"(davon {k.mit_beleg} mit Beleg), {k.offen} offen"
    )


# ---------------------------------------------------------------------------
# Klassifikation
# ---------------------------------------------------------------------------
@app.command()
def classify(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    llm: bool = typer.Option(True, "--llm/--no-llm", help="LLM-Stufe nutzen"),
    config: str = KONFIG_OPTION,
) -> None:
    """Transaktionen automatisch kontieren — mit Beleg aus dem Beleg."""
    from rich.markup import escape

    from accounti.buchung.kontierung import kontiere_umsaetze
    from accounti.db import init_db, session_factory
    from accounti.klassifikation.engine import (
        STANDARD_REGELN,
        KlassifikationsEngine,
        RegelwerkEngine,
    )
    from accounti.klassifikation.llm import LLMEngine
    from accounti.klassifikation.regeln_loader import lade_regeln
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung

    try:
        einstellungen = lade_buchhaltung(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    # Eigene Regeln (config/regeln.yaml) haben Vorrang, dann das Standard-Regelwerk.
    regeln = lade_regeln("config/regeln.yaml")
    if regeln:
        regelwerk = RegelwerkEngine(regeln + STANDARD_REGELN)
    else:
        regelwerk = RegelwerkEngine()
    engine = KlassifikationsEngine(
        regelwerk=regelwerk,
        llm=LLMEngine() if llm else None,
    )

    db_engine, make_session = session_factory(db)
    init_db(db_engine)
    with make_session() as s:
        # Nur Offenes: schon gebuchte und offenen Posten zugeordnete Zahlungen bleiben
        # unangetastet (sonst Doppelbuchung bzw. doppelter Aufwand).
        lauf = kontiere_umsaetze(s, engine, einstellungen)
        s.commit()
    console.print(
        f"[green]{lauf.kontiert}[/green] kontiert (davon {lauf.mit_beleg} mit Beleg), "
        f"[yellow]{lauf.offen}[/yellow] offen."
    )


# ---------------------------------------------------------------------------
# BWA
# ---------------------------------------------------------------------------
@app.command()
def bwa(
    period: str = typer.Option(..., help="Zeitraum im Format YYYY-MM"),
    vergleich: bool = typer.Option(False, help="Vorjahresvergleich anzeigen"),
) -> None:
    """Betriebswirtschaftliche Auswertung erstellen."""
    console.print(f"[bold]BWA:[/bold] Zeitraum {period}")
    if vergleich:
        console.print("[dim]Mit Vorjahresvergleich[/dim]")
    console.print("[yellow]⚠ Noch nicht implementiert — siehe Roadmap Phase 2[/yellow]")


# ---------------------------------------------------------------------------
# DATEV-Export
# ---------------------------------------------------------------------------
export_app = typer.Typer(help="Daten exportieren.")
app.add_typer(export_app, name="export")


@export_app.command("datev")
def export_datev(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    berater: str = typer.Option(..., help="DATEV Beraternummer"),
    mandant: str = typer.Option(..., help="DATEV Mandantennummer"),
    output: str = typer.Option("./export", help="Ausgabeverzeichnis"),
    alle: bool = typer.Option(
        False, "--alle", help="Auch ungeprüfte Buchungen exportieren"
    ),
) -> None:
    """DATEV-konformen Buchungsstapel exportieren (nur freigegebene Buchungen)."""
    from accounti.db import session_factory
    from accounti.db.repository import lade_buchungen
    from accounti.export.datev import DATEVConfig, DATEVExporter
    from accounti.models import BuchungStatus

    freigegeben = (
        None
        if alle
        else {
            BuchungStatus.AUTO_GEBUCHT,
            BuchungStatus.GEPRUEFT,
            BuchungStatus.KORRIGIERT,
            BuchungStatus.EXPORTIERT,
        }
    )
    from accounti.pruefung.storno import markiere_exportiert

    _, make_session = session_factory(db)
    with make_session() as s:
        buchungen = lade_buchungen(s, status=freigegeben)
        cfg = DATEVConfig(berater_nummer=berater, mandanten_nummer=mandant)
        datei = DATEVExporter(cfg).exportiere(buchungen, output)
        # Baustein 7: ab Export nur noch Storno; der Export steht im Journal
        markiert, gesperrt = markiere_exportiert(s, buchungen, datei, "datev")
        s.commit()
    console.print(f"[green]Export:[/green] {datei} ({len(buchungen)} Buchungen)")
    if markiert or gesperrt:
        console.print(
            f"[dim]{markiert} als exportiert vermerkt"
            + (
                f", {gesperrt} in abgeschlossenen Zeiträumen unverändert"
                if gesperrt
                else ""
            )
            + "[/dim]"
        )


def _regel_speichern(
    name: str,
    muster: str,
    soll: str,
    haben: str,
    steuer: int | None,
    feld: str = "beide",
) -> None:
    """Hängt eine Regel an config/regeln.yaml an."""
    from pathlib import Path

    import yaml

    pfad = Path("config/regeln.yaml")
    if pfad.exists():
        regeln = yaml.safe_load(pfad.read_text(encoding="utf-8")) or []
    else:
        regeln = []
    regeln.append(
        {
            "name": name,
            "muster": muster,
            "feld": feld,
            "soll_konto": soll,
            "haben_konto": haben,
            "steuer_schluessel": steuer,
            "buchungstext": name,
        }
    )
    pfad.write_text(
        yaml.safe_dump(regeln, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


@app.command()
def lerne(
    muster: str = typer.Option(..., help="Text-Muster (Regex)"),
    soll: str = typer.Option(..., help="Soll-Konto"),
    haben: str = typer.Option(..., help="Haben-Konto"),
    name: str = typer.Option(..., help="Regel-Name"),
    steuer: int | None = typer.Option(None, help="Steuerschlüssel"),
) -> None:
    """Korrektur als neue Regel speichern (Lernschleife)."""
    _regel_speichern(name, muster, soll, haben, steuer)
    console.print(f"[green]Regel '{name}' gespeichert.[/green]")


# ---------------------------------------------------------------------------
# Supervisor-Loop: prüfen, bestätigen, korrigieren
# ---------------------------------------------------------------------------
@app.command()
def review(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
) -> None:
    """Buchungen zur Prüfung anzeigen (Supervisor-Übersicht)."""
    from rich.table import Table

    from accounti.db import session_factory
    from accounti.db.repository import lade_buchungen, lade_pruefliste
    from accounti.models import BuchungStatus

    _, make_session = session_factory(db)
    with make_session() as s:
        alle = lade_buchungen(s)
        pruefliste = lade_pruefliste(s)

    zaehler: dict[BuchungStatus, int] = {}
    for b in alle:
        zaehler[b.status] = zaehler.get(b.status, 0) + 1
    console.print("[bold]Status-Übersicht:[/bold]")
    for status, anzahl in zaehler.items():
        console.print(f"  {status.value:12} {anzahl}")
    storniert = sum(1 for b in alle if b.storniert_durch is not None)
    if storniert:
        console.print(
            f"  {'storniert':12} {storniert} (mit Stornobuchung, beide sichtbar: "
            "accounti buchung zeige <ID>)"
        )

    if not pruefliste:
        console.print("[green]Nichts zu prüfen — alles freigegeben.[/green]")
        return

    tabelle = Table(title="Zur Prüfung")
    tabelle.add_column("ID")
    tabelle.add_column("Verwendungszweck")
    tabelle.add_column("Soll")
    tabelle.add_column("Haben")
    tabelle.add_column("St")
    tabelle.add_column("Conf", justify="right")
    for buchung, tx in pruefliste:
        tabelle.add_row(
            str(buchung.id)[:8],
            (tx.verwendungszweck[:35] if tx else buchung.buchungstext),
            buchung.soll_konto,
            buchung.haben_konto,
            str(buchung.steuer_schluessel or "—"),
            f"{buchung.confidence:.2f}",
        )
    console.print(tabelle)
    console.print(
        "[dim]Freigeben: accounti bestaetige <ID> · "
        "Korrigieren: accounti korrigiere <ID> --soll .. --haben .. "
        "(freigegebene Buchungen: Storno mit Neubuchung)[/dim]"
    )


@app.command()
def bestaetige(
    buchung_id: str = typer.Argument(help="(Anfang der) Buchungs-ID"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    von: str | None = typer.Option(
        None, help="Wer gibt frei (sonst ACCOUNTI_BENUTZER bzw. Anmeldename)"
    ),
) -> None:
    """Eine Buchung freigeben (geprüft) — die Freigabe steht im Journal."""
    from rich.markup import escape

    from accounti.db import session_factory
    from accounti.db.tabellen import UnveraenderbarError
    from accounti.db.tabellen_abschluss import JahrGesperrtError
    from accounti.pruefung.storno import StornoError, freigeben

    _, make_session = session_factory(db)
    with make_session() as s:
        try:
            b, geaendert = freigeben(s, buchung_id, von)
            s.commit()
        except (StornoError, JahrGesperrtError, UnveraenderbarError) as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
    if geaendert:
        console.print(f"[green]Freigegeben:[/green] {str(b.id)[:8]} → geprüft")
    else:
        console.print(
            f"[yellow]Schon freigegeben:[/yellow] {str(b.id)[:8]} ({b.status.value})"
        )


def _lerne_sachkonto(
    session: "Session", buchung: "Buchungssatz", soll: str, haben: str
) -> str | None:
    """Lernschleife für Belegbuchungen: das Sachkonto wird zum Vorschlag am Kontakt."""
    from accounti.db.repository import (
        aktualisiere_kontakt,
        lade_kontakt,
        lade_posten_fuer_beleg,
    )

    if buchung.beleg_id is None:
        return None
    posten = lade_posten_fuer_beleg(session, buchung.beleg_id)
    if posten is None:
        return None
    kontakt = lade_kontakt(session, str(posten.kontakt_id))
    if kontakt.kreditor_konto == haben:
        sachkonto = soll  # Eingang: Aufwand an Kreditor
    elif kontakt.debitor_konto == soll:
        sachkonto = haben  # Ausgang: Debitor an Erlös
    else:
        return None
    aktualisiere_kontakt(session, kontakt.model_copy(update={"sachkonto": sachkonto}))
    return f"Sachkonto {sachkonto} als Vorschlag für {kontakt.name}"


@app.command()
def korrigiere(
    buchung_id: str = typer.Argument(help="(Anfang der) Buchungs-ID"),
    soll: str = typer.Option(..., help="Korrigiertes Soll-Konto"),
    haben: str = typer.Option(..., help="Korrigiertes Haben-Konto"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    steuer: int | None = typer.Option(
        None, help="Neuer Steuerschlüssel (ohne Angabe bleibt er)"
    ),
    ohne_steuer: bool = typer.Option(
        False, "--ohne-steuer", help="Steuerschlüssel entfernen"
    ),
    von: str | None = typer.Option(
        None, help="Wer korrigiert (sonst ACCOUNTI_BENUTZER bzw. Anmeldename)"
    ),
    grund: str | None = typer.Option(None, help="Begründung (steht im Journal)"),
    datum: str | None = typer.Option(
        None,
        help="Datum für Storno und Neubuchung, wenn der Zeitraum abgeschlossen ist",
    ),
    lernen: bool = typer.Option(False, "--lernen", help="Korrektur als Regel merken"),
    config: str = KONFIG_OPTION,
) -> None:
    """Eine Buchung korrigieren — nach der Freigabe als Storno mit Neubuchung."""
    from rich.markup import escape

    from accounti.abschluss.kontenrahmen import KontenrahmenError, lade_kontenrahmen
    from accounti.db import session_factory
    from accounti.db.repository import lade_transaktion
    from accounti.db.tabellen import UnveraenderbarError
    from accounti.db.tabellen_abschluss import JahrGesperrtError
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung
    from accounti.pruefung.storno import StornoError
    from accounti.pruefung.storno import korrigiere as korrigiere_buchung

    try:
        kontenrahmen = lade_kontenrahmen(lade_buchhaltung(config).kontenrahmen)
    except (KonfigurationError, KontenrahmenError) as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    tag = _datum_option(datum, "--datum")
    _, make_session = session_factory(db)
    gelernt = None
    gegenkonto = zweck = None
    with make_session() as s:
        try:
            k = korrigiere_buchung(
                s,
                buchung_id,
                soll,
                haben,
                steuer=steuer,
                ohne_steuer=ohne_steuer,
                von=von,
                grund=grund,
                datum=tag,
                kontenrahmen=kontenrahmen,
            )
            if lernen and k.original.transaktion_id is None:
                gelernt = _lerne_sachkonto(s, k.original, soll, haben)
            elif lernen and k.original.transaktion_id is not None:
                tx = lade_transaktion(s, k.original.transaktion_id)
                if tx is not None:
                    gegenkonto, zweck = tx.gegenkonto_name, tx.verwendungszweck
            s.commit()
        except (StornoError, JahrGesperrtError, UnveraenderbarError) as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            raise typer.Exit(1) from fehler
    kurz = str(k.original.id)[:8]
    if k.storno is None:
        console.print(
            f"[green]Korrigiert:[/green] {kurz} → Soll {soll} / Haben {haben}"
        )
    else:
        assert k.neu is not None
        console.print(
            f"[green]Storniert:[/green] {kurz} durch Storno {str(k.storno.id)[:8]}; "
            f"Neubuchung {str(k.neu.id)[:8]} → Soll {soll} / Haben {haben}"
        )
        console.print(
            "[dim]Die Buchung war freigegeben — Original, Storno und Neubuchung "
            f"bleiben sichtbar (accounti buchung zeige {kurz}).[/dim]"
        )
    if gelernt:
        console.print(f"[green]Gelernt:[/green] {gelernt}")
    if lernen and (gegenkonto or zweck):
        import re

        basis = (gegenkonto or zweck or "").strip()
        muster = re.escape(basis.split()[0]) if basis else ""
        if muster:
            schluessel = k.neu.steuer_schluessel if k.neu else steuer
            _regel_speichern(
                f"gelernt_{muster}".lower(), muster, soll, haben, schluessel
            )
            console.print(f"[green]Regel gelernt:[/green] Muster '{muster}'")


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host-Adresse"),
    port: int = typer.Option(8400, help="Port"),
) -> None:
    """Web-UI für Supervision starten."""
    console.print(f"[bold]accounti server[/bold] → http://{host}:{port}")
    console.print("[yellow]⚠ Noch nicht implementiert — siehe Roadmap Phase 4[/yellow]")


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------
db_app = typer.Typer(help="Datenbank verwalten.")
app.add_typer(db_app, name="db")


@db_app.command("init")
def db_init(db: str = typer.Option("sqlite:///accounti.db", help="DB-URL")) -> None:
    """Datenbank initialisieren."""
    from accounti.db import init_db, session_factory

    engine, _ = session_factory(db)
    init_db(engine)
    console.print(f"[green]Datenbank initialisiert:[/green] {db}")


# ---------------------------------------------------------------------------
# Befehlsgruppen der Bausteine (accounti.befehle.*) — automatisch eingehängt
# ---------------------------------------------------------------------------
def haenge_befehle_ein(
    ziel: typer.Typer, module: "list[ModuleType] | None" = None
) -> None:
    from accounti.befehle import befehlsmodule

    for modul in befehlsmodule() if module is None else module:
        ziel.add_typer(modul.befehl, name=modul.NAME)


haenge_befehle_ein(app)


if __name__ == "__main__":
    app()
